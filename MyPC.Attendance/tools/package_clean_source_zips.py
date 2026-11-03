#!/usr/bin/env python3
"""Build allowlisted changed/full source ZIPs from tracked git files only.

Fails closed if the sensitive-path scanner finds denied paths (including nested
archives). SHA256SUMS is written *after* ZIP bytes are frozen and lives beside
the archives (never inside them).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # MyPC.Attendance
REPO = ROOT.parent
TOOLS = Path(__file__).resolve().parent

# Never package these even if somehow tracked
DENY_NAME_FRAGMENTS = (
    "/data/",
    "/secrets/",
    "FIRST_RUN_ADMIN.txt",
    "master.key",
    "session.secret",
    "face_templates.key",
    ".sqlite3",
    ".env",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_tracked_under_mypc() -> list[Path]:
    out = subprocess.check_output(
        ["git", "ls-files", "-z", "MyPC.Attendance"],
        cwd=REPO,
    )
    files: list[Path] = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="surrogateescape")
        p = REPO / rel
        if not p.is_file():
            continue
        posix = rel.replace("\\", "/")
        low = posix.lower()
        if any(frag.lower() in low for frag in DENY_NAME_FRAGMENTS):
            raise SystemExit(f"REFUSING tracked sensitive path: {rel}")
        # Never nest prior release/handoff archives inside new archives
        if "/release/" in low or low.endswith("/release"):
            continue
        if low.endswith(".zip"):
            continue
        if p.suffix in {".pyc", ".onnx"}:
            continue
        files.append(p)
    return sorted(files)


def changed_paths_since(base_ref: str) -> set[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD", "--", "MyPC.Attendance"],
        cwd=REPO,
        text=True,
    )
    return {line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()}


def write_zip(path: Path, files: list[Path], *, full_prefix: bool) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            rel = f.relative_to(REPO).as_posix()
            arc = rel if full_prefix else f.relative_to(ROOT).as_posix()
            if full_prefix:
                arc = rel  # MyPC.Attendance/...
            zf.write(f, arc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True, help="Artifact tag, e.g. PR13-RELSAFE-<sha12>")
    parser.add_argument(
        "--base-ref",
        default="",
        help="Optional git ref for CHANGED zip (diff base...HEAD)",
    )
    parser.add_argument(
        "--include-handoff-text",
        action="store_true",
        help="Include audit/handoffs text (still skips .zip binaries)",
    )
    args = parser.parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    tracked = git_tracked_under_mypc()
    if not args.include_handoff_text:
        tracked = [
            p
            for p in tracked
            if "/audit/handoffs/" not in p.relative_to(REPO).as_posix().replace("\\", "/")
        ]

    # FULL = all allowlisted tracked source
    full_name = f"MyPC.Attendance-FULL-{args.tag}.zip"
    full_path = out_dir / full_name
    write_zip(full_path, tracked, full_prefix=True)

    # CHANGED = diff vs base, else all tracked under backend/tests/tools/scripts/frontend src
    if args.base_ref:
        changed_set = changed_paths_since(args.base_ref)
        changed_files = [
            p
            for p in tracked
            if p.relative_to(REPO).as_posix().replace("\\", "/") in changed_set
        ]
    else:
        changed_files = tracked
    changed_name = f"MyPC.Attendance-CHANGED-{args.tag}.zip"
    changed_path = out_dir / changed_name
    write_zip(changed_path, changed_files, full_prefix=True)

    # Fail-closed scanner
    sys.path.insert(0, str(TOOLS))
    from sensitive_path_scanner import scan_zip_file

    for label, zp in ("FULL", full_path), ("CHANGED", changed_path):
        denied = scan_zip_file(zp)
        if denied:
            print(f"BLOCK {label}: {len(denied)} sensitive paths")
            for d in denied[:40]:
                print(" ", d)
            full_path.unlink(missing_ok=True)
            changed_path.unlink(missing_ok=True)
            return 2

    sums = {
        changed_name: sha256_file(changed_path),
        full_name: sha256_file(full_path),
    }
    sums_path = out_dir / "SHA256SUMS.txt"
    sums_path.write_text(
        "\n".join(f"{digest}  {name}" for name, digest in sums.items()) + "\n",
        encoding="utf-8",
    )
    meta = {
        "tag": args.tag,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "full_entries": len(tracked),
        "changed_entries": len(changed_files),
        "sha256": sums,
        "note": "SHA256SUMS written after ZIP freeze; not embedded inside archives.",
    }
    (out_dir / "PACKAGE_META.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
