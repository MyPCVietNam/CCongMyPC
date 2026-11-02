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
from app.models import entities as _entity_models  # noqa: F401 — register P02Q tables
from app.services.attendance_service import AttendanceService
from app.services.bootstrap import ensure_admin, write_first_run_secret_file
from app.services.config_service import ConfigService
from app.services.auto_enrollment_service import AutoEnrollmentService
from app.services.enrollment_service import EnrollmentService
from app.services.secrets_store import SecretsStore
from app.vision.body.person_detector import PersonDetector
from app.vision.camera.gateway import MockFrameGateway
from app.vision.camera.registry import CameraSourceRegistry
from app.vision.faces.pipeline import FacePipeline, FacePipelineConfig
from app.vision.faces.template_store import FaceTemplateStore
from app.vision.mock_camera import MockCameraGateway


def create_app(settings: AppSettings | None = None, clock=None) -> FastAPI:
    settings = settings or AppSettings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    clock = clock or SystemClock()

    # Persistent session signer — never serve production with historic weak default.
    # Existing but unreadable secrets → SECRET_ACCESS_DENIED (never regenerate).
    from app.core.secret_bootstrap import WeakSecretError, load_or_create_session_secret
    from app.core.windows_secrets_acl import SecretAccessDeniedError

    try:
        settings.secret_key = load_or_create_session_secret(
            settings.data_dir,
            env_value=settings.secret_key or None,
            app_env=settings.app_env,
            demo_mode=settings.demo_mode,
            allow_ephemeral_dev=settings.app_env in {"development", "demo", "test"} or settings.demo_mode,
        )
    except SecretAccessDeniedError:
        raise
    except WeakSecretError:
        raise

    engine = create_db_engine(settings.resolved_database_url())
    # Prefer Alembic; create_all fills missing tables for empty/dev. Production migration
    # failures are recorded on the app container (fail-closed for ops), not silently ignored.
    alembic_error: str | None = None
    alembic_ok = False
    try:
        alembic_ok = _run_alembic_if_available(settings, raise_on_error=True)
    except Exception as exc:  # noqa: BLE001 — surface via health; avoid import crash on dirty local DB
        alembic_error = str(exc)
        alembic_ok = False
        if settings.is_production() and settings.app_env == "production":
            # Still allow process start for recovery tooling; mark unhealthy
            pass
    Base.metadata.create_all(engine)
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
        settings=settings,
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
        camera_gateway=MockFrameGateway(camera_id="default-mock"),
        camera_registry=CameraSourceRegistry(),
    )
    container.alembic_ok = alembic_ok
    container.alembic_error = alembic_error

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
            try:
                write_first_run_secret_file(
                    settings.data_dir / "FIRST_RUN_ADMIN.txt",
                    user.username,
                    generated,
                )
            except FileExistsError:
                # Never overwrite an existing secret file; operator must resolve manually.
                pass

    app = FastAPI(title=APP_NAME, version=__version__, docs_url="/api/docs", redoc_url=None)
    app.state.container = container

    @app.on_event("shutdown")
    def _shutdown_camera_sources() -> None:
        reg = getattr(container, "camera_registry", None)
        if reg is not None:
            try:
                reg.shutdown_all()
            except Exception:
                pass
        gw = getattr(container, "camera_gateway", None)
        if gw is not None:
            try:
                gw.stop()
            except Exception:
                pass

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


def _run_alembic_if_available(settings: AppSettings, *, raise_on_error: bool = False) -> bool:
    """Apply Alembic migrations when alembic.ini is present; never delete data."""
    root = Path(__file__).resolve().parents[2]
    ini = root / "alembic.ini"
    if not ini.exists():
        return False
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(ini))
        cfg.set_main_option("sqlalchemy.url", settings.resolved_database_url())
        command.upgrade(cfg, "head")
        return True
    except Exception as exc:
        if raise_on_error:
            raise RuntimeError(f"Alembic migration failed: {exc}") from exc
        return False


app = create_app()
