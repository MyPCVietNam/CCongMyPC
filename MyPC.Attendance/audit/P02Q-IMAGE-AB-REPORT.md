# P02Q Image A/B Report (shadow only)

## Effective policy

| Requested UI | Effective | Official decision |
|--------------|-----------|-------------------|
| Tự động / AUTO | **AUTO_TEST_ONLY** (default) | Original aligned crop |
| OFF | OFF | Original only |
| AUTO_VALIDATED | Only with admin LIVE pilot pins | Not granted in this run |
| AUTO_REVERTED | On operator rollback / hard regression | Fallback original |

## Enhancements allowed (copies only)

- Mild luminance gamma (~0.82) when dark
- Mild CLAHE on Y channel
- Reject extreme dark/bright/blur; no generative restore / super-resolution for identity

## Offline evaluator

`evaluate_pairs()` never returns `can_auto_enable_enhancement=True` from CSV alone. Hard blockers:

- `NO_OWNER_LIVE_APPROVAL`
- `NO_LIVE_SAMPLES` / `MOCK_ONLY_INSUFFICIENT`
- `HARD_REGRESSION_OR_FALSE_ACCEPT` / `ENHANCED_FALSE_ACCEPT`

## This run

Synthetic/mock pairs only — see `original_vs_enhanced_validation.csv` (pseudonymous). **Cannot** promote AUTO_VALIDATED. FACE_PILOT remains BLOCKED.
