"""AES-GCM encrypted face template storage."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models.biometric import FaceTemplate
from app.vision.faces.crypto_media import MediaCrypto


class FaceTemplateStore:
    def __init__(self, data_dir: Path, clock: Clock) -> None:
        self._clock = clock
        self._crypto = MediaCrypto(data_dir)
        self.key_version = self._crypto.key_version

    def encrypt_embedding(self, vec: np.ndarray, aad: bytes = b"mypc-face-v1") -> tuple[bytes, bytes]:
        return self._crypto.encrypt_embedding(vec, aad)

    def decrypt_embedding(self, ciphertext: bytes, nonce: bytes, aad: bytes = b"mypc-face-v1") -> np.ndarray:
        return self._crypto.decrypt_embedding(ciphertext, nonce, aad)

    def encrypt_image(self, data: bytes, aad: bytes = b"mypc-body-ref-v1") -> tuple[bytes, bytes]:
        return self._crypto.encrypt_image(data, aad)

    def decrypt_image(self, ciphertext: bytes, nonce: bytes, aad: bytes = b"mypc-body-ref-v1") -> bytes:
        return self._crypto.decrypt_image(ciphertext, nonce, aad)

    def save_template(
        self,
        session: Session,
        *,
        enrollment_id: int,
        vec: np.ndarray,
        quality_score: float,
        quality_metadata: dict,
        vector_version: str,
        active: bool = False,
        pose_slot: str = "",
    ) -> FaceTemplate:
        ct, nonce = self.encrypt_embedding(vec)
        row = FaceTemplate(
            enrollment_id=enrollment_id,
            encrypted_embedding=ct,
            nonce=nonce,
            key_version=self.key_version,
            vector_version=vector_version,
            quality_score=quality_score,
            quality_metadata=json.dumps(quality_metadata, ensure_ascii=False),
            created_at=self._clock.now_utc(),
            active=active,
            pose_slot=pose_slot or str(quality_metadata.get("pose_slot") or ""),
        )
        session.add(row)
        session.flush()
        return row

    def load_active_templates(self, session: Session) -> list[tuple[FaceTemplate, np.ndarray, int]]:
        """Returns (template, embedding, employee_id via enrollment join)."""
        from app.models.biometric import BiometricEnrollment

        rows = session.execute(
            select(FaceTemplate, BiometricEnrollment)
            .join(BiometricEnrollment, FaceTemplate.enrollment_id == BiometricEnrollment.id)
            .where(
                FaceTemplate.active.is_(True),
                FaceTemplate.deleted_at.is_(None),
                BiometricEnrollment.status == "ACTIVE",
            )
        ).all()
        out: list[tuple[FaceTemplate, np.ndarray, int]] = []
        for tmpl, enr in rows:
            vec = self.decrypt_embedding(tmpl.encrypted_embedding, tmpl.nonce)
            out.append((tmpl, vec, enr.employee_id))
        return out

    def load_enrollment_templates(
        self,
        session: Session,
        enrollment_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[tuple[FaceTemplate, np.ndarray]]:
        q = select(FaceTemplate).where(
            FaceTemplate.enrollment_id == enrollment_id,
            FaceTemplate.deleted_at.is_(None),
        )
        if not include_inactive:
            q = q.where(FaceTemplate.active.is_(True))
        rows = session.scalars(q).all()
        return [(r, self.decrypt_embedding(r.encrypted_embedding, r.nonce)) for r in rows]

    def activate_enrollment_templates(self, session: Session, enrollment_id: int) -> int:
        rows = session.scalars(
            select(FaceTemplate).where(
                FaceTemplate.enrollment_id == enrollment_id,
                FaceTemplate.deleted_at.is_(None),
            )
        ).all()
        for r in rows:
            r.active = True
        session.flush()
        return len(rows)

    def deactivate_enrollment_templates(self, session: Session, enrollment_id: int) -> int:
        rows = session.scalars(
            select(FaceTemplate).where(
                FaceTemplate.enrollment_id == enrollment_id,
                FaceTemplate.active.is_(True),
            )
        ).all()
        now = self._clock.now_utc()
        for r in rows:
            r.active = False
            r.deleted_at = now
            # Overwrite ciphertext in-place for stronger deletion (best-effort)
            r.encrypted_embedding = b"\0" * len(r.encrypted_embedding)
        session.flush()
        return len(rows)
