#!/usr/bin/env python3
"""Build PR16-HF3 four delivery ZIPs + outer COMPLETE-AUDIT (fail-closed scan)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "MyPC.Attendance"
HANDOFF = ROOT / "audit" / "handoffs" / "PR16-HF3-HMAC-TRUST-20261103"
BASELINE = "1fa4a1c47196089a61da9ad91d524e7e2e56b80f"

sys.path.insert(0, str(ROOT))
from tools.release_sensitive_scan import ScanFailure, scan_zip_path  # noqa: E402


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


def git_diff_names(base: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}...HEAD", "--", "MyPC.Attendance"],
        cwd=REPO,
        text=True,
    )
    return [ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()]


def git_ls_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z", "MyPC.Attendance"], cwd=REPO)
    files = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode()
        low = rel.lower().replace("\\", "/")
        if low.endswith(".zip") or "/release/" in low or low.endswith(".onnx") or low.endswith(".pyc"):
            continue
        if "/data/" in low or "/secrets/" in low or low.endswith(".sqlite3"):
            raise SystemExit(f"REFUSE tracked sensitive: {rel}")
        files.append(rel)
    return sorted(files)


def write_zip(path: Path, members: list[tuple[str, Path]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in members:
            z.writestr(arc, src.read_bytes())
        bad = z.testzip()
        if bad:
            raise SystemExit(f"CRC fail: {bad}")


def main() -> int:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    HANDOFF.mkdir(parents=True, exist_ok=True)
    changed = [p for p in git_diff_names(BASELINE) if not p.lower().endswith(".zip")]
    code_paths = [p for p in changed if "/audit/handoffs/" not in p]
    handoff_paths = [p for p in changed if "/audit/handoffs/" in p]

    a_members = [(rel, REPO / rel) for rel in changed if (REPO / rel).is_file()]
    a_zip = HANDOFF / "CHANGED-SOURCE-AUDIT.zip"
    write_zip(a_zip, a_members)

    b_members = [(rel, REPO / rel) for rel in git_ls_files() if (REPO / rel).is_file()]
    b_zip = HANDOFF / "FULL-SOURCE.zip"
    write_zip(b_zip, b_members)

    with zipfile.ZipFile(a_zip) as za, zipfile.ZipFile(b_zip) as zb:
        for name in za.namelist():
            if "/audit/handoffs/" in name:
                continue
            if name not in zb.namelist():
                raise SystemExit(f"CHANGED missing from FULL: {name}")
            if za.read(name) != zb.read(name):
                raise SystemExit(f"BYTE MISMATCH: {name}")

    evid_dir = HANDOFF / "_evidence_stage"
    if evid_dir.exists():
        import shutil

        shutil.rmtree(evid_dir)
    evid_dir.mkdir()
    for name in [
        "BASELINE_RCA.md",
        "CHANGELOG.md",
        "ACCEPTANCE_MATRIX.md",
        "OWNER_WINDOWS_STEPS_VI.md",
        "FREEZE_VS_TIP_TIMELINE.md",
        "TEST_REPORT.txt",
        "FRONTEND_BUILD_REPORT.txt",
        "VERSIONS.txt",
        "CODE_PATHS.txt",
        "HANDOFF_PATHS.txt",
        "CHANGED_PATHS.txt",
        "BASELINE_COMMIT.txt",
        "FEATURE_COMMIT.txt",
        "PACKAGING_FREEZE_COMMIT.txt",
        "REMOTE_PR_TIP.txt",
        "FINAL_HEAD.txt",
        "COMMIT_GRAPH.txt",
    ]:
        p = HANDOFF / name
        if p.exists():
            (evid_dir / name).write_bytes(p.read_bytes())
    c_zip = HANDOFF / "WINDOWS-SAFE-EVIDENCE.zip"
    write_zip(
        c_zip,
        [
            (f"PR16-HF3-WINDOWS-SAFE-EVIDENCE/{p.name}", p)
            for p in sorted(evid_dir.iterdir())
            if p.is_file()
        ],
    )

    for zpath in (a_zip, b_zip, c_zip):
        try:
            scan_zip_path(zpath)
        except ScanFailure as exc:
            raise SystemExit(f"SCAN BLOCKED {zpath.name}: {exc}") from exc

    sums = {a_zip.name: sha256(a_zip), b_zip.name: sha256(b_zip), c_zip.name: sha256(c_zip)}
    (HANDOFF / "SHA256SUMS.txt").write_text(
        "".join(f"{h}  {n}\n" for n, h in sums.items()), encoding="utf-8"
    )
    feature = (
        (HANDOFF / "FEATURE_COMMIT.txt").read_text().strip()
        if (HANDOFF / "FEATURE_COMMIT.txt").exists()
        else head
    )
    meta = {
        "schema": "mypc.package-meta.v2",
        "baseline": BASELINE,
        "feature_commit": feature,
        "packaging_freeze_commit": head,
        "remote_pr_tip": None,
        "remote_pr_tip_note": (
            "Null until post-push sidecar. packaging_freeze_commit is the ZIP byte freeze; "
            "never equal to COMPLETE self-hash. See FREEZE_VS_TIP_TIMELINE.md."
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_paths": code_paths,
        "handoff_paths": handoff_paths,
        "sha256": sums,
        "gates_blocked": [
            "LIVE_STABILITY_PASS",
            "FACE_PILOT",
            "INSTALLER",
            "PRODUCTION_ATTENDANCE",
            "WINDOWS_PHYSICAL_SOAK",
            "HEVC_NATIVE_RCA",
        ],
    }
    (HANDOFF / "PACKAGE_META.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (HANDOFF / "PACKAGING_FREEZE_COMMIT.txt").write_text(head + "\n", encoding="utf-8")

    outer = HANDOFF / "MYPC-PR16-HF3-COMPLETE-AUDIT.zip"
    outer_members = [
        ("SHA256SUMS.txt", HANDOFF / "SHA256SUMS.txt"),
        ("PACKAGE_META.json", HANDOFF / "PACKAGE_META.json"),
        ("README.md", HANDOFF / "README.md"),
        ("CHANGELOG.md", HANDOFF / "CHANGELOG.md"),
        ("ACCEPTANCE_MATRIX.md", HANDOFF / "ACCEPTANCE_MATRIX.md"),
        ("BASELINE_RCA.md", HANDOFF / "BASELINE_RCA.md"),
        ("OWNER_WINDOWS_STEPS_VI.md", HANDOFF / "OWNER_WINDOWS_STEPS_VI.md"),
        ("FREEZE_VS_TIP_TIMELINE.md", HANDOFF / "FREEZE_VS_TIP_TIMELINE.md"),
        ("TEST_REPORT.txt", HANDOFF / "TEST_REPORT.txt"),
        ("FRONTEND_BUILD_REPORT.txt", HANDOFF / "FRONTEND_BUILD_REPORT.txt"),
        ("VERSIONS.txt", HANDOFF / "VERSIONS.txt"),
        ("CODE_PATHS.txt", HANDOFF / "CODE_PATHS.txt"),
        ("HANDOFF_PATHS.txt", HANDOFF / "HANDOFF_PATHS.txt"),
        ("CHANGED_PATHS.txt", HANDOFF / "CHANGED_PATHS.txt"),
        ("BASELINE_COMMIT.txt", HANDOFF / "BASELINE_COMMIT.txt"),
        ("FEATURE_COMMIT.txt", HANDOFF / "FEATURE_COMMIT.txt"),
        ("PACKAGING_FREEZE_COMMIT.txt", HANDOFF / "PACKAGING_FREEZE_COMMIT.txt"),
        ("REMOTE_PR_TIP.txt", HANDOFF / "REMOTE_PR_TIP.txt"),
        ("FINAL_HEAD.txt", HANDOFF / "FINAL_HEAD.txt"),
        ("COMMIT_GRAPH.txt", HANDOFF / "COMMIT_GRAPH.txt"),
        ("CHANGED-SOURCE-AUDIT.zip", a_zip),
        ("FULL-SOURCE.zip", b_zip),
        ("WINDOWS-SAFE-EVIDENCE.zip", c_zip),
    ]
    write_zip(outer, [(n, p) for n, p in outer_members if p.exists()])
    try:
        scan_zip_path(outer)
    except ScanFailure as exc:
        raise SystemExit(f"SCAN BLOCKED outer: {exc}") from exc
    outer_hash = sha256(outer)
    (HANDOFF / "SHA256SUMS-COMPLETE.txt").write_text(
        (HANDOFF / "SHA256SUMS.txt").read_text() + f"{outer_hash}  {outer.name}\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "outer": outer_hash,
                "outer_bytes": outer.stat().st_size,
                "inner": sums,
                "packaging_freeze": head,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
