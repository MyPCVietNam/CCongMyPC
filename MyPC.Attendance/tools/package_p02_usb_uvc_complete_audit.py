#!/usr/bin/env python3
"""Build P02-USB UVC four delivery ZIPs + COMPLETE-AUDIT (fail-closed scan)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "MyPC.Attendance"
HANDOFF = ROOT / "audit" / "handoffs" / "P02-USB-UVC-20261106"
BASELINE = "ca07916e20c3858b75dc1500df8443e68e53dae0"
OUTER_NAME = "MYPC-P02-USB-UVC-COMPLETE-AUDIT.zip"

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
    (HANDOFF / "CODE_PATHS.txt").write_text("\n".join(code_paths) + "\n", encoding="utf-8")
    (HANDOFF / "HANDOFF_PATHS.txt").write_text("\n".join(handoff_paths) + "\n", encoding="utf-8")
    (HANDOFF / "CHANGED_PATHS.txt").write_text("\n".join(changed) + "\n", encoding="utf-8")
    (HANDOFF / "FEATURE_COMMIT.txt").write_text(head + "\n", encoding="utf-8")
    (HANDOFF / "PACKAGING_FREEZE_COMMIT.txt").write_text(head + "\n", encoding="utf-8")
    (HANDOFF / "FINAL_HEAD.txt").write_text(head + "\n", encoding="utf-8")
    graph = subprocess.check_output(
        ["git", "log", "--oneline", f"{BASELINE}..HEAD"], cwd=REPO, text=True
    )
    (HANDOFF / "COMMIT_GRAPH.txt").write_text(graph, encoding="utf-8")

    a_members = [(rel, REPO / rel) for rel in changed if (REPO / rel).is_file()]
    # Ensure CODE_PATHS.txt etc. from handoff are included even if already in changed
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
        shutil.rmtree(evid_dir)
    evid_dir.mkdir()
    for name in [
        "BASELINE_RCA.md",
        "CHANGELOG.md",
        "ACCEPTANCE_MATRIX.md",
        "ARCHITECTURE_DECISIONS.md",
        "OWNER_WINDOWS_STEPS_VI.md",
        "FREEZE_VS_TIP_TIMELINE.md",
        "TEST_REPORT.txt",
        "FRONTEND_BUILD_REPORT.txt",
        "BASELINE_FAIL.txt",
        "VERSIONS.txt",
        "CODE_PATHS.txt",
        "HANDOFF_PATHS.txt",
        "CHANGED_PATHS.txt",
        "DELETED_PATHS.txt",
        "BASELINE_COMMIT.txt",
        "FEATURE_COMMIT.txt",
        "PACKAGING_FREEZE_COMMIT.txt",
        "REMOTE_PR_TIP.txt",
        "FINAL_HEAD.txt",
        "COMMIT_GRAPH.txt",
        "SCANNER_REPORT.txt",
    ]:
        p = HANDOFF / name
        if p.exists():
            (evid_dir / name).write_bytes(p.read_bytes())
    # Include windows script + gate matrix copies (redacted)
    for src in [
        ROOT / "scripts" / "windows" / "p02_usb_uvc_physical_checks.ps1",
        ROOT / "docs" / "gates" / "P02-USB-UVC-GATE-MATRIX.md",
        ROOT / "docs" / "runbooks" / "P02-USB-UVC-OWNER-RUNBOOK-VI.md",
    ]:
        if src.is_file():
            (evid_dir / src.name).write_bytes(src.read_bytes())

    c_zip = HANDOFF / "WINDOWS-SAFE-EVIDENCE.zip"
    write_zip(
        c_zip,
        [(f"P02-USB-WINDOWS-SAFE-EVIDENCE/{p.name}", p) for p in sorted(evid_dir.iterdir()) if p.is_file()],
    )

    scan_notes = []
    for zpath in (a_zip, b_zip, c_zip):
        try:
            scan_zip_path(zpath)
            scan_notes.append(f"PASS {zpath.name}")
        except ScanFailure as exc:
            raise SystemExit(f"SCAN BLOCKED {zpath.name}: {exc}") from exc
    (HANDOFF / "SCANNER_REPORT.txt").write_text("\n".join(scan_notes) + "\n", encoding="utf-8")

    sums = {a_zip.name: sha256(a_zip), b_zip.name: sha256(b_zip), c_zip.name: sha256(c_zip)}
    (HANDOFF / "SHA256SUMS.txt").write_text(
        "".join(f"{h}  {n}\n" for n, h in sums.items()), encoding="utf-8"
    )
    meta = {
        "schema": "mypc.package-meta.v2",
        "baseline": BASELINE,
        "feature_commit": head,
        "packaging_freeze_commit": head,
        "remote_pr_tip": None,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_paths": code_paths,
        "handoff_paths": handoff_paths,
        "sha256": sums,
        "gates_blocked": [
            "USB_WINDOWS_PHYSICAL",
            "USB_STABILITY_30_MIN",
            "USB_CAMERA_LAB_OWNER_SIGN",
            "FACE_PILOT",
            "INSTALLER",
            "PRODUCTION_READY",
        ],
        "synthetic_credentials_in_tests": True,
        "phase": "USB_UVC_SOURCE_CODE_FIX",
        "candidate_port": 18878,
        "do_not_touch_ports": [18876, 18877],
    }
    (HANDOFF / "PACKAGE_META.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    outer = HANDOFF / OUTER_NAME
    docs = [
        "SHA256SUMS.txt",
        "PACKAGE_META.json",
        "README.md",
        "CHANGELOG.md",
        "ACCEPTANCE_MATRIX.md",
        "ARCHITECTURE_DECISIONS.md",
        "BASELINE_RCA.md",
        "OWNER_WINDOWS_STEPS_VI.md",
        "FREEZE_VS_TIP_TIMELINE.md",
        "TEST_REPORT.txt",
        "FRONTEND_BUILD_REPORT.txt",
        "VERSIONS.txt",
        "CODE_PATHS.txt",
        "HANDOFF_PATHS.txt",
        "CHANGED_PATHS.txt",
        "DELETED_PATHS.txt",
        "BASELINE_COMMIT.txt",
        "FEATURE_COMMIT.txt",
        "PACKAGING_FREEZE_COMMIT.txt",
        "REMOTE_PR_TIP.txt",
        "FINAL_HEAD.txt",
        "COMMIT_GRAPH.txt",
        "SCANNER_REPORT.txt",
        "BASELINE_FAIL.txt",
    ]
    outer_members = [(n, HANDOFF / n) for n in docs] + [
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
        (HANDOFF / "SHA256SUMS.txt").read_text() + f"{outer_hash}  {OUTER_NAME}\n",
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
