"""Unit tests for panels/remote_sources.py — remote.ini parsing and local
drive/mount enumeration."""
from __future__ import annotations

import platform

import pytest

from panels import remote_sources


# --------------------------------------------------------------- find_config

def test_find_config_absent(chdir_tmp):
    assert remote_sources.find_config() is None


def test_find_config_present(chdir_tmp):
    (chdir_tmp / "remote.ini").write_text("[x]\ntype = s3\n", encoding="utf-8")
    assert remote_sources.find_config() == chdir_tmp / "remote.ini"


# ----------------------------------------------------------- list_connections

def test_list_connections_no_file_returns_empty(chdir_tmp):
    assert remote_sources.list_connections() == []


def test_list_connections_parses_sections(chdir_tmp):
    (chdir_tmp / "remote.ini").write_text(
        "[myserver]\n"
        "type = sftp\n"
        "host = example.com\n"
        "username = bob\n"
        "\n"
        "[bucket1]\n"
        "type = s3\n"
        "bucket = my-bucket\n",
        encoding="utf-8",
    )
    conns = remote_sources.list_connections()
    assert [c.name for c in conns] == ["myserver", "bucket1"]
    assert conns[0].type == "sftp"
    assert conns[0].options["host"] == "example.com"
    assert conns[1].type == "s3"
    assert conns[1].options["bucket"] == "my-bucket"


def test_list_connections_skips_unknown_type(chdir_tmp):
    (chdir_tmp / "remote.ini").write_text(
        "[weird]\ntype = ftp\nhost = x\n\n[good]\ntype = gcs\nbucket = b\n",
        encoding="utf-8",
    )
    conns = remote_sources.list_connections()
    assert [c.name for c in conns] == ["good"]


def test_list_connections_skips_section_with_missing_type(chdir_tmp):
    (chdir_tmp / "remote.ini").write_text("[nosuchtype]\nhost = x\n", encoding="utf-8")
    assert remote_sources.list_connections() == []


def test_list_connections_type_matching_is_case_insensitive(chdir_tmp):
    (chdir_tmp / "remote.ini").write_text("[x]\ntype = S3\nbucket = b\n", encoding="utf-8")
    conns = remote_sources.list_connections()
    assert conns[0].type == "s3"


def test_list_connections_malformed_ini_returns_empty(chdir_tmp):
    (chdir_tmp / "remote.ini").write_text("not [a valid ini{{{", encoding="utf-8")
    assert remote_sources.list_connections() == []


# --------------------------------------------------------------- local drives

def test_list_local_drives_returns_list():
    drives = remote_sources.list_local_drives()
    assert isinstance(drives, list)
    if platform.system() == "Windows":
        assert all(d.endswith(":\\") for d in drives)
    else:
        assert "/" in drives


def test_list_local_drives_windows_only_existing_letters(monkeypatch):
    monkeypatch.setattr(remote_sources.platform, "system", lambda: "Windows")
    existing = {"C:\\"}
    monkeypatch.setattr(remote_sources.Path, "exists", lambda self: str(self) in existing)
    drives = remote_sources.list_local_drives()
    assert drives == ["C:\\"]


def test_list_local_drives_linux_always_includes_root(monkeypatch, tmp_path):
    import builtins

    monkeypatch.setattr(remote_sources.platform, "system", lambda: "Linux")

    fake_mounts = tmp_path / "mounts"
    fake_mounts.write_text(
        "proc /proc proc rw 0 0\n"
        "/dev/sda1 /data ext4 rw 0 0\n"
        "tmpfs /tmp tmpfs rw 0 0\n",
        encoding="utf-8",
    )
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if path == "/proc/mounts":
            return real_open(fake_mounts, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    drives = remote_sources.list_local_drives()
    assert drives[0] == "/"
    assert "/data" in drives
    assert "/proc" not in drives
    assert "/tmp" not in drives


def test_list_local_drives_linux_skips_malformed_mount_lines(monkeypatch, tmp_path):
    import builtins

    monkeypatch.setattr(remote_sources.platform, "system", lambda: "Linux")
    fake_mounts = tmp_path / "mounts"
    fake_mounts.write_text(
        "malformed-line-with-no-fields\n"
        "/dev/sda1 /data ext4 rw 0 0\n",
        encoding="utf-8",
    )
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if path == "/proc/mounts":
            return real_open(fake_mounts, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    drives = remote_sources.list_local_drives()
    assert drives == ["/", "/data"]


def test_list_local_drives_linux_no_proc_mounts_still_has_root(monkeypatch):
    import builtins

    monkeypatch.setattr(remote_sources.platform, "system", lambda: "Linux")

    def raise_oserror(path, *args, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(builtins, "open", raise_oserror)
    assert remote_sources.list_local_drives() == ["/"]
