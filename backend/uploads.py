import json
from pathlib import Path
from uuid import uuid4

from backend.config import SCRIPTS_DIR, TMP_SCRIPT_UPLOADS_DIR, TMP_UPLOADS_DIR, VIDEOS_DIR
from backend.models import ASSET_TYPE_SCRIPT, ASSET_TYPE_VIDEO

META_SUFFIX = ".meta.json"
ENCODING = "utf-8"

TMP_UPLOADS_ROOT: Path = TMP_UPLOADS_DIR
TMP_SCRIPT_UPLOADS_ROOT: Path = TMP_SCRIPT_UPLOADS_DIR
SCRIPTS_ROOT: Path = SCRIPTS_DIR


def metadata_path(video_path: Path) -> Path:
    return video_path.parent / f"{video_path.name}{META_SUFFIX}"


def load_display_metadata(video_path: Path):
    meta_path = metadata_path(video_path)
    if not meta_path.exists():
        return video_path.name, video_path.stem

    try:
        payload = json.loads(meta_path.read_text(encoding=ENCODING))
    except json.JSONDecodeError:
        return video_path.name, video_path.stem

    display_name = payload.get("display_name") or video_path.name
    display_stem = payload.get("display_stem") or Path(display_name).stem
    return display_name, display_stem


def _persist_display_metadata(video_path: Path, display_name: str):
    meta_path = metadata_path(video_path)
    meta_path.write_text(
        json.dumps(
            {
                "display_name": display_name,
                "display_stem": Path(display_name).stem,
            },
            ensure_ascii=False,
        ),
        encoding=ENCODING,
    )


def save_upload(file_name: str, file_bytes: bytes, persist: bool, asset_type: str = ASSET_TYPE_VIDEO):
    if asset_type == ASSET_TYPE_SCRIPT:
        target_root = SCRIPTS_ROOT if persist else TMP_SCRIPT_UPLOADS_ROOT / uuid4().hex
    else:
        target_root = VIDEOS_DIR if persist else TMP_UPLOADS_ROOT / uuid4().hex
    target_root.mkdir(parents=True, exist_ok=True)
    stem = Path(file_name).stem
    default_suffix = ".txt" if asset_type == ASSET_TYPE_SCRIPT else ".mp4"
    suffix = Path(file_name).suffix or default_suffix
    stored_name = f"{stem}-{uuid4().hex[:8]}{suffix}"
    target_path = target_root / stored_name
    target_path.write_bytes(file_bytes)
    _persist_display_metadata(target_path, file_name)
    return target_path
