# Frontend npm audit (RealCam phase)

Captured without `npm audit fix --force`.

Totals: {'info': 0, 'low': 0, 'moderate': 3, 'high': 1, 'critical': 0, 'total': 4}

### `esbuild`
- severity: moderate
- range: <=0.24.2
- isDev: None
- fixAvailable: {'name': 'vite', 'version': '8.3.5', 'isSemVerMajor': True}
- via: esbuild enables any website to send any requests to the development server and read the response [moderate] https://github.com/advisories/GHSA-67mh-4wv8-2f99

### `react-router`
- severity: moderate
- range: 6.0.0 - 7.17.0
- isDev: None
- fixAvailable: {'name': 'react-router-dom', 'version': '7.18.5', 'isSemVerMajor': True}
- via: React Router: Open redirect via backslash in <Link> and useNavigate (CVE-2025-68470 bypass) [moderate] https://github.com/advisories/GHSA-wrjc-x8rr-h8h6; React Router: Arbitrary Constructor Injection via deserializeErrors() in React Router SSR Hydration [moderate] https://github.com/advisories/GHSA-337j-9hxr-rhxg

### `react-router-dom`
- severity: moderate
- range: 6.0.0-alpha.0 - 7.17.0
- isDev: None
- fixAvailable: {'name': 'react-router-dom', 'version': '7.18.5', 'isSemVerMajor': True}
- via: react-router

### `vite`
- severity: high
- range: <=6.4.3
- isDev: None
- fixAvailable: {'name': 'vite', 'version': '8.3.5', 'isSemVerMajor': True}
- via: Vite Vulnerable to Path Traversal in Optimized Deps `.map` Handling [moderate] https://github.com/advisories/GHSA-4w7w-66w2-5vf9; launch-editor: NTLMv2 hash disclosure via UNC path handling on Windows [moderate] https://github.com/advisories/GHSA-v6wh-96g9-6wx3; launch-editor: escapeCmdArgs() omits % escaping on Windows [moderate] https://github.com/advisories/GHSA-698v-4r3x-3vcv; launch-editor: Editor CLI flag misinterpretation causing arbitrary command execution for some editors [moderate] https://github.com/advisories/GHSA-r825-w8mm-5pxw; launch-editor: `fs.existsSync()` existence check can be bypassed on Windows [high] https://github.com/advisories/GHSA-587h-7wmj-h5pm; Vite: Cross origin script execution through Vite custom middleware [low] https://github.com/advisories/GHSA-9jrq-w75r-8gcw; Vite: Files outside `server.fs.allow` could be served when project paths match system paths on non-Windows machine [moderate] https://github.com/advisories/GHSA-rq7h-c2jc-7f22; vite: `server.fs.deny` bypass on Windows alternate paths [moderate] https://github.com/advisories/GHSA-fx2h-pf6j-xcff; esbuild

## Policy
- Do not force major upgrades blindly.
- Classify each as prod runtime vs build/dev tooling.
- Re-test Vite build after any upgrade.
