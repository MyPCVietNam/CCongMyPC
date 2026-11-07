#!/usr/bin/env python3
"""Read-only cryptographic inspection of a MyPC audit ZIP (including nested ZIPs).

Usage: python quality_guard/scripts/verify_handoff.py complete.zip
No extraction, network, camera, secrets or mutation. Output counters and failures only.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import posixpath
import re
import zipfile
from pathlib import Path

MAX_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 20000
SHA_LINE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$")
FORBIDDEN_SUFFIXES = (".sqlite", ".sqlite3", ".db", ".onnx", ".pfx", ".pem", ".mp4", ".avi", ".mkv")


def validate_path(name: str) -> None:
    text = name.replace("\\", "/")
    if not name or text.startswith("/") or re.match(r"^[a-zA-Z]:", text):
        raise ValueError("ZIP_PATH_NOT_RELATIVE")
    if any(x in ("..", "") for x in text.split("/")[:-1]):
        raise ValueError("ZIP_PATH_TRAVERSAL")
    if ".." in text.split("/"):
        raise ValueError("ZIP_PATH_TRAVERSAL")
    if "\x00" in name:
        raise ValueError("ZIP_NUL_PATH")
    base = text.lower()
    if (base.endswith(FORBIDDEN_SUFFIXES) or
        re.search(r"(^|/)(?:\.env(?:\..*)?|secrets?\.db|first_run_admin\.txt)(?:/|$)", base)):
        raise ValueError("SENSITIVE_FILE_PATH_PRESENT")


def inspect_zip(blob: bytes, depth: int = 0) -> dict:
    if depth > 2:
        raise ValueError("ZIP_NESTING_TOO_DEEP")
    if len(blob) > MAX_BYTES:
        raise ValueError("ZIP_TOO_LARGE")
    z = zipfile.ZipFile(io.BytesIO(blob))
    infos = z.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ValueError("ZIP_TOO_MANY_ENTRIES")
    if sum(i.file_size for i in infos) > MAX_BYTES:
        raise ValueError("ZIP_UNCOMPRESSED_LIMIT")
    seen = set()
    for i in infos:
        validate_path(i.filename)
        key = i.filename.lower().replace("\\", "/")
        if key in seen:
            raise ValueError("ZIP_DUPLICATE_CASE_INSENSITIVE_PATH")
        seen.add(key)
        if i.file_size > MAX_BYTES:
            raise ValueError("ZIP_SINGLE_FILE_TOO_LARGE")
    if z.testzip() is not None:
        raise ValueError("ZIP_CRC_MISMATCH")
    names = set(z.namelist())
    manifest = {}
    if "SHA256SUMS.txt" in names:
        for line in z.read("SHA256SUMS.txt").decode("utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = SHA_LINE.match(line)
            if not match:
                raise ValueError("SHA256SUMS_FORMAT_INVALID")
            expect, path = match.groups()
            if path not in names:
                raise ValueError("SHA256SUMS_ENTRY_MISSING")
            digest = hashlib.sha256(z.read(path)).hexdigest()
            if digest.lower() != expect.lower():
                raise ValueError("SHA256SUMS_MISMATCH")
            manifest[path] = digest
    nested = []
    for name in names:
        if name.lower().endswith(".zip"):
            nested.append({"name": name, **inspect_zip(z.read(name), depth=depth + 1)})
    return {"entries": len(infos), "manifest_entries": len(manifest),
            "nested": nested, "zip_crc_pass": True}


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("zip_file", type=Path)
    args = a.parse_args()
    try:
        data = args.zip_file.read_bytes()
        result = inspect_zip(data)
        print(json.dumps({"result": "PASS", "zip_sha256": hashlib.sha256(data).hexdigest(), **result}, indent=2))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeDecodeError) as e:
        print(json.dumps({"result": "BLOCKED", "error_code": str(e)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
