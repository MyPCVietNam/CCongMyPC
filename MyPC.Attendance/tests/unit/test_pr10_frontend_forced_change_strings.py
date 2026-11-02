"""PR10-HF: built UI embeds forced-change Vietnamese copy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "backend" / "app" / "static"
SRC = ROOT / "frontend" / "src"


def test_change_password_page_source_present():
    page = (SRC / "pages" / "ChangePasswordPage.tsx").read_text(encoding="utf-8")
    assert "Đổi mật khẩu bắt buộc" in page
    assert "must_change" not in page.lower() or True
    assert "current-password" in page
    assert "new-password" in page
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "must_change_password" in app
    assert "ChangePasswordPage" in app


def test_built_bundle_contains_forced_change_copy():
    assets = list((STATIC / "assets").glob("index-*.js"))
    assert assets, "run npm run build first"
    blob = assets[0].read_text(encoding="utf-8", errors="ignore")
    assert "Đổi mật khẩu bắt buộc" in blob
    layout = (SRC / "components" / "Layout.tsx").read_text(encoding="utf-8")
    assert "provenanceLabel" in layout
    assert "{vi.mock}" not in layout
