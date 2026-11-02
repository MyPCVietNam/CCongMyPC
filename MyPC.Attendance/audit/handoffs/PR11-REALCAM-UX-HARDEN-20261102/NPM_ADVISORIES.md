# npm advisory disposition — RealCam UX Harden

**Lockfile:** `frontend/package-lock.json`  
**Command:** `npm audit` (no `npm audit fix --force`)

## Upgrades applied

| Package | Prior risk (reported) | Patched version | Exposure |
| --- | --- | --- | --- |
| vite | moderate/high (dev server / esbuild) | **6.4.5** | Build-time / Vite dev server only — not shipped as runtime API surface |
| esbuild (transitive via vite) | moderate | pulled by vite 6.4.5 | Dev/build only |
| react-router-dom | moderate | **7.18.5** | Production SPA routing — upgraded with compatibility build verification |

## Result

```
npm audit → found 0 vulnerabilities
frontend build → success (vite v6.4.5)
```

## Residual

None at packaging time. Re-run `npm audit` after any future dependency bump. Do not use `--force`.
