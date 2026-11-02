"""Derive model/gallery/threshold pins on the server — never trust client hashes."""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.services.gallery_loader import GallerySnapshot, load_active_gallery
from app.vision.faces.template_store import FaceTemplateStore


def threshold_id_from_pipeline(pipeline: Any) -> str:
    """Pin full acceptance policy: threshold + margin + min face + detector/embedder ids."""
    cfg = getattr(pipeline, "cfg", None)
    thr = float(getattr(cfg, "match_threshold", 0.45) if cfg is not None else 0.45)
    margin = float(getattr(cfg, "match_margin", 0.05) if cfg is not None else 0.05)
    min_px = int(getattr(cfg, "min_face_px", 120) if cfg is not None else 120)
    st = pipeline.status()
    det = st.get("detector") or {}
    emb = st.get("embedder") or {}
    raw = (
        f"thr={thr:.4f}|margin={margin:.4f}|min_face={min_px}"
        f"|det={det.get('model_id')}|det_h={det.get('model_hash')}"
        f"|emb={emb.get('model_id')}|emb_h={emb.get('model_hash')}"
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"policy-{digest}"


def model_hash_from_pipeline(pipeline: Any) -> str:
    """Combined YuNet+SFace (+backend) manifest pin — detector change invalidates approvals."""
    st = pipeline.status()
    det = st.get("detector") or {}
    emb = st.get("embedder") or {}
    det_h = str(det.get("model_hash") or "").strip()
    emb_h = str(emb.get("model_hash") or "").strip()
    if not emb_h:
        raise ValueError("Không suy ra được model_hash từ pipeline.")
    cfg = getattr(pipeline, "cfg", None)
    yunet_sha = str(getattr(cfg, "yunet_sha256", "") if cfg is not None else "")
    sface_sha = str(getattr(cfg, "sface_sha256", "") if cfg is not None else "")
    raw = f"det={det_h}|emb={emb_h}|yunet_file={yunet_sha}|sface_file={sface_sha}|mode={st.get('inference_mode')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


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
