# CURSOR ASSIGNMENT — Integrate MyPC Engineering Quality Guard v1.0

Repository: `https://github.com/MyPCVietNam/CCongMyPC`.
PR #27 source branch observed at package preparation: `cursor/p02-usb-hf3-dshow-com-enum-83a8`, base branch `cursor/p02-usb-hf2-verified-binding-83a8`. These refs are **observations, not trusted current pointers**. Do not assume `main` has the app (`main` was LICENSE-only). Re-fetch current refs and immutable SHAs before any action.

## Objective

Install the exact contents of `repository-overlay/` (from attached `MYPC-ENGINEERING-QUALITY-GUARD-v1.0.zip`) into the **actual Git repository root**, without flattening the tree or overwriting unrelated files. Establish a permanent code-quality control plane for MyPC Attendance with reproducible CI, Cursor rules/skill/hooks, negative regression tests and artifact integrity. Keep PR #27 in-place unless branch topology makes that impossible; record deviations and seek owner approval for merge/push operations outside the normal code-change flow. Do NOT merge to `main`, force push, run `Prepare`, `Start`, `Stop` or synthetic PID runtime on any owner machine.

## Procedure

1. Inspect `AGENTS.md`, the guard docs, current repo tree, current HEAD/base refs, clean/dirty state, and all current workflows/hooks. Reconcile collisions conservatively. All actual changes must be in a reviewable Git commit; no modifications to owner Windows data or secrets.
2. Integrate ALL files under `repository-overlay/`. Keep Cursor rule frontmatter and skill paths unchanged. No new arbitrary MCP or external network agent privileges are needed.
3. Independently run guard framework selftests and hook tests:
   - `python -m unittest discover -s quality_guard/tests -p 'test_framework.py' -v`
   - `python -m unittest discover -s quality_guard/tests -p 'test_archive_verifier.py' -v`
   - `node --test .cursor/hooks/guard-shell.test.cjs`
   - `python quality_guard/check.py --root . --selftest`
4. Use the uploaded immutable PID Safety V2 freeze `0ea4264440bf330f005af7447bbd6bdb6cfabb46` in a **separate disposable baseline checkout** to preserve baseline RED evidence: it fails 5 independent HF3 assertions and raises 3 static blocker codes. The PR has since moved to a **PID Safety V3** tip; DO NOT assume the current HEAD is still RED. Run the exact same independent tests against **current HEAD**: it must be GREEN for the right reason. Never soften assertions to make it appear GREEN. Treat any current failing case as HOLD. If old V2 freeze cannot be checked out safely, cite the provided independent RED log rather than altering the worktree.
5. Verify whether the recent V3 commit `97c1e9df2d54314098066eca7c88c7e82edc4c79` already resolves these regressions. If so, do not rewrite fixed code; maintain the exact parsed `--app-dir` and mocked default `Stop-Process`. If not, refactor the affected functions minimally with safe dependency injection at the *actual process kill boundary*, parsed exact normalized CLI flags, and deterministic tests for fake/reused PID, missing creation time, conhost, foreign/ambiguous listener, and wrong backend in `--log-config`. No real OS kill in default tests or GitHub-hosted CI. Any optional process-spawning lab needs explicit owner approval, separate mode and verified own-process cleanup. Preserve existing COM/VT_BSTR/strict USB identity, model pins, rollback and prior data isolation.
6. Validate the 4 GitHub Actions jobs on the exact commit: `guard-contract`, `backend-linux`, `frontend`, `windows-contract` (Windows PowerShell 5.1, static AST/PSA and pure Pester; no physical device). Fix actual dependency/workflow failures, not by `continue-on-error`, skipped test requirements or `|| true`. Test workflow configuration syntax and branch event behavior; if Actions not enabled, label checks UNRUN and do not claim PASS.
7. Perform independent diff-focused review with adversarial tests by a separate agent/reviewer. Record positive/negative behavior, safety boundaries and rollback. Do not trust the coding agent's own 521 pytest PASS alone.
8. Package FULL-SOURCE, CHANGED-SOURCE, WINDOWS-SAFE-EVIDENCE and COMPLETE-AUDIT ZIPs with SHA256SUMS, relative path manifest, changelog, actual CI links, exact feature/freeze/tip SHAs and blockers. Never include biometrics, raw device IDs, credentials/HMAC or owner database/logs. Verify archive SHA+CRC and cross-compare source.

## Important security constraints

- Owner-only ports `18876/18877` and UGREEN HF3 sandbox `18878` stay untouched by this task. No automatic camera frame capture, hardware restart, Python venv installer, model download or storage mutation.
- The fake PID 4242 must never be passed to a real `Stop-Process` from a test; both the process-enumeration boundary and termination boundary require injectability.
- Source and CI success never imply USB_WINDOWS_PHYSICAL, USB_STABILITY_30_MIN or USB_CAMERA_LAB_OWNER_SIGN. Preserve all physical gates as BLOCKED.
- Do not modify `AGENTS.md` or rules to justify lowering safety. Do not conflate a skipped or timed-out check with PASS.

## Deliverables / acceptance

A reviewed PR update (or reviewable quality-only branch if necessary), 4 CI job names appearing on the correct source-carrying commit, guard selftests GREEN, all independent HF3 safety regressions GREEN, and fresh, verified source/evidence ZIPs. In your final response supply exact immutable commit SHAs, commands and counts, explicit unrun/skipped tests, links to Actions runs, and a Vietnamese owner next-steps note. If any check remains RED/UNRUN, report HOLD and do not instruct owner to Start.
