"""Backend data models for workbench responses and score payloads."""

from dataclasses import dataclass


TASK_TYPE_GENERATE = "generate"
TASK_TYPE_HIGHLIGHT = "highlight"
TASK_TYPE_SCORE = "score"
TASK_TYPE_OPTIMIZE = "optimize"
ASSET_TYPE_VIDEO = "video"
ASSET_TYPE_SCRIPT = "script"


@dataclass(frozen=True)
class VideoItem:
    video_id: str
    video_name: str
    video_path: str
    stored_name: str
    display_name: str
    display_stem: str
    has_output: bool
    output_ready: bool
    source_type: str = "catalog"
    asset_type: str = ASSET_TYPE_VIDEO

    def to_dict(self):
        return {
            "video_id": self.video_id,
            "video_name": self.video_name,
            "video_path": self.video_path,
            "stored_name": self.stored_name,
            "display_name": self.display_name,
            "display_stem": self.display_stem,
            "has_output": self.has_output,
            "output_ready": self.output_ready,
            "source_type": self.source_type,
            "asset_type": self.asset_type,
        }


@dataclass(frozen=True)
class ScoreDimension:
    key: str
    label: str
    score: int
    max_score: int
    reason: str

    def to_dict(self):
        return {
            "key": self.key,
            "label": self.label,
            "score": self.score,
            "max_score": self.max_score,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ScorePayload:
    version: int
    video_id: str
    video_name: str
    task_id: str
    parent_task_id: str | None
    generated_at: str
    model: dict
    total_score: int
    summary: str
    dimensions: list[ScoreDimension]

    def to_dict(self):
        return {
            "version": self.version,
            "video_id": self.video_id,
            "video_name": self.video_name,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "generated_at": self.generated_at,
            "model": dict(self.model),
            "total_score": self.total_score,
            "summary": self.summary,
            "dimensions": [item.to_dict() for item in self.dimensions],
        }


@dataclass(frozen=True)
class EmotionPoint:
    time: float
    tension: int
    risk: int

    def to_dict(self):
        return {
            "time": self.time,
            "tension": self.tension,
            "risk": self.risk,
        }


@dataclass(frozen=True)
class PredictionWindow:
    start: float
    end: float
    kind: str
    reason: str
    suggestion: str
    confidence: int

    def to_dict(self):
        return {
            "start": self.start,
            "end": self.end,
            "kind": self.kind,
            "reason": self.reason,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class BestOpportunity:
    start: float
    end: float
    kind: str
    reason: str
    suggestion: str
    confidence: int

    def to_dict(self):
        return {
            "start": self.start,
            "end": self.end,
            "kind": self.kind,
            "reason": self.reason,
            "suggestion": self.suggestion,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class HighlightPayload:
    version: int
    video_id: str
    video_name: str
    task_id: str
    parent_task_id: str | None
    generated_at: str
    model: dict
    summary: str
    breakout_score: int
    position_mode: str
    emotion_curve: list[EmotionPoint]
    risk_windows: list[PredictionWindow]
    opportunity_windows: list[PredictionWindow]
    best_opportunity: BestOpportunity | None

    def to_dict(self):
        return {
            "version": self.version,
            "video_id": self.video_id,
            "video_name": self.video_name,
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "generated_at": self.generated_at,
            "model": dict(self.model),
            "summary": self.summary,
            "breakout_score": self.breakout_score,
            "position_mode": self.position_mode,
            "emotion_curve": [item.to_dict() for item in self.emotion_curve],
            "risk_windows": [item.to_dict() for item in self.risk_windows],
            "opportunity_windows": [item.to_dict() for item in self.opportunity_windows],
            "best_opportunity": self.best_opportunity.to_dict() if self.best_opportunity else None,
        }
