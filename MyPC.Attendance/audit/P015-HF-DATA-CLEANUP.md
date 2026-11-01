# P01.5-HF Data Cleanup Guidance

## What the Alembic scrub does

Revision `20261102_0003` rewrites `enrollment_sessions.progress_json` to drop keys such as `face_embeddings`, passwords, and dense vector dumps.

## What it does **not** do

- Does **not** securely erase SQLite WAL pages, freelist, or unvacuumed remnants.
- Does **not** rewrite filesystem snapshots, Time Machine/VSS, or off-site backups.
- Does **not** rotate the AES-GCM template key automatically.

## Operator checklist if any real employee data may have been enrolled on vulnerable builds

1. Stop the service; copy DB for forensic hold if required by policy.
2. Run migrations to HEAD (`alembic upgrade head`).
3. Review `enrollment_sessions.progress_json` for residual dense floats.
4. If real embeddings were written in plaintext: treat backups as sensitive; rotate `data/secrets/face_templates.key` **only** with a planned re-enrollment (old ciphertext becomes unreadable).
5. `VACUUM` SQLite after scrub **reduces** free-page retention but is still not certified secure deletion.
6. Document disposal of old diagnostic ZIPs that might contain DB dumps.

Never claim “secure deletion” unless a verified wipe procedure was executed and evidenced.
