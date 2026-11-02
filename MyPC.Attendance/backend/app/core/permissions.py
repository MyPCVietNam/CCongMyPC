"""Role / permission matrix — enforced server-side only."""

from __future__ import annotations

import json
from typing import Any

# Fine-grained permissions
CAMERA_MANAGE = "CAMERA_MANAGE"
SETTINGS_APPLY = "SETTINGS_APPLY"
EMPLOYEE_MANAGE = "EMPLOYEE_MANAGE"
ENROLLMENT_MANAGE = "ENROLLMENT_MANAGE"
BIOMETRIC_READ = "BIOMETRIC_READ"
TIMEKEEPER_APPROVE = "TIMEKEEPER_APPROVE"
DEMO_MOCK_INGEST = "DEMO_MOCK_INGEST"
AUDIT_READ = "AUDIT_READ"
ATTENDANCE_READ = "ATTENDANCE_READ"
ATTENDANCE_CORRECT = "ATTENDANCE_CORRECT"
MODEL_MANAGE = "MODEL_MANAGE"
PILOT_APPROVE = "PILOT_APPROVE"  # signed CAMERA_LAB / AUTO_VALIDATED approvals only

ROLE_DEFAULTS: dict[str, set[str]] = {
    "SYSTEM_ADMIN": {
        CAMERA_MANAGE,
        SETTINGS_APPLY,
        EMPLOYEE_MANAGE,
        ENROLLMENT_MANAGE,
        BIOMETRIC_READ,
        AUDIT_READ,
        ATTENDANCE_READ,
        MODEL_MANAGE,
        PILOT_APPROVE,
        # NOTE: SYSTEM_ADMIN does NOT get TIMEKEEPER_APPROVE by default
        # NOTE: DEMO_MOCK_INGEST only when demo mode enabled + explicit grant
    },
    "TIMEKEEPER": {
        TIMEKEEPER_APPROVE,
        ATTENDANCE_READ,
        ATTENDANCE_CORRECT,
        AUDIT_READ,
        EMPLOYEE_MANAGE,
    },
    "ENROLLMENT_OPERATOR": {
        ENROLLMENT_MANAGE,
        BIOMETRIC_READ,
        ATTENDANCE_READ,
        EMPLOYEE_MANAGE,
    },
    "AUDITOR": {
        AUDIT_READ,
        ATTENDANCE_READ,
    },
    "EMPLOYEE": {
        ATTENDANCE_READ,
    },
    "DEMO_OPERATOR": {
        DEMO_MOCK_INGEST,
        ATTENDANCE_READ,
        CAMERA_MANAGE,  # only for mock cameras in demo
        EMPLOYEE_MANAGE,
    },
}


def permissions_for_user(user_row: Any) -> set[str]:
    """Merge role defaults with explicit permissions_json grants."""
    role = getattr(user_row, "role", "") or ""
    perms = set(ROLE_DEFAULTS.get(role, set()))
    raw = getattr(user_row, "permissions_json", "[]") or "[]"
    try:
        extra = json.loads(raw)
        if isinstance(extra, list):
            perms |= {str(x) for x in extra}
    except json.JSONDecodeError:
        pass
    return perms


def user_has_permission(user_row: Any, permission: str) -> bool:
    return permission in permissions_for_user(user_row)
