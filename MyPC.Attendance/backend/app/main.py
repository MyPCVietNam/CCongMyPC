"""MyPC Attendance — FastAPI entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app import APP_NAME, __version__
from app.api import attendance, auth, cameras, employees, health, leave, overview, settings_api
from app.api.deps import AppState
from app.core.clock import SystemClock
from app.core.database import Base, create_db_engine, make_session_factory
from app.core.settings import AppSettings
from app.services.attendance_service import AttendanceService
from app.services.bootstrap import ensure_admin
from app.services.config_service import ConfigService
from app.services.secrets_store import SecretsStore
from app.vision.mock_camera import MockCameraGateway


def create_app(settings: AppSettings | None = None, clock=None) -> FastAPI:
    settings = settings or AppSettings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    clock = clock or SystemClock()

    engine = create_db_engine(settings.resolved_database_url())
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)

    config_service = ConfigService(clock)
    attendance_service = AttendanceService(clock)
    secrets = SecretsStore(settings.data_dir)
    camera = MockCameraGateway()
    camera.connect_mock()

    container = AppState(
        settings=settings,
        clock=clock,
        session_factory=session_factory,
        config_service=config_service,
        attendance_service=attendance_service,
        secrets=secrets,
        camera=camera,
    )

    with session_factory() as session:
        config_service.load_from_db(session)
        user, generated = ensure_admin(
            session,
            clock,
            username=settings.bootstrap_username,
            password=settings.bootstrap_password or None,
        )
        session.commit()
        container.bootstrap_password_once = generated
        if generated:
            # Write once to local setup file (not committed); never log password
            setup_path = settings.data_dir / "FIRST_RUN_ADMIN.txt"
            setup_path.write_text(
                f"username={user.username}\npassword={generated}\n"
                "Xóa tệp này sau khi đổi mật khẩu.\n",
                encoding="utf-8",
            )

    app = FastAPI(title=APP_NAME, version=__version__, docs_url="/api/docs", redoc_url=None)
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(employees.router)
    app.include_router(cameras.router)
    app.include_router(attendance.router)
    app.include_router(settings_api.router)
    app.include_router(leave.router)
    app.include_router(overview.router)

    static_dir = Path(__file__).resolve().parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/")
    def index():
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {
            "app": APP_NAME,
            "message_vi": "Giao diện chưa được build. Chạy npm run build trong frontend/.",
            "api_docs": "/api/docs",
            "health": "/api/v1/health",
        }

    assets = static_dir / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    # SPA fallback for client routes (excluding API)
    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api"):
            return {"detail": "Not Found"}
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"detail": "UI chưa build", "path": full_path}

    return app


app = create_app()
