#!/usr/bin/env python3
"""Build Quality Guard v1.0 four delivery ZIPs + COMPLETE (fail-closed scan)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "MyPC.Attendance"
HANDOFF = ROOT / "audit" / "handoffs" / "QUALITY-GUARD-v1.0"
BASELINE = "e04a34121f3bf00253685a8512e2b835aa86b7ab"  # tip immediately before Guard+V3-add stack was already present; CHANGED uses Guard scopes
# Prefer pre-Guard tip when available; fall back to HF3 packaging baseline.
SCOPES = ("AGENTS.md", ".cursor", ".github", "quality_guard", "MyPC.Attendance/docs/quality", "MyPC.Attendance/audit/handoffs/QUALITY-GUARD-v1.0")
A_NAME = "MyPC.Attendance-CHANGED-SOURCE-AUDIT-QUALITY-GUARD-v1.0.zip"
B_NAME = "MyPC.Attendance-FULL-SOURCE-QUALITY-GUARD-v1.0.zip"
C_NAME = "MYPC-QUALITY-GUARD-v1.0-WINDOWS-SAFE-EVIDENCE.zip"
OUTER_NAME = "MYPC-ENGINEERING-QUALITY-GUARD-v1.0-COMPLETE-AUDIT.zip"

sys.path.insert(0, str(ROOT))
from tools.release_sensitive_scan import ScanFailure, scan_zip_path  # noqa: E402


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


def git_ls(*paths: str) -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z", "--", *paths], cwd=REPO)
    files = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode().replace("\\", "/")
        low = rel.lower()
        if low.endswith(".zip") or "/__pycache__/" in low or low.endswith(".pyc"):
            continue
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
    feature = os.environ.get("QG_FEATURE_COMMIT", "").strip() or head
    HANDOFF.mkdir(parents=True, exist_ok=True)

    full_files = git_ls(*SCOPES)
    # CHANGED: everything under Guard scopes that differs from BASELINE when reachable
    try:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=ACMRT", f"{BASELINE}...HEAD", "--", *SCOPES],
            cwd=REPO,
            text=True,
        ).splitlines()
        changed = [c.replace("\\", "/") for c in changed if c.strip() and not c.lower().endswith(".zip")]
    except subprocess.CalledProcessError:
        changed = list(full_files)

    (HANDOFF / "FEATURE_COMMIT.txt").write_text(feature + "\n", encoding="utf-8")
    (HANDOFF / "PACKAGING_FREEZE_COMMIT.txt").write_text(head + "\n", encoding="utf-8")
    (HANDOFF / "FINAL_HEAD.txt").write_text(head + "\n", encoding="utf-8")
    (HANDOFF / "CHANGED_PATHS.txt").write_text("\n".join(changed) + "\n", encoding="utf-8")
    (HANDOFF / "FULL_PATHS.txt").write_text("\n".join(full_files) + "\n", encoding="utf-8")

    a_members = [(rel, REPO / rel) for rel in changed if (REPO / rel).is_file()]
    b_members = [(rel, REPO / rel) for rel in full_files if (REPO / rel).is_file()]
    a_zip, b_zip = HANDOFF / A_NAME, HANDOFF / B_NAME
    write_zip(a_zip, a_members)
    write_zip(b_zip, b_members)

    with zipfile.ZipFile(a_zip) as za, zipfile.ZipFile(b_zip) as zb:
        for name in za.namelist():
            if name not in zb.namelist():
                raise SystemExit(f"CHANGED missing from FULL: {name}")
            if za.read(name) != zb.read(name):
                raise SystemExit(f"BYTE MISMATCH: {name}")

    evid_names = [
        "README-VI.md",
        "OWNER_NEXT_STEPS_VI.md",
        "PROJECT-AUDIT-VI.md",
        "CURSOR-IMPLEMENTATION-PROMPT-EN.md",
        "INTEGRATION_NOTES.md",
        "OVERLAY_INTEGRITY.txt",
        "TEST-REPORT.txt",
        "INDEPENDENT_REVIEW.md",
        "INDEPENDENT_REVIEW_V3ADD.md",
        "V2_FREEZE_STRICT_BLOCKED.json",
        "V2_FREEZE_HF3_SAFETY_RED.txt",
        "V2_FREEZE_V3_INDEPENDENT_RED.txt",
        "HEAD_STRICT_PASS.json",
        "HEAD_SELFTEST_PASS.json",
        "HEAD_HF3_SAFETY_GREEN.txt",
        "HEAD_V3_INDEPENDENT_GREEN.txt",
        "GUARD_FRAMEWORK_SELFTEST.txt",
        "GUARD_ARCHIVE_SELFTEST.txt",
        "GUARD_HOOK_SELFTEST.txt",
        "GUARD_UNITTEST_HEAD.txt",
        "GUARD_AFTER_V3_ADD.txt",
        "FEATURE_COMMIT.txt",
        "PACKAGING_FREEZE_COMMIT.txt",
        "FINAL_HEAD.txt",
        "CHANGED_PATHS.txt",
        "FULL_PATHS.txt",
        "GITHUB_ACTIONS.txt",
    ]
    c_members = []
    for n in evid_names:
        p = HANDOFF / n
        if p.is_file():
            c_members.append((f"QUALITY-GUARD-v1.0-WINDOWS-SAFE-EVIDENCE/{n}", p))
    c_zip = HANDOFF / C_NAME
    write_zip(c_zip, c_members)

    for zpath in (a_zip, b_zip, c_zip):
        try:
            scan_zip_path(zpath)
        except ScanFailure as exc:
            raise SystemExit(f"SCAN BLOCKED {zpath.name}: {exc}") from exc

    sums = {a_zip.name: sha256(a_zip), b_zip.name: sha256(b_zip), c_zip.name: sha256(c_zip)}
    (HANDOFF / "SHA256SUMS.txt").write_text(
        "".join(f"{h}  {n}\n" for n, h in sums.items()), encoding="utf-8"
    )
    meta = {
        "schema": "mypc.package-meta.v2",
        "package": "MYPC-ENGINEERING-QUALITY-GUARD-v1.0",
        "version": "1.0.0",
        "baseline_v2_freeze": "0ea4264440bf330f005af7447bbd6bdb6cfabb46",
        "baseline_v2_complete_sha256": "58017ee3f09b5e6f21dd6097c390058ff48616cf83cc8b1932e93a32627a0e6a",
        "v3_feature": "97c1e9df2d54314098066eca7c88c7e82edc4c79",
        "feature_commit": feature,
        "packaging_freeze_commit": head,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": sums,
        "overlay_zip_sha256": "06d904a6b4b5da6c163aac61d3ce077e9de9d73939bbdd539e8aae31e2a6c707",
        "gates_blocked": [
            "USB_WINDOWS_PHYSICAL",
            "USB_STABILITY_30_MIN",
            "USB_CAMERA_LAB_OWNER_SIGN",
            "FACE_PILOT",
            "INSTALLER",
            "PRODUCTION_READY",
        ],
        "github_actions": {
            "tip": "b4652d497bc7cceb53d510ab70bdccd50db2724a",
            "workflow_run_url": "https://github.com/MyPCVietNam/CCongMyPC/actions/runs/42355748368",
            "conclusion": "success",
            "jobs": ["guard-contract", "backend-linux", "frontend", "windows-contract"],
        },
        "owner_usb_physical_approved": False,
    }
    (HANDOFF / "PACKAGE_META.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    docs = [
        "SHA256SUMS.txt",
        "PACKAGE_META.json",
        "README-VI.md",
        "OWNER_NEXT_STEPS_VI.md",
        "PROJECT-AUDIT-VI.md",
        "CURSOR-IMPLEMENTATION-PROMPT-EN.md",
        "INTEGRATION_NOTES.md",
        "OVERLAY_INTEGRITY.txt",
        "TEST-REPORT.txt",
        "INDEPENDENT_REVIEW_V3ADD.md",
        "INDEPENDENT_REVIEW.md",
        "V2_FREEZE_STRICT_BLOCKED.json",
        "V2_FREEZE_HF3_SAFETY_RED.txt",
        "HEAD_STRICT_PASS.json",
        "HEAD_HF3_SAFETY_GREEN.txt",
        "FEATURE_COMMIT.txt",
        "PACKAGING_FREEZE_COMMIT.txt",
        "FINAL_HEAD.txt",
        "CHANGED_PATHS.txt",
        "FULL_PATHS.txt",
        "GITHUB_ACTIONS.txt",
    ]
    outer = HANDOFF / OUTER_NAME
    outer_members = [(n, HANDOFF / n) for n in docs if (HANDOFF / n).is_file()] + [
        (A_NAME, a_zip),
        (B_NAME, b_zip),
        (C_NAME, c_zip),
    ]
    write_zip(outer, outer_members)
    try:
        scan_zip_path(outer)
    except ScanFailure as exc:
        raise SystemExit(f"SCAN BLOCKED outer: {exc}") from exc
    outer_hash = sha256(outer)
    (HANDOFF / "SHA256SUMS-COMPLETE.txt").write_text(
        (HANDOFF / "SHA256SUMS.txt").read_text() + f"{outer_hash}  {OUTER_NAME}\n",
        encoding="utf-8",
    )
    print(json.dumps({"outer": outer_hash, "inner": sums, "freeze": head}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
