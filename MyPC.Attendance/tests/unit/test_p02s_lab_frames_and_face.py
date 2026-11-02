"""P02S: distinct LIVE frames + FACE_PILOT outcome gates (PR9-01/02)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.entities import CameraDevice, Employee
from app.services import lab_run_service as lab
from app.vision.camera.gateway import (
    CameraFrame,
    ClockTrust,
    DecoderStatus,
    GatewayHealth,
    StreamProvenance,
)
from app.vision.faces.types import MatchOutcome, QualityReport, VerificationResult


class _StubGw:
    def __init__(self, mode: str = "advance", w=160, h=120):
        self.mode = mode
        self.w, self.h = w, h
        self._n = 0
        self.config_revision = "rev-a"
        self._running = True

    def health(self):
        return GatewayHealth(
            provenance=StreamProvenance.CAMERA_LIVE,
            decoder_status=DecoderStatus.OK,
            native_width=self.w,
            native_height=self.h,
            fps_estimate=8.0,
            detail_vi="stub",
            camera_lab_pass=False,
            operationally_ready=False,
        )

    def get_latest_frame(self):
        now = datetime.now(timezone.utc)
        if self.mode == "duplicate":
            img = np.full((self.h, self.w, 3), 40, dtype=np.uint8)
            return CameraFrame.from_bgr(
                img,
                frame_id="same",
                camera_id="1",
                capture_time_utc=now,
                receive_time_utc=now,
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=DecoderStatus.OK,
                config_revision=self.config_revision,
                clock_trust=ClockTrust.SERVER_RECEIVE,
                receive_monotonic=1000.0,  # never advances
            )
        if self.mode == "no_mono":
            self._n += 1
            img = np.full((self.h, self.w, 3), 40, dtype=np.uint8)
            return CameraFrame.from_bgr(
                img,
                frame_id=f"f{self._n}",
                camera_id="1",
                capture_time_utc=now,
                receive_time_utc=now,
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=DecoderStatus.OK,
                config_revision=self.config_revision,
                clock_trust=ClockTrust.SERVER_RECEIVE,
                receive_monotonic=0.0,
            )
        if self.mode == "stale":
            self._n += 1
            img = np.full((self.h, self.w, 3), 40, dtype=np.uint8)
            old = now - timedelta(seconds=30)
            return CameraFrame.from_bgr(
                img,
                frame_id=f"f{self._n}",
                camera_id="1",
                capture_time_utc=old,
                receive_time_utc=old,
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=DecoderStatus.OK,
                config_revision=self.config_revision,
                clock_trust=ClockTrust.SERVER_RECEIVE,
                receive_monotonic=1000.0 + self._n,
            )
        if self.mode == "neg_age":
            self._n += 1
            img = np.full((self.h, self.w, 3), 40, dtype=np.uint8)
            future = now + timedelta(seconds=5)
            return CameraFrame.from_bgr(
                img,
                frame_id=f"f{self._n}",
                camera_id="1",
                capture_time_utc=future,
                receive_time_utc=future,
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=DecoderStatus.OK,
                config_revision=self.config_revision,
                clock_trust=ClockTrust.SERVER_RECEIVE,
                receive_monotonic=1000.0 + self._n * 0.1,
            )
        if self.mode == "unstable_dim":
            self._n += 1
            ww = self.w if self._n % 2 else self.w + 16
            img = np.full((self.h, ww, 3), 40, dtype=np.uint8)
            return CameraFrame.from_bgr(
                img,
                frame_id=f"f{self._n}",
                camera_id="1",
                capture_time_utc=now,
                receive_time_utc=now,
                provenance=StreamProvenance.CAMERA_LIVE,
                decoder_status=DecoderStatus.OK,
                config_revision=self.config_revision,
                clock_trust=ClockTrust.SERVER_RECEIVE,
                receive_monotonic=1000.0 + self._n * 0.1,
            )
        # advance — distinct ids + advancing mono
        self._n += 1
        img = np.full((self.h, self.w, 3), 40, dtype=np.uint8)
        return CameraFrame.from_bgr(
            img,
            frame_id=f"f{self._n}",
            camera_id="1",
            capture_time_utc=now,
            receive_time_utc=now,
            provenance=StreamProvenance.CAMERA_LIVE,
            decoder_status=DecoderStatus.OK,
            config_revision=self.config_revision,
            clock_trust=ClockTrust.SERVER_RECEIVE,
            receive_monotonic=1000.0 + self._n * 0.1,
        )


class _Reg:
    def __init__(self, gw: _StubGw, cam_id: int = 1):
        from app.vision.camera.registry import BoundSource

        self._bound = BoundSource(
            camera_db_id=cam_id,
            gateway=gw,
            config_revision=gw.config_revision,
            provenance=StreamProvenance.CAMERA_LIVE,
            profile="MAIN",
        )
        self._gw = gw

    def get(self, camera_id: int):
        return self._bound if camera_id == self._bound.camera_db_id else None

    def get_frame(self, camera_id: int, **kwargs):
        from app.vision.camera.registry import FrameAccessError

        fr = self._gw.get_latest_frame()
        if fr is None:
            raise FrameAccessError("NO_FRAME", "none")
        age = (datetime.now(timezone.utc) - fr.receive_time_utc).total_seconds()
        if age < 0 and kwargs.get("for_biometric"):
            # still return; measure_live_frames checks age
            pass
        return self._bound, fr


@pytest.fixture()
def db_session(tmp_path):
    from app.core.utc_time import utc_now

    engine = create_engine(f"sqlite:///{tmp_path / 'p02s.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as s:
        now = utc_now()
        cam = CameraDevice(
            name="T", host="192.168.1.1", mock_mode=False, enabled=True, created_at=now
        )
        s.add(cam)
        s.flush()
        yield s, cam.id
        s.rollback()


def _start(db, cam_id, kind="CAMERA_LAB"):
    return lab.start_lab_run(
        db,
        camera_id=cam_id,
        kind=kind,
        operator="admin",
        pins={"model_hash_pin": "m", "gallery_revision_pin": "g", "threshold_id_pin": "t"},
    )


def test_frm01_duplicate_frame_id_fails(db_session):
    db, cam_id = db_session
    run = _start(db, cam_id)
    lab.MEASURE_TIMEOUT_S = 0.4
    with pytest.raises(lab.LabRunError) as ei:
        lab.measure_live_frames(
            db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("duplicate")), samples=3
        )
    assert ei.value.code in {"DISTINCT_FRAMES_TIMEOUT", "OBS_WINDOW_TOO_SHORT", "FPS_TOO_LOW"}
    lab.MEASURE_TIMEOUT_S = 8.0


def test_frm03_advancing_frames_pass(db_session):
    db, cam_id = db_session
    run = _start(db, cam_id)
    out = lab.measure_live_frames(
        db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("advance")), samples=3
    )
    assert out.state == lab.STATE_LIVE_MEASURED
    assert out.fps_measured and out.fps_measured >= lab.MIN_FPS
    assert out.decoded_w == 160


def test_frm02_zero_fps_cannot_physical(db_session):
    """Even if somehow LIVE_MEASURED with bad fps, promote rejects."""
    db, cam_id = db_session
    run = _start(db, cam_id)
    out = lab.measure_live_frames(
        db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("advance")), samples=3
    )
    ch = out.owner_challenge
    lab.owner_review(
        db,
        run_id=out.run_id,
        camera_id=cam_id,
        operator="admin",
        challenge=ch,
        ack_vi="Xác nhận kết nối LIVE",
    )
    out.fps_measured = 0.0
    db.flush()
    with pytest.raises(lab.LabRunError) as ei:
        lab.promote_physical(
            db,
            run_id=out.run_id,
            camera_id=cam_id,
            operator="admin",
            registry=_Reg(_StubGw("advance")),
            pins={"model_hash_pin": "m", "gallery_revision_pin": "g", "threshold_id_pin": "t"},
        )
    assert ei.value.code == "FPS_TOO_LOW"


def test_frm04_stale_fails(db_session):
    db, cam_id = db_session
    run = _start(db, cam_id)
    with pytest.raises(lab.LabRunError) as ei:
        lab.measure_live_frames(
            db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("stale")), samples=3
        )
    assert ei.value.code == "FRAME_TOO_OLD"


def test_frm05_negative_age_fails(db_session):
    db, cam_id = db_session
    run = _start(db, cam_id)
    with pytest.raises(lab.LabRunError) as ei:
        lab.measure_live_frames(
            db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("neg_age")), samples=3
        )
    assert ei.value.code == "NEGATIVE_FRAME_AGE"


def test_frm06_missing_monotonic_fails(db_session):
    db, cam_id = db_session
    run = _start(db, cam_id)
    with pytest.raises(lab.LabRunError) as ei:
        lab.measure_live_frames(
            db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("no_mono")), samples=3
        )
    assert ei.value.code == "RECV_MONOTONIC_MISSING"


def test_frm09_unstable_dims(db_session):
    db, cam_id = db_session
    run = _start(db, cam_id)
    with pytest.raises(lab.LabRunError) as ei:
        lab.measure_live_frames(
            db,
            run_id=run.run_id,
            camera_id=cam_id,
            registry=_Reg(_StubGw("unstable_dim")),
            samples=3,
        )
    assert ei.value.code == "UNSTABLE_DIMENSIONS"


class _Pipe:
    def __init__(self, outcome=MatchOutcome.UNKNOWN, emp=None):
        self.outcome = outcome
        self.emp = emp

    def verify(self, image, gallery=None, **kw):
        return VerificationResult(
            outcome=self.outcome,
            employee_id=self.emp,
            similarity=0.1,
            second_best_similarity=0.0,
            message_vi="t",
            quality=QualityReport(
                ok=True,
                score=1.0,
                face_width_px=120,
                inter_eye_px=40.0,
                blur_score=1.0,
                laplacian_var=200.0,
                pose=None,
                hard_fail=False,
                reasons_vi=[],
                breakdown={},
                metadata={},
            ),
            model_id="t",
            threshold=0.4,
            inference_mode="REAL",
        )


def test_fpt01_known_empty_gallery_rejected(db_session):
    db, cam_id = db_session
    run = _start(db, cam_id, kind="FACE_PILOT")
    lab.measure_live_frames(
        db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("advance")), samples=3
    )
    with pytest.raises(lab.LabRunError) as ei:
        lab.record_face_pilot_case(
            db,
            run_id=run.run_id,
            camera_id=cam_id,
            registry=_Reg(_StubGw("advance")),
            pipeline=_Pipe(),
            gallery_pairs=[],
            pins={"model_hash_pin": "m", "gallery_revision_pin": "g", "threshold_id_pin": "t"},
            truth_label="KNOWN:1",
            consent_ack_vi="Đồng ý",
            supervised_by="admin",
            subject_key="A",
        )
    assert ei.value.code == "GALLERY_EMPTY"


def test_fpt02_inactive_known_rejected(db_session):
    from app.core.utc_time import utc_now

    db, cam_id = db_session
    now = utc_now()
    emp = Employee(code="X", full_name="X", active=False, created_at=now, updated_at=now)
    db.add(emp)
    db.flush()
    run = _start(db, cam_id, kind="FACE_PILOT")
    lab.measure_live_frames(
        db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("advance")), samples=3
    )
    vec = np.zeros(128, dtype=np.float32)
    with pytest.raises(lab.LabRunError) as ei:
        lab.record_face_pilot_case(
            db,
            run_id=run.run_id,
            camera_id=cam_id,
            registry=_Reg(_StubGw("advance")),
            pipeline=_Pipe(),
            gallery_pairs=[(emp.id, vec)],
            pins={"model_hash_pin": "m", "gallery_revision_pin": "g", "threshold_id_pin": "t"},
            truth_label=f"KNOWN:{emp.id}",
            consent_ack_vi="Đồng ý",
            supervised_by="admin",
            subject_key="A",
        )
    assert ei.value.code == "KNOWN_INACTIVE_OR_MISSING"


def test_fpt03_wrong_blocks_owner_review(db_session):
    from app.core.utc_time import utc_now

    db, cam_id = db_session
    now = utc_now()
    emp = Employee(code="K1", full_name="K", active=True, created_at=now, updated_at=now)
    db.add(emp)
    db.flush()
    run = _start(db, cam_id, kind="FACE_PILOT")
    gw = _StubGw("advance")
    reg = _Reg(gw)
    lab.measure_live_frames(db, run_id=run.run_id, camera_id=cam_id, registry=reg, samples=3)
    vec = np.zeros(128, dtype=np.float32)
    pins = {"model_hash_pin": "m", "gallery_revision_pin": "g", "threshold_id_pin": "t"}
    # Inject WRONG + enough CORRECT labels won't matter — WRONG blocks
    for truth, pipe, subj in [
        (f"KNOWN:{emp.id}", _Pipe(MatchOutcome.MATCH, emp=999), "S1"),
        ("UNKNOWN", _Pipe(MatchOutcome.UNKNOWN), "S2"),
        ("UNKNOWN", _Pipe(MatchOutcome.UNKNOWN), "S3"),
        ("UNKNOWN", _Pipe(MatchOutcome.UNKNOWN), "S4"),
        (f"KNOWN:{emp.id}", _Pipe(MatchOutcome.MATCH, emp=emp.id), "S5"),
        (f"KNOWN:{emp.id}", _Pipe(MatchOutcome.MATCH, emp=emp.id), "S6"),
        (f"KNOWN:{emp.id}", _Pipe(MatchOutcome.MATCH, emp=emp.id), "S7"),
    ]:
        lab.record_face_pilot_case(
            db,
            run_id=run.run_id,
            camera_id=cam_id,
            registry=reg,
            pipeline=pipe,
            gallery_pairs=[(emp.id, vec), (999, vec)],
            pins=pins,
            truth_label=truth,
            consent_ack_vi="Đồng ý",
            supervised_by="admin",
            subject_key=subj,
        )
    ch = run.owner_challenge
    with pytest.raises(lab.LabRunError) as ei:
        lab.owner_review(
            db,
            run_id=run.run_id,
            camera_id=cam_id,
            operator="admin",
            challenge=ch,
            ack_vi="Xác nhận",
        )
    assert ei.value.code == "FACE_PILOT_OUTCOMES_FAILED"


def test_fpt04_false_accept_blocks(db_session):
    from app.core.utc_time import utc_now

    db, cam_id = db_session
    now = utc_now()
    emp = Employee(code="K2", full_name="K", active=True, created_at=now, updated_at=now)
    db.add(emp)
    db.flush()
    run = _start(db, cam_id, kind="FACE_PILOT")
    gw = _StubGw("advance")
    reg = _Reg(gw)
    lab.measure_live_frames(db, run_id=run.run_id, camera_id=cam_id, registry=reg, samples=3)
    vec = np.zeros(128, dtype=np.float32)
    pins = {"model_hash_pin": "m", "gallery_revision_pin": "g", "threshold_id_pin": "t"}
    lab.record_face_pilot_case(
        db,
        run_id=run.run_id,
        camera_id=cam_id,
        registry=reg,
        pipeline=_Pipe(MatchOutcome.MATCH, emp=emp.id),
        gallery_pairs=[(emp.id, vec)],
        pins=pins,
        truth_label="UNKNOWN",
        consent_ack_vi="Đồng ý",
        supervised_by="admin",
        subject_key="U1",
    )
    ch = run.owner_challenge
    with pytest.raises(lab.LabRunError) as ei:
        lab.owner_review(
            db,
            run_id=run.run_id,
            camera_id=cam_id,
            operator="admin",
            challenge=ch,
            ack_vi="Xác nhận",
        )
    assert ei.value.code == "FACE_PILOT_OUTCOMES_FAILED"


def test_fpt05_one_known_one_unknown_insufficient(db_session):
    from app.core.utc_time import utc_now

    db, cam_id = db_session
    now = utc_now()
    emp = Employee(code="K3", full_name="K", active=True, created_at=now, updated_at=now)
    db.add(emp)
    db.flush()
    run = _start(db, cam_id, kind="FACE_PILOT")
    gw = _StubGw("advance")
    reg = _Reg(gw)
    lab.measure_live_frames(db, run_id=run.run_id, camera_id=cam_id, registry=reg, samples=3)
    vec = np.zeros(128, dtype=np.float32)
    pins = {"model_hash_pin": "m", "gallery_revision_pin": "g", "threshold_id_pin": "t"}
    lab.record_face_pilot_case(
        db,
        run_id=run.run_id,
        camera_id=cam_id,
        registry=reg,
        pipeline=_Pipe(MatchOutcome.MATCH, emp=emp.id),
        gallery_pairs=[(emp.id, vec)],
        pins=pins,
        truth_label=f"KNOWN:{emp.id}",
        consent_ack_vi="Đồng ý",
        supervised_by="admin",
        subject_key="S1",
    )
    lab.record_face_pilot_case(
        db,
        run_id=run.run_id,
        camera_id=cam_id,
        registry=reg,
        pipeline=_Pipe(MatchOutcome.UNKNOWN),
        gallery_pairs=[(emp.id, vec)],
        pins=pins,
        truth_label="UNKNOWN",
        consent_ack_vi="Đồng ý",
        supervised_by="admin",
        subject_key="S2",
    )
    ch = run.owner_challenge
    with pytest.raises(lab.LabRunError) as ei:
        lab.owner_review(
            db,
            run_id=run.run_id,
            camera_id=cam_id,
            operator="admin",
            challenge=ch,
            ack_vi="Xác nhận",
        )
    assert ei.value.code == "INSUFFICIENT_EVIDENCE"


def test_fpt06_duplicate_frame_rejected(db_session):
    db, cam_id = db_session
    run = _start(db, cam_id, kind="FACE_PILOT")
    lab.measure_live_frames(
        db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("advance")), samples=3
    )
    # Force same frame_id by resetting stub counter carefully — use duplicate mode after measure
    gw = _StubGw("advance")
    gw._n = 50
    reg = _Reg(gw)
    # First case OK
    lab.record_face_pilot_case(
        db,
        run_id=run.run_id,
        camera_id=cam_id,
        registry=reg,
        pipeline=_Pipe(),
        gallery_pairs=[],
        pins={"model_hash_pin": "m", "gallery_revision_pin": "g", "threshold_id_pin": "t"},
        truth_label="UNKNOWN",
        consent_ack_vi="Đồng ý",
        supervised_by="admin",
        subject_key="U",
    )
    # Replay same n → same frame id sequence if we reset
    gw._n = 50
    with pytest.raises(lab.LabRunError) as ei:
        lab.record_face_pilot_case(
            db,
            run_id=run.run_id,
            camera_id=cam_id,
            registry=reg,
            pipeline=_Pipe(),
            gallery_pairs=[],
            pins={"model_hash_pin": "m", "gallery_revision_pin": "g", "threshold_id_pin": "t"},
            truth_label="UNKNOWN",
            consent_ack_vi="Đồng ý",
            supervised_by="admin",
            subject_key="U2",
        )
    assert ei.value.code == "DUPLICATE_CASE_FRAME"


def test_challenge_not_in_start_metrics_secret(db_session):
    db, cam_id = db_session
    run = _start(db, cam_id)
    assert run.owner_challenge
    # reveal works after measure
    lab.measure_live_frames(
        db, run_id=run.run_id, camera_id=cam_id, registry=_Reg(_StubGw("advance")), samples=3
    )
    revealed = lab.reveal_owner_challenge(
        db, run_id=run.run_id, camera_id=cam_id, operator="admin"
    )
    assert revealed["owner_challenge"] == run.owner_challenge
