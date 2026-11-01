"""Offline aggregate paired A/B evaluator — never auto-enables AUTO_VALIDATED."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

LABELS = {"UNKNOWN", "AMBIGUOUS"}
SOURCES = {"MOCK", "REPLAY", "LIVE"}
CONDITIONS = {"DAY", "DUSK", "NIGHT_IR", "BACKLIGHT", "OTHER"}
REQUIRED = {
    "case_id",
    "frame_id",
    "source",
    "condition",
    "truth_id",
    "original_pred",
    "enhanced_pred",
    "original_latency_ms",
    "enhanced_latency_ms",
    "native_face_width_px",
    "model_hash",
    "gallery_revision",
    "threshold_id",
}


class EvaluationInputError(ValueError):
    pass


def _classification(truth: str, pred: str) -> str:
    if truth == "UNKNOWN":
        return "unknown_rejected" if pred in LABELS else "unknown_false_accept"
    if pred == truth:
        return "known_correct"
    return "known_missed" if pred in LABELS else "known_wrong_identity"


def _percentile(vals: list[float], percent: float) -> float | None:
    if not vals:
        return None
    sorted_vals = sorted(vals)
    pos = (len(sorted_vals) - 1) * percent / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo), 3)


def evaluate_pairs(rows: list[dict[str, str]]) -> dict[str, Any]:
    if not rows:
        return {
            "samples": 0,
            "source": "OFFLINE_REFERENCE",
            "can_auto_enable_enhancement": False,
            "blockers": ["NO_VALIDATION_SAMPLES", "NO_OWNER_LIVE_APPROVAL"],
            "per_condition": {},
        }
    sample_counts: Counter[str] = Counter()
    original_counts: Counter[str] = Counter()
    enhanced_counts: Counter[str] = Counter()
    conditions: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {"original": Counter(), "enhanced": Counter()}
    )
    original_latencies: list[float] = []
    enhanced_latencies: list[float] = []
    seen: set[tuple[str, str]] = set()
    common_version = None
    paired_correct_to_wrong = paired_unknown_to_accept = paired_correct_to_missed = corrected = 0
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict) or REQUIRED.difference(row):
            raise EvaluationInputError(f"row {i} missing mandatory fields")
        pair = (row["case_id"], row["frame_id"])
        if pair in seen:
            raise EvaluationInputError(f"row {i} duplicate frame pair")
        seen.add(pair)
        if row["source"] not in SOURCES or row["condition"] not in CONDITIONS:
            raise EvaluationInputError(f"row {i} untrusted source/condition")
        versions = (row["model_hash"], row["gallery_revision"], row["threshold_id"])
        if common_version is None:
            common_version = versions
        if versions != common_version:
            raise EvaluationInputError("mixed model/gallery/threshold revisions")
        orig_latency = float(row["original_latency_ms"])
        enh_latency = float(row["enhanced_latency_ms"])
        face_width = float(row["native_face_width_px"])
        if any(not math.isfinite(v) or v < 0 for v in (orig_latency, enh_latency, face_width)):
            raise EvaluationInputError(f"row {i} invalid numeric metric")
        orig = _classification(row["truth_id"], row["original_pred"])
        enh = _classification(row["truth_id"], row["enhanced_pred"])
        sample_counts[row["source"]] += 1
        original_counts[orig] += 1
        enhanced_counts[enh] += 1
        conditions[row["condition"]]["original"][orig] += 1
        conditions[row["condition"]]["enhanced"][enh] += 1
        original_latencies.append(orig_latency)
        enhanced_latencies.append(enh_latency)
        if orig == "known_correct" and enh == "known_wrong_identity":
            paired_correct_to_wrong += 1
        if orig == "unknown_rejected" and enh == "unknown_false_accept":
            paired_unknown_to_accept += 1
        if orig == "known_correct" and enh == "known_missed":
            paired_correct_to_missed += 1
        if orig != "known_correct" and enh == "known_correct":
            corrected += 1

    blockers = ["NO_OWNER_LIVE_APPROVAL"]
    if sample_counts.get("LIVE", 0) == 0:
        blockers.append("NO_LIVE_SAMPLES")
    if sample_counts.get("MOCK", 0) and not sample_counts.get("LIVE", 0):
        blockers.append("MOCK_ONLY_INSUFFICIENT")
    if paired_correct_to_wrong or paired_unknown_to_accept:
        blockers.append("HARD_REGRESSION_OR_FALSE_ACCEPT")
    if enhanced_counts.get("unknown_false_accept", 0) > 0:
        blockers.append("ENHANCED_FALSE_ACCEPT")

    return {
        "samples": len(rows),
        "by_source": dict(sample_counts),
        "original": dict(original_counts),
        "enhanced": dict(enhanced_counts),
        "paired": {
            "correct_to_wrong_identity": paired_correct_to_wrong,
            "unknown_rejected_to_false_accept": paired_unknown_to_accept,
            "correct_to_missed": paired_correct_to_missed,
            "improved_to_correct": corrected,
        },
        "latency_ms": {
            "original_p50": _percentile(original_latencies, 50),
            "original_p95": _percentile(original_latencies, 95),
            "enhanced_p50": _percentile(enhanced_latencies, 50),
            "enhanced_p95": _percentile(enhanced_latencies, 95),
        },
        "per_condition": {
            k: {"original": dict(v["original"]), "enhanced": dict(v["enhanced"])}
            for k, v in conditions.items()
        },
        "can_auto_enable_enhancement": False,  # NEVER true from offline CSV alone
        "blockers": blockers,
        "frozen_versions": {
            "model_hash": common_version[0] if common_version else None,
            "gallery_revision": common_version[1] if common_version else None,
            "threshold_id": common_version[2] if common_version else None,
        },
    }
