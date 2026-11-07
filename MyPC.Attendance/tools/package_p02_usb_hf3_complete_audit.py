#!/usr/bin/env python3
"""Build P02-USB-HF3 four delivery ZIPs + COMPLETE-AUDIT (fail-closed scan)."""
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
HANDOFF = ROOT / "audit" / "handoffs" / "P02-USB-HF3-20261106"
# CHANGED zip is relative to PR #27 tip before Quality Guard v1.0 integration.
# Prior tips remain in PACKAGE_META for custody; do not rewrite immutable pins.
# CHANGED zip is relative to PR #27 tip immediately before V3-additional corrective.
BASELINE = "e04a34121f3bf00253685a8512e2b835aa86b7ab"
BASELINE_PID_SAFETY_V3_FEATURE = "97c1e9df2d54314098066eca7c88c7e82edc4c79"
BASELINE_PID_SAFETY_V3_FREEZE = "00858e3f78325517c43c4d688e5547748928b3a0"
BASELINE_PID_SAFETY_V2_FREEZE = "0ea4264440bf330f005af7447bbd6bdb6cfabb46"
BASELINE_PID_SAFETY_V2_FEATURE = "ae003b8f703e62144feb1eed77e0462b536d74dd"
BASELINE_PID_OWNERSHIP = "2fcb5bf05cd61d47be93cbfbbbbb62ec4e16bddc"
BASELINE_PR26 = "146d04cb930a446f891f48178a33672f0537b95e"
BASELINE_PROPERTY_BAG = "05f6ba991b4b43b3719125551298b18441578bcb"
BASELINE_COM_RELEASE = "ff6789ecd15ede618101e6a4c4938c3290ed1748"
BASELINE_COINIT = "98d8d40290018d688749931a9f78d4ee016b126b"
BASELINE_VTBSTR = "aa0c385f414d410d2c6aa0cdec7d676fb8f2ac7e"
BASELINE_PID_OWNERSHIP_FREEZE = "59148ebd1d545aa887c4cb4a6288d9c8c394ba1b"
BASELINE_PID_OWNERSHIP_FEATURE = "3c989facccc9443c351e0526dc76db7ee2f742a0"
A_NAME = "MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip"
B_NAME = "MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip"
C_NAME = "MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip"
OUTER_NAME = "MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"

sys.path.insert(0, str(ROOT))
from tools.release_sensitive_scan import ScanFailure, scan_zip_path  # noqa: E402


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


# Repo-root quality-control plane paths (Quality Guard v1.0 overlay).
ROOT_SCOPES = (
    "MyPC.Attendance",
    "AGENTS.md",
    ".gitignore",
    ".cursor",
    ".github",
    "quality_guard",
)


def git_diff_names(base: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", f"{base}...HEAD", "--", *ROOT_SCOPES],
        cwd=REPO,
        text=True,
    )
    return [ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()]


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
        rel = raw.decode()
        low = rel.lower().replace("\\", "/")
        if low.endswith(".zip") or "/release/" in low or low.endswith(".onnx") or low.endswith(".pyc"):
            continue
        if "/__pycache__/" in low or low.endswith(".pyo"):
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
    import os

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    feature = os.environ.get("HF3_FEATURE_COMMIT", "").strip() or head
    HANDOFF.mkdir(parents=True, exist_ok=True)
    changed = [p for p in git_diff_names(BASELINE) if not p.lower().endswith(".zip")]
    deleted = git_deleted_names(BASELINE)
    code_paths = [p for p in changed if "/audit/handoffs/" not in p]
    handoff_paths = [p for p in changed if "/audit/handoffs/" in p]
    (HANDOFF / "CODE_PATHS.txt").write_text("\n".join(code_paths) + "\n", encoding="utf-8")
    (HANDOFF / "HANDOFF_PATHS.txt").write_text("\n".join(handoff_paths) + "\n", encoding="utf-8")
    (HANDOFF / "CHANGED_PATHS.txt").write_text("\n".join(changed) + "\n", encoding="utf-8")
    (HANDOFF / "DELETED_PATHS.txt").write_text(
        ("\n".join(deleted) + "\n") if deleted else "(none)\n", encoding="utf-8"
    )
    (HANDOFF / "FEATURE_COMMIT.txt").write_text(feature + "\n", encoding="utf-8")
    (HANDOFF / "PACKAGING_FREEZE_COMMIT.txt").write_text(head + "\n", encoding="utf-8")
    (HANDOFF / "FINAL_HEAD.txt").write_text(head + "\n", encoding="utf-8")
    (HANDOFF / "BASELINE_COMMIT.txt").write_text(BASELINE + "\n", encoding="utf-8")
    graph = subprocess.check_output(
        ["git", "log", "--oneline", f"{BASELINE}..HEAD"], cwd=REPO, text=True
    )
    (HANDOFF / "COMMIT_GRAPH.txt").write_text(graph or "(no commits yet)\n", encoding="utf-8")
    (HANDOFF / "REMOTE_PR_TIP.txt").write_text(
        "PR stacked on #26; tip filled after push.\n", encoding="utf-8"
    )

    a_members = [(rel, REPO / rel) for rel in changed if (REPO / rel).is_file()]
    seen_arcs = {arc for arc, _ in a_members}
    for name in ("CODE_PATHS.txt", "CHANGED_PATHS.txt", "DELETED_PATHS.txt", "CHANGELOG.md", "BASELINE_RCA.md"):
        arc = f"MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/{name}"
        p = HANDOFF / name
        if p.exists() and arc not in seen_arcs:
            a_members.append((arc, p))
            seen_arcs.add(arc)
    a_zip = HANDOFF / A_NAME
    write_zip(a_zip, a_members)

    b_members = [(rel, REPO / rel) for rel in git_ls_files() if (REPO / rel).is_file()]
    b_zip = HANDOFF / B_NAME
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
        "README.md",
        "IDENTITY_BOUNDARY_REPRO_RED.txt",
        "IDENTITY_BOUNDARY_REPRO_GREEN.txt",
        "INDEPENDENT_REPRO_test_p02_usb_hf3_identity_boundary.py",
        "COM_RELEASE_REPRO_RED.txt",
        "INDEPENDENT_REPRO_test_p02_usb_hf3_com_release_update.py",
        "INDEPENDENT_REPRO_test_p02_usb_hf3_coinit_signature.py",
        "COINIT_REPRO_RED.txt",
        "OWNER-WINDOWS-EVIDENCE-SAFE.json",
        "INDEPENDENT_REPRO_test_hf3_owner_vtbstr_direct.py",
        "VTBSTR_REPRO_RED.txt",
        "P02-USB-HF3-OWNER-PID-OWNERSHIP-VI.md",
        "PID_OWNERSHIP_BASELINE_RED.md",
        "OWNER-PID-RESULTS-AND-RCA.md",
        "PID_SAFETY_BASELINE_RED.md",
        "PID_SAFETY_RATIONALE.md",
        "PID_SAFETY_GREEN.txt",
        "PID_SAFETY_V3_BASELINE_RED.txt",
        "PID_SAFETY_V3_GREEN.txt",
        "PID_SAFETY_V3_RATIONALE.md",
        "V3_ADDITIONAL_BASELINE_RED.txt",
        "V3_ADDITIONAL_GREEN.txt",
        "V3_ADDITIONAL_RATIONALE.md",
        "V3_ADDITIONAL_HF3_84_PASS.txt",
        "INDEPENDENT_REPRO_test_hf3_v3_safety_additional.py",
        "OMITTED_HISTORICAL_ARCHIVES.md",
        "GITHUB_ACTIONS.txt",
    ]:
        p = HANDOFF / name
        if p.exists():
            (evid_dir / name).write_bytes(p.read_bytes())
    for src in [
        ROOT / "scripts" / "windows" / "p02_usb_hf3_candidate_18878.ps1",
        ROOT / "scripts" / "windows" / "p02_usb_hf3_readonly_diag.py",
        ROOT / "scripts" / "windows" / "p02_usb_hf3_pid_safety_runtime_tests.ps1",
        ROOT / "docs" / "gates" / "P02-USB-HF3-GATE-MATRIX.md",
        ROOT / "docs" / "runbooks" / "P02-USB-HF3-OWNER-RUNBOOK-VI.md",
        ROOT / "docs" / "runbooks" / "P02-USB-HF3-OWNER-PID-OWNERSHIP-VI.md",
    ]:
        if src.is_file():
            (evid_dir / src.name).write_bytes(src.read_bytes())

    c_zip = HANDOFF / C_NAME
    write_zip(
        c_zip,
        [(f"P02-USB-HF3-WINDOWS-SAFE-EVIDENCE/{p.name}", p) for p in sorted(evid_dir.iterdir()) if p.is_file()],
    )

    notes = []
    for zpath in (a_zip, b_zip, c_zip):
        try:
            scan_zip_path(zpath)
            notes.append(f"PASS {zpath.name}")
        except ScanFailure as exc:
            raise SystemExit(f"SCAN BLOCKED {zpath.name}: {exc}") from exc
    (HANDOFF / "SCANNER_REPORT.txt").write_text("\n".join(notes) + "\n", encoding="utf-8")
    (evid_dir / "SCANNER_REPORT.txt").write_bytes((HANDOFF / "SCANNER_REPORT.txt").read_bytes())
    write_zip(
        c_zip,
        [(f"P02-USB-HF3-WINDOWS-SAFE-EVIDENCE/{p.name}", p) for p in sorted(evid_dir.iterdir()) if p.is_file()],
    )
    try:
        scan_zip_path(c_zip)
    except ScanFailure as exc:
        raise SystemExit(f"SCAN BLOCKED C refresh: {exc}") from exc

    sums = {a_zip.name: sha256(a_zip), b_zip.name: sha256(b_zip), c_zip.name: sha256(c_zip)}
    (HANDOFF / "SHA256SUMS.txt").write_text(
        "".join(f"{h}  {n}\n" for n, h in sums.items()), encoding="utf-8"
    )
    meta = {
        "schema": "mypc.package-meta.v2",
        "baseline": BASELINE,
        "baseline_note": "PR #27 tip before V3-additional corrective (Quality Guard on e04a341; audited V3 freeze 00858e3)",
        "baseline_pid_safety_v3_feature": BASELINE_PID_SAFETY_V3_FEATURE,
        "baseline_pid_safety_v3_freeze": BASELINE_PID_SAFETY_V3_FREEZE,
        "audited_v3_complete_sha256": "508f4fbc444f1ebb5fa7782a52ba8bb236448822e679718de344aeab10fce80f",
        "historical_zip_digests_omitted_from_full_source": True,
        "historical_zip_digests_note": "Tracked SHA256SUMS*.txt under older handoffs list digests for intentionally omitted .zip archives; see OMITTED_HISTORICAL_ARCHIVES.md — do not claim those binaries are verified inside FULL-SOURCE.",
        "baseline_pid_safety_v2_freeze": BASELINE_PID_SAFETY_V2_FREEZE,
        "baseline_pid_safety_v2_feature": BASELINE_PID_SAFETY_V2_FEATURE,
        "baseline_pid_ownership": BASELINE_PID_OWNERSHIP,
        "baseline_pid_ownership_feature": BASELINE_PID_OWNERSHIP_FEATURE,
        "baseline_pid_ownership_freeze": BASELINE_PID_OWNERSHIP_FREEZE,
        "baseline_pr26": BASELINE_PR26,
        "baseline_property_bag": BASELINE_PROPERTY_BAG,
        "baseline_com_release": BASELINE_COM_RELEASE,
        "baseline_coinit": BASELINE_COINIT,
        "baseline_vtbstr": BASELINE_VTBSTR,
        "baseline_pr": 27,
        "feature_commit": feature,
        "packaging_freeze_commit": head,
        "audit_staging_note": "feature_commit=code/docs fix; packaging_freeze_commit=HEAD when ZIP built; tip pin may advance after freeze",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_paths": code_paths,
        "deleted_paths": deleted,
        "sha256": sums,
        "gates_blocked": [
            "USB_WINDOWS_PHYSICAL",
            "USB_STABILITY_30_MIN",
            "USB_CAMERA_LAB_OWNER_SIGN",
            "FACE_PILOT",
            "INSTALLER",
            "PRODUCTION_READY",
        ],
        "candidate_port": 18878,
        "phase": "USB_HF3_QUALITY_GUARD_V1",
        "github_actions": {
            "feature_tip": "a0e88efb74c850c21526501f3f343357965f649c",
            "workflow_run_url": "https://github.com/MyPCVietNam/CCongMyPC/actions/runs/42354905763",
            "conclusion": "success",
            "jobs": [
                "guard-contract",
                "windows-contract",
                "backend-linux",
                "frontend",
            ],
            "note": "Check runs on feature tip before packaging-freeze commit; freeze may re-trigger Actions.",
        },
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
        "IDENTITY_BOUNDARY_REPRO_RED.txt",
        "IDENTITY_BOUNDARY_REPRO_GREEN.txt",
        "INDEPENDENT_REPRO_test_p02_usb_hf3_identity_boundary.py",
        "COM_RELEASE_REPRO_RED.txt",
        "INDEPENDENT_REPRO_test_p02_usb_hf3_com_release_update.py",
        "INDEPENDENT_REPRO_test_p02_usb_hf3_coinit_signature.py",
        "COINIT_REPRO_RED.txt",
        "OWNER-WINDOWS-EVIDENCE-SAFE.json",
        "INDEPENDENT_REPRO_test_hf3_owner_vtbstr_direct.py",
        "VTBSTR_REPRO_RED.txt",
        "P02-USB-HF3-OWNER-PID-OWNERSHIP-VI.md",
        "PID_OWNERSHIP_BASELINE_RED.md",
        "OWNER-PID-RESULTS-AND-RCA.md",
        "PID_SAFETY_BASELINE_RED.md",
        "PID_SAFETY_RATIONALE.md",
        "PID_SAFETY_GREEN.txt",
        "PID_SAFETY_V3_BASELINE_RED.txt",
        "PID_SAFETY_V3_GREEN.txt",
        "PID_SAFETY_V3_RATIONALE.md",
        "V3_ADDITIONAL_BASELINE_RED.txt",
        "V3_ADDITIONAL_GREEN.txt",
        "V3_ADDITIONAL_RATIONALE.md",
        "V3_ADDITIONAL_HF3_84_PASS.txt",
        "INDEPENDENT_REPRO_test_hf3_v3_safety_additional.py",
        "OMITTED_HISTORICAL_ARCHIVES.md",
        "GITHUB_ACTIONS.txt",
    ]
    outer_members = [(n, HANDOFF / n) for n in docs if (HANDOFF / n).exists()] + [
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
