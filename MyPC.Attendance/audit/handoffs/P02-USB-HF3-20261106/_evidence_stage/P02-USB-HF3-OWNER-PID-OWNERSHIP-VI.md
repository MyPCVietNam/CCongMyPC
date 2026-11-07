# HF3 — Quyền sở hữu PID listener (18878)

## Vấn đề

`Start-Process` trên venv Python 3.12 có thể trả PID launcher (redirector); tiến trình
`python.exe` con mới là uvicorn thật. So khớp cứng `OwningProcess -eq launcher`
gây false-negative dù health 200.

## Quyết định tin cậy

| Relationship | Ý nghĩa |
|---|---|
| DIRECT | Listener PID = launcher và cmdline uvicorn khớp |
| VERIFIED_DESCENDANT | `python.exe` con/cháu, cmdline khớp, PPID/session proof |
| UNVERIFIED / AMBIGUOUS | Từ chối; không kill |

`conhost.exe` không bao giờ là server. HTTP 200 từ process lạ → FAIL, process lạ sống.

Start PASS chỉ khi: ownership tin cậy **và** `status=ok` **và** `startup_phase=READY`.

## Lệnh

Xem `OWNER_WINDOWS_STEPS_VI.md`. Probe chỉ-đọc (không Start): `MYPC-HF3-PID-OWNER-READONLY.ps1`.
