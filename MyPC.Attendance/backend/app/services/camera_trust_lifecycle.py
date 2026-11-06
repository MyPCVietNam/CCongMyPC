"""Camera source / configuration identity lifecycle for physical trust (PR16-HF4).

Material source changes rotate config_revision and revoke PHYSICAL evidence, lab runs,
and HMAC approvals. Harmless edits (e.g. display name) do not. Temporarily disabling a
camera closes the operational gate without forcing a physical re-lab on resume.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import CameraDevice, CameraLiveBinding


# Fields that change the PHYSICAL evidence subject / source identity
MATERIAL_DEVICE_FIELDS = frozenset(
    {
        "host",
        "rtsp_url_override",
        "model",
        "firmware",
        "mock_mode",  # LIVE↔MOCK transition
        "credential",  # replace/remove
        "source_type",  # RTSP ↔ USB_UVC
        "usb_stable_id",  # different physical USB device
    }
)
HARMLESS_DEVICE_FIELDS = frozenset({"name", "usb_friendly_name", "usb_index_hint"})


@dataclass(frozen=True)
class MaterialChangePlan:
    reasons: list[str] = field(default_factory=list)
    rotate_revision: bool = False
    revoke_trust: bool = False
    unbind_runtime: bool = False
    mark_binding_stale: bool = False

    @property
    def is_material(self) -> bool:
        return bool(self.reasons)


def _norm(s: str | None) -> str:
    return (s or "").strip()


def _norm_host(s: str | None) -> str:
    return _norm(s).lower().rstrip(".")


def classify_camera_update(
    *,
    row: CameraDevice,
    proposed_host: str | None,
    proposed_rtsp: str | None,
    proposed_model: str | None,
    proposed_firmware: str | None,
    proposed_mock: bool | None,
    proposed_enabled: bool | None,
    credential_action: str,
    proposed_source_type: str | None = None,
    proposed_usb_stable_id: str | None = None,
) -> MaterialChangePlan:
    """Compare proposed PATCH against current row (before mutation).

    Declared ``credential_action=keep`` alone is NOT material — ``apply_camera_credentials``
    may still change the secret under keep (implicit password replace / username re-encrypt).
    Callers MUST merge ``CredentialApplyResult.changed`` via
    ``merge_effective_credential_change`` after apply.
    """
    reasons: list[str] = []
    if proposed_host is not None and _norm_host(proposed_host) != _norm_host(row.host):
        reasons.append("host")
    if proposed_rtsp is not None and _norm(proposed_rtsp) != _norm(row.rtsp_url_override):
        reasons.append("rtsp_url_override")
    if proposed_model is not None and _norm(proposed_model) != _norm(row.model):
        reasons.append("model")
    if proposed_firmware is not None and _norm(proposed_firmware) != _norm(row.firmware):
        reasons.append("firmware")
    if proposed_mock is not None and bool(proposed_mock) != bool(row.mock_mode):
        reasons.append("mock_mode")
    if proposed_source_type is not None:
        cur_st = _norm(getattr(row, "source_type", None) or "RTSP").upper()
        new_st = _norm(proposed_source_type).upper()
        if new_st and new_st != cur_st:
            reasons.append("source_type")
    if proposed_usb_stable_id is not None:
        cur_usb = _norm(getattr(row, "usb_stable_id", None) or "")
        new_usb = _norm(proposed_usb_stable_id)
        if new_usb != cur_usb:
            reasons.append("usb_stable_id")
    action = (credential_action or "keep").strip().lower()
    if action in {"replace", "remove"}:
        reasons.append("credential")

    # enabled=False alone is operational (no revoke). enabled=True resume is harmless here.
    _ = proposed_enabled

    if not reasons:
        return MaterialChangePlan()
    return MaterialChangePlan(
        reasons=reasons,
        rotate_revision=True,
        revoke_trust=True,
        unbind_runtime=True,
        mark_binding_stale=True,
    )


def classify_usb_bind_change(
    *,
    row: CameraDevice,
    stable_id: str,
    source_type: str = "USB_UVC",
) -> MaterialChangePlan:
    """Material when switching to/from USB or binding a different USB stable_id."""
    reasons: list[str] = []
    cur_st = _norm(getattr(row, "source_type", None) or "RTSP").upper()
    new_st = _norm(source_type).upper() or "USB_UVC"
    if cur_st != new_st:
        reasons.append("source_type")
    cur_usb = _norm(getattr(row, "usb_stable_id", None) or "")
    new_usb = _norm(stable_id)
    if new_usb != cur_usb:
        reasons.append("usb_stable_id")
    # RTSP credential/HMAC must never transfer — switching kinds always revokes
    if "source_type" in reasons or "usb_stable_id" in reasons:
        return MaterialChangePlan(
            reasons=reasons,
            rotate_revision=True,
            revoke_trust=True,
            unbind_runtime=True,
            mark_binding_stale=True,
        )
    return MaterialChangePlan()


def merge_effective_credential_change(
    plan: MaterialChangePlan,
    *,
    credential_changed: bool,
    declared_action: str,
    effective_action: str,
) -> MaterialChangePlan:
    """Promote plan to material when the secret store actually changed (PR16-HF5).

    Covers keep+nonempty password and keep+username re-encrypt where the helper
    returns changed=True even if action remains labeled ``keep``.
    """
    if not credential_changed:
        return plan
    reasons = list(plan.reasons)
    tag = "credential_effective"
    # Distinguish declared vs effective without leaking secrets
    if (declared_action or "").strip().lower() == "keep" and (
        (effective_action or "").strip().lower() in {"keep", "replace"}
    ):
        tag = "credential_effective_under_keep"
    if tag not in reasons and "credential" not in reasons:
        reasons.append(tag)
    elif "credential" not in reasons and tag not in reasons:
        reasons.append(tag)
    return MaterialChangePlan(
        reasons=reasons,
        rotate_revision=True,
        revoke_trust=True,
        unbind_runtime=True,
        mark_binding_stale=True,
    )


def rotate_config_revision(row: CameraDevice) -> str:
    rev = str(uuid.uuid4())
    row.config_revision = rev
    return rev


def revoke_camera_physical_trust(db: Session, *, camera_id: int, reason: str) -> dict[str, int]:
    """Revoke approvals + lab runs + PHYSICAL evidence; keep audit rows and signatures."""
    from app.services.evidence_store import revoke_physical_evidence_for_camera
    from app.services.lab_run_service import revoke_lab_runs_for_camera
    from app.services.pilot_approval import revoke_approvals

    return {
        "approvals": revoke_approvals(db, camera_id=camera_id, reason=reason),
        "lab_runs": revoke_lab_runs_for_camera(db, camera_id=camera_id, reason=reason),
        "evidence": revoke_physical_evidence_for_camera(
            db, camera_id=camera_id, reason=reason
        ),
    }


def mark_live_binding_stale(db: Session, *, camera_id: int, new_device_revision: str) -> None:
    """Keep binding row for audit but force rebind — revision/device drift is intentional."""
    binding = db.scalar(
        select(CameraLiveBinding).where(CameraLiveBinding.camera_id == camera_id)
    )
    if binding is None:
        return
    # Leave binding.config_revision at the prior value so device≠binding is detectable,
    # or clear it — prefer explicit disable + empty revision to fail closed.
    binding.enabled = False
    # Do not silently rewrite host/path to the new source; operator must reconfigure LIVE.
    if new_device_revision and binding.config_revision == new_device_revision:
        # Should not happen after rotate; ensure mismatch if somehow equal
        binding.config_revision = f"stale-before:{new_device_revision}"


def device_endpoint_identity(row: CameraDevice) -> dict[str, Any]:
    """Normalized source identity derived from CameraDevice (no secrets)."""
    source_type = _norm(getattr(row, "source_type", None) or "RTSP").upper() or "RTSP"
    usb_sid = _norm(getattr(row, "usb_stable_id", None) or "")
    if source_type == "USB_UVC":
        return {
            "scheme": "uvc",
            "host": "",
            "port": 0,
            "path": usb_sid[:24] if usb_sid else "",
            "source_type": "USB_UVC",
            "usb_stable_id": usb_sid,
        }
    host = _norm_host(row.host)
    port = 554
    path = ""
    scheme = "rtsp"
    rtsp = _norm(row.rtsp_url_override)
    if rtsp:
        p = urlparse(rtsp)
        if p.hostname:
            host = _norm_host(p.hostname)
        if p.port:
            port = int(p.port)
        path = p.path or ""
        if p.scheme:
            scheme = p.scheme.lower()
    return {
        "scheme": scheme,
        "host": host,
        "port": port,
        "path": path,
        "source_type": "RTSP",
        "usb_stable_id": "",
    }


def binding_source_mismatch(row: CameraDevice, binding: CameraLiveBinding | None) -> str:
    """Return reason code if persisted LIVE binding disagrees with device source identity."""
    if binding is None:
        return ""
    if not binding.enabled and not (binding.host or "").strip() and not (
        getattr(binding, "usb_stable_id", "") or ""
    ).strip():
        return ""
    ident = device_endpoint_identity(row)
    if ident.get("source_type") == "USB_UVC":
        b_usb = _norm(getattr(binding, "usb_stable_id", None) or "")
        d_usb = _norm(ident.get("usb_stable_id") or "")
        if b_usb and d_usb and b_usb != d_usb:
            return "USB_STABLE_ID_MISMATCH"
        if (binding.scheme or "").lower() not in {"", "uvc"} and d_usb:
            return "SOURCE_TYPE_MISMATCH"
        return ""
    b_host = _norm_host(binding.host)
    if b_host and ident["host"] and b_host != ident["host"]:
        return "SOURCE_IDENTITY_MISMATCH"
    b_path = (binding.path or "").strip()
    d_path = (ident["path"] or "").strip()
    if b_path and d_path and b_path != d_path:
        return "SOURCE_IDENTITY_MISMATCH"
    if binding.port and ident["port"] and int(binding.port) != int(ident["port"]):
        # Only when both sides have meaningful RTSP identity
        if b_host or d_path:
            return "SOURCE_IDENTITY_MISMATCH"
    b_usb = _norm(getattr(binding, "usb_stable_id", None) or "")
    if b_usb and ident.get("source_type") == "RTSP":
        return "SOURCE_TYPE_MISMATCH"
    return ""


def apply_material_trust_invalidation(
    db: Session,
    *,
    row: CameraDevice,
    state: Any,
    plan: MaterialChangePlan,
    actor: str,
) -> dict[str, Any]:
    """Rotate revision, revoke trust, unbind runtime, stale-mark binding."""
    from app.core.utc_time import utc_now
    from app.models.entities import AuditLog

    if not plan.is_material:
        return {"material": False}
    new_rev = rotate_config_revision(row) if plan.rotate_revision else (row.config_revision or "")
    reason = "CAMERA_SOURCE_MATERIAL_CHANGE:" + ",".join(plan.reasons)
    counts = {"approvals": 0, "lab_runs": 0, "evidence": 0}
    if plan.revoke_trust:
        counts = revoke_camera_physical_trust(db, camera_id=row.id, reason=reason)
    if plan.mark_binding_stale:
        mark_live_binding_stale(db, camera_id=row.id, new_device_revision=new_rev)
    if plan.unbind_runtime and state is not None and getattr(state, "camera_registry", None):
        state.camera_registry.unbind(row.id)
    row.connection_status = "NEEDS_REBIND"
    db.add(
        AuditLog(
            actor=actor,
            action="CAMERA_TRUST_INVALIDATED",
            entity_type="camera",
            entity_id=str(row.id),
            reason=f"{reason}; rev={new_rev}; counts={counts}; secrets_redacted=true",
            timestamp=utc_now(),
        )
    )
    return {
        "material": True,
        "reasons": list(plan.reasons),
        "config_revision": new_rev,
        "revoked": counts,
    }
