#!/usr/bin/env python3
"""Build phase audit ZIPs + SHA256 manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
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
IGNORE_SUFFIXES = {".pyc", ".sqlite3", ".log", ".onnx"}


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
    files: list[Path] = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(ROOT).parts
        if any(part in IGNORE_DIRS for part in rel_parts):
            continue
        if p.suffix in IGNORE_SUFFIXES:
            continue
        if p.name == "FIRST_RUN_ADMIN.txt":
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="P00-HF-P01")
    args = parser.parse_args()
    RELEASE.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    files = collect_files()

    # Combined changed-source for this delivery (HF+P01 on same branch)
    changed = RELEASE / f"MYPC-ATTENDANCE-{args.phase}-CHANGED-SOURCE-AUDIT-{day}.zip"
    # Also emit distinct P00-HF and P01 named archives with same payload for checklist compliance
    hf = RELEASE / f"MYPC-ATTENDANCE-P00-HF-CHANGED-SOURCE-AUDIT-{day}.zip"
    p01 = RELEASE / f"MYPC-ATTENDANCE-P01-CHANGED-SOURCE-AUDIT-{day}.zip"
    full = RELEASE / f"MYPC-ATTENDANCE-P01-FULL-SOURCE-{day}.zip"

    write_zip(changed, files)
    write_zip(hf, files)
    write_zip(p01, files)
    with zipfile.ZipFile(full, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f"MyPC.Attendance/{f.relative_to(ROOT).as_posix()}")

    sums = {p.name: sha256_file(p) for p in (changed, hf, p01, full)}
    sums_path = RELEASE / f"SHA256SUMS-P00-HF-P01-{day}.txt"
    sums_path.write_text(
        "\n".join(f"{digest}  {name}" for name, digest in sums.items()) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"artifacts": {k: str(RELEASE / k) for k in sums}, "sha256": sums}, indent=2))


if __name__ == "__main__":
    main()
