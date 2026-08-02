from __future__ import annotations

import configparser
import platform
import string
from dataclasses import dataclass, field
from pathlib import Path

# ------------------------------------------------------------- configuration
# Remote storage targets for CHNG DRV live in remote.ini in the current
# working directory. Each section is a named connection with a `type` of
# sftp / s3 / gcs / azure, plus the credentials/options that backend needs.
# See remote.ini in the project root for a documented example of each.
CONFIG_FILENAME = "remote.ini"

BACKEND_TYPES = ("sftp", "s3", "gcs", "azure")


class RemoteConfigError(Exception):
    """Raised when a remote connection is missing, misconfigured, or unreachable."""


@dataclass
class RemoteConnection:
    """A named [section] from remote.ini."""

    name: str
    type: str
    options: dict[str, str] = field(default_factory=dict)


@dataclass
class RemoteEntry:
    """One directory/file entry returned by a remote backend listing."""

    name: str
    is_dir: bool
    size: int = 0


def find_config() -> Path | None:
    candidate = Path.cwd() / CONFIG_FILENAME
    return candidate if candidate.is_file() else None


def list_connections() -> list[RemoteConnection]:
    """Parse remote.ini and return the configured remote connections.

    Sections with an unrecognized or missing `type` are silently skipped
    so the popup only ever offers connections it knows how to browse.
    """
    config_path = find_config()
    if config_path is None:
        return []

    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except configparser.Error:
        return []

    connections: list[RemoteConnection] = []
    for section in parser.sections():
        options = dict(parser[section])
        rtype = options.get("type", "").strip().lower()
        if rtype not in BACKEND_TYPES:
            continue
        connections.append(RemoteConnection(name=section, type=rtype, options=options))
    return connections


# ------------------------------------------------------------- local drives
# Real, user-relevant filesystem types — used to filter out the dozens of
# virtual/pseudo mounts (proc, sysfs, cgroup, overlay, tmpfs, ...) that show
# up in /proc/mounts on Linux/WSL.
_REAL_FSTYPES = {
    "ext4", "ext3", "ext2", "xfs", "btrfs", "ntfs", "ntfs3", "vfat", "exfat",
    "fat", "fat32", "hfs", "hfsplus", "apfs", "zfs", "drvfs", "fuseblk",
    "iso9660", "udf",
}


def list_local_drives() -> list[str]:
    """Return local mount points / drive letters to offer under 'Local:'."""
    if platform.system() == "Windows":
        drives = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if Path(root).exists():
                drives.append(root)
        return drives

    drives = ["/"]
    seen = {"/"}
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mountpoint, fstype = parts[1], parts[2]
                if fstype not in _REAL_FSTYPES or mountpoint in seen:
                    continue
                drives.append(mountpoint)
                seen.add(mountpoint)
    except OSError:
        pass
    return drives
