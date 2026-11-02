"""Derive model/gallery/threshold pins on the server — never trust client hashes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.gallery_loader import GallerySnapshot, load_active_gallery
from app.vision.faces.template_store import FaceTemplateStore


def threshold_id_from_pipeline(pipeline: Any) -> str:
    cfg = getattr(pipeline, "cfg", None)
    thr = float(getattr(cfg, "match_threshold", 0.45) if cfg is not None else 0.45)
    return f"sface-match-{thr:.4f}"


def model_hash_from_pipeline(pipeline: Any) -> str:
    st = pipeline.status()
    emb = st.get("embedder") or {}
    h = str(emb.get("model_hash") or "").strip()
    if not h:
        raise ValueError("Không suy ra được model_hash từ pipeline.")
    return h


def derive_live_pins(
    db: Session,
    *,
    pipeline: Any,
    store: FaceTemplateStore,
) -> tuple[dict[str, str], GallerySnapshot]:
    gallery = load_active_gallery(db, store)
    pins = {
        "model_hash_pin": model_hash_from_pipeline(pipeline),
        "gallery_revision_pin": gallery.revision,
        "threshold_id_pin": threshold_id_from_pipeline(pipeline),
    }
    return pins, gallery
