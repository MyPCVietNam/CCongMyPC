# Freeze vs tip timeline (HF2 custody explained; HF3 labels)

## Why freeze ≠ tip

A COMPLETE audit ZIP cannot contain its own final SHA or the final remote tip commit that records that ZIP: packaging freezes bytes first; tip/sidecar commits happen after push. Labels must stay distinct.

## PR16-HF2 observed timeline (PR #18)

| Label | Commit | Meaning |
|-------|--------|---------|
| Feature / scanner fix | `279de1c53a6a9fceef72845a5b802a755eac2056` | Code freeze content reflected in early PACKAGE_META inside some downloaded COMPLETE ZIPs |
| Packaging freeze (ZIP bytes) | `7d51e13aeb489e90002a8aa38e562eb7605ec435` | Commit that adds COMPLETE-AUDIT ZIP; PR description cites this as ZIP freeze |
| Sidecar pin of freeze | `ac513d3…` | Documents freeze `7d51e13` without rewriting ZIP bytes |
| Remote PR tip (after push) | `1fa4a1c47196089a61da9ad91d524e7e2e56b80f` | PR #18 HEAD when HF3 started; includes REMOTE_PR_TIP recording |
| Earlier REMOTE_PR_TIP.txt value `005d310…` | intermediate tip | Tip moved forward after that sidecar was written; not a SHA of the ZIP itself |

Downloaded COMPLETE ZIP CRC/SHA256 can be correct while **inner** `PACKAGE_META.json` / `PACKAGING_FREEZE_COMMIT.txt` still name an earlier freeze (`279de1c`) and an intermediate tip (`005d310`). That is metadata lag, not ZIP bit-rot. Do not rewrite prior signed artifact history merely to relabel.

## PR16-HF3 labeling (this handoff)

- `BASELINE_COMMIT.txt` = HF2 tip / PR #18 HEAD used as branch point (`1fa4a1c…`)
- `FEATURE_COMMIT.txt` = HF3 code corrective commit (no COMPLETE ZIP yet)
- `PACKAGING_FREEZE_COMMIT.txt` = commit that freezes A/B/C/D ZIP bytes
- `REMOTE_PR_TIP.txt` / sidecars = tip after push (may be later than freeze)
- `PACKAGE_META.json` schema fields: `baseline`, `feature_commit`, `packaging_freeze_commit`, `remote_pr_tip` (optional/null until push), `sha256` of A/B/C only (never self-hash of COMPLETE)
