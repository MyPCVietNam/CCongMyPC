# First-run (P00)

1. Create venv and install `backend/requirements.txt`.
2. Build frontend (`frontend/npm install && npm run build`) so static UI is under `backend/app/static`.
3. Set `MYPC_SECRET_KEY` to a long random value for non-dev use.
4. Optionally set `MYPC_BOOTSTRAP_PASSWORD` for the first admin; otherwise a random password is written once to `data/FIRST_RUN_ADMIN.txt` (delete after changing password).
5. Start: `python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765`
6. Open http://127.0.0.1:8765 — default bind is loopback only.
7. Configure camera in **Camera & Vùng nhận diện**. Prefer Mock mode until CAMERA_LAB_PASS.

## Windows installer

P06. NSIS/WinSW packaging is **BLOCKED** on this Linux cloud agent — no fake EXE will be produced.
