---
name: mypc-safe-change
description: Use for every MyPC Attendance bug fix, Windows PowerShell or USB/RTSP camera change, security change, regression, release, PR, source ZIP handoff, and deployment preparation. Enforce base-ref verification, baseline RED reproduction, negative tests, isolated Windows/Linux CI, independent review and fail-closed physical gates.
---

# MyPC Safe Change

## Runbook (use for every code change)

1. **Establish custody.** Record repository name, exact base SHA, branch, HEAD, clean/dirty state and all affected files. Do not assume `main` contains source. For a PR with moving HEAD, inspect the immutable commit being reviewed.
2. **Map impact.** Read the owning module, callers, API/frontend clients, process lifecycle, data schema, trust invalidation, rollback and tests. Classify the change as `CODE_ONLY`, `WINDOWS_HOST`, `SECURITY_SENSITIVE`, or `PHYSICAL_CAMERA`.
3. **Prove the baseline issue.** Add executable test(s) that FAIL on baseline for the actual defect, including two hostile/negative cases. Do not alter test thresholds to hide failures.
4. **Implement minimally.** Preserve known-good COM, PID, model pin, protected ports, DataDir and HMAC. Do not expand to feature work without an explicit owner request.
5. **Run safe tests.** Execute quality guard selftests, static contract, backend pytest, frontend CI, Windows PowerShell 5.1 PSScriptAnalyzer/Pester in GitHub-hosted CI; never invoke real camera, kill PID or owner data in CI. Differentiate SKIP vs PASS.
6. **Independent review.** A separate reviewer/agent analyzes the diff with negative/adversarial tests; record findings and fixes. It must not merely trust the coding agent's PASS summary.
7. **Freeze evidence.** Include immutable feature SHA, packaging SHA, remote tip SHA, FULL/CHANGED/EVIDENCE/COMPLETE ZIP, SHA256 manifest, changelog, test logs, known blockers. Reconcile `CODE_PATHS`, `CHANGED_PATHS` and archive file hashes.
8. **Gate.** Code gate only with required GitHub checks GREEN; Windows owner lab only for runtime and camera gates; physical PASS only with owner evidence and explicit sign-off.

## Stop conditions

- Any test executes a real OS side effect against a fake PID, synthetic camera or real owner DataDir.
- Any command-line identity check permits path substring fallbacks or missing timestamps; HTTP 200 alone counts as Start PASS.
- A risky shell command was allowed because a Cursor hook did not load; hooks are advisory, CI must still be green.
- CI has skipped, missing, canceled or failing required checks; a packaging report is not authoritative.
- The same PR contains unrelated changes that cannot be explained by the impact map.

## Reporting template

Report: immutable source SHA and PR/base; changed paths; reproduced baseline RED; final tests with exact commands and environment, skips, CI links, independent review findings, artifacts and hashes; `CODE_GATE`, `WINDOWS_SIMULATION`, `OWNER_PHYSICAL`, `SOAK_30_MIN`, `CAMERA_LAB`, `PRODUCTION` statuses separately.

Read [references/negative-cases.md](references/negative-cases.md) for minimum adversarial matrix and [references/handoff.md](references/handoff.md) for packaging.
