"""P1 UX: six-group operator nav and progressive-disclosure contracts in source."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "frontend" / "src" / "components" / "Layout.tsx"
CAMERA = ROOT / "frontend" / "src" / "pages" / "CameraPage.tsx"
LAB = ROOT / "frontend" / "src" / "pages" / "WindowsLabPage.tsx"
SETTINGS = ROOT / "frontend" / "src" / "pages" / "SettingsPage.tsx"


def test_six_primary_nav_groups():
    text = LAYOUT.read_text(encoding="utf-8")
    for label in ("Tổng quan", "Chấm công", "Nhân viên", "Camera", "Báo cáo", "Cài đặt"):
        assert f'label: "{label}"' in text
    # Progressive disclosure placement
    assert "/tang-ca" in text and "Chấm công" in text
    assert "/dang-ky-khuon-mat" in text and "Nhân viên" in text
    assert "/lab-windows" in text and "adminOnly: true" in text
    assert "/nhat-ky" in text and "adminOnly: true" in text
    assert "SYSTEM_ADMIN" in text


def test_camera_page_operator_primary_actions():
    text = CAMERA.read_text(encoding="utf-8")
    for label in ("Kết nối lại", "Sửa", "Kiểm tra"):
        assert label in text
    assert "Điều khiển quản trị" in text
    assert "Hiện đã lưu trữ" in text
    assert "Cấu hình MOCK" in text
    assert "delete-blockers" in text


def test_windows_lab_wizard_and_technical_details():
    text = LAB.read_text(encoding="utf-8")
    assert "Wizard" in text or "wizard" in text.lower() or "Bước" in text
    assert "Chi tiết kỹ thuật" in text
    assert "camera_lab_pass" in text
    assert "Promote PHYSICAL" in text


def test_settings_admin_section_links():
    text = SETTINGS.read_text(encoding="utf-8")
    assert "Phần quản trị" in text
    assert "/lab-windows" in text
    assert "/nhat-ky" in text
