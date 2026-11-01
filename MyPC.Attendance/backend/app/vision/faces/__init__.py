"""Face detection / recognition pipeline (P01)."""

from app.vision.faces.pipeline import FacePipeline, FacePipelineConfig
from app.vision.faces.types import MatchOutcome, VerificationResult

__all__ = ["FacePipeline", "FacePipelineConfig", "MatchOutcome", "VerificationResult"]
