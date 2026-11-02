# PR10-HF Dependency Audit

## Python

| Package | Pin | Notes |
|---------|-----|-------|
| opencv-contrib-python-headless | ==4.13.0.92 | Owner-verified YuNet/SFace APIs; single OpenCV wheel |
| numpy | >=1.26,<2.3 | Compatible with OpenCV 4.13 |
| pip check | PASS | After switch from opencv-python-headless 4.14 |

## npm (`npm audit` 2026-11-02, Node v22.23.4)

| Advisory | Severity | Package | Production reachability | Action |
|----------|----------|---------|-------------------------|--------|
| GHSA-67mh-4wv8-2f99 | moderate | esbuild ≤0.24.2 via vite@5 | Dev server only; production serves static build | **No force upgrade** (would pull Vite 8) |
| GHSA-wrjc-x8rr-rh8h6 | moderate | react-router 6.x–7.17 | CSR SPA; open-redirect via Link/navigate | Residual; avoid user-controlled `to` with backslashes |
| GHSA-337j-9hxr-rhxg | high | react-router SSR hydrate | **Not reachable** — no React Router SSR | Residual documented |

Did **not** run `npm audit fix --force`. Frontend `npm run build`: 1600 modules OK.
