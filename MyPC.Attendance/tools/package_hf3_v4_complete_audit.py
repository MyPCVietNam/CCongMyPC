#!/usr/bin/env python3
"""Build HF3 V4 four delivery ZIPs + COMPLETE (fail-closed scan)."""
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
HANDOFF = ROOT / "audit" / "handoffs" / "P02-USB-HF3-V4-20261107"
BASELINE = "8dc2dfed68464eb7ba98db6fc4efae90ee3f07a4"
ROOT_SCOPES = (
    "MyPC.Attendance",
    "AGENTS.md",
    ".gitignore",
    ".cursor",
    ".github",
    "quality_guard",
)
A_NAME = "MyPC.Attendance-CHANGED-SOURCE-AUDIT-HF3-V4.zip"
B_NAME = "MyPC.Attendance-FULL-SOURCE-HF3-V4.zip"
C_NAME = "MYPC-HF3-V4-WINDOWS-SAFE-EVIDENCE.zip"
OUTER_NAME = "MYPC-HF3-V4-COMPLETE-AUDIT.zip"

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
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", f"{base}...HEAD", "--", *ROOT_SCOPES],
        cwd=REPO,
        text=True,
    )
    return [ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip() and not ln.lower().endswith(".zip")]


def git_deleted_names(base: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=D", f"{base}...HEAD", "--", *ROOT_SCOPES],
        cwd=REPO,
        text=True,
    )
    return [ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()]


def git_ls_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z", "--", *ROOT_SCOPES], cwd=REPO)
    files = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode().replace("\\", "/")
        low = rel.lower()
        if low.endswith(".zip") or "/release/" in low or low.endswith((".onnx", ".pyc", ".pyo")):
            continue
        if "/__pycache__/" in low or "/data/" in low or "/secrets/" in low or low.endswith(".sqlite3"):
            if "/data/" in low or "/secrets/" in low or low.endswith(".sqlite3"):
                raise SystemExit(f"REFUSE tracked sensitive: {rel}")
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
    feature = os.environ.get("HF3_FEATURE_COMMIT", "").strip() or head
    HANDOFF.mkdir(parents=True, exist_ok=True)
    changed = git_diff_names(BASELINE)
    deleted = git_deleted_names(BASELINE)
    (HANDOFF / "CHANGED_PATHS.txt").write_text("\n".join(changed) + "\n", encoding="utf-8")
    (HANDOFF / "DELETED_PATHS.txt").write_text(("\n".join(deleted) + "\n") if deleted else "(none)\n", encoding="utf-8")
    (HANDOFF / "FEATURE_COMMIT.txt").write_text(feature + "\n", encoding="utf-8")
    (HANDOFF / "PACKAGING_FREEZE_COMMIT.txt").write_text(head + "\n", encoding="utf-8")
    (HANDOFF / "FINAL_HEAD.txt").write_text(head + "\n", encoding="utf-8")
    (HANDOFF / "BASELINE_COMMIT.txt").write_text(BASELINE + "\n", encoding="utf-8")
    graph = subprocess.check_output(["git", "log", "--oneline", f"{BASELINE}..HEAD"], cwd=REPO, text=True)
    (HANDOFF / "COMMIT_GRAPH.txt").write_text(graph or "(none)\n", encoding="utf-8")

    a_members = [(rel, REPO / rel) for rel in changed if (REPO / rel).is_file()]
    write_zip(HANDOFF / A_NAME, a_members)
    b_members = [(rel, REPO / rel) for rel in git_ls_files() if (REPO / rel).is_file()]
    write_zip(HANDOFF / B_NAME, b_members)
    (HANDOFF / "FULL_MANIFEST.txt").write_text(
        "\n".join(rel for rel, _ in b_members) + "\n", encoding="utf-8"
    )
    (HANDOFF / "COMPLETE_MEMBER_MANIFEST.txt").write_text(
        "# filled after COMPLETE build\n", encoding="utf-8"
    )

    with zipfile.ZipFile(HANDOFF / A_NAME) as za, zipfile.ZipFile(HANDOFF / B_NAME) as zb:
        for name in za.namelist():
            if "/audit/handoffs/" in name:
                continue
            if name not in zb.namelist():
                raise SystemExit(f"CHANGED missing from FULL: {name}")
            if za.read(name) != zb.read(name):
                raise SystemExit(f"BYTE MISMATCH: {name}")

    evid = []
    for name in sorted(HANDOFF.iterdir()):
        if name.is_file() and not name.name.lower().endswith(".zip") and name.name not in (
            "SHA256SUMS.txt",
            "SHA256SUMS-COMPLETE.txt",
            "PACKAGE_META.json",
        ):
            evid.append((f"HF3-V4-WINDOWS-SAFE-EVIDENCE/{name.name}", name))
    for src in [
        ROOT / "scripts" / "windows" / "p02_usb_hf3_candidate_18878.ps1",
        ROOT / "scripts" / "windows" / "p02_usb_hf3_v4_fail_closed_runtime_tests.ps1",
        ROOT / "scripts" / "windows" / "hf3_pid_ownership.py",
    ]:
        if src.is_file():
            evid.append((f"HF3-V4-WINDOWS-SAFE-EVIDENCE/{src.name}", src))
    write_zip(HANDOFF / C_NAME, evid)

    for zname in (A_NAME, B_NAME, C_NAME):
        try:
            scan_zip_path(HANDOFF / zname)
        except ScanFailure as exc:
            raise SystemExit(f"SCAN BLOCKED {zname}: {exc}") from exc

    sums = {n: sha256(HANDOFF / n) for n in (A_NAME, B_NAME, C_NAME)}
    (HANDOFF / "SHA256SUMS.txt").write_text("".join(f"{h}  {n}\n" for n, h in sums.items()), encoding="utf-8")
    meta = {
        "schema": "mypc.package-meta.v2",
        "phase": "HF3_PID_SAFETY_V4_FAIL_CLOSED",
        "baseline": BASELINE,
        "feature_commit": feature,
        "packaging_freeze_commit": head,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": sums,
        "gates_blocked": [
            "USB_WINDOWS_PHYSICAL",
            "USB_STABILITY_30_MIN",
            "USB_CAMERA_LAB_OWNER_SIGN",
            "FACE_PILOT",
            "INSTALLER",
            "PRODUCTION_READY",
        ],
        "verdict": "READY_FOR_INDEPENDENT_REAUDIT",
        "owner_start_approved": False,
        "candidate_port": 18878,
    }
    (HANDOFF / "PACKAGE_META.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    docs = [
        "SHA256SUMS.txt",
        "PACKAGE_META.json",
        "README.md",
        "CHANGELOG.md",
        "OWNER_RUNBOOK_VI.md",
        "CUSTODY.txt",
        "CHANGED_PATHS.txt",
        "DELETED_PATHS.txt",
        "BASELINE_COMMIT.txt",
        "FEATURE_COMMIT.txt",
        "PACKAGING_FREEZE_COMMIT.txt",
        "FINAL_HEAD.txt",
        "COMMIT_GRAPH.txt",
        "REMOTE_PR_TIP.txt",
        "V4_INDEPENDENT_INVARIANT_RED.json",
        "V4_BEHAVIORAL_BASELINE_RED.txt",
        "V4_BEHAVIORAL_GREEN.txt",
        "INDEPENDENT_REVIEW_V4.md",
        "TEST_REPORT.txt",
        "GITHUB_ACTIONS.txt",
        "FULL_MANIFEST.txt",
        "GATE_MATRIX.txt",
        "REMOTE_VERIFY.txt",
    ]
    # Pre-write COMPLETE member list (docs + three inners) for inclusion inside COMPLETE.
    planned = [n for n in docs if (HANDOFF / n).is_file()] + [A_NAME, B_NAME, C_NAME]
    (HANDOFF / "COMPLETE_MEMBER_MANIFEST.txt").write_text(
        "\n".join(planned) + "\n", encoding="utf-8"
    )
    if "COMPLETE_MEMBER_MANIFEST.txt" not in docs:
        docs.append("COMPLETE_MEMBER_MANIFEST.txt")
    outer_members = [(n, HANDOFF / n) for n in docs if (HANDOFF / n).is_file()] + [
        (A_NAME, HANDOFF / A_NAME),
        (B_NAME, HANDOFF / B_NAME),
        (C_NAME, HANDOFF / C_NAME),
    ]
    write_zip(HANDOFF / OUTER_NAME, outer_members)
    try:
        scan_zip_path(HANDOFF / OUTER_NAME)
    except ScanFailure as exc:
        raise SystemExit(f"SCAN BLOCKED outer: {exc}") from exc
    outer_hash = sha256(HANDOFF / OUTER_NAME)
    with zipfile.ZipFile(HANDOFF / OUTER_NAME) as zo:
        (HANDOFF / "COMPLETE_MEMBER_MANIFEST.txt").write_text(
            "\n".join(sorted(zo.namelist())) + "\n", encoding="utf-8"
        )
    (HANDOFF / "SHA256SUMS-COMPLETE.txt").write_text(
        (HANDOFF / "SHA256SUMS.txt").read_text() + f"{outer_hash}  {OUTER_NAME}\n", encoding="utf-8"
    )
    print(json.dumps({"outer": outer_hash, "inner": sums, "freeze": head}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
