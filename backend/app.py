import json
import mimetypes
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from backend.catalog import (
    build_video_record,
    delete_results_by_video_id,
    delete_video_by_id,
    find_video_by_id,
    list_videos,
    load_results_by_video_id,
)
from backend.config import (
    FFMPEG_PATH,
    FFPROBE_PATH,
    FRONTEND_DIST_DIR,
    OUTPUT_DIR,
    SCRIPTS_DIR,
    TMP_SCRIPT_UPLOADS_DIR,
    TMP_UPLOADS_DIR,
    VIDEOS_DIR,
)
from backend.models import ASSET_TYPE_SCRIPT, ASSET_TYPE_VIDEO
from backend.viral_prediction import load_highlight_payload
from backend.runner import run_task
from backend.scoring import load_score_payload
from backend.task_queue import TaskQueue
from backend.uploads import save_upload

app = FastAPI(title="Nova Short Drama Workbench")

FRONTEND_MEDIA_TYPE_OVERRIDES = {
    ".css": "text/css",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".mjs": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


class CreateTaskRequest(BaseModel):
    video_id: str


def create_queue_service(runner=None, start_immediately: bool = True):
    return TaskQueue(
        video_lookup=find_video_by_id,
        video_catalog=list_videos,
        runner=runner or run_task,
        start_immediately=start_immediately,
    )


def get_queue_service():
    queue_service = getattr(app.state, "queue_service", None)
    if queue_service is None:
        queue_service = create_queue_service()
        app.state.queue_service = queue_service
    return queue_service


app.state.queue_service = create_queue_service()


def _path_status(path: Path) -> dict[str, object]:
    return {"path": str(path), "exists": path.exists()}


def _tool_status(tool_path: str) -> dict[str, object]:
    path_candidate = Path(tool_path)
    tool_exists = path_candidate.exists()
    if not tool_exists:
        tool_exists = shutil.which(tool_path) is not None
    return {"path": tool_path, "exists": tool_exists}


def _frontend_index_path() -> Path:
    return FRONTEND_DIST_DIR / "index.html"


def _frontend_dist_status() -> dict[str, object]:
    return {"path": str(FRONTEND_DIST_DIR), "exists": _frontend_index_path().exists()}


def _frontend_favicon_path() -> tuple[Path, str | None] | None:
    candidates = (
        ("favicon.ico", None),
        ("favicon.svg", "image/svg+xml"),
    )
    for filename, media_type in candidates:
        candidate = FRONTEND_DIST_DIR / filename
        if candidate.is_file():
            return candidate, media_type
    return None


def _frontend_media_type(path: Path) -> str | None:
    override = FRONTEND_MEDIA_TYPE_OVERRIDES.get(path.suffix.lower())
    if override is not None:
        return override
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed


def _resolve_frontend_asset(relative_path: str) -> Path | None:
    if not relative_path:
        return _frontend_index_path()

    frontend_root = FRONTEND_DIST_DIR.resolve()
    try:
        candidate = (FRONTEND_DIST_DIR / relative_path).resolve()
        candidate.relative_to(frontend_root)
    except (OSError, ValueError):
        return None

    if candidate.is_file():
        return candidate
    return None


def _serve_frontend_request(frontend_path: str):
    asset_path = _resolve_frontend_asset(frontend_path)
    if asset_path is not None and asset_path.exists():
        return FileResponse(asset_path, media_type=_frontend_media_type(asset_path))

    if frontend_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")

    if Path(frontend_path).suffix:
        raise HTTPException(status_code=404, detail="Not Found")

    index_path = _frontend_index_path()
    if index_path.exists():
        return FileResponse(index_path, media_type=_frontend_media_type(index_path))

    raise HTTPException(status_code=404, detail="Not Found")


@app.get("/api/health")
def health():
    return {
        "backend": "ok",
        "paths": {
            "videos": {"path": str(VIDEOS_DIR), "exists": VIDEOS_DIR.exists()},
            "scripts": {"path": str(SCRIPTS_DIR), "exists": SCRIPTS_DIR.exists()},
            "output": {"path": str(OUTPUT_DIR), "exists": OUTPUT_DIR.exists()},
            "tmp_uploads": {
                "path": str(TMP_UPLOADS_DIR),
                "exists": TMP_UPLOADS_DIR.exists(),
            },
            "tmp_script_uploads": {
                "path": str(TMP_SCRIPT_UPLOADS_DIR),
                "exists": TMP_SCRIPT_UPLOADS_DIR.exists(),
            },
            "frontend_dist": _frontend_dist_status(),
            "ffmpeg": _tool_status(FFMPEG_PATH),
            "ffprobe": _tool_status(FFPROBE_PATH),
        },
    }


@app.get("/favicon.ico", include_in_schema=False)
def serve_favicon():
    favicon = _frontend_favicon_path()
    if favicon is None:
        return Response(status_code=204)
    favicon_path, media_type = favicon
    return FileResponse(favicon_path, media_type=media_type)


@app.get("/api/videos")
def get_videos():
    return {"items": [item.to_dict() for item in list_videos()]}


@app.post("/api/uploads")
async def upload_video(file: UploadFile, persist: bool = True):
    file_bytes = await file.read()
    target_path = save_upload(file.filename, file_bytes, persist=persist, asset_type=ASSET_TYPE_VIDEO)
    source_type = "upload_persist" if persist else "upload_temp"
    return build_video_record(target_path, source_type=source_type).to_dict()


@app.post("/api/script-uploads")
async def upload_script(file: UploadFile, persist: bool = True):
    file_bytes = await file.read()
    target_path = save_upload(file.filename, file_bytes, persist=persist, asset_type=ASSET_TYPE_SCRIPT)
    source_type = "upload_persist" if persist else "upload_temp"
    item = build_video_record(target_path, source_type=source_type)
    output_dir = OUTPUT_DIR / item.video_name
    output_dir.mkdir(parents=True, exist_ok=True)
    script_text = file_bytes.decode("utf-8")
    (output_dir / "script.txt").write_text(script_text, encoding="utf-8")
    (output_dir / "script_original.txt").write_text(script_text, encoding="utf-8")
    return build_video_record(target_path, source_type=source_type).to_dict()


@app.get("/api/results/{video_id}")
def get_results(video_id: str):
    try:
        item, output_dir = load_results_by_video_id(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc

    if not item.output_ready:
        raise HTTPException(status_code=409, detail="results not ready")

    try:
        dialogues = json.loads((output_dir / "dialogues.json").read_text(encoding="utf-8"))
        segments = json.loads((output_dir / "segments.json").read_text(encoding="utf-8"))
        script = (output_dir / "script.txt").read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        if item.asset_type == ASSET_TYPE_SCRIPT:
            script_path = output_dir / "script.txt"
            if not script_path.exists():
                raise HTTPException(status_code=409, detail="required output files missing") from exc
            dialogues = []
            segments = []
            script = script_path.read_text(encoding="utf-8")
        else:
            raise HTTPException(status_code=409, detail="required output files missing") from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=409, detail="required output files not decodable") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=409, detail="output files corrupted") from exc

    original_script_path = output_dir / "script_original.txt"
    original_script = original_script_path.read_text(encoding="utf-8") if original_script_path.exists() else None

    try:
        score = load_score_payload(output_dir)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="score file corrupted") from exc

    try:
        highlights = load_highlight_payload(output_dir)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="highlights file corrupted") from exc

    return {
        "video": item.to_dict(),
        "dialogues": dialogues,
        "segments": segments,
        "script": script,
        "original_script": original_script,
        "asset_type": item.asset_type,
        "highlights": highlights.to_dict() if highlights else None,
        "score": score.to_dict() if score and item.asset_type == ASSET_TYPE_VIDEO else None,
        "media_url": f"/api/media/{video_id}" if item.asset_type == ASSET_TYPE_VIDEO else None,
    }


@app.get("/api/media/{video_id}")
def get_media(video_id: str):
    try:
        item = find_video_by_id(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc

    video_path = Path(item.video_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="video file missing")
    if item.asset_type != ASSET_TYPE_VIDEO:
        raise HTTPException(status_code=404, detail="media not available")

    return FileResponse(video_path, media_type="video/mp4")


def _ensure_video_not_running(video_id: str) -> None:
    if get_queue_service().has_running_task_for_video(video_id):
        raise HTTPException(status_code=409, detail="video task is running")


def _ensure_score_supported(video_id: str) -> None:
    try:
        item = find_video_by_id(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc
    if item.asset_type != ASSET_TYPE_VIDEO:
        raise HTTPException(status_code=409, detail="score not supported for script assets")


def _ensure_results_ready(video_id: str) -> None:
    try:
        item = find_video_by_id(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc
    if not item.output_ready:
        raise HTTPException(status_code=409, detail="results not ready")


def _ensure_highlight_exists(video_id: str) -> None:
    try:
        _, output_dir = load_results_by_video_id(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc

    try:
        highlights = load_highlight_payload(output_dir)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="highlights file corrupted") from exc

    if highlights is None:
        raise HTTPException(status_code=409, detail="highlights not ready")


@app.delete("/api/results/{video_id}")
def delete_results(video_id: str):
    _ensure_video_not_running(video_id)
    try:
        item = delete_results_by_video_id(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc

    return {
        "deleted": "results",
        "video_id": item.video_id,
        "video_name": item.video_name,
    }


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: str):
    _ensure_video_not_running(video_id)
    try:
        item = delete_video_by_id(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc

    return {
        "deleted": "video",
        "video_id": item.video_id,
        "video_name": item.video_name,
    }


@app.post("/api/tasks")
def create_task(payload: CreateTaskRequest):
    queue_service = get_queue_service()
    try:
        task = queue_service.enqueue_for_video(payload.video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc

    queue_service.maybe_start_next()
    return task.to_dict()


@app.post("/api/tasks/{video_id}/score")
def create_score_task(video_id: str):
    _ensure_score_supported(video_id)
    queue_service = get_queue_service()
    try:
        task = queue_service.enqueue_score_for_video(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc

    queue_service.maybe_start_next()
    return task.to_dict()


@app.post("/api/tasks/{video_id}/highlight")
def create_highlight_task(video_id: str):
    _ensure_results_ready(video_id)
    queue_service = get_queue_service()
    try:
        task = queue_service.enqueue_highlight_for_video(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc

    queue_service.maybe_start_next()
    return task.to_dict()


@app.post("/api/tasks/{video_id}/optimize")
def create_optimize_task(video_id: str):
    _ensure_highlight_exists(video_id)
    queue_service = get_queue_service()
    try:
        task = queue_service.enqueue_optimize_for_video(video_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="video not found") from exc

    queue_service.maybe_start_next()
    return task.to_dict()


@app.get("/api/tasks")
def list_tasks():
    return {"items": get_queue_service().serialize_tasks()}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    try:
        return get_queue_service().serialize_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@app.post("/api/tasks/run-all")
def run_all():
    queue_service = get_queue_service()
    count = queue_service.enqueue_all_known_videos()
    queue_service.maybe_start_next()
    return {"enqueued": count}


@app.get("/", include_in_schema=False)
def serve_frontend_root():
    return _serve_frontend_request("")


@app.get("/{frontend_path:path}", include_in_schema=False)
def serve_frontend(frontend_path: str):
    return _serve_frontend_request(frontend_path)
