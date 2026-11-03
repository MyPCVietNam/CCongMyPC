#!/usr/bin/env python3
"""Fail-closed sensitive-path scanner for trees and ZIP archives.

Inspects paths / ZIP entry names only — never reads, prints, or extracts secret
file contents. Exit 0 = clean, exit 2 = blocked, exit 1 = usage/invalid.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

DENY_BASENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "master.key",
    "session.secret",
    "face_templates.key",
    "first_run_admin.txt",
}
DENY_PARTS = {
    "data",
    "secrets",
    ".venv",
    "node_modules",
    ".git",
    "__pycache__",
}
DENY_SUFFIXES = (
    ".sqlite3",
    ".sqlite3-wal",
    ".sqlite3-shm",
    ".db",
    ".db-wal",
    ".db-shm",
    ".pem",
    ".pfx",
    ".p12",
)
# Nested archives are scanned recursively (names + nested zip members).
NESTED_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2")


def forbidden_path(name: str) -> bool:
    n = name.replace("\\", "/").lstrip("./")
    parts = [p.lower() for p in PurePosixPath(n).parts if p not in {"", "."}]
    if not parts:
        return False
    last = parts[-1]
    if any(p in DENY_PARTS for p in parts):
        return True
    if last in DENY_BASENAMES:
        return True
    if last.endswith(DENY_SUFFIXES):
        return True
    if re.search(r"(?:^|/)(?:id_rsa|id_ed25519)(?:\.pub)?$", last) is not None:
        return True
    return False


def scan_zip_bytes(data: bytes, *, prefix: str = "") -> list[str]:
    denied: list[str] = []
    try:
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = f"{prefix}{info.filename}" if prefix else info.filename
                if forbidden_path(info.filename) or forbidden_path(name):
                    denied.append(name)
                    continue
                lower = info.filename.lower()
                if lower.endswith(".zip") and info.file_size < 80_000_000:
                    try:
                        nested = zf.read(info)
                        denied.extend(
                            scan_zip_bytes(nested, prefix=f"{name}!")
                        )
                    except (OSError, zipfile.BadZipFile, RuntimeError):
                        denied.append(f"{name}!(unreadable-nested-zip)")
    except (OSError, zipfile.BadZipFile) as exc:
        denied.append(f"{prefix or '<zip>'}!(invalid:{type(exc).__name__})")
    return denied


def scan_zip_file(path: Path) -> list[str]:
    denied: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if forbidden_path(info.filename):
                    denied.append(info.filename)
                    continue
                lower = info.filename.lower()
                if lower.endswith(".zip") and info.file_size < 80_000_000:
                    try:
                        nested = zf.read(info)
                        denied.extend(
                            scan_zip_bytes(nested, prefix=f"{info.filename}!")
                        )
                    except (OSError, zipfile.BadZipFile, RuntimeError):
                        denied.append(f"{info.filename}!(unreadable-nested-zip)")
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"<zip>!(invalid:{type(exc).__name__})"]
    return denied


def scan_tree(root: Path) -> list[str]:
    denied: list[str] = []
    if not root.exists():
        return [f"{root}!(missing)"]
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if forbidden_path(rel) or forbidden_path(p.name):
            denied.append(rel)
            continue
        if p.suffix.lower() == ".zip" and p.stat().st_size < 80_000_000:
            nested = scan_zip_file(p)
            denied.extend(f"{rel}!{n}" for n in nested)
    return denied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", help="Files, directories, or ZIP paths")
    args = parser.parse_args(argv)
    all_denied: list[str] = []
    for raw in args.targets:
        path = Path(raw)
        if path.is_dir():
            found = scan_tree(path)
            label = str(path)
        elif path.suffix.lower() == ".zip" and path.is_file():
            found = scan_zip_file(path)
            label = str(path)
        elif path.is_file():
            found = [path.name] if forbidden_path(path.name) else []
            label = str(path)
        else:
            print(f"MISSING: {path}")
            return 1
        if found:
            print(f"BLOCK: {label}: {len(found)} sensitive path(s)")
            for x in found[:80]:
                print(f"  {x}")
            if len(found) > 80:
                print(f"  ... and {len(found) - 80} more")
            all_denied.extend(found)
        else:
            print(f"PASS: {label}")
    if all_denied:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
