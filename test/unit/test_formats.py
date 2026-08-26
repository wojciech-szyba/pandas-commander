"""Unit tests for panels/formats.py — format registry, compression handling,
code generation, and dataframe loading."""
from __future__ import annotations

import gzip
import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from panels import formats

# --------------------------------------------------------------- split_compression

@pytest.mark.parametrize(
    "name, expected",
    [
        ("data.csv.gz", ("gzip", ".csv")),
        ("data.csv.gzip", ("gzip", ".csv")),
        ("data.json.bz2", ("bz2", ".json")),
        ("data.csv.xz", ("xz", ".csv")),
        ("data.csv.zst", ("zstd", ".csv")),
        ("data.csv.snappy", ("snappy", ".csv")),
        ("archive.zip", ("zip", "")),
        ("data.gz", ("gzip", "")),
        ("data.csv", (None, ".csv")),
        ("noext", (None, "")),
    ],
)
def test_split_compression(name, expected):
    assert formats.split_compression(Path(name)) == expected


def test_split_compression_is_case_insensitive():
    assert formats.split_compression(Path("data.CSV.GZ")) == ("gzip", ".csv")


# --------------------------------------------------------------------- is_binary

@pytest.mark.parametrize("name", ["data.parquet", "data.xlsx", "data.pkl", "data.gz", "data.zip"])
def test_is_binary_true(name):
    assert formats.is_binary(Path(name)) is True


@pytest.mark.parametrize("name", ["data.csv", "script.py", "notes.txt", "query.sql"])
def test_is_binary_false(name):
    assert formats.is_binary(Path(name)) is False


# -------------------------------------------------------------- required_packages

def test_required_packages_plain_csv_none():
    assert formats.required_packages(Path("data.csv")) == []


def test_required_packages_parquet():
    assert formats.required_packages(Path("data.parquet")) == ["pyarrow"]


def test_required_packages_avro():
    assert formats.required_packages(Path("data.avro")) == ["fastavro"]


def test_required_packages_compression_extra():
    assert formats.required_packages(Path("data.csv.zst")) == ["zstandard"]


def test_required_packages_combines_format_and_compression(tmp_path):
    # A binary format wrapped in a compression that itself needs an extra package.
    path = tmp_path / "data.csv.zst"
    path.write_bytes(b"a,b\n1,2\n")  # content irrelevant; suffix drives the check
    assert formats.required_packages(path) == ["zstandard"]


def test_required_packages_gzip_needs_nothing_extra():
    assert formats.required_packages(Path("data.csv.gz")) == []


def test_required_packages_sniffs_bare_compressed_suffix(tmp_path):
    # "data.gz" has no recognisable inner suffix from the name alone --
    # required_packages must sniff the content via detect_inner_suffix().
    path = tmp_path / "data.gz"
    with gzip.open(path, "wb") as f:
        f.write(b'{"a": 1}')
    assert formats.required_packages(path) == []  # json needs no extra package


# ------------------------------------------------------------- detect_inner_suffix

def test_detect_inner_suffix_zip_prefers_member_name(tmp_path):
    zpath = tmp_path / "archive.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("payload.json", '{"a": 1}')
    assert formats.detect_inner_suffix(zpath, "zip") == ".json"


def test_detect_inner_suffix_zip_empty_falls_back(tmp_path):
    zpath = tmp_path / "empty.zip"
    with zipfile.ZipFile(zpath, "w"):
        pass
    # No members at all -> _zip_first_member returns None -> best-effort ".csv".
    assert formats.detect_inner_suffix(zpath, "zip") == ".csv"


def test_detect_inner_suffix_sniffs_json(tmp_path):
    gpath = tmp_path / "data.gz"
    with gzip.open(gpath, "wb") as f:
        f.write(b'{"a": 1}')
    assert formats.detect_inner_suffix(gpath, "gzip") == ".json"


def test_detect_inner_suffix_sniffs_jsonl(tmp_path):
    gpath = tmp_path / "data.gz"
    with gzip.open(gpath, "wb") as f:
        f.write(b'{"a": 1}\n{"a": 2}\n')
    assert formats.detect_inner_suffix(gpath, "gzip") == ".jsonl"


def test_detect_inner_suffix_sniffs_xml(tmp_path):
    gpath = tmp_path / "data.gz"
    with gzip.open(gpath, "wb") as f:
        f.write(b"<root><a>1</a></root>")
    assert formats.detect_inner_suffix(gpath, "gzip") == ".xml"


def test_detect_inner_suffix_sniffs_parquet_magic(tmp_path):
    gpath = tmp_path / "data.gz"
    with gzip.open(gpath, "wb") as f:
        f.write(b"PAR1" + b"\x00" * 32)
    assert formats.detect_inner_suffix(gpath, "gzip") == ".parquet"


def test_detect_inner_suffix_sniffs_orc_magic(tmp_path):
    gpath = tmp_path / "data.gz"
    with gzip.open(gpath, "wb") as f:
        f.write(b"ORC" + b"\x00" * 32)
    assert formats.detect_inner_suffix(gpath, "gzip") == ".orc"


def test_detect_inner_suffix_defaults_to_csv(tmp_path):
    gpath = tmp_path / "data.gz"
    with gzip.open(gpath, "wb") as f:
        f.write(b"a,b\n1,2\n")
    assert formats.detect_inner_suffix(gpath, "gzip") == ".csv"


def test_detect_inner_suffix_best_effort_on_broken_archive(tmp_path):
    # Not actually gzip data -> decompression raises -> best-effort ".csv".
    bad = tmp_path / "broken.gz"
    bad.write_bytes(b"not gzip data at all")
    assert formats.detect_inner_suffix(bad, "gzip") == ".csv"


# ------------------------------------------------------------------------ read_code

def test_read_code_plain_csv():
    code = formats.read_code(Path("/tmp/data.csv"))
    assert code == 'df = pd.read_csv("/tmp/data.csv")'


def test_read_code_unrecognised_suffix_falls_back_to_read_table():
    code = formats.read_code(Path("/tmp/data.xyz"))
    assert "read_table" in code
    assert "unrecognised format" in code


def test_read_code_binary_format_notes_required_package():
    code = formats.read_code(Path("/tmp/data.parquet"))
    assert code.split("  #")[0] == 'df = pd.read_parquet("/tmp/data.parquet")'
    assert "pip install pyarrow" in code


def test_read_code_compressed_compressible_inner_uses_compression_kwarg():
    code = formats.read_code(Path("/tmp/data.csv.gz"))
    assert code == 'df = pd.read_csv("/tmp/data.csv.gz", compression="gzip")'


def test_read_code_compressed_tsv():
    code = formats.read_code(Path("/tmp/data.tsv.bz2"))
    assert 'compression="bz2"' in code
    assert 'sep="\\t"' in code


def test_read_code_bare_gz_sniffs_and_annotates(tmp_path):
    gpath = tmp_path / "mystery.gz"
    with gzip.open(gpath, "wb") as f:
        f.write(b'{"a": 1}')
    code = formats.read_code(gpath)
    assert 'pd.read_json("' in code
    assert 'compression="gzip"' in code
    assert "json content detected inside the archive" in code


def test_read_code_zip_of_compressible_inner_uses_compression_kwarg(tmp_path):
    # csv/json/... can take compression="zip" directly -> no manual unzip needed.
    zpath = tmp_path / "archive.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("payload.csv", "a,b\n1,2\n")
    code = formats.read_code(zpath)
    assert 'compression="zip"' in code
    assert "zipfile.ZipFile" not in code


def test_read_code_zip_of_binary_inner_wraps_with_zipfile_snippet(tmp_path):
    # xlsx can't take compression=..., so it needs the manual unzip-then-read snippet.
    zpath = tmp_path / "archive.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("payload.xlsx", b"not-really-xlsx-bytes")
    code = formats.read_code(zpath)
    assert "zipfile.ZipFile" in code
    assert "io.BytesIO(data)" in code
    assert "pd.read_excel(io.BytesIO(data))" in code


def test_read_code_xz_of_compressible_inner_uses_compression_kwarg():
    code = formats.read_code(Path("/tmp/data.csv.xz"))
    assert 'compression="xz"' in code
    assert "import lzma" not in code


def test_read_code_xz_of_binary_inner_uses_lzma_stream():
    # xlsx isn't in _COMPRESSIBLE, so xz needs the manual lzma.open() stream.
    code = formats.read_code(Path("/tmp/data.xlsx.xz"))
    assert "import lzma" in code
    assert 'lzma.open("/tmp/data.xlsx.xz", "rb")' in code
    assert "pd.read_excel(f)" in code


def test_read_code_snappy_has_dedicated_branch():
    code = formats.read_code(Path("/tmp/data.csv.snappy"))
    assert "pip install python-snappy" in code
    assert "snappy.uncompress" in code
    assert "io.BytesIO(data)" in code


def test_read_code_binary_format_wrapped_in_compression_drops_double_note():
    # A binary reader (parquet) whose snippet has no {path} substring for
    # compression=... : still goes through the streaming/open() path since
    # parquet isn't in _COMPRESSIBLE.
    code = formats.read_code(Path("/tmp/data.parquet.gz"))
    assert "gzip.open" in code
    assert "pd.read_parquet(f)" in code
    assert "pip install pyarrow" in code


def test_read_code_forward_slashes_on_windows_style_path():
    code = formats.read_code(Path(r"C:\Users\me\data.csv"))
    assert "C:/Users/me/data.csv" in code
    assert "\\U" not in code


# --------------------------------------------------------------------- read_df_head

def test_read_df_head_pickle_prints_whole_df():
    assert formats.read_df_head(Path("data.pickle")) == "\nprint(df)\n"


def test_read_df_head_default_prints_head():
    assert formats.read_df_head(Path("data.csv")) == "\nprint(df.head())\n"


# ------------------------------------------------------------------- load_dataframe

def test_load_dataframe_uncompressed_csv_has_no_registered_preview_reader(tmp_path):
    # load_dataframe is only wired up for binary/compressed formats (is_binary());
    # plain .csv is editable text and never routed through it by EditorPanel.
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No preview reader"):
        formats.load_dataframe(path)


def test_load_dataframe_tsv(tmp_path):
    path = tmp_path / "data.tsv"
    path.write_text("a\tb\n1\t2\n", encoding="utf-8")
    # .tsv is not itself a FORMATS/binary suffix handled by load_dataframe's
    # top-level dispatch (only compressed .tsv goes through _load_compressed);
    # ensure the uncompressed case still raises the documented ValueError.
    with pytest.raises(ValueError):
        formats.load_dataframe(path)


def test_load_dataframe_gzip_compressed_csv(tmp_path):
    path = tmp_path / "data.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write("a,b\n1,2\n")
    df = formats.load_dataframe(path)
    assert list(df.columns) == ["a", "b"]


def test_load_dataframe_gzip_compressed_tsv(tmp_path):
    path = tmp_path / "data.tsv.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write("a\tb\n1\t2\n")
    df = formats.load_dataframe(path)
    assert list(df.columns) == ["a", "b"]


def test_load_dataframe_gzip_compressed_jsonl(tmp_path):
    path = tmp_path / "data.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write('{"a": 1}\n{"a": 2}\n')
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


def test_load_dataframe_zip_wraps_first_member(tmp_path):
    path = tmp_path / "data.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("inner.csv", "a,b\n5,6\n")
    df = formats.load_dataframe(path)
    assert df.iloc[0]["a"] == 5


def test_load_dataframe_pickle_roundtrip(tmp_path):
    path = tmp_path / "data.pkl"
    pd.DataFrame({"a": [1, 2]}).to_pickle(path)
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


def test_load_dataframe_pickle_compressed_roundtrip(tmp_path):
    path = tmp_path / "data.pkl.gz"
    pd.DataFrame({"a": [1, 2]}).to_pickle(path, compression="gzip")
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


def test_load_dataframe_stata_roundtrip(tmp_path):
    path = tmp_path / "data.dta"
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_stata(path, write_index=False)
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


def test_load_dataframe_xlsx_roundtrip(tmp_path):
    pytest.importorskip("openpyxl")
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"a": [1, 2]}).to_excel(path, index=False)
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


def test_load_dataframe_unsupported_suffix_raises_value_error():
    with pytest.raises(ValueError, match="No preview reader"):
        formats.load_dataframe(Path("data.weird"))


def test_load_dataframe_parquet_dispatches_via_pandas(tmp_path, monkeypatch):
    """pyarrow's native lib may be unavailable in CI/sandboxes; verify the
    dispatch logic itself with a stub instead of requiring a real engine."""
    path = tmp_path / "data.parquet"
    path.touch()
    sentinel = pd.DataFrame({"x": [1]})
    monkeypatch.setattr(pd, "read_parquet", lambda p: sentinel)
    assert formats.load_dataframe(path) is sentinel


def test_load_dataframe_orc_dispatches_via_pandas(tmp_path, monkeypatch):
    path = tmp_path / "data.orc"
    path.touch()
    sentinel = pd.DataFrame({"x": [1]})
    monkeypatch.setattr(pd, "read_orc", lambda p: sentinel)
    assert formats.load_dataframe(path) is sentinel


def test_load_dataframe_feather_dispatches_via_pandas(tmp_path, monkeypatch):
    path = tmp_path / "data.feather"
    path.touch()
    sentinel = pd.DataFrame({"x": [1]})
    monkeypatch.setattr(pd, "read_feather", lambda p: sentinel)
    assert formats.load_dataframe(path) is sentinel


def test_load_dataframe_hdf_dispatches_via_pandas(tmp_path, monkeypatch):
    path = tmp_path / "data.h5"
    path.touch()
    sentinel = pd.DataFrame({"x": [1]})
    monkeypatch.setattr(pd, "read_hdf", lambda p: sentinel)
    assert formats.load_dataframe(path) is sentinel


def test_load_dataframe_sas_dispatches_via_pandas(tmp_path, monkeypatch):
    path = tmp_path / "data.sas7bdat"
    path.touch()
    sentinel = pd.DataFrame({"x": [1]})
    monkeypatch.setattr(pd, "read_sas", lambda p: sentinel)
    assert formats.load_dataframe(path) is sentinel


def test_load_dataframe_spss_dispatches_via_pandas(tmp_path, monkeypatch):
    path = tmp_path / "data.sav"
    path.touch()
    sentinel = pd.DataFrame({"x": [1]})
    monkeypatch.setattr(pd, "read_spss", lambda p: sentinel)
    assert formats.load_dataframe(path) is sentinel


def test_load_dataframe_avro_dispatches_via_fastavro(tmp_path, monkeypatch):
    path = tmp_path / "data.avro"
    path.write_bytes(b"")
    fake_fastavro = type("FakeFastavro", (), {"reader": staticmethod(lambda f: [{"a": 1}, {"a": 2}])})
    monkeypatch.setitem(__import__("sys").modules, "fastavro", fake_fastavro)
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


def test_load_dataframe_zstd_compressed_dispatches_via_decompress_open(tmp_path, monkeypatch):
    """zstandard may not be installed. csv/json/... take pandas' own
    compression=... kwarg directly, but binary formats like xlsx are streamed
    through _decompress_open() first -- verify that dispatch with a stub."""
    pytest.importorskip("openpyxl")
    path = tmp_path / "data.xlsx.zst"
    path.write_bytes(b"unused")

    buffer = io.BytesIO()
    pd.DataFrame({"a": [7, 8]}).to_excel(buffer, index=False)
    buffer.seek(0)

    def fake_decompress_open(p, comp):
        assert comp == "zstd"
        return buffer

    monkeypatch.setattr(formats, "_decompress_open", fake_decompress_open)
    df = formats.load_dataframe(path)
    assert df.iloc[0]["a"] == 7


# --------------------------------------------------------------- _snappy_bytes

def test_snappy_bytes_uses_raw_uncompress_first(monkeypatch):
    fake_snappy = type(
        "FakeSnappy",
        (),
        {"uncompress": staticmethod(lambda raw: b"decoded")},
    )
    monkeypatch.setitem(__import__("sys").modules, "snappy", fake_snappy)
    assert formats._snappy_bytes(b"raw-bytes") == b"decoded"


def test_snappy_bytes_falls_back_to_stream_decompress(monkeypatch):
    def boom(raw):
        raise ValueError("not raw snappy")

    def stream_decompress(src, dst):
        dst.write(b"streamed")

    fake_snappy = type(
        "FakeSnappy",
        (),
        {
            "uncompress": staticmethod(boom),
            "stream_decompress": staticmethod(stream_decompress),
        },
    )
    monkeypatch.setitem(__import__("sys").modules, "snappy", fake_snappy)
    assert formats._snappy_bytes(b"raw-bytes") == b"streamed"


def test_snappy_bytes_raises_when_nothing_works(monkeypatch):
    def boom(raw):
        raise ValueError("nope")

    fake_snappy = type("FakeSnappy", (), {"uncompress": staticmethod(boom)})
    monkeypatch.setitem(__import__("sys").modules, "snappy", fake_snappy)
    with pytest.raises(ValueError, match="not a recognised snappy stream"):
        formats._snappy_bytes(b"raw-bytes")


def test_snappy_bytes_falls_back_to_hadoop_stream_decompress(monkeypatch):
    """uncompress() and stream_decompress() both fail; hadoop_stream_decompress()
    is the last fallback tried."""

    def boom(raw):
        raise ValueError("not raw snappy")

    def stream_boom(src, dst):
        raise ValueError("not framed snappy either")

    def hadoop_stream_decompress(src, dst):
        dst.write(b"hadoop-framed")

    fake_snappy = type(
        "FakeSnappy",
        (),
        {
            "uncompress": staticmethod(boom),
            "stream_decompress": staticmethod(stream_boom),
            "hadoop_stream_decompress": staticmethod(hadoop_stream_decompress),
        },
    )
    monkeypatch.setitem(__import__("sys").modules, "snappy", fake_snappy)
    assert formats._snappy_bytes(b"raw-bytes") == b"hadoop-framed"


# ------------------------------------------------ _decompress_open (real streams)

def test_decompress_open_bz2_real_stream(tmp_path):
    import bz2

    path = tmp_path / "data.bz2"
    path.write_bytes(bz2.compress(b"hello-bz2"))
    with formats._decompress_open(path, "bz2") as f:
        assert f.read() == b"hello-bz2"


def test_decompress_open_xz_real_stream(tmp_path):
    import lzma

    path = tmp_path / "data.xz"
    path.write_bytes(lzma.compress(b"hello-xz"))
    with formats._decompress_open(path, "xz") as f:
        assert f.read() == b"hello-xz"


def test_decompress_open_zstd_not_installed_raises_import_error(tmp_path):
    path = tmp_path / "data.zst"
    path.write_bytes(b"irrelevant")
    with pytest.raises(ImportError):
        formats._decompress_open(path, "zstd")


def test_decompress_open_unknown_compression_raises():
    with pytest.raises(ValueError, match="unknown compression"):
        formats._decompress_open(Path("data.mystery"), "mystery")


def test_decompress_open_zip_reads_first_member_bytes(tmp_path):
    path = tmp_path / "archive.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.md", b"# hello")
    with formats._decompress_open(path, "zip") as f:
        assert f.read() == b"# hello"


def test_decompress_open_empty_zip_raises_value_error(tmp_path):
    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w"):
        pass
    with pytest.raises(ValueError, match="empty zip archive"):
        formats._decompress_open(path, "zip")


def test_detect_inner_suffix_zip_member_with_unrecognised_suffix_sniffs_content(tmp_path):
    # Member name isn't a known data suffix (.md), so detect_inner_suffix
    # must fall through to reading and sniffing the actual bytes.
    zpath = tmp_path / "archive.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("readme.md", '{"a": 1}')
    assert formats.detect_inner_suffix(zpath, "zip") == ".json"


# --------------------------------------------- _load_compressed dispatch (binary)

def test_load_dataframe_gzip_compressed_json_uses_direct_compression_kwarg(tmp_path):
    path = tmp_path / "data.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write('{"a": [1, 2]}')
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


def test_load_dataframe_gzip_compressed_xml_uses_direct_compression_kwarg(tmp_path):
    pytest.importorskip("lxml")
    path = tmp_path / "data.xml.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write("<root><row><a>1</a></row><row><a>2</a></row></root>")
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


@pytest.mark.parametrize("suffix,attr", [(".parquet", "read_parquet"), (".orc", "read_orc"), (".feather", "read_feather")])
def test_load_dataframe_gzip_compressed_binary_dispatches_via_decompress_stream(tmp_path, monkeypatch, suffix, attr):
    path = tmp_path / f"data{suffix}.gz"
    with gzip.open(path, "wb") as f:
        f.write(b"irrelevant-bytes")
    sentinel = pd.DataFrame({"x": [1]})
    monkeypatch.setattr(pd, attr, lambda f: sentinel)
    assert formats.load_dataframe(path) is sentinel


def test_load_dataframe_gzip_compressed_avro_dispatches_via_fastavro(tmp_path, monkeypatch):
    path = tmp_path / "data.avro.gz"
    with gzip.open(path, "wb") as f:
        f.write(b"irrelevant-bytes")
    fake_fastavro = type("FakeFastavro", (), {"reader": staticmethod(lambda f: [{"a": 5}])})
    monkeypatch.setitem(__import__("sys").modules, "fastavro", fake_fastavro)
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [5]


# ---------------------------------- _load_compressed dispatch (text, via snappy)

def _fake_snappy_identity(monkeypatch, raw: bytes) -> None:
    """Installs a fake `snappy` module whose uncompress() is the identity
    function, so a ".snappy" file's on-disk bytes ARE the "decompressed"
    content -- lets these tests exercise real pandas readers without a real
    snappy stream or the python-snappy package."""
    fake_snappy = type("FakeSnappy", (), {"uncompress": staticmethod(lambda data: raw)})
    monkeypatch.setitem(__import__("sys").modules, "snappy", fake_snappy)


def test_load_dataframe_snappy_tsv(tmp_path, monkeypatch):
    raw = b"a\tb\n1\t2\n"
    _fake_snappy_identity(monkeypatch, raw)
    path = tmp_path / "data.tsv.snappy"
    path.write_bytes(b"placeholder")
    df = formats.load_dataframe(path)
    assert list(df.columns) == ["a", "b"]


def test_load_dataframe_snappy_jsonl(tmp_path, monkeypatch):
    raw = b'{"a": 1}\n{"a": 2}\n'
    _fake_snappy_identity(monkeypatch, raw)
    path = tmp_path / "data.jsonl.snappy"
    path.write_bytes(b"placeholder")
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


def test_load_dataframe_snappy_json(tmp_path, monkeypatch):
    raw = b'{"a": [1, 2]}'
    _fake_snappy_identity(monkeypatch, raw)
    path = tmp_path / "data.json.snappy"
    path.write_bytes(b"placeholder")
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1, 2]


def test_load_dataframe_snappy_xml(tmp_path, monkeypatch):
    pytest.importorskip("lxml")
    raw = b"<root><row><a>1</a></row></root>"
    _fake_snappy_identity(monkeypatch, raw)
    path = tmp_path / "data.xml.snappy"
    path.write_bytes(b"placeholder")
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [1]


def test_load_dataframe_snappy_generic_suffix_falls_back_to_csv(tmp_path, monkeypatch):
    # comp == "snappy" always skips the top compression=... shortcut (even
    # for csv-like content), so an unrecognised/default-sniffed suffix ends
    # up at _load_compressed's final bare `pd.read_csv(f)` fallback.
    raw = b"a,b\n3,4\n"
    _fake_snappy_identity(monkeypatch, raw)
    path = tmp_path / "data.mystery.snappy"
    path.write_bytes(b"placeholder")
    df = formats.load_dataframe(path)
    assert list(df.columns) == ["a", "b"]
    assert df.iloc[0]["a"] == 3


def test_load_dataframe_snappy_pickle(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    pd.DataFrame({"a": [9]}).to_pickle(buffer)
    _fake_snappy_identity(monkeypatch, buffer.getvalue())
    path = tmp_path / "data.pkl.snappy"
    path.write_bytes(b"placeholder")
    df = formats.load_dataframe(path)
    assert list(df["a"]) == [9]
