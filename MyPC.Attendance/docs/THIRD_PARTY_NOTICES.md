# Third-Party Notices — MyPC Attendance

This file lists open-source components used or planned for MyPC Attendance.
Status reflects P00 audit. Components marked **PLANNED** are not yet runtime-bundled.

## Runtime / development (Python)

| Component | License | Evidence | Status |
|-----------|---------|----------|--------|
| FastAPI | MIT | https://github.com/fastapi/fastapi | PINNED in requirements |
| Starlette | BSD-3-Clause | transitive via FastAPI | PINNED |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn | PINNED |
| Pydantic | MIT | https://github.com/pydantic/pydantic | PINNED |
| SQLAlchemy | MIT | https://github.com/sqlalchemy/sqlalchemy | PINNED |
| Alembic | MIT | https://github.com/sqlalchemy/alembic | PINNED |
| argon2-cffi | MIT | https://github.com/hynek/argon2-cffi | PINNED |
| cryptography | Apache-2.0 / BSD | https://github.com/pyca/cryptography | PINNED |
| httpx | BSD-3-Clause | https://github.com/encode/httpx | PINNED |
| openpyxl | MIT | https://foss.heptapod.net/openpyxl/openpyxl | PINNED |
| pytest | MIT | https://github.com/pytest-dev/pytest | DEV |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart | PINNED |
| itsdangerous | BSD-3-Clause | https://github.com/pallets/itsdangerous | PINNED |
| tzdata | Apache-2.0 | https://github.com/python/tzdata | PINNED |

## Frontend

| Component | License | Status |
|-----------|---------|--------|
| React | MIT | PINNED |
| Vite | MIT | PINNED |
| TypeScript | Apache-2.0 | PINNED |
| Tailwind CSS | MIT | PINNED |
| lucide-react | ISC | PINNED |

## Camera / CV (planned packaging)

| Component | License | Status |
|-----------|---------|--------|
| go2rtc | MIT | PLANNED (config template only in P00) |
| onvif-python | MIT | OPTIONAL; mock used when unavailable |
| OpenCV | Apache-2.0 | OPTIONAL in P00 (mock frames without OpenCV) |
| YuNet face detection (opencv_zoo) | MIT | PLANNED — see models/manifest.json |
| SFace recognition (opencv_zoo) | Apache-2.0 | PLANNED — see models/manifest.json |
| ReportLab | BSD | DEFERRED (PDF) |
| WinSW | MIT | PLANNED P06 |
| NSIS | zlib/libpng-like | PLANNED P06 |
| PyInstaller | GPL with exception | PLANNED P06 — compatibility decision required at packaging |
| FFmpeg | LGPL/GPL depending on build | **LICENSE_BLOCKED** until audited binary chosen |

## Explicitly rejected

- InsightFace buffalo_l and similar commercially restricted weights
- Proprietary hosted face APIs
- Unreviewed AGPL components as shortcuts

## Notes

- Product brand: MyPC Attendance. Footer attribution: “Phát triển bởi MyPC Việt Nam” → https://mypc.vn
- Do not remove upstream license notices when redistributing binaries.
