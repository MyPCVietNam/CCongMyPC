# P02-USB-HF3 changelog

## Patch on PR #27 — V3 additional independent corrective (in-place)

- Start free-port: probe `Read-Hf3LaunchMeta` + `Get-Win32ProcessById`; refuse with
  `EXIT_START_STALE_LAUNCHER` / `EXIT_START_STALE_IDENTITY_UNVERIFIED` / legacy PID block;
  archive redacted meta only when identities proven absent (never kill to clear).
- Contiguous Python → `-m uvicorn app.main:app` entrypoint (reject `-c` / `--reload` / `--workers`);
  DIRECT listener requires Python process name; PS mirror matches Python helper.
- Synthetic lab: approval env only; no qualified real `Stop-Process`; natural exit; default
  harness asserts mock-only kill boundary.
- Quality Guard gates + Pester extended; CI `fetch-depth: 0` for ancestry; Inspect `$profile` rename.
- Packaging hygiene: `OMITTED_HISTORICAL_ARCHIVES.md`; truthful feature vs freeze vs tip naming.
- Independent 6 additional tests GREEN; physical gates remain BLOCKED.

## Patch on PR #27 — Engineering Quality Guard v1.0 (in-place)

- Installed `repository-overlay/` at repo root: `AGENTS.md`, `.cursor/` rules/hooks/skill,
  `quality_guard/`, `.github/workflows/mypc-quality-guard.yml` (4 jobs).
- Guard selftests GREEN; V2 freeze RED preserved in disposable checkout; V3 tip remains GREEN
  without rewriting HF3 PID safety.
- GitHub Actions labeled UNRUN until workflow runs appear on the commit.

## Patch on PR #27 — PID safety corrective V3 (in-place)

- Mocked Stop-Process in default Windows PID runtime harness; no real kill of synthetic PIDs.
- Synthetic lab opt-in: health request + finally teardown + port release asserts.
- Exact tokenized `--app-dir` / port / host ownership (no IndexOf substring).
- Stop no-listener fail-closed on live/unverifiable launcher; preserve meta.
- Start failure preserves redacted evidence when cleanup blocked; Update refuses live prior launcher.

## Patch on PR #27 — PID safety corrective V2 (in-place)

- Rename kill iterators off automatic `$PID`; `Stop-VerifiedHf3Identity` / `LaunchTree`.
- Fail-closed legacy pid-only Stop; require nonblank listener/launcher creation stamps.
- Remove `$venvMarker` / folder-substring kill authorization; never kill conhost.
- Preserve launch meta on Stop refusal; success only when 18878 has no listener.
- Update: SHA256 + staged layout before owned stop; leaf Rename-Item + rollback.
- Stricter uvicorn cmdline tokens; top-level health `status=ok` + `startup_phase=READY`.
- Static independent suite GREEN; Windows PS 5.1 runtime harness added (owner-gated).

## Prior — venv redirector PID ownership (in-place)

- Verified descendant listener ownership for 18878.
- Launch meta JSON; Stop/Update share trust model; no foreign kills.

## Prior — VT_BSTR direct Read / CoInit / COM release / Update leaf rename / identity

Retained.
