"""Helpers for enumerating video and output assets."""

import hashlib
from pathlib import Path
from typing import List, Tuple

from backend.config import OUTPUT_DIR, SCRIPTS_DIR, TMP_SCRIPT_UPLOADS_DIR, TMP_UPLOADS_DIR, VIDEOS_DIR
from backend.fs_cleanup import safe_rmdir, safe_remove_tree, safe_unlink
from backend.models import ASSET_TYPE_SCRIPT, ASSET_TYPE_VIDEO, VideoItem
from backend.uploads import load_display_metadata, metadata_path

VIDEOS_ROOT: Path = VIDEOS_DIR
SCRIPTS_ROOT: Path = SCRIPTS_DIR
OUTPUT_ROOT: Path = OUTPUT_DIR
TMP_UPLOADS_ROOT: Path = TMP_UPLOADS_DIR
TMP_SCRIPT_UPLOADS_ROOT: Path = TMP_SCRIPT_UPLOADS_DIR


def build_video_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]


def iter_video_paths():
    yield from sorted(VIDEOS_ROOT.glob("*.mp4"))
    if TMP_UPLOADS_ROOT.exists():
        yield from sorted(TMP_UPLOADS_ROOT.rglob("*.mp4"))
    yield from sorted(SCRIPTS_ROOT.glob("*.txt"))
    if TMP_SCRIPT_UPLOADS_ROOT.exists():
        yield from sorted(TMP_SCRIPT_UPLOADS_ROOT.rglob("*.txt"))


def _asset_type_for_path(asset_path: Path) -> str:
    return ASSET_TYPE_SCRIPT if asset_path.suffix.lower() == ".txt" else ASSET_TYPE_VIDEO


def _source_type_for_path(asset_path: Path) -> str:
    try:
        asset_path.relative_to(TMP_UPLOADS_ROOT)
        return "upload_temp"
    except ValueError:
        try:
            asset_path.relative_to(TMP_SCRIPT_UPLOADS_ROOT)
            return "upload_temp"
        except ValueError:
            return "catalog"


def build_video_record(video_path: Path, source_type: str = "catalog") -> VideoItem:
    asset_type = _asset_type_for_path(video_path)
    video_name = video_path.stem
    output_dir = OUTPUT_ROOT / video_name
    if asset_type == ASSET_TYPE_SCRIPT:
        output_ready = (output_dir / "script.txt").exists()
    else:
        output_filenames = ("dialogues.json", "segments.json", "script.txt")
        output_ready = all((output_dir / filename).exists() for filename in output_filenames)
    display_name, display_stem = load_display_metadata(video_path)
    return VideoItem(
        video_id=build_video_id(video_path),
        video_name=video_name,
        video_path=str(video_path),
        stored_name=video_path.name,
        display_name=display_name,
        display_stem=display_stem,
        has_output=output_dir.exists(),
        output_ready=output_ready,
        source_type=source_type,
        asset_type=asset_type,
    )


def list_videos() -> List[VideoItem]:
    return [
        build_video_record(video_path, source_type=_source_type_for_path(video_path))
        for video_path in iter_video_paths()
    ]


def find_video_by_id(video_id: str) -> VideoItem:
    for item in list_videos():
        if item.video_id == video_id:
            return item
    raise KeyError(video_id)


def load_results_by_video_id(video_id: str) -> Tuple[VideoItem, Path]:
    item = find_video_by_id(video_id)
    output_dir = OUTPUT_ROOT / item.video_name
    return item, output_dir


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _cleanup_staging_root(root: Path) -> Path:
    return root / ".cleanup-staging"


def _staging_root_for_path(asset_path: Path) -> Path:
    for root in (
        OUTPUT_ROOT,
        VIDEOS_ROOT,
        TMP_UPLOADS_ROOT,
        SCRIPTS_ROOT,
        TMP_SCRIPT_UPLOADS_ROOT,
    ):
        if _is_within(asset_path, root):
            return _cleanup_staging_root(root)
    return asset_path.parent / ".cleanup-staging"


def _remove_output_dir(video_name: str) -> Path:
    output_dir = (OUTPUT_ROOT / video_name).resolve()
    if not _is_within(output_dir, OUTPUT_ROOT):
        raise ValueError("output path outside managed root")
    safe_remove_tree(output_dir, staging_root=_cleanup_staging_root(OUTPUT_ROOT))
    return output_dir


def delete_results_by_video_id(video_id: str) -> VideoItem:
    item, _ = load_results_by_video_id(video_id)
    _remove_output_dir(item.video_name)
    return item


def _cleanup_empty_upload_dirs(parent_dir: Path) -> None:
    current = parent_dir.resolve()
    upload_roots = [TMP_UPLOADS_ROOT.resolve(), TMP_SCRIPT_UPLOADS_ROOT.resolve()]
    upload_root = next((root for root in upload_roots if _is_within(current, root)), None)
    if upload_root is None:
        return

    while current != upload_root:
        if any(current.iterdir()):
            return
        safe_rmdir(current, staging_root=_cleanup_staging_root(upload_root))
        current = current.parent


def delete_video_by_id(video_id: str) -> VideoItem:
    item = find_video_by_id(video_id)
    video_path = Path(item.video_path).resolve()
    managed_roots = [
        VIDEOS_ROOT,
        TMP_UPLOADS_ROOT,
        SCRIPTS_ROOT,
        TMP_SCRIPT_UPLOADS_ROOT,
    ]
    if not any(_is_within(video_path, root) for root in managed_roots):
        raise ValueError("asset path outside managed roots")

    meta_path = metadata_path(video_path)
    parent_dir = video_path.parent

    _remove_output_dir(item.video_name)

    safe_unlink(meta_path, staging_root=_staging_root_for_path(meta_path))
    safe_unlink(video_path, staging_root=_staging_root_for_path(video_path))

    _cleanup_empty_upload_dirs(parent_dir)
    return item
