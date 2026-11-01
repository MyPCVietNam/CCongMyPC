"""MyPC Attendance — FastAPI entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app import APP_NAME, __version__
from app.api import (
    attendance,
    auth,
    auto_enrollment,
    cameras,
    employees,
    enrollment,
    health,
    leave,
    overview,
    settings_api,
)
from app.api.deps import AppState
from app.core.clock import SystemClock
from app.core.database import Base, create_db_engine, make_session_factory
from app.core.settings import AppSettings
from app.models import biometric as _biometric_models  # noqa: F401 — register tables
from app.services.attendance_service import AttendanceService
from app.services.bootstrap import ensure_admin, write_first_run_secret_file
from app.services.config_service import ConfigService
from app.services.auto_enrollment_service import AutoEnrollmentService
from app.services.enrollment_service import EnrollmentService
from app.services.secrets_store import SecretsStore
from app.vision.body.person_detector import PersonDetector
from app.vision.faces.pipeline import FacePipeline, FacePipelineConfig
from app.vision.faces.template_store import FaceTemplateStore
from app.vision.mock_camera import MockCameraGateway


def create_app(settings: AppSettings | None = None, clock=None) -> FastAPI:
    settings = settings or AppSettings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    clock = clock or SystemClock()

    engine = create_db_engine(settings.resolved_database_url())
    # Prefer Alembic in production; create_all remains for empty/dev bootstrap compatibility
    Base.metadata.create_all(engine)
    _run_alembic_if_available(settings)
    session_factory = make_session_factory(engine)

    config_service = ConfigService(clock)
    attendance_service = AttendanceService(clock)
    secrets = SecretsStore(settings.data_dir)
    camera = MockCameraGateway()
    camera.connect_mock()

    face_pipeline = FacePipeline(
        FacePipelineConfig(
            models_dir=settings.models_dir,
        )
    )
    template_store = FaceTemplateStore(settings.data_dir, clock)
    enrollment_service = EnrollmentService(clock, face_pipeline, template_store)
    auto_enrollment_service = AutoEnrollmentService(
        clock,
        face_pipeline,
        template_store,
        enrollment_service,
        person_detector=PersonDetector(),
    )

    container = AppState(
        settings=settings,
        clock=clock,
        session_factory=session_factory,
        config_service=config_service,
        attendance_service=attendance_service,
        secrets=secrets,
        camera=camera,
        face_pipeline=face_pipeline,
        template_store=template_store,
        enrollment_service=enrollment_service,
        auto_enrollment_service=auto_enrollment_service,
    )

    with session_factory() as session:
        config_service.load_from_db(session)
        user, generated = ensure_admin(
            session,
            clock,
            username=settings.bootstrap_username,
            password=settings.bootstrap_password or None,
            require_password_change=settings.require_password_change,
        )
        session.commit()
        container.bootstrap_password_once = generated
        if generated:
            write_first_run_secret_file(
                settings.data_dir / "FIRST_RUN_ADMIN.txt",
                user.username,
                generated,
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
    app.include_router(enrollment.router)
    app.include_router(auto_enrollment.router)

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

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api"):
            return {"detail": "Not Found"}
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"detail": "UI chưa build", "path": full_path}

    return app


def _run_alembic_if_available(settings: AppSettings) -> None:
    """Apply Alembic migrations when alembic.ini is present; never delete data."""
    root = Path(__file__).resolve().parents[2]
    ini = root / "alembic.ini"
    if not ini.exists():
        return
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(ini))
        cfg.set_main_option("sqlalchemy.url", settings.resolved_database_url())
        command.upgrade(cfg, "head")
    except Exception:
        # Dev/test may rely on create_all; migration failures must not wipe DB
        pass


app = create_app()
