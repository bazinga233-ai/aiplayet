import os
import sys
from pathlib import Path


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_runtime_root() -> Path:
    if is_frozen_runtime():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_frontend_dist_dir() -> Path:
    return get_runtime_root() / "frontend_dist"


def _tool_binary_name(name: str) -> str:
    if os.name == "nt":
        return f"{name}.exe"
    return name


def get_ffmpeg_path() -> str:
    override = os.getenv("NOVALAI_FFMPEG_PATH")
    if override:
        return override
    if is_frozen_runtime():
        return str(get_runtime_root() / _tool_binary_name("ffmpeg"))
    return "ffmpeg"


def get_ffprobe_path() -> str:
    override = os.getenv("NOVALAI_FFPROBE_PATH")
    if override:
        return override
    if is_frozen_runtime():
        return str(get_runtime_root() / _tool_binary_name("ffprobe"))
    return "ffprobe"


def get_backend_state_path() -> Path:
    return get_runtime_root() / "backend_state"


def validate_release_layout() -> tuple[bool, list[str]]:
    if not is_frozen_runtime():
        return True, []

    missing: list[str] = []
    required_paths = [
        get_frontend_dist_dir() / "index.html",
        Path(get_ffmpeg_path()),
        Path(get_ffprobe_path()),
    ]
    for path in required_paths:
        if not path.exists():
            missing.append(str(path))

    return len(missing) == 0, missing


def ensure_runtime_dirs() -> None:
    root = get_runtime_root()
    for path in (
        root / "videos",
        root / "scripts",
        root / "output",
        root / "tmp_uploads",
        root / "tmp_script_uploads",
        get_backend_state_path(),
    ):
        path.mkdir(parents=True, exist_ok=True)
