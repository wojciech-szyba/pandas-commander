from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


class DataFormat(NamedTuple):
    """One openable data-file format."""

    snippet: str          # pandas code loading the file into `df`; "{path}" is substituted
    binary: bool = False  # True: shown as a read-only DataFrame preview, not editable text
    requires: str | None = None  # extra pip package needed on top of pandas, if any


_AVRO_SNIPPET = (
    "# Avro is not built into pandas — requires:  pip install fastavro\n"
    "import fastavro\n"
    "\n"
    'with open("{path}", "rb") as f:\n'
    "    df = pd.DataFrame.from_records(list(fastavro.reader(f)))"
)

# Registry of data formats, keyed by lowercase suffix.
FORMATS: dict[str, DataFormat] = {
    # text formats — editable in the text area
    ".csv": DataFormat('df = pd.read_csv("{path}")'),
    ".tsv": DataFormat('df = pd.read_csv("{path}", sep="\\t")'),
    ".json": DataFormat('df = pd.read_json("{path}")'),
    ".jsonl": DataFormat('df = pd.read_json("{path}", lines=True)'),
    ".ndjson": DataFormat('df = pd.read_json("{path}", lines=True)'),
    ".xml": DataFormat('df = pd.read_xml("{path}")', requires="lxml"),
    ".html": DataFormat('df = pd.read_html("{path}")[0]', requires="lxml"),
    # binary formats — read-only DataFrame preview
    ".parquet": DataFormat('df = pd.read_parquet("{path}")', binary=True, requires="pyarrow"),
    ".orc": DataFormat('df = pd.read_orc("{path}")', binary=True, requires="pyarrow"),
    ".feather": DataFormat('df = pd.read_feather("{path}")', binary=True, requires="pyarrow"),
    ".avro": DataFormat(_AVRO_SNIPPET, binary=True, requires="fastavro"),
    ".xlsx": DataFormat('df = pd.read_excel("{path}")', binary=True, requires="openpyxl"),
    ".xlsm": DataFormat('df = pd.read_excel("{path}")', binary=True, requires="openpyxl"),
    ".xls": DataFormat('df = pd.read_excel("{path}")', binary=True, requires="xlrd"),
    ".ods": DataFormat('df = pd.read_excel("{path}")', binary=True, requires="odfpy"),
    ".pkl": DataFormat('df = pd.read_pickle("{path}")', binary=True),
    ".pickle": DataFormat('df = pd.read_pickle("{path}")', binary=True),
    ".h5": DataFormat('df = pd.read_hdf("{path}")', binary=True, requires="tables"),
    ".hdf5": DataFormat('df = pd.read_hdf("{path}")', binary=True, requires="tables"),
    ".dta": DataFormat('df = pd.read_stata("{path}")', binary=True),
    ".sas7bdat": DataFormat('df = pd.read_sas("{path}")', binary=True),
    ".xpt": DataFormat('df = pd.read_sas("{path}")', binary=True),
    ".sav": DataFormat('df = pd.read_spss("{path}")', binary=True, requires="pyreadstat"),
}

# Suffixes that cannot be shown or edited as plain text.
BINARY_SUFFIXES = {suffix for suffix, fmt in FORMATS.items() if fmt.binary}

# --------------------------------------------------------------- compression
# Compression wrappers, keyed by outer suffix -> pandas `compression=` name.
COMPRESSIONS: dict[str, str] = {
    ".gz": "gzip",
    ".gzip": "gzip",
    ".bz2": "bz2",
    ".zip": "zip",
    ".xz": "xz",
    ".zst": "zstd",
    ".snappy": "snappy",  # not pandas-native for text formats; needs python-snappy
}

# Extra pip package needed to decompress, beyond the stdlib.
_COMPRESSION_REQUIRES = {"zstd": "zstandard", "snappy": "python-snappy"}

# Inner formats whose pandas reader accepts a `compression=` argument directly.
_COMPRESSIBLE = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".xml", ".pkl", ".pickle"}

# Import line + open expression used in generated snippets when the inner
# reader cannot take `compression=` and needs a decompressed stream instead.
_OPEN_SNIPPETS = {
    "gzip": ("import gzip", 'gzip.open("{path}", "rb")'),
    "bz2": ("import bz2", 'bz2.open("{path}", "rb")'),
    "xz": ("import lzma", 'lzma.open("{path}", "rb")'),
    "zstd": (
        "import zstandard  # requires:  pip install zstandard",
        'zstandard.open("{path}", "rb")',
    ),
}


def split_compression(path: Path) -> tuple[str | None, str]:
    """(pandas compression name or None, inner format suffix).

    'data.csv.gz' -> ("gzip", ".csv");  'data.gz' -> ("gzip", "") — the caller
    may then sniff the archive content with detect_inner_suffix().
    """
    comp = COMPRESSIONS.get(path.suffix.lower())
    if comp is None:
        return None, path.suffix.lower()
    return comp, Path(path.stem).suffix.lower()


def _sniff_suffix(sample: bytes) -> str:
    """Guess the data format of decompressed `sample` bytes by magic/shape."""
    if sample.startswith(b"PAR1"):
        return ".parquet"
    if sample.startswith(b"ORC"):
        return ".orc"
    stripped = sample.lstrip()
    if stripped.startswith((b"{", b"[")):
        # Several complete lines each starting with '{' -> JSON Lines.
        lines = [ln for ln in sample.splitlines() if ln.strip()]
        if len(lines) > 1 and all(ln.lstrip().startswith(b"{") for ln in lines[:-1]):
            return ".jsonl"
        return ".json"
    if stripped.startswith(b"<"):
        return ".xml"
    return ".csv"


def _zip_first_member(path: Path) -> str | None:
    import zipfile  # noqa: PLC0415

    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.endswith("/"):
                return name
    return None


def _snappy_bytes(raw: bytes) -> bytes:
    """Decompress raw/framed/hadoop-framed snappy data."""
    import io  # noqa: PLC0415

    import snappy  # noqa: PLC0415  # requires: pip install python-snappy

    try:
        return snappy.uncompress(raw)
    except Exception:  # noqa: BLE001 - not raw-block snappy, try the framings
        pass
    for name in ("stream_decompress", "hadoop_stream_decompress"):
        func = getattr(snappy, name, None)
        if func is None:
            continue
        try:
            dst = io.BytesIO()
            func(io.BytesIO(raw), dst)
            return dst.getvalue()
        except Exception:  # noqa: BLE001
            continue
    raise ValueError("not a recognised snappy stream (raw, framed, or hadoop)")


def _decompress_open(path: Path, comp: str):
    """Open `path` as a decompressed binary stream."""
    import io  # noqa: PLC0415

    if comp == "gzip":
        import gzip  # noqa: PLC0415

        return gzip.open(path, "rb")
    if comp == "bz2":
        import bz2  # noqa: PLC0415

        return bz2.open(path, "rb")
    if comp == "xz":
        import lzma  # noqa: PLC0415

        return lzma.open(path, "rb")
    if comp == "zstd":
        import zstandard  # noqa: PLC0415  # requires: pip install zstandard

        return zstandard.open(path, "rb")
    if comp == "zip":
        import zipfile  # noqa: PLC0415

        with zipfile.ZipFile(path) as zf:
            member = _zip_first_member(path)
            if member is None:
                raise ValueError("empty zip archive")
            return io.BytesIO(zf.read(member))
    if comp == "snappy":
        return io.BytesIO(_snappy_bytes(path.read_bytes()))
    raise ValueError(f"unknown compression '{comp}'")


def detect_inner_suffix(path: Path, comp: str) -> str:
    """Format suffix of the data inside the archive, for files like 'data.gz'.

    Prefers the first member's filename (zip), otherwise sniffs the first
    decompressed bytes. Falls back to '.csv' when nothing can be determined.
    """
    try:
        if comp == "zip":
            member = _zip_first_member(path)
            if member:
                inner = Path(member).suffix.lower()
                if inner in FORMATS:
                    return inner
        with _decompress_open(path, comp) as f:
            return _sniff_suffix(f.read(4096))
    except Exception:  # noqa: BLE001 - detection is best-effort
        return ".csv"


def required_packages(path: Path) -> list[str]:
    """Extra pip packages needed to open `path`, beyond pandas."""
    comp, inner = split_compression(path)
    if comp is not None and inner not in FORMATS:
        inner = detect_inner_suffix(path, comp)
    fmt = FORMATS.get(inner)
    packages = [fmt.requires] if fmt and fmt.requires else []
    if comp in _COMPRESSION_REQUIRES:
        packages.append(_COMPRESSION_REQUIRES[comp])
    return packages


def is_binary(path: Path) -> bool:
    """True when the file cannot be shown/edited as plain text in the editor."""
    suffix = path.suffix.lower()
    return suffix in BINARY_SUFFIXES or suffix in COMPRESSIONS


# ------------------------------------------------------------ code generation
def read_code(path: Path) -> str:
    """Pandas code that loads `path` into `df`, for the generated .pandas canvas."""
    # Forward slashes so Windows backslashes never form escape sequences ("C:\Users" -> \U).
    posix = path.as_posix()
    comp, suffix = split_compression(path)

    if comp is None:
        fmt = FORMATS.get(suffix)
        if fmt is None:
            return f'df = pd.read_table("{posix}")  # unrecognised format — adjust the reader'
        code = fmt.snippet.replace("{path}", posix)
        if fmt.requires and "requires" not in code:
            code += f"  # requires:  pip install {fmt.requires}"
        return code

    note = ""
    if suffix not in FORMATS:
        suffix = detect_inner_suffix(path, comp)
        note = f"  # {suffix.lstrip('.')} content detected inside the archive"
    fmt = FORMATS.get(suffix, FORMATS[".csv"])
    packages = [p for p in (fmt.requires, _COMPRESSION_REQUIRES.get(comp)) if p]
    if packages:
        note += "  # requires:  pip install " + " ".join(packages)

    # Multiline snippets (e.g. avro) can't be rewritten to take a stream; fall
    # back to a csv reader the user can adjust.
    call = fmt.snippet if "\n" not in fmt.snippet else FORMATS[".csv"].snippet

    if comp == "snappy":
        buffer_call = call.replace('"{path}"', "io.BytesIO(data)")
        return (
            "# Snappy is not built into pandas — requires:  pip install python-snappy\n"
            "import io\n"
            "import snappy\n"
            "\n"
            f'with open("{posix}", "rb") as f:\n'
            "    data = snappy.uncompress(f.read())  # framed/hadoop: snappy.stream_decompress\n"
            f"{buffer_call}{note}"
        )

    if suffix in _COMPRESSIBLE:
        code = call.replace('"{path}"', f'"{posix}", compression="{comp}"')
        return code + note

    if comp == "zip":
        buffer_call = call.replace('"{path}"', "io.BytesIO(data)")
        return (
            "import io\n"
            "import zipfile\n"
            "\n"
            f'with zipfile.ZipFile("{posix}") as zf:\n'
            "    data = zf.read(zf.namelist()[0])\n"
            f"{buffer_call}{note}"
        )

    imp, open_expr = _OPEN_SNIPPETS[comp]
    open_expr = open_expr.replace("{path}", posix)
    stream_call = call.replace('"{path}"', "f")
    return f"{imp}\n\nwith {open_expr} as f:\n    {stream_call}{note}"


def read_df_head(path: Path) -> str:
    posix = path.as_posix()
    comp, suffix = split_compression(path)
    
    if suffix == '.pickle':
        return '\nprint(df)\n'
    else:
        return '\nprint(df.head())\n'

# --------------------------------------------------------------- data loading
def load_dataframe(path: Path):
    """Load a binary or compressed data file into a DataFrame for the read-only preview."""
    import pandas as pd  # noqa: PLC0415

    comp, suffix = split_compression(path)
    if comp is not None:
        return _load_compressed(path, comp, suffix, pd)

    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".orc":
        return pd.read_orc(path)
    if suffix == ".feather":
        return pd.read_feather(path)
    if suffix == ".avro":
        import fastavro  # noqa: PLC0415

        with open(path, "rb") as f:
            return pd.DataFrame.from_records(list(fastavro.reader(f)))
    if suffix in (".xlsx", ".xlsm", ".xls", ".ods"):
        return pd.read_excel(path)
    if suffix in (".pkl", ".pickle"):
        return pd.read_pickle(path)
    if suffix in (".h5", ".hdf5"):
        return pd.read_hdf(path)
    if suffix == ".dta":
        return pd.read_stata(path)
    if suffix in (".sas7bdat", ".xpt"):
        return pd.read_sas(path)
    if suffix == ".sav":
        return pd.read_spss(path)
    raise ValueError(f"No preview reader for '{suffix}' files")


def _load_compressed(path: Path, comp: str, suffix: str, pd):
    """Preview reader for compressed files ('data.csv.gz', 'data.zip', 'data.snappy'…)."""
    if suffix not in FORMATS:
        suffix = detect_inner_suffix(path, comp)

    # Readers that take the compressed path + `compression=` directly.
    if comp != "snappy" and suffix in _COMPRESSIBLE:
        if suffix == ".tsv":
            return pd.read_csv(path, sep="\t", compression=comp)
        if suffix in (".jsonl", ".ndjson"):
            return pd.read_json(path, lines=True, compression=comp)
        if suffix == ".json":
            return pd.read_json(path, compression=comp)
        if suffix == ".xml":
            return pd.read_xml(path, compression=comp)
        if suffix in (".pkl", ".pickle"):
            return pd.read_pickle(path, compression=comp)
        return pd.read_csv(path, compression=comp)

    # Everything else: decompress to a stream and hand it to the normal reader.
    with _decompress_open(path, comp) as f:
        if suffix == ".parquet":
            return pd.read_parquet(f)
        if suffix == ".orc":
            return pd.read_orc(f)
        if suffix == ".feather":
            return pd.read_feather(f)
        if suffix == ".avro":
            import fastavro  # noqa: PLC0415

            return pd.DataFrame.from_records(list(fastavro.reader(f)))
        if suffix in (".xlsx", ".xlsm", ".xls", ".ods"):
            return pd.read_excel(f)
        if suffix in (".pkl", ".pickle"):
            return pd.read_pickle(f)
        if suffix == ".tsv":
            return pd.read_csv(f, sep="\t")
        if suffix in (".jsonl", ".ndjson"):
            return pd.read_json(f, lines=True)
        if suffix == ".json":
            return pd.read_json(f)
        if suffix == ".xml":
            return pd.read_xml(f)
        return pd.read_csv(f)
