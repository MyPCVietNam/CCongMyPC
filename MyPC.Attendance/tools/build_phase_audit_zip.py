#!/usr/bin/env python3
"""Build phase audit ZIPs + SHA256 manifests (allowlisted + fail-closed scanner)."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
TOOLS = Path(__file__).resolve().parent

IGNORE_DIRS = {
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "release",
    "data",
    "secrets",
    ".git",
    "weights",  # onnx weights stay out of audit source zips
}
IGNORE_SUFFIXES = {".pyc", ".sqlite3", ".log", ".onnx", ".zip"}
DENY_BASENAMES = {
    "FIRST_RUN_ADMIN.txt",
    "master.key",
    "session.secret",
    "face_templates.key",
    ".env",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT.parent, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def collect_files() -> list[Path]:
    """Prefer git-tracked files; fall back to filtered walk."""
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "-z", "MyPC.Attendance"],
            cwd=ROOT.parent,
        )
        files: list[Path] = []
        for raw in out.split(b"\0"):
            if not raw:
                continue
            rel = raw.decode("utf-8", errors="surrogateescape")
            p = ROOT.parent / rel
            if not p.is_file():
                continue
            try:
                rel_parts = p.relative_to(ROOT).parts
            except ValueError:
                continue
            if any(part in IGNORE_DIRS for part in rel_parts):
                continue
            if p.suffix in IGNORE_SUFFIXES:
                continue
            if p.name in DENY_BASENAMES:
                continue
            files.append(p)
        return sorted(files)
    except Exception:
        pass

    files = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(ROOT).parts
        if any(part in IGNORE_DIRS for part in rel_parts):
            continue
        if p.suffix in IGNORE_SUFFIXES:
            continue
        if p.name in DENY_BASENAMES:
            continue
        files.append(p)
    return sorted(files)


def write_zip(path: Path, files: list[Path], prefix: str = "") -> list[dict]:
    manifest = []
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            rel = f.relative_to(ROOT).as_posix()
            arc = f"{prefix}{rel}" if prefix else rel
            zf.write(f, arc)
            manifest.append(
                {
                    "path": rel,
                    "change_type": "added_or_modified",
                    "sha256": sha256_file(f),
                    "bytes": f.stat().st_size,
                }
            )
        zf.writestr(
            "AUDIT/changed-files-manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )
        zf.writestr("AUDIT/deletion-manifest.json", json.dumps([], indent=2))
        zf.writestr(
            "AUDIT/meta.json",
            json.dumps(
                {
                    "commit": git_commit(),
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "file_count": len(files),
                    "spec_version": "1.5",
                },
                indent=2,
            ),
        )
    return manifest


def _scan_or_die(path: Path) -> None:
    sys.path.insert(0, str(TOOLS))
    from sensitive_path_scanner import scan_zip_file

    denied = scan_zip_file(path)
    if denied:
        print(f"BLOCK: sensitive paths in {path.name}: {len(denied)}")
        for d in denied[:40]:
            print(" ", d)
        path.unlink(missing_ok=True)
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="P00-HF-P01")
    args = parser.parse_args()
    RELEASE.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    files = collect_files()

    changed = RELEASE / f"MYPC-ATTENDANCE-{args.phase}-CHANGED-SOURCE-AUDIT-{day}.zip"
    hf = RELEASE / f"MYPC-ATTENDANCE-P00-HF-CHANGED-SOURCE-AUDIT-{day}.zip"
    p01 = RELEASE / f"MYPC-ATTENDANCE-P01-CHANGED-SOURCE-AUDIT-{day}.zip"
    full = RELEASE / f"MYPC-ATTENDANCE-P01-FULL-SOURCE-{day}.zip"

    write_zip(changed, files)
    write_zip(hf, files)
    write_zip(p01, files)
    with zipfile.ZipFile(full, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f"MyPC.Attendance/{f.relative_to(ROOT).as_posix()}")

    for zp in (changed, hf, p01, full):
        _scan_or_die(zp)

    sums = {p.name: sha256_file(p) for p in (changed, hf, p01, full)}
    sums_path = RELEASE / f"SHA256SUMS-P00-HF-P01-{day}.txt"
    sums_path.write_text(
        "\n".join(f"{digest}  {name}" for name, digest in sums.items()) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"artifacts": {k: str(RELEASE / k) for k in sums}, "sha256": sums}, indent=2))


if __name__ == "__main__":
    main()
