from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock, Thread
from typing import Callable
from uuid import uuid4

from backend.log_parser import parse_progress_line
from backend.models import ASSET_TYPE_VIDEO, TASK_TYPE_GENERATE, TASK_TYPE_HIGHLIGHT, TASK_TYPE_OPTIMIZE, TASK_TYPE_SCORE

LOG_TAIL_LIMIT = 50


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass
class TaskState:
    task_id: str
    video_id: str
    video_name: str
    video_path: str
    source_type: str = "catalog"
    asset_type: str = ASSET_TYPE_VIDEO
    task_type: str = TASK_TYPE_GENERATE
    parent_task_id: str | None = None
    status: str = "queued"
    stage: str = "queued"
    stage_progress: float = 0.0
    created_at: str = field(default_factory=_utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None
    logs_tail: list[str] = field(default_factory=list)
    stage_current: int | None = None
    stage_total: int | None = None

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "video_id": self.video_id,
            "video_name": self.video_name,
            "video_path": self.video_path,
            "source_type": self.source_type,
            "asset_type": self.asset_type,
            "task_type": self.task_type,
            "parent_task_id": self.parent_task_id,
            "status": self.status,
            "stage": self.stage,
            "stage_progress": self.stage_progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
            "logs_tail": list(self.logs_tail),
            "stage_current": self.stage_current,
            "stage_total": self.stage_total,
        }


class TaskQueue:
    def __init__(
        self,
        video_lookup: Callable[[str], object],
        video_catalog: Callable[[], list[object]],
        runner: Callable[[TaskState, Callable[[str], None]], int],
        start_immediately: bool = True,
    ):
        self.items: list[TaskState] = []
        self.current_task_id: str | None = None
        self._video_lookup = video_lookup
        self._video_catalog = video_catalog
        self._runner = runner
        self._start_immediately = start_immediately
        self._lock = RLock()

    def enqueue(self, task: TaskState) -> TaskState:
        with self._lock:
            self.items.append(task)
            return task

    def enqueue_for_video(self, video_id: str) -> TaskState:
        video = self._video_lookup(video_id)
        task_type = TASK_TYPE_GENERATE if video.asset_type == ASSET_TYPE_VIDEO else TASK_TYPE_HIGHLIGHT
        return self._enqueue_task_for_video(video_id, task_type=task_type)

    def enqueue_score_for_video(self, video_id: str) -> TaskState:
        return self._enqueue_task_for_video(video_id, task_type=TASK_TYPE_SCORE)

    def enqueue_highlight_for_video(self, video_id: str) -> TaskState:
        return self._enqueue_task_for_video(video_id, task_type=TASK_TYPE_HIGHLIGHT)

    def enqueue_optimize_for_video(self, video_id: str) -> TaskState:
        return self._enqueue_task_for_video(video_id, task_type=TASK_TYPE_OPTIMIZE)

    def _enqueue_task_for_video(self, video_id: str, *, task_type: str) -> TaskState:
        video = self._video_lookup(video_id)
        task = TaskState(
            task_id=uuid4().hex[:12],
            video_id=video.video_id,
            video_name=video.video_name,
            video_path=video.video_path,
            source_type=video.source_type,
            asset_type=video.asset_type,
            task_type=task_type,
        )
        return self.enqueue(task)

    def enqueue_all_known_videos(self) -> int:
        videos = self._video_catalog()
        for video in videos:
            self.enqueue(
                TaskState(
                    task_id=uuid4().hex[:12],
                    video_id=video.video_id,
                    video_name=video.video_name,
                    video_path=video.video_path,
                    source_type=video.source_type,
                    asset_type=video.asset_type,
                    task_type=TASK_TYPE_GENERATE if video.asset_type == ASSET_TYPE_VIDEO else TASK_TYPE_HIGHLIGHT,
                )
            )
        return len(videos)

    def list_tasks(self) -> list[TaskState]:
        with self._lock:
            return list(self.items)

    def get_task(self, task_id: str) -> TaskState:
        with self._lock:
            for task in self.items:
                if task.task_id == task_id:
                    return task
        raise KeyError(task_id)

    def serialize_tasks(self) -> list[dict]:
        return [task.to_dict() for task in self.list_tasks()]

    def serialize_task(self, task_id: str) -> dict:
        return self.get_task(task_id).to_dict()

    def has_running_task_for_video(self, video_id: str) -> bool:
        with self._lock:
            return any(task.video_id == video_id and task.status == "running" for task in self.items)

    def maybe_start_next(self) -> TaskState | None:
        with self._lock:
            if not self._start_immediately or self.current_task_id is not None:
                return None

            next_task = next((task for task in self.items if task.status == "queued"), None)
            if next_task is None:
                return None

            self.mark_running(next_task)
            thread = Thread(target=self._run_task, args=(next_task,), daemon=True)
            thread.start()
            return next_task

    def mark_running(self, task: TaskState) -> None:
        with self._lock:
            self.current_task_id = task.task_id
            task.status = "running"
            task.started_at = task.started_at or _utc_now()
            task.error_message = None

    def mark_completed(self, task: TaskState) -> None:
        with self._lock:
            task.status = "completed"
            task.stage = "done"
            task.stage_progress = 1.0
            task.finished_at = _utc_now()
            if self.current_task_id == task.task_id:
                self.current_task_id = None

    def mark_failed(self, task: TaskState, message: str) -> None:
        with self._lock:
            task.status = "failed"
            task.stage = "failed"
            task.error_message = message
            task.finished_at = _utc_now()
            if self.current_task_id == task.task_id:
                self.current_task_id = None

    def append_log(self, task: TaskState, line: str) -> None:
        with self._lock:
            task.logs_tail.append(line)
            task.logs_tail[:] = task.logs_tail[-LOG_TAIL_LIMIT:]

            update = parse_progress_line(line)
            if update is None:
                return

            task.stage = update.stage
            task.stage_current = update.current
            task.stage_total = update.total

            if update.stage == "done":
                task.stage_progress = 1.0
                return

            if update.current is not None and update.total:
                task.stage_progress = round(update.current / update.total, 4)
                return

            if update.stage in {"asr", "segmenting", "multimodal", "merging", "highlighting", "optimizing"}:
                task.stage_progress = 0.0

            if update.stage == "scoring":
                task.stage_progress = 0.0

    def enqueue_followup_tasks(self, parent_task: TaskState) -> list[TaskState]:
        with self._lock:
            parent_index = next(
                (index for index, item in enumerate(self.items) if item.task_id == parent_task.task_id),
                len(self.items) - 1,
            )
            highlight_task = TaskState(
                task_id=uuid4().hex[:12],
                video_id=parent_task.video_id,
                video_name=parent_task.video_name,
                video_path=parent_task.video_path,
                source_type=parent_task.source_type,
                asset_type=parent_task.asset_type,
                task_type=TASK_TYPE_HIGHLIGHT,
                parent_task_id=parent_task.task_id,
            )
            self.items[parent_index + 1:parent_index + 1] = [highlight_task]
            return [highlight_task]

    def _run_task(self, task: TaskState) -> None:
        try:
            exit_code = self._runner(task, lambda line: self.append_log(task, line))
        except Exception as exc:
            self.mark_failed(task, str(exc))
        else:
            if exit_code == 0:
                self.mark_completed(task)
                if task.task_type == TASK_TYPE_GENERATE:
                    self.enqueue_followup_tasks(task)
            else:
                self.mark_failed(task, f"{task.task_type} task exited with code {exit_code}")
        finally:
            self.maybe_start_next()
