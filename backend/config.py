import os

from backend.runtime import (
    ensure_runtime_dirs,
    get_backend_state_path,
    get_ffmpeg_path,
    get_ffprobe_path,
    get_frontend_dist_dir,
    get_runtime_root,
    is_frozen_runtime,
    validate_release_layout,
)

ROOT_DIR = get_runtime_root()
VIDEOS_DIR = ROOT_DIR / "videos"
SCRIPTS_DIR = ROOT_DIR / "scripts"
OUTPUT_DIR = ROOT_DIR / "output"
TMP_UPLOADS_DIR = ROOT_DIR / "tmp_uploads"
TMP_SCRIPT_UPLOADS_DIR = ROOT_DIR / "tmp_script_uploads"
FRONTEND_DIST_DIR = get_frontend_dist_dir()
BACKEND_STATE_PATH = get_backend_state_path()
FFMPEG_PATH = get_ffmpeg_path()
FFPROBE_PATH = get_ffprobe_path()
RELEASE_LAYOUT_VALID, RELEASE_LAYOUT_ERRORS = validate_release_layout()
if is_frozen_runtime() and not RELEASE_LAYOUT_VALID:
    missing_text = "\n".join(f"- {path}" for path in RELEASE_LAYOUT_ERRORS)
    raise RuntimeError(
        "Invalid release layout in frozen mode. Missing required runtime assets:\n"
        f"{missing_text}"
    )

LLM_BASE_URL = os.getenv("NOVALAI_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
LLM_CHAT_COMPLETIONS_URL = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
LLM_API_KEY = os.getenv("NOVALAI_LLM_API_KEY", "EMPTY")
LLM_MODEL_NAME = os.getenv("NOVALAI_LLM_MODEL_NAME", "qwen-vl")
LLM_TIMEOUT = int(os.getenv("NOVALAI_LLM_TIMEOUT", "3600"))


def ensure_runtime_directories() -> None:
    ensure_runtime_dirs()
