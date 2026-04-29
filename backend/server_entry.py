import argparse
import json
import os
from pathlib import Path

import uvicorn
from backend.fs_cleanup import safe_unlink

CONFIG_IMPORT_ERROR = None

try:
    from backend.config import (
        BACKEND_STATE_PATH,
        OUTPUT_DIR,
        RELEASE_LAYOUT_ERRORS,
        RELEASE_LAYOUT_VALID,
        SCRIPTS_DIR,
        VIDEOS_DIR,
        ensure_runtime_directories,
    )
except RuntimeError as exc:
    CONFIG_IMPORT_ERROR = exc
    BACKEND_STATE_PATH = Path("backend_state")
    OUTPUT_DIR = Path("output")
    SCRIPTS_DIR = Path("scripts")
    VIDEOS_DIR = Path("videos")
    RELEASE_LAYOUT_ERRORS = []
    RELEASE_LAYOUT_VALID = False

    def ensure_runtime_directories() -> None:
        return None

STATE_FILE_NAME = "server.json"
DEFAULT_HOST = "127.0.0.1"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Nova Workbench packaged backend entrypoint")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    return parser.parse_args(argv)


def validate_release_layout() -> None:
    if CONFIG_IMPORT_ERROR is not None:
        message = str(CONFIG_IMPORT_ERROR).replace(
            "Invalid release layout in frozen mode.",
            "Invalid release layout.",
            1,
        )
        raise SystemExit(message)
    if RELEASE_LAYOUT_VALID:
        return

    missing_text = "\n".join(f"- {item}" for item in RELEASE_LAYOUT_ERRORS)
    raise SystemExit(
        "Invalid release layout. Missing required runtime assets:\n"
        f"{missing_text}"
    )


def ensure_release_directories() -> None:
    ensure_runtime_directories()
    for path in (VIDEOS_DIR, SCRIPTS_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def get_state_file_path() -> Path:
    return BACKEND_STATE_PATH / STATE_FILE_NAME


def _read_state_pid(state_path: Path) -> int | None:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    pid = payload.get("pid")
    return pid if isinstance(pid, int) else None


def write_backend_state(host: str, port: int) -> None:
    BACKEND_STATE_PATH.mkdir(parents=True, exist_ok=True)
    state_path = get_state_file_path()
    temp_path = state_path.with_suffix(".tmp")
    payload = {"pid": os.getpid(), "host": host, "port": port}
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        temp_path.replace(state_path)
    except PermissionError:
        state_path.write_text(
            temp_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        try:
            safe_unlink(temp_path, staging_root=BACKEND_STATE_PATH / ".cleanup-staging")
        except OSError:
            pass


def remove_backend_state(expected_pid: int | None = None) -> None:
    state_path = get_state_file_path()
    if expected_pid is not None and _read_state_pid(state_path) != expected_pid:
        return
    safe_unlink(state_path, staging_root=BACKEND_STATE_PATH / ".cleanup-staging")


def main(argv=None) -> int:
    args = parse_args(argv)
    validate_release_layout()
    ensure_release_directories()
    current_pid = os.getpid()
    try:
        write_backend_state(args.host, args.port)
        uvicorn.run("backend.app:app", host=args.host, port=args.port)
    finally:
        remove_backend_state(expected_pid=current_pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
