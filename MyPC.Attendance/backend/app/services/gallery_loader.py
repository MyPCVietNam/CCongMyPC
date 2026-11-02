"""Load ACTIVE encrypted gallery for recognition / paired A/B — never empty-as-success."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.vision.faces.template_store import FaceTemplateStore


@dataclass(frozen=True)
class GallerySnapshot:
    pairs: list[tuple[int, np.ndarray]]  # (employee_id, embedding)
    revision: str
    count: int
    status: str  # OK | BLOCKED_GALLERY


def load_active_gallery(db: Session, store: FaceTemplateStore) -> GallerySnapshot:
    rows = store.load_active_templates(db)
    if not rows:
        return GallerySnapshot([], "EMPTY", 0, "BLOCKED_GALLERY")
    pairs: list[tuple[int, np.ndarray]] = []
    digest = hashlib.sha256()
    for tmpl, vec, emp_id in rows:
        pairs.append((int(emp_id), vec))
        digest.update(str(emp_id).encode())
        digest.update(str(tmpl.id).encode())
        digest.update(str(tmpl.vector_version or "").encode())
        digest.update(str(tmpl.key_version or "").encode())
        # Content-sensitive: same ID/version with replaced embedding must change revision
        digest.update(np.ascontiguousarray(vec).tobytes())
        if getattr(tmpl, "encrypted_embedding", None) is not None:
            digest.update(bytes(tmpl.encrypted_embedding))
        if getattr(tmpl, "nonce", None) is not None:
            digest.update(bytes(tmpl.nonce))
    return GallerySnapshot(pairs, digest.hexdigest()[:32], len(pairs), "OK")
