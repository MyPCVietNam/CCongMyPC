#!/usr/bin/env python3
"""Static Windows PowerShell 5.1 safety checks for Repair-MyPCSecretsAcl.ps1.

Cloud/Linux cannot execute Windows PowerShell 5.1. This script validates the
distributed file bytes that would otherwise trip VariableNotWritable ($HOME).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGETS = [
    HERE / "Repair-MyPCSecretsAcl.ps1",
    HERE / "MyPC-Secrets-ACL-Audit-Repair.ps1",
]


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    raw = path.read_bytes()
    if not raw.startswith(b"\xef\xbb\xbf"):
        errors.append("missing UTF-8 BOM")
    text = raw[3:].decode("utf-8") if raw.startswith(b"\xef\xbb\xbf") else raw.decode("utf-8")
    if re.search(r"(?i)\$home\s*=", text):
        errors.append("assigns $home (conflicts with automatic $HOME on PS 5.1)")
    if not re.search(r"(?i)\$attendanceHome\s*=", text):
        errors.append("missing $attendanceHome assignment")
    if "REPAIR-EXISTING-SECRETS" not in text:
        errors.append("missing repair confirmation token")
    if "Everyone" not in text:
        errors.append("expected Everyone removal safeguards")
    return errors


def main() -> int:
    failed = 0
    for path in TARGETS:
        errs = validate(path)
        if errs:
            failed += 1
            print(f"FAIL {path.name}: {'; '.join(errs)}")
        else:
            print(f"PASS {path.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
