"""Unit tests for panels/remote_backends.py.

None of paramiko / boto3 / google-cloud-storage / azure-storage-blob are
installed in this environment (they're optional, per requirements.txt), so
two kinds of coverage are used:

1. The real "not installed" path is exercised for real (no mocking needed —
   the import genuinely fails), verifying the friendly RemoteConfigError.
2. Fake modules are injected into sys.modules to exercise the actual
   list/download logic against each backend's real (documented) SDK shape,
   without needing the heavy real SDKs installed.
"""
from __future__ import annotations

import stat as stat_module
import sys
import types
from pathlib import Path

import pytest

from panels import remote_backends
from panels.remote_sources import RemoteConfigError, RemoteConnection


def _install_module(monkeypatch: pytest.MonkeyPatch, dotted_name: str, module: types.ModuleType) -> None:
    """Insert `module` into sys.modules under `dotted_name`, wiring up any
    intermediate packages so `import a.b.c` / `from a.b import c` both work."""
    parts = dotted_name.split(".")
    for i in range(1, len(parts) + 1):
        name = ".".join(parts[:i])
        current = module if i == len(parts) else sys.modules.get(name) or types.ModuleType(name)
        if not hasattr(current, "__path__"):
            current.__path__ = []
        monkeypatch.setitem(sys.modules, name, current)
        if i > 1:
            setattr(sys.modules[".".join(parts[: i - 1])], parts[i - 1], current)


# ------------------------------------------------------------------ not-installed

@pytest.mark.parametrize("rtype,pkg", [("sftp", "paramiko"), ("s3", "boto3"), ("gcs", "google-cloud-storage"), ("azure", "azure-storage-blob")])
def test_list_dir_reports_missing_package(rtype, pkg, monkeypatch):
    for mod in ("paramiko", "boto3", "google.cloud.storage", "azure.storage.blob"):
        monkeypatch.delitem(sys.modules, mod, raising=False)
    conn = RemoteConnection(name="conn1", type=rtype, options={})
    with pytest.raises(RemoteConfigError, match=f"pip install {pkg}"):
        remote_backends.list_dir(conn, "")


@pytest.mark.parametrize("rtype,pkg", [("sftp", "paramiko"), ("s3", "boto3"), ("gcs", "google-cloud-storage"), ("azure", "azure-storage-blob")])
def test_download_reports_missing_package(rtype, pkg, monkeypatch, tmp_path):
    for mod in ("paramiko", "boto3", "google.cloud.storage", "azure.storage.blob"):
        monkeypatch.delitem(sys.modules, mod, raising=False)
    conn = RemoteConnection(name="conn1", type=rtype, options={})
    with pytest.raises(RemoteConfigError, match=f"pip install {pkg}"):
        remote_backends.download(conn, "file.csv", tmp_path / "file.csv")


def test_list_dir_unsupported_type_raises():
    conn = RemoteConnection(name="conn1", type="ftp", options={})
    with pytest.raises(RemoteConfigError, match="Unsupported remote type"):
        remote_backends.list_dir(conn, "")


def test_download_unsupported_type_raises(tmp_path):
    conn = RemoteConnection(name="conn1", type="ftp", options={})
    with pytest.raises(RemoteConfigError, match="Unsupported remote type"):
        remote_backends.download(conn, "file.csv", tmp_path / "file.csv")


# ------------------------------------------------------------------------- sftp

class _FakeSFTPAttr:
    def __init__(self, filename, is_dir, size=0):
        self.filename = filename
        self.st_mode = stat_module.S_IFDIR if is_dir else stat_module.S_IFREG
        self.st_size = size


class _FakeSFTPClient:
    def __init__(self, listing, download_content=b"remote-bytes"):
        self._listing = listing
        self.closed = False
        self.gets = []
        self._download_content = download_content

    def listdir_attr(self, path):
        return self._listing[path]

    def get(self, remote_path, local_path):
        self.gets.append((remote_path, local_path))
        Path(local_path).write_bytes(self._download_content)

    def close(self):
        self.closed = True


class _FakeSSHClient:
    def __init__(self, sftp):
        self._sftp = sftp
        self.policy = None
        self.connect_kwargs = None
        self.closed = False

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def connect(self, **kwargs):
        self.connect_kwargs = kwargs

    def open_sftp(self):
        return self._sftp

    def close(self):
        self.closed = True


def _install_fake_paramiko(monkeypatch, listing, download_content=b"remote-bytes"):
    sftp = _FakeSFTPClient(listing, download_content)
    holder = {}

    def make_client():
        client = _FakeSSHClient(sftp)
        holder["client"] = client
        return client

    fake = types.ModuleType("paramiko")
    fake.SSHClient = make_client
    fake.AutoAddPolicy = lambda: "AUTO_ADD"
    _install_module(monkeypatch, "paramiko", fake)
    return sftp, holder


@pytest.fixture
def sftp_conn():
    return RemoteConnection(
        name="myserver",
        type="sftp",
        options={"host": "example.com", "username": "bob", "password": "secret", "path": "/srv/data"},
    )


def test_sftp_list_root(monkeypatch, sftp_conn):
    listing = {
        "/srv/data": [
            _FakeSFTPAttr("b.csv", is_dir=False, size=10),
            _FakeSFTPAttr("a_dir", is_dir=True),
        ]
    }
    sftp, holder = _install_fake_paramiko(monkeypatch, listing)
    entries = remote_backends.list_dir(sftp_conn, "")
    # dirs first, then alphabetical.
    assert [(e.name, e.is_dir, e.size) for e in entries] == [("a_dir", True, 0), ("b.csv", False, 10)]
    assert sftp.closed is True
    assert holder["client"].closed is True
    assert holder["client"].connect_kwargs["hostname"] == "example.com"
    assert holder["client"].connect_kwargs["port"] == 22


def test_sftp_list_subpath_joins_root(monkeypatch, sftp_conn):
    listing = {"/srv/data/sub": [_FakeSFTPAttr("x.txt", is_dir=False, size=1)]}
    _install_fake_paramiko(monkeypatch, listing)
    entries = remote_backends.list_dir(sftp_conn, "sub")
    assert entries[0].name == "x.txt"


def test_sftp_list_default_root_when_path_option_absent(monkeypatch):
    conn = RemoteConnection(name="s", type="sftp", options={"host": "h"})
    listing = {".": [_FakeSFTPAttr("f.csv", is_dir=False, size=2)]}
    _install_fake_paramiko(monkeypatch, listing)
    entries = remote_backends.list_dir(conn, "")
    assert entries[0].name == "f.csv"


def test_sftp_download(monkeypatch, sftp_conn, tmp_path):
    _install_fake_paramiko(monkeypatch, {}, download_content=b"hello-sftp")
    dest = tmp_path / "out.csv"
    remote_backends.download(sftp_conn, "b.csv", dest)
    assert dest.read_bytes() == b"hello-sftp"


def test_sftp_uses_custom_port(monkeypatch, sftp_conn):
    sftp_conn.options["port"] = "2222"
    _, holder = _install_fake_paramiko(monkeypatch, {"/srv/data": []})
    remote_backends.list_dir(sftp_conn, "")
    assert holder["client"].connect_kwargs["port"] == 2222


# --------------------------------------------------------------------------- s3

def _install_fake_boto3(monkeypatch, list_objects_response, downloads):
    class FakeS3Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def list_objects_v2(self, **kwargs):
            downloads.setdefault("list_calls", []).append(kwargs)
            return list_objects_response

        def download_file(self, bucket, key, dest):
            downloads.setdefault("downloaded", []).append((bucket, key, dest))
            Path(dest).write_bytes(b"s3-bytes")

    holder = {}

    def client(service, **kwargs):
        c = FakeS3Client(**kwargs)
        holder["client"] = c
        return c

    fake = types.ModuleType("boto3")
    fake.client = client
    _install_module(monkeypatch, "boto3", fake)
    return holder


@pytest.fixture
def s3_conn():
    return RemoteConnection(name="bucket1", type="s3", options={"bucket": "my-bucket", "region": "us-east-1"})


def test_s3_list_dirs_and_files(monkeypatch, s3_conn):
    downloads = {}
    holder = _install_fake_boto3(
        monkeypatch,
        {
            "CommonPrefixes": [{"Prefix": "sub/"}],
            "Contents": [{"Key": "a.csv", "Size": 5}, {"Key": "sub/nested.csv", "Size": 9}],
        },
        downloads,
    )
    entries = remote_backends.list_dir(s3_conn, "")
    names = {(e.name, e.is_dir, e.size) for e in entries}
    assert ("sub", True, 0) in names
    assert ("a.csv", False, 5) in names
    # Nested key under a different prefix must not leak into the root listing.
    assert not any(e.name == "sub/nested.csv" for e in entries)
    assert holder["client"].kwargs["region_name"] == "us-east-1"


def test_s3_list_missing_bucket_raises(monkeypatch):
    conn = RemoteConnection(name="c", type="s3", options={})
    _install_fake_boto3(monkeypatch, {"Contents": []}, {})
    with pytest.raises(RemoteConfigError, match="missing required option 'bucket'"):
        remote_backends.list_dir(conn, "")


def test_s3_download(monkeypatch, s3_conn, tmp_path):
    downloads = {}
    _install_fake_boto3(monkeypatch, {"Contents": []}, downloads)
    dest = tmp_path / "out.csv"
    remote_backends.download(s3_conn, "a.csv", dest)
    assert dest.read_bytes() == b"s3-bytes"
    assert downloads["downloaded"] == [("my-bucket", "a.csv", str(dest))]


def test_s3_client_passes_explicit_credentials(monkeypatch):
    conn = RemoteConnection(
        name="c",
        type="s3",
        options={"bucket": "b", "access_key": "AK", "secret_key": "SK", "endpoint_url": "http://localhost:9000"},
    )
    holder = _install_fake_boto3(monkeypatch, {"Contents": []}, {})
    remote_backends.list_dir(conn, "")
    kwargs = holder["client"].kwargs
    assert kwargs["aws_access_key_id"] == "AK"
    assert kwargs["aws_secret_access_key"] == "SK"
    assert kwargs["endpoint_url"] == "http://localhost:9000"


# -------------------------------------------------------------------------- gcs

class _FakeBlob:
    def __init__(self, name, size=0):
        self.name = name
        self.size = size
        self.downloaded_to = None

    def download_to_filename(self, dest):
        self.downloaded_to = dest
        Path(dest).write_bytes(b"gcs-bytes")


class _FakeBlobIterator(list):
    def __init__(self, blobs, prefixes):
        super().__init__(blobs)
        self.prefixes = prefixes


class _FakeBucket:
    def __init__(self, name, blob_map):
        self.name = name
        self._blob_map = blob_map

    def blob(self, path):
        return self._blob_map.setdefault(path, _FakeBlob(path))


def _install_fake_gcs(monkeypatch, blobs, prefixes):
    blob_map = {b.name: b for b in blobs}

    class FakeClient:
        def __init__(self, project=None):
            self.project = project

        @classmethod
        def from_service_account_json(cls, path, project=None):
            return cls(project=project)

        def bucket(self, name):
            return _FakeBucket(name, blob_map)

        def list_blobs(self, bucket, prefix="", delimiter="/"):
            filtered = [b for b in blobs if b.name.startswith(prefix)]
            return _FakeBlobIterator(filtered, prefixes)

    storage_mod = types.ModuleType("google.cloud.storage")
    storage_mod.Client = FakeClient
    _install_module(monkeypatch, "google.cloud.storage", storage_mod)
    return blob_map


@pytest.fixture
def gcs_conn():
    return RemoteConnection(name="bucket1", type="gcs", options={"bucket": "my-bucket"})


def test_gcs_list_dirs_and_files(monkeypatch, gcs_conn):
    _install_fake_gcs(monkeypatch, [_FakeBlob("a.csv", 3), _FakeBlob("sub/x.csv", 4)], prefixes=["sub/"])
    entries = remote_backends.list_dir(gcs_conn, "")
    names = {(e.name, e.is_dir, e.size) for e in entries}
    assert ("sub", True, 0) in names
    assert ("a.csv", False, 3) in names


def test_gcs_download(monkeypatch, gcs_conn, tmp_path):
    _install_fake_gcs(monkeypatch, [_FakeBlob("a.csv", 3)], prefixes=[])
    dest = tmp_path / "out.csv"
    remote_backends.download(gcs_conn, "a.csv", dest)
    assert dest.read_bytes() == b"gcs-bytes"


def test_gcs_list_missing_bucket_raises(monkeypatch):
    conn = RemoteConnection(name="c", type="gcs", options={})
    _install_fake_gcs(monkeypatch, [], prefixes=[])
    with pytest.raises(RemoteConfigError, match="missing required option 'bucket'"):
        remote_backends.list_dir(conn, "")


# ------------------------------------------------------------------------ azure

class _FakeBlobItem:
    def __init__(self, name, size=0):
        self.name = name
        self.size = size


class _FakeBlobPrefix(_FakeBlobItem):
    """Distinct type so isinstance(item, BlobPrefix) can tell dirs from files."""


def _install_fake_azure(monkeypatch, items, download_content=b"azure-bytes"):
    class FakeBlobClient:
        def __init__(self, name):
            self.name = name

        def download_blob(self):
            return self

        def readall(self):
            return download_content

    class FakeContainerClient:
        def __init__(self, container_name):
            self.container_name = container_name

        def walk_blobs(self, name_starts_with="", delimiter="/"):
            return [i for i in items if i.name.startswith(name_starts_with)]

        def get_blob_client(self, path):
            return FakeBlobClient(path)

    class FakeBlobServiceClient:
        def __init__(self, account_url=None, credential=None):
            self.account_url = account_url
            self.credential = credential

        @classmethod
        def from_connection_string(cls, conn_str):
            return cls(account_url=conn_str)

        def get_container_client(self, name):
            return FakeContainerClient(name)

    blob_mod = types.ModuleType("azure.storage.blob")
    blob_mod.BlobServiceClient = FakeBlobServiceClient
    blob_mod.BlobPrefix = _FakeBlobPrefix
    _install_module(monkeypatch, "azure.storage.blob", blob_mod)


@pytest.fixture
def azure_conn():
    return RemoteConnection(
        name="cont1", type="azure", options={"container": "my-container", "account_name": "acct"}
    )


def test_azure_list_dirs_and_files(monkeypatch, azure_conn):
    items = [_FakeBlobPrefix("sub/"), _FakeBlobItem("a.csv", 6)]
    _install_fake_azure(monkeypatch, items)
    entries = remote_backends.list_dir(azure_conn, "")
    names = {(e.name, e.is_dir, e.size) for e in entries}
    assert ("sub", True, 0) in names
    assert ("a.csv", False, 6) in names


def test_azure_download(monkeypatch, azure_conn, tmp_path):
    _install_fake_azure(monkeypatch, [], download_content=b"azure-payload")
    dest = tmp_path / "out.csv"
    remote_backends.download(azure_conn, "a.csv", dest)
    assert dest.read_bytes() == b"azure-payload"


def test_azure_list_missing_container_raises(monkeypatch):
    conn = RemoteConnection(name="c", type="azure", options={"account_name": "a"})
    _install_fake_azure(monkeypatch, [])
    with pytest.raises(RemoteConfigError, match="missing required option 'container'"):
        remote_backends.list_dir(conn, "")


def test_azure_uses_connection_string_when_present(monkeypatch):
    conn = RemoteConnection(
        name="c", type="azure", options={"container": "ct", "connection_string": "DefaultEndpointsProtocol=..."}
    )
    _install_fake_azure(monkeypatch, [])
    # Should not raise despite no account_name being set.
    entries = remote_backends.list_dir(conn, "")
    assert entries == []


def test_azure_skips_item_matching_the_prefix_itself(monkeypatch, azure_conn):
    # walk_blobs() can yield the prefix "directory marker" itself (relative
    # name resolves to "" after stripping the prefix) -- it must be skipped.
    marker = _FakeBlobItem("", 0)
    real_item = _FakeBlobItem("a.csv", 3)
    _install_fake_azure(monkeypatch, [marker, real_item])
    entries = remote_backends.list_dir(azure_conn, "")
    assert [e.name for e in entries] == ["a.csv"]


# ------------------------------------------------------------------- extra opts

def test_s3_client_passes_session_token(monkeypatch):
    conn = RemoteConnection(name="c", type="s3", options={"bucket": "b", "session_token": "TOK"})
    holder = _install_fake_boto3(monkeypatch, {"Contents": []}, {})
    remote_backends.list_dir(conn, "")
    assert holder["client"].kwargs["aws_session_token"] == "TOK"


def test_gcs_client_uses_service_account_credentials_file(monkeypatch):
    conn = RemoteConnection(name="c", type="gcs", options={"bucket": "b", "credentials_file": "/creds.json"})
    calls = {}

    class FakeClient:
        def __init__(self, project=None):
            self.project = project

        @classmethod
        def from_service_account_json(cls, path, project=None):
            calls["path"] = path
            calls["project"] = project
            return cls(project=project)

        def bucket(self, name):
            return _FakeBucket(name, {})

        def list_blobs(self, bucket, prefix="", delimiter="/"):
            return _FakeBlobIterator([], [])

    storage_mod = types.ModuleType("google.cloud.storage")
    storage_mod.Client = FakeClient
    _install_module(monkeypatch, "google.cloud.storage", storage_mod)
    remote_backends.list_dir(conn, "")
    assert calls == {"path": "/creds.json", "project": None}
