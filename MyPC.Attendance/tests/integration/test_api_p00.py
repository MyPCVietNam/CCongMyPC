"""P00 API integration — auth, health, mock camera, settings apply, leave perms, PM ingest."""

from __future__ import annotations

from datetime import date

from app.core.clock import local_wall
from app.core.settings import OperationalConfig, default_operational_config


def login(client, username="admin", password="TestAdminPass!234"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    return data["csrf_token"]


def test_health_and_diagnostics(app_client):
    client, _ = app_client
    h = client.get("/api/v1/health")
    assert h.status_code == 200
    body = h.json()
    assert body["spec_version"] == "1.5"
    assert body["status"] == "ok"

    d = client.get("/api/v1/system/diagnostics")
    assert d.status_code == 200
    diag = d.json()
    assert diag["camera"]["rtsp_tested"] is False
    assert diag["camera"]["camera_lab_pass"] is False
    assert diag["afternoon_window"]["end_exclusive"] == "23:56:00"
    assert diag["afternoon_window"]["end_exclusive"] != "19:00:00"
    assert diag["gates"]["EXIT_VERIFICATION_GATE"] == "BLOCKED"


def test_auth_me_and_csrf(app_client):
    client, _ = app_client
    csrf = login(client)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert csrf


def test_employee_crud_and_mock_pm_selection(app_client):
    client, app = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}

    # create employee
    r = client.post(
        "/api/v1/employees",
        headers=headers,
        json={
            "code": "NV001",
            "full_name": "Nguyễn Văn An",
            "department": "Kỹ thuật",
            "job_title": "Kỹ thuật viên",
        },
    )
    assert r.status_code == 200, r.text
    emp_id = r.json()["id"]

    work_date = date(2026, 3, 2)

    # PM05 via API: 17:57 vs 18:04
    for ts in (
        local_wall(2026, 3, 2, 17, 57, 0),
        local_wall(2026, 3, 2, 18, 4, 0),
    ):
        resp = client.post(
            "/api/v1/attendance/mock-observation",
            headers=headers,
            json={
                "employee_id": emp_id,
                "work_date": work_date.isoformat(),
                "observed_at": ts.isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text

    ref = client.get(
        f"/api/v1/attendance/{emp_id}/afternoon-reference",
        params={"work_date": work_date.isoformat()},
    )
    assert ref.status_code == 200
    data = ref.json()
    assert data["afternoon_reference_observed_at"] is not None
    from datetime import datetime
    from zoneinfo import ZoneInfo

    observed = datetime.fromisoformat(data["afternoon_reference_observed_at"])
    local = observed.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    # Must be 17:57 local, not fabricated 18:00
    assert (local.hour, local.minute) == (17, 57)


def test_pm08_via_api_no_fabricated_1800(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV002", "full_name": "Trần Thị Bình"},
    ).json()
    work_date = date(2026, 3, 2)
    for ts in (local_wall(2026, 3, 2, 18, 20), local_wall(2026, 3, 2, 21, 0)):
        client.post(
            "/api/v1/attendance/mock-observation",
            headers=headers,
            json={
                "employee_id": emp["id"],
                "work_date": work_date.isoformat(),
                "observed_at": ts.isoformat(),
            },
        )
    ref = client.get(
        f"/api/v1/attendance/{emp['id']}/afternoon-reference",
        params={"work_date": work_date.isoformat()},
    ).json()
    from datetime import datetime
    from zoneinfo import ZoneInfo

    observed = datetime.fromisoformat(ref["afternoon_reference_observed_at"])
    local = observed.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    assert (local.hour, local.minute) == (18, 20)
    assert ref["selection_status"] == "AFTERNOON_LATE_FALLBACK"
    assert ref["review_required"] is True


def test_settings_apply_ack_and_reject_19_00(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    cur = client.get("/api/v1/settings").json()
    version = cur["config"]["version"]
    cfg = OperationalConfig.model_validate(cur["config"])
    cfg.windows.afternoon_recognition_end_exclusive = "23:50:00"
    ok = client.post(
        "/api/v1/settings/apply",
        headers=headers,
        json={
            "expected_version": version,
            "config": cfg.model_dump(),
            "reason": "test-apply",
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["applied"] is True
    assert body["ui_status_vi"] == "Đã áp dụng"

    # CFG03 simulate ACK failure
    cur2 = client.get("/api/v1/settings").json()
    cfg2 = OperationalConfig.model_validate(cur2["config"])
    fail = client.post(
        "/api/v1/settings/apply",
        headers=headers,
        json={
            "expected_version": cur2["config"]["version"],
            "config": cfg2.model_dump(),
            "reason": "ack-fail",
            "simulate_ack_failure": True,
        },
    )
    assert fail.status_code == 200
    assert fail.json()["applied"] is False
    assert "chưa phản hồi" in fail.json()["message_vi"]

    # Reject 19:00 end
    cur3 = client.get("/api/v1/settings").json()
    bad = OperationalConfig.model_validate(cur3["config"])
    bad.windows.afternoon_recognition_end_exclusive = "19:00:00"
    r = client.post(
        "/api/v1/settings/apply",
        headers=headers,
        json={
            "expected_version": cur3["config"]["version"],
            "config": bad.model_dump(),
            "reason": "bad",
        },
    )
    assert r.status_code == 422


def test_leave_admin_without_timekeeper_403(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV003", "full_name": "Lê Văn Cường"},
    ).json()
    leave = client.post(
        "/api/v1/leave",
        headers=headers,
        json={
            "employee_id": emp["id"],
            "kind": "AFTERNOON",
            "work_date": "2026-03-02",
            "reason": "Việc gia đình",
        },
    )
    assert leave.status_code == 200
    lid = leave.json()["id"]
    # SYSTEM_ADMIN lacks TIMEKEEPER_APPROVE by default
    approve = client.post(f"/api/v1/leave/{lid}/approve", headers=headers)
    assert approve.status_code == 403
    assert "tính công" in approve.json()["detail"]


def test_mock_camera_diagnostics_and_preview(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Mock Cam", "host": "", "mock_mode": True},
    )
    assert cam.status_code == 200
    cid = cam.json()["id"]
    diag = client.post(f"/api/v1/cameras/{cid}/diagnostics", headers=headers)
    assert diag.status_code == 200
    assert diag.json()["mock"] is True
    assert diag.json()["camera_lab_pass"] is False
    assert "mô phỏng" in diag.json()["indicator_vi"].lower() or "Mô" in diag.json()["indicator_vi"]

    preview = client.get(f"/api/v1/cameras/{cid}/preview")
    assert preview.status_code == 200
    assert preview.json()["mock"] is True
    assert preview.json()["data_base64"]

    # Live path remains BLOCKED / not CAMERA_LAB_PASS
    live = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Live", "host": "192.168.1.50", "mock_mode": False, "username": "u", "password": "p"},
    )
    live_id = live.json()["id"]
    live_diag = client.post(f"/api/v1/cameras/{live_id}/diagnostics", headers=headers).json()
    assert live_diag["camera_lab_pass"] is False
    assert live_diag["rtsp_tested"] is False
    stages = {s["name"]: s["status"] for s in live_diag["stages"]}
    assert stages.get("rtsp") == "BLOCKED"


def test_roi_invalidates_exit_calibration(app_client):
    client, _ = app_client
    csrf = login(client)
    headers = {"X-CSRF-Token": csrf}
    cam = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "ROI Cam", "mock_mode": True},
    ).json()
    r = client.put(
        f"/api/v1/cameras/{cam['id']}/regions",
        headers=headers,
        json={"name": "arrival", "x": 0.2, "y": 0.1, "w": 0.5, "h": 0.3},
    )
    assert r.status_code == 200
    assert r.json()["exit_calibration_valid"] is False


def test_default_config_has_v15_window():
    cfg = default_operational_config()
    assert cfg.windows.afternoon_recognition_start == "17:00:00"
    assert cfg.windows.afternoon_recognition_end_exclusive == "23:56:00"
    assert cfg.windows.afternoon_selection.reference_time == "18:00:00"
    assert "19:00" not in cfg.windows.afternoon_recognition_end_exclusive
