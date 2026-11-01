#!/usr/bin/env python3
"""Build Pxx changed-source audit ZIP + SHA256 manifests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
PHASE = "P00"


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
    ignore_dirs = {
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "release",
        "data",
        "secrets",
        ".git",
    }
    ignore_suffixes = {".pyc", ".sqlite3", ".log"}
    files: list[Path] = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        parts = set(p.relative_to(ROOT).parts)
        if parts & ignore_dirs:
            continue
        if any(part in ignore_dirs for part in p.relative_to(ROOT).parts):
            continue
        if p.suffix in ignore_suffixes:
            continue
        if p.name == "FIRST_RUN_ADMIN.txt":
            continue
        # skip large built assets? include static build for audit of UI
        files.append(p)
    return sorted(files)


def main() -> None:
    RELEASE.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    changed_name = f"MYPC-ATTENDANCE-{PHASE}-CHANGED-SOURCE-AUDIT-{day}.zip"
    full_name = f"MYPC-ATTENDANCE-{PHASE}-FULL-SOURCE-{day}.zip"
    changed_path = RELEASE / changed_name
    full_path = RELEASE / full_name

    files = collect_files()
    manifest = []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        digest = sha256_file(f)
        manifest.append(
            {
                "path": rel,
                "change_type": "added",
                "sha256": digest,
                "bytes": f.stat().st_size,
            }
        )

    # Changed-source ZIP (P00 = all project files under MyPC.Attendance)
    with zipfile.ZipFile(changed_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.relative_to(ROOT).as_posix())
        zf.writestr(
            "AUDIT/changed-files-manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )
        zf.writestr("AUDIT/deletion-manifest.json", json.dumps([], indent=2))
        zf.writestr(
            "AUDIT/meta.json",
            json.dumps(
                {
                    "phase": PHASE,
                    "spec_version": "1.5",
                    "commit": git_commit(),
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "file_count": len(files),
                },
                indent=2,
            ),
        )

    # Full-source ZIP identical content for P00 checkpoint
    with zipfile.ZipFile(full_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f"MyPC.Attendance/{f.relative_to(ROOT).as_posix()}")

    sums = {
        changed_name: sha256_file(changed_path),
        full_name: sha256_file(full_path),
    }
    (RELEASE / f"SHA256SUMS-{PHASE}-{day}.txt").write_text(
        "\n".join(f"{digest}  {name}" for name, digest in sums.items()) + "\n",
        encoding="utf-8",
    )
    (RELEASE / f"manifest-{PHASE}-{day}.json").write_text(
        json.dumps({"phase": PHASE, "artifacts": sums, "files": len(files)}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"changed": str(changed_path), "full": str(full_path), "sha256": sums}, indent=2))


if __name__ == "__main__":
    main()
