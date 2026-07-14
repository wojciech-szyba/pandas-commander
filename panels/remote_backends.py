from __future__ import annotations

from pathlib import Path

from panels.remote_sources import RemoteConfigError, RemoteConnection, RemoteEntry

# Package required for each backend, surfaced in the error message when the
# matching library isn't installed (they are optional — see requirements.txt).
_REQUIRED_PACKAGE = {
    "sftp": "paramiko",
    "s3": "boto3",
    "gcs": "google-cloud-storage",
    "azure": "azure-storage-blob",
}


def _require(conn: RemoteConnection, key: str) -> str:
    value = conn.options.get(key)
    if not value:
        raise RemoteConfigError(f"[{conn.name}] is missing required option '{key}'")
    return value


def list_dir(conn: RemoteConnection, path: str) -> list[RemoteEntry]:
    """List one 'directory' level of a remote connection (path is '' at the root)."""
    try:
        if conn.type == "sftp":
            return _sftp_list(conn, path)
        if conn.type == "s3":
            return _s3_list(conn, path)
        if conn.type == "gcs":
            return _gcs_list(conn, path)
        if conn.type == "azure":
            return _azure_list(conn, path)
    except ImportError as exc:
        raise RemoteConfigError(
            f"'{_REQUIRED_PACKAGE[conn.type]}' is not installed — cannot browse [{conn.name}].\n"
            f"Install with:  pip install {_REQUIRED_PACKAGE[conn.type]}"
        ) from exc
    raise RemoteConfigError(f"Unsupported remote type '{conn.type}' for [{conn.name}]")


def download(conn: RemoteConnection, path: str, dest: Path) -> None:
    """Download a single remote file to a local path (read-only preview copy)."""
    try:
        if conn.type == "sftp":
            _sftp_download(conn, path, dest)
            return
        if conn.type == "s3":
            _s3_download(conn, path, dest)
            return
        if conn.type == "gcs":
            _gcs_download(conn, path, dest)
            return
        if conn.type == "azure":
            _azure_download(conn, path, dest)
            return
    except ImportError as exc:
        raise RemoteConfigError(
            f"'{_REQUIRED_PACKAGE[conn.type]}' is not installed — cannot download from [{conn.name}].\n"
            f"Install with:  pip install {_REQUIRED_PACKAGE[conn.type]}"
        ) from exc
    raise RemoteConfigError(f"Unsupported remote type '{conn.type}' for [{conn.name}]")


# ------------------------------------------------------------------------ sftp
def _sftp_connect(conn: RemoteConnection):
    import paramiko  # noqa: PLC0415

    opts = conn.options
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=_require(conn, "host"),
        port=int(opts.get("port", 22)),
        username=opts.get("username"),
        password=opts.get("password"),
        key_filename=opts.get("key_filename") or None,
        timeout=10,
    )
    return client, client.open_sftp()


def _sftp_full_path(conn: RemoteConnection, path: str) -> str:
    root = conn.options.get("path", ".").rstrip("/") or "."
    return f"{root}/{path}" if path else root


def _sftp_list(conn: RemoteConnection, path: str) -> list[RemoteEntry]:
    import stat as stat_module  # noqa: PLC0415

    client, sftp = _sftp_connect(conn)
    try:
        entries = [
            RemoteEntry(
                name=attr.filename,
                is_dir=stat_module.S_ISDIR(attr.st_mode or 0),
                size=attr.st_size or 0,
            )
            for attr in sftp.listdir_attr(_sftp_full_path(conn, path))
        ]
    finally:
        sftp.close()
        client.close()
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


def _sftp_download(conn: RemoteConnection, path: str, dest: Path) -> None:
    client, sftp = _sftp_connect(conn)
    try:
        sftp.get(_sftp_full_path(conn, path), str(dest))
    finally:
        sftp.close()
        client.close()


# -------------------------------------------------------------------------- s3
def _s3_client(conn: RemoteConnection):
    import boto3  # noqa: PLC0415

    opts = conn.options
    kwargs = {}
    if opts.get("access_key"):
        kwargs["aws_access_key_id"] = opts["access_key"]
    if opts.get("secret_key"):
        kwargs["aws_secret_access_key"] = opts["secret_key"]
    if opts.get("session_token"):
        kwargs["aws_session_token"] = opts["session_token"]
    if opts.get("region"):
        kwargs["region_name"] = opts["region"]
    if opts.get("endpoint_url"):
        kwargs["endpoint_url"] = opts["endpoint_url"]
    return boto3.client("s3", **kwargs)


def _s3_list(conn: RemoteConnection, path: str) -> list[RemoteEntry]:
    client = _s3_client(conn)
    bucket = _require(conn, "bucket")
    prefix = f"{path}/" if path else ""
    resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")

    entries = [
        RemoteEntry(name=cp["Prefix"][len(prefix):].rstrip("/"), is_dir=True)
        for cp in resp.get("CommonPrefixes", [])
    ]
    for obj in resp.get("Contents", []):
        name = obj["Key"][len(prefix):]
        if not name or "/" in name:
            continue
        entries.append(RemoteEntry(name=name, is_dir=False, size=obj.get("Size", 0)))
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


def _s3_download(conn: RemoteConnection, path: str, dest: Path) -> None:
    client = _s3_client(conn)
    client.download_file(_require(conn, "bucket"), path, str(dest))


# ------------------------------------------------------------------------- gcs
def _gcs_client(conn: RemoteConnection):
    from google.cloud import storage  # noqa: PLC0415

    opts = conn.options
    project = opts.get("project") or None
    creds_file = opts.get("credentials_file")
    if creds_file:
        return storage.Client.from_service_account_json(creds_file, project=project)
    return storage.Client(project=project)


def _gcs_list(conn: RemoteConnection, path: str) -> list[RemoteEntry]:
    client = _gcs_client(conn)
    bucket = client.bucket(_require(conn, "bucket"))
    prefix = f"{path}/" if path else ""
    iterator = client.list_blobs(bucket, prefix=prefix, delimiter="/")
    blobs = list(iterator)  # must exhaust the iterator before .prefixes is populated

    entries = [
        RemoteEntry(name=name[len(prefix):].rstrip("/"), is_dir=True)
        for name in sorted(iterator.prefixes)
    ]
    for blob in blobs:
        name = blob.name[len(prefix):]
        if not name or "/" in name:
            continue
        entries.append(RemoteEntry(name=name, is_dir=False, size=blob.size or 0))
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


def _gcs_download(conn: RemoteConnection, path: str, dest: Path) -> None:
    client = _gcs_client(conn)
    bucket = client.bucket(_require(conn, "bucket"))
    bucket.blob(path).download_to_filename(str(dest))


# ----------------------------------------------------------------------- azure
def _azure_client(conn: RemoteConnection):
    from azure.storage.blob import BlobServiceClient  # noqa: PLC0415

    opts = conn.options
    if opts.get("connection_string"):
        return BlobServiceClient.from_connection_string(opts["connection_string"])
    account_name = _require(conn, "account_name")
    account_url = opts.get("account_url") or f"https://{account_name}.blob.core.windows.net"
    return BlobServiceClient(account_url=account_url, credential=opts.get("account_key"))


def _azure_list(conn: RemoteConnection, path: str) -> list[RemoteEntry]:
    from azure.storage.blob import BlobPrefix  # noqa: PLC0415

    client = _azure_client(conn)
    container = client.get_container_client(_require(conn, "container"))
    prefix = f"{path}/" if path else ""

    entries = []
    for item in container.walk_blobs(name_starts_with=prefix, delimiter="/"):
        name = item.name[len(prefix):].rstrip("/")
        if not name:
            continue
        if isinstance(item, BlobPrefix):
            entries.append(RemoteEntry(name=name, is_dir=True))
        else:
            entries.append(RemoteEntry(name=name, is_dir=False, size=item.size or 0))
    return sorted(entries, key=lambda e: (not e.is_dir, e.name.lower()))


def _azure_download(conn: RemoteConnection, path: str, dest: Path) -> None:
    client = _azure_client(conn)
    container = client.get_container_client(_require(conn, "container"))
    with open(dest, "wb") as f:
        f.write(container.get_blob_client(path).download_blob().readall())
