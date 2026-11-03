"""Fail-closed sensitive content / path scanner for release ZIPs (PR16-HF2).

Does not log matched secret values — only path + rule id.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

DENY_PATH = re.compile(
    r"(^|/)"
    r"(data/|secrets/|\.git/)"
    r"|FIRST_RUN_ADMIN"
    r"|\.sqlite3(-wal|-shm)?$"
    r"|master\.key$|session\.secret$|face_templates\.key$"
    r"|(^|/)\.env(\.|$)"
    r"|embeddings?/"
    r"|employee[_-]?photo"
    r"|\.onnx$",
    re.I,
)

# Content rules — high confidence only. Matched value never printed.
CONTENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "GENERIC_PASSWORD_ASSIGN",
        re.compile(
            r"(?i)(password|passwd|pwd|secret_key|api_key|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"
        ),
    ),
    ("SQLITE_HEADER", re.compile(rb"^SQLite format 3\x00")),
]

# Exact relative paths allowed to contain synthetic fixture markers (tests only).
ALLOWLIST_EXACT = {
    "MyPC.Attendance/tests/fixtures/release_scan/synthetic_secret_fixture.txt",
    "MyPC.Attendance/tests/unit/test_pr16_hf2_release_scanner.py",
}

# Path prefixes where GENERIC_PASSWORD_ASSIGN is permitted (unit/integration fixtures).
# PRIVATE_KEY / AWS / SQLITE / DENY_PATH still fail closed everywhere.
ALLOW_GENERIC_PASSWORD_PREFIXES = (
    "MyPC.Attendance/tests/",
)


class ScanFailure(Exception):
    def __init__(self, rule: str, path: str):
        self.rule = rule
        self.path = path
        super().__init__(f"SCAN_FAIL rule={rule} path={path}")


def _scan_bytes(name: str, data: bytes, *, allow_fixture: bool) -> None:
    norm = name.replace("\\", "/")
    if DENY_PATH.search(norm):
        raise ScanFailure("DENY_PATH", name)
    # binary sqlite header
    if data.startswith(b"SQLite format 3\x00"):
        raise ScanFailure("SQLITE_HEADER", name)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="ignore")
    for rule_id, pat in CONTENT_RULES:
        if rule_id == "SQLITE_HEADER":
            continue
        if isinstance(pat.pattern, (bytes, bytearray)):
            continue
        if not pat.search(text or ""):
            continue
        if allow_fixture and norm in ALLOWLIST_EXACT:
            continue
        if rule_id == "GENERIC_PASSWORD_ASSIGN" and any(
            norm.startswith(p) for p in ALLOW_GENERIC_PASSWORD_PREFIXES
        ):
            continue
        # Non-test path with password assign / key material → fail closed
        raise ScanFailure(rule_id, name)


def scan_zip_bytes(raw: bytes, *, outer_name: str = "zip") -> None:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        bad = z.testzip()
        if bad:
            raise ScanFailure("CRC", f"{outer_name}:{bad}")
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            data = z.read(info)
            allow = name in ALLOWLIST_EXACT
            _scan_bytes(name, data, allow_fixture=allow)
            if name.lower().endswith(".zip"):
                # nested — recursive; fixtures inside nested still fail unless allowlisted path
                try:
                    scan_zip_bytes(data, outer_name=f"{outer_name}:{name}")
                except ScanFailure:
                    raise


def scan_zip_path(path: Path) -> None:
    scan_zip_bytes(path.read_bytes(), outer_name=path.name)


def would_fail_on_member(name: str, data: bytes) -> str | None:
    try:
        _scan_bytes(name, data, allow_fixture=False)
    except ScanFailure as exc:
        return exc.rule
    return None
