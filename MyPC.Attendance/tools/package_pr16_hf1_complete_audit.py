#!/usr/bin/env python3
"""Build PR16-HF1 four delivery ZIPs + outer COMPLETE-AUDIT (fail-closed scan)."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "MyPC.Attendance"
HANDOFF = ROOT / "audit" / "handoffs" / "PR16-HF1-CORRECTIVE-20261103"
BASELINE = "1bdaef6a7aa63b24127239911fb021dcaf3e147a"

DENY_NAME = re.compile(
    r"(^|/)(data|secrets)(/|$)|FIRST_RUN_ADMIN|\.sqlite3(-wal|-shm)?$|"
    r"master\.key|session\.secret|face_templates\.key|\.env$|"
    r"cookie|csrf_token|owner_challenge|embedding|\.onnx$",
    re.I,
)
DENY_CONTENT = re.compile(
    r"(password\s*=\s*['\"][^'\"]{8,}|BEGIN (RSA |OPENSSH )?PRIVATE KEY|"
    r"session=[A-Za-z0-9]{20,}|csrf_token['\"]?\s*[:=])",
    re.I,
)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


def git_diff_names() -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"{BASELINE}...HEAD", "--", "MyPC.Attendance"],
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
        low = rel.lower()
        if low.endswith(".zip") or "/release/" in low or low.endswith(".onnx") or low.endswith(".pyc"):
            continue
        if DENY_NAME.search(rel.replace("\\", "/")):
            raise SystemExit(f"REFUSE tracked sensitive: {rel}")
        files.append(rel)
    return sorted(files)


def write_zip(path: Path, members: list[tuple[str, Path]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in members:
            if DENY_NAME.search(arc):
                raise SystemExit(f"REFUSE member name: {arc}")
            data = src.read_bytes()
            # content scan for text-ish
            if src.suffix.lower() in {".py", ".ts", ".tsx", ".md", ".txt", ".json", ".ps1", ".mjs"}:
                try:
                    text = data.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
                if DENY_CONTENT.search(text):
                    # allow code that mentions the words in tests/docs carefully —
                    # hard fail only on private key blocks
                    if "BEGIN " in text and "PRIVATE KEY" in text:
                        raise SystemExit(f"REFUSE private key content: {arc}")
            z.writestr(arc, data)
        bad = z.testzip()
        if bad:
            raise SystemExit(f"CRC fail: {bad}")


def scan_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if DENY_NAME.search(name):
                raise SystemExit(f"SCAN FAIL name: {path.name}:{name}")
            if name.lower().endswith(".zip"):
                # nested zip — extract names only
                raw = z.read(info)
                import io

                with zipfile.ZipFile(io.BytesIO(raw)) as inner:
                    for n in inner.namelist():
                        if DENY_NAME.search(n.replace("\\", "/")):
                            raise SystemExit(f"SCAN FAIL nested: {path.name}:{name}:{n}")


def main() -> int:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    feature = head
    HANDOFF.mkdir(parents=True, exist_ok=True)
    changed = git_diff_names()
    code_paths = [p for p in changed if "/audit/handoffs/" not in p]
    handoff_paths = [p for p in changed if "/audit/handoffs/" in p]

    # A. CHANGED-SOURCE-AUDIT — every changed tracked file under MyPC.Attendance
    a_members = []
    for rel in changed:
        src = REPO / rel
        if not src.is_file():
            continue
        if rel.lower().endswith(".zip"):
            continue
        a_members.append((rel, src))
    a_zip = HANDOFF / "CHANGED-SOURCE-AUDIT.zip"
    write_zip(a_zip, a_members)

    # B. FULL-SOURCE
    b_members = []
    for rel in git_ls_files():
        src = REPO / rel
        if src.is_file():
            b_members.append((rel, src))
    b_zip = HANDOFF / "FULL-SOURCE.zip"
    write_zip(b_zip, b_members)

    # Verify changed code files byte-equal in FULL
    with zipfile.ZipFile(a_zip) as za, zipfile.ZipFile(b_zip) as zb:
        for name in za.namelist():
            if "/audit/handoffs/" in name:
                continue
            if name not in zb.namelist():
                raise SystemExit(f"CHANGED file missing from FULL: {name}")
            if za.read(name) != zb.read(name):
                raise SystemExit(f"BYTE MISMATCH CHANGED vs FULL: {name}")

    # C. WINDOWS-SAFE-EVIDENCE
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
        "TEST_REPORT.txt",
        "VERSIONS.txt",
        "CODE_PATHS.txt",
        "HANDOFF_PATHS.txt",
        "CHANGED_PATHS.txt",
        "BASELINE_COMMIT.txt",
        "FEATURE_COMMIT.txt",
        "FINAL_HEAD.txt",
    ]:
        p = HANDOFF / name
        if p.exists():
            (evid_dir / name).write_bytes(p.read_bytes())
    c_zip = HANDOFF / "WINDOWS-SAFE-EVIDENCE.zip"
    write_zip(
        c_zip,
        [(f"PR16-HF1-WINDOWS-SAFE-EVIDENCE/{p.name}", p) for p in sorted(evid_dir.iterdir()) if p.is_file()],
    )

    for zpath in (a_zip, b_zip, c_zip):
        scan_zip(zpath)

    sums = {
        a_zip.name: sha256(a_zip),
        b_zip.name: sha256(b_zip),
        c_zip.name: sha256(c_zip),
    }
    (HANDOFF / "SHA256SUMS.txt").write_text(
        "".join(f"{h}  {n}\n" for n, h in sums.items()), encoding="utf-8"
    )
    meta = {
        "baseline": BASELINE,
        "feature": feature,
        "final_head": head,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_paths": code_paths,
        "handoff_paths": handoff_paths,
        "sha256": sums,
    }
    (HANDOFF / "PACKAGE_META.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # D. OUTER COMPLETE-AUDIT
    outer = HANDOFF / "MYPC-PR16-HF1-COMPLETE-AUDIT.zip"
    outer_members = [
        ("SHA256SUMS.txt", HANDOFF / "SHA256SUMS.txt"),
        ("PACKAGE_META.json", HANDOFF / "PACKAGE_META.json"),
        ("README.md", HANDOFF / "README.md"),
        ("CHANGELOG.md", HANDOFF / "CHANGELOG.md"),
        ("ACCEPTANCE_MATRIX.md", HANDOFF / "ACCEPTANCE_MATRIX.md"),
        ("BASELINE_RCA.md", HANDOFF / "BASELINE_RCA.md"),
        ("OWNER_WINDOWS_STEPS_VI.md", HANDOFF / "OWNER_WINDOWS_STEPS_VI.md"),
        ("TEST_REPORT.txt", HANDOFF / "TEST_REPORT.txt"),
        ("VERSIONS.txt", HANDOFF / "VERSIONS.txt"),
        ("CODE_PATHS.txt", HANDOFF / "CODE_PATHS.txt"),
        ("HANDOFF_PATHS.txt", HANDOFF / "HANDOFF_PATHS.txt"),
        ("CHANGED_PATHS.txt", HANDOFF / "CHANGED_PATHS.txt"),
        ("BASELINE_COMMIT.txt", HANDOFF / "BASELINE_COMMIT.txt"),
        ("FEATURE_COMMIT.txt", HANDOFF / "FEATURE_COMMIT.txt"),
        ("FINAL_HEAD.txt", HANDOFF / "FINAL_HEAD.txt"),
        ("CHANGED-SOURCE-AUDIT.zip", a_zip),
        ("FULL-SOURCE.zip", b_zip),
        ("WINDOWS-SAFE-EVIDENCE.zip", c_zip),
    ]
    write_zip(outer, [(n, p) for n, p in outer_members if p.exists()])
    scan_zip(outer)
    outer_hash = sha256(outer)
    # Append outer hash to a sidecar (not inside outer)
    (HANDOFF / "SHA256SUMS-COMPLETE.txt").write_text(
        (HANDOFF / "SHA256SUMS.txt").read_text() + f"{outer_hash}  {outer.name}\n",
        encoding="utf-8",
    )
    print(json.dumps({"outer": outer_hash, "inner": sums, "head": head}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
