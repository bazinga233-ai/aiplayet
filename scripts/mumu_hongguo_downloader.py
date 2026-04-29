"""MuMu 模拟器中红果免费短剧官方缓存自动化脚本。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).with_name("hongguo_downloader_config.json")
DEFAULT_STATE_PATH = Path("output/hongguo_download_state.json")
DEFAULT_RUN_OUTPUT_PATH = Path("output/hongguo_download_run.json")
DEFAULT_DEBUG_DIR = Path("output/hongguo_download_debug")
DEFAULT_STAGE_DIR = Path("output/hongguo_download_stage")
DEFAULT_ARCHIVE_OUTPUT_DIR = Path("output/hongguo_videos")
DEFAULT_DEVICE_DOWNLOAD_DIR = "/sdcard/Android/data/com.phoenix.read/files/ttvideo_offline"
DOWNLOAD_MANAGEMENT_ACTIVITY = "com.dragon.read.component.download.impl.DownloadManagementActivity"
DEFAULT_VIDEO_EXTENSIONS = [".mp4", ".m4v", ".mov", ".mkv", ".avi", ".ts"]
TEMP_FILE_EXTENSIONS = {".tmp", ".download", ".part", ".crdownload"}
EPISODE_TITLE_PATTERN = re.compile(r"^第\s*\d+\s*集$")
DEFAULT_KEYWORDS = {
    "rank": ["排行榜", "热榜", "榜单", "推荐榜", "热播榜", "红果推荐榜"],
    "download": ["下载到本地", "下载", "缓存", "离线看", "离线缓存"],
    "confirm": ["确定", "确认", "继续", "立即下载", "允许"],
}
THEATER_KEYWORDS = ["剧场", "找剧"]
DOWNLOAD_MANAGEMENT_KEYWORDS = ["我的下载", "已下载", "下载中"]
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DOWNLOAD_TRIGGERED = "download_triggered"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
INVALID_FILENAME_CHARS = r'<>:"/\|?*'


class DownloaderError(RuntimeError):
    """脚本业务错误。"""


class ConfigError(DownloaderError):
    """配置错误。"""


class StepError(DownloaderError):
    """流程步骤失败。"""


def _now_timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def sanitize_name(value: str) -> str:
    """清理 Windows 目录名中的非法字符。"""

    text = " ".join(str(value or "").strip().split())
    if not text:
        return "untitled"
    sanitized = "".join("_" if char in INVALID_FILENAME_CHARS else char for char in text)
    sanitized = sanitized.rstrip(". ")
    return sanitized or "untitled"


def parse_bounds(raw: str | None) -> tuple[int, int, int, int] | None:
    if not raw:
        return None
    match = BOUNDS_PATTERN.fullmatch(raw.strip())
    if not match:
        return None
    left, top, right, bottom = (int(part) for part in match.groups())
    return left, top, right, bottom


def bounds_center(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = bounds
    return (left + right) // 2, (top + bottom) // 2


def resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def make_path(path_value: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    root = base_dir if base_dir is not None else resolve_repo_root()
    return (root / path).resolve()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    temp_path.write_text(serialized, encoding="utf-8")
    try:
        temp_path.replace(path)
    except PermissionError:
        path.write_text(serialized, encoding="utf-8")
        try:
            temp_path.unlink()
        except OSError:
            pass


@dataclass
class TimeoutConfig:
    app_launch: float = 30.0
    page_wait: float = 20.0
    download_start: float = 30.0
    file_stable: float = 300.0
    stable_window: float = 8.0
    poll_interval: float = 2.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TimeoutConfig":
        payload = payload or {}
        return cls(
            app_launch=_safe_float(payload.get("app_launch"), 30.0),
            page_wait=_safe_float(payload.get("page_wait"), 20.0),
            download_start=_safe_float(payload.get("download_start"), 30.0),
            file_stable=_safe_float(payload.get("file_stable"), 300.0),
            stable_window=_safe_float(payload.get("stable_window"), 8.0),
            poll_interval=_safe_float(payload.get("poll_interval"), 2.0),
        )


@dataclass
class DownloaderConfig:
    config_path: Path
    adb_path: str = "adb"
    adb_serial: str = ""
    adb_connect: str = ""
    app_package: str = ""
    app_activity: str = ""
    shared_folder: Path | None = None
    device_download_dir: str = DEFAULT_DEVICE_DOWNLOAD_DIR
    output_dir: Path = DEFAULT_ARCHIVE_OUTPUT_DIR
    state_path: Path = DEFAULT_STATE_PATH
    run_output_path: Path = DEFAULT_RUN_OUTPUT_PATH
    debug_dir: Path = DEFAULT_DEBUG_DIR
    stage_dir: Path = DEFAULT_STAGE_DIR
    top_n: int = 10
    resume: bool = True
    skip_success: bool = True
    archive_mode: str = "copy"
    delete_existing_before_download: bool = False
    title_resource_ids: list[str] = field(default_factory=list)
    keywords: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_KEYWORDS))
    fallback_taps: dict[str, Any] = field(default_factory=dict)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    video_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_VIDEO_EXTENSIONS))

    @classmethod
    def from_file(
        cls,
        config_path: Path,
        state_path: Path | None = None,
        run_output_path: Path | None = None,
        debug_dir: Path | None = None,
    ) -> "DownloaderConfig":
        if not config_path.exists():
            raise ConfigError(f"配置文件不存在: {config_path}")
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"配置文件不是合法 JSON: {config_path}") from exc
        if not isinstance(payload, dict):
            raise ConfigError(f"配置文件根节点必须是对象: {config_path}")

        repo_root = resolve_repo_root()
        merged_keywords: dict[str, list[str]] = {}
        raw_keywords = payload.get("keywords") or {}
        for key, defaults in DEFAULT_KEYWORDS.items():
            values = raw_keywords.get(key)
            if isinstance(values, list) and values:
                merged_keywords[key] = [str(item).strip() for item in values if str(item).strip()]
            else:
                merged_keywords[key] = list(defaults)

        raw_exts = payload.get("video_extensions")
        if isinstance(raw_exts, list) and raw_exts:
            video_extensions = []
            for item in raw_exts:
                text = str(item).strip().lower()
                if not text:
                    continue
                video_extensions.append(text if text.startswith(".") else f".{text}")
        else:
            video_extensions = list(DEFAULT_VIDEO_EXTENSIONS)

        shared_folder = payload.get("shared_folder")
        output_dir = payload.get("output_dir", DEFAULT_ARCHIVE_OUTPUT_DIR)
        cfg = cls(
            config_path=config_path,
            adb_path=str(payload.get("adb_path") or "adb"),
            adb_serial=str(payload.get("adb_serial") or "").strip(),
            adb_connect=str(payload.get("adb_connect") or "").strip(),
            app_package=str(payload.get("app_package") or "").strip(),
            app_activity=str(payload.get("app_activity") or "").strip(),
            shared_folder=make_path(shared_folder, repo_root) if shared_folder else None,
            device_download_dir=str(payload.get("device_download_dir") or DEFAULT_DEVICE_DOWNLOAD_DIR).strip(),
            output_dir=make_path(output_dir, repo_root),
            state_path=make_path(state_path or payload.get("state_path", DEFAULT_STATE_PATH), repo_root),
            run_output_path=make_path(run_output_path or payload.get("run_output_path", DEFAULT_RUN_OUTPUT_PATH), repo_root),
            debug_dir=make_path(debug_dir or payload.get("debug_dir", DEFAULT_DEBUG_DIR), repo_root),
            stage_dir=make_path(payload.get("stage_dir", DEFAULT_STAGE_DIR), repo_root),
            top_n=max(1, _safe_int(payload.get("top_n"), 10)),
            resume=bool(payload.get("resume", True)),
            skip_success=bool(payload.get("skip_success", True)),
            archive_mode=str(payload.get("archive_mode") or "copy").strip().lower(),
            delete_existing_before_download=bool(payload.get("delete_existing_before_download", False)),
            title_resource_ids=[
                str(item).strip()
                for item in (payload.get("title_resource_ids") or [])
                if str(item).strip()
            ],
            keywords=merged_keywords,
            fallback_taps=dict(payload.get("fallback_taps") or {}),
            timeouts=TimeoutConfig.from_dict(payload.get("timeouts")),
            video_extensions=video_extensions,
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.archive_mode not in {"copy", "move"}:
            raise ConfigError("archive_mode 只支持 copy 或 move。")
        if self.shared_folder is None:
            raise ConfigError("shared_folder 未配置。需要填写 MuMu 共享目录映射到宿主机的路径。")
        if not self.video_extensions:
            raise ConfigError("video_extensions 不能为空。")


@dataclass
class FileSnapshotEntry:
    path: Path
    size: int
    mtime_ns: int

    def signature(self) -> tuple[int, int]:
        return (self.size, self.mtime_ns)


@dataclass
class DeviceFileSnapshotEntry:
    path: str
    size: int
    mtime: int

    def signature(self) -> tuple[int, int]:
        return (self.size, self.mtime)


@dataclass
class TaskRecord:
    rank: int
    title: str = ""
    status: str = STATUS_PENDING
    retries: int = 0
    archived_files: list[str] = field(default_factory=list)
    last_error: str = ""
    last_debug_dir: str = ""
    updated_at: str = field(default_factory=_now_timestamp)

    def key(self) -> str:
        title_part = sanitize_name(self.title) if self.title else "unknown"
        return f"{self.rank}:{title_part}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunState:
    """断点续跑状态。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.tasks: dict[str, TaskRecord] = {}

    @classmethod
    def load(cls, path: Path) -> "RunState":
        state = cls(path)
        if not path.exists():
            return state
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"状态文件不是合法 JSON: {path}") from exc
        task_items = payload.get("tasks", []) if isinstance(payload, dict) else []
        if not isinstance(task_items, list):
            raise ConfigError(f"状态文件 tasks 字段格式错误: {path}")
        for item in task_items:
            if not isinstance(item, dict):
                continue
            record = TaskRecord(
                rank=_safe_int(item.get("rank"), 0),
                title=str(item.get("title") or ""),
                status=str(item.get("status") or STATUS_PENDING),
                retries=_safe_int(item.get("retries"), 0),
                archived_files=[str(part) for part in item.get("archived_files", [])],
                last_error=str(item.get("last_error") or ""),
                last_debug_dir=str(item.get("last_debug_dir") or ""),
                updated_at=str(item.get("updated_at") or _now_timestamp()),
            )
            state.tasks[record.key()] = record
        return state

    def get(self, rank: int, title: str = "") -> TaskRecord | None:
        title_part = sanitize_name(title) if title else "unknown"
        return self.tasks.get(f"{rank}:{title_part}")

    def upsert(self, record: TaskRecord) -> None:
        record.updated_at = _now_timestamp()
        self.tasks[record.key()] = record

    def save(self) -> None:
        payload = {
            "updated_at": _now_timestamp(),
            "tasks": [record.to_dict() for record in sorted(self.tasks.values(), key=lambda item: (item.rank, item.title))],
        }
        atomic_write_json(self.path, payload)


def take_folder_snapshot(root: Path, allowed_extensions: list[str]) -> dict[str, FileSnapshotEntry]:
    snapshot: dict[str, FileSnapshotEntry] = {}
    if not root.exists():
        return snapshot
    allowed = {ext.lower() for ext in allowed_extensions}
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        suffix = file_path.suffix.lower()
        if suffix in TEMP_FILE_EXTENSIONS:
            continue
        if allowed and suffix not in allowed:
            continue
        stat_result = file_path.stat()
        key = str(file_path.resolve())
        snapshot[key] = FileSnapshotEntry(
            path=file_path.resolve(),
            size=stat_result.st_size,
            mtime_ns=stat_result.st_mtime_ns,
        )
    return snapshot


def build_pulled_video_name(remote_path: str) -> str:
    remote_name = Path(remote_path).name
    suffix = Path(remote_name).suffix.lower()
    if suffix == ".mdl":
        return f"{Path(remote_name).stem}.mp4"
    return remote_name


def validate_video_file(path: Path) -> None:
    """用真实解码验证文件是否是可播放视频，而不是只看容器头。"""

    try:
        run_subprocess(
            [
                "ffmpeg",
                "-v",
                "error",
                "-xerror",
                "-i",
                str(path),
                "-t",
                "20",
                "-f",
                "null",
                "NUL" if os.name == "nt" else "/dev/null",
            ],
            timeout=120.0,
        )
    except StepError as exc:
        raise StepError(
            f"视频文件无法正常解码，说明它是红果 App 私有离线缓存而不是可直接播放的标准 MP4: {path}"
        ) from exc


def diff_snapshot_entries(
    baseline: dict[str, FileSnapshotEntry],
    current: dict[str, FileSnapshotEntry],
) -> dict[str, FileSnapshotEntry]:
    changed: dict[str, FileSnapshotEntry] = {}
    for key, entry in current.items():
        previous = baseline.get(key)
        if previous is None or previous.signature() != entry.signature():
            changed[key] = entry
    return changed


def diff_device_snapshot_entries(
    baseline: dict[str, DeviceFileSnapshotEntry],
    current: dict[str, DeviceFileSnapshotEntry],
) -> dict[str, DeviceFileSnapshotEntry]:
    changed: dict[str, DeviceFileSnapshotEntry] = {}
    for key, entry in current.items():
        previous = baseline.get(key)
        if previous is None or previous.signature() != entry.signature():
            changed[key] = entry
    return changed


def wait_for_stable_files(
    folder: Path,
    baseline: dict[str, FileSnapshotEntry],
    allowed_extensions: list[str],
    timeout_seconds: float,
    poll_interval_seconds: float,
    stable_window_seconds: float,
) -> list[Path]:
    deadline = time.monotonic() + timeout_seconds
    tracker: dict[str, tuple[tuple[int, int], float]] = {}
    stable_files: list[Path] = []

    while time.monotonic() < deadline:
        current = take_folder_snapshot(folder, allowed_extensions)
        changed = diff_snapshot_entries(baseline, current)
        now = time.monotonic()
        for key, entry in changed.items():
            signature = entry.signature()
            previous = tracker.get(key)
            if previous is None or previous[0] != signature:
                tracker[key] = (signature, now)
            elif now - previous[1] >= stable_window_seconds:
                stable_files.append(entry.path)
        if stable_files:
            unique_files = sorted({path.resolve() for path in stable_files})
            return unique_files
        time.sleep(poll_interval_seconds)
    return []


def archive_files(files: list[Path], target_root: Path, title: str, archive_mode: str) -> list[Path]:
    destination_dir = target_root / sanitize_name(title)
    destination_dir.mkdir(parents=True, exist_ok=True)
    archived_paths: list[Path] = []
    for source_path in files:
        target_path = destination_dir / source_path.name
        if archive_mode == "move":
            shutil.move(str(source_path), str(target_path))
        else:
            shutil.copy2(source_path, target_path)
        archived_paths.append(target_path.resolve())
    return archived_paths


def pull_device_files(
    config: DownloaderConfig,
    serial: str,
    remote_files: list[str],
    target_root: Path,
    title: str,
) -> list[Path]:
    stage_dir = config.stage_dir / sanitize_name(title) / _now_timestamp()
    stage_dir.mkdir(parents=True, exist_ok=True)
    staged_paths: list[Path] = []
    for remote_path in remote_files:
        target_path = stage_dir / build_pulled_video_name(remote_path)
        run_subprocess(
            build_adb_base_args(config, serial) + ["pull", remote_path, str(target_path)],
            timeout=120.0,
        )
        validate_video_file(target_path)
        staged_paths.append(target_path.resolve())
    return archive_files(staged_paths, target_root, title, "move")


def build_debug_dir(base_dir: Path, label: str) -> Path:
    debug_dir = base_dir / f"{_now_timestamp()}-{sanitize_name(label)}"
    debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def require_uiautomator2():
    try:
        import uiautomator2 as u2  # type: ignore
    except ImportError as exc:
        raise ConfigError(
            "当前 Python 环境缺少 uiautomator2。请先安装后再运行需要设备会话的命令。"
        ) from exc
    return u2


def run_subprocess(
    args: list[str],
    *,
    timeout: float | None = None,
    capture_output: bool = True,
    text: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            args,
            timeout=timeout,
            capture_output=capture_output,
            text=text,
            encoding="utf-8" if text else None,
            errors="replace" if text else None,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ConfigError(f"命令不存在: {args[0]}") from exc
    if check and result.returncode != 0:
        stderr_text = ""
        if capture_output:
            stderr_raw = result.stderr if result.stderr is not None else ""
            stderr_text = stderr_raw if isinstance(stderr_raw, str) else stderr_raw.decode("utf-8", errors="replace")
        raise StepError(f"命令执行失败: {' '.join(args)}\n{stderr_text.strip()}")
    return result


def build_adb_base_args(config: DownloaderConfig, serial: str | None = None) -> list[str]:
    args = [config.adb_path]
    target_serial = serial or config.adb_serial
    if target_serial:
        args.extend(["-s", target_serial])
    return args


def ensure_paths(config: DownloaderConfig) -> None:
    if config.shared_folder is None:
        raise ConfigError("shared_folder 未配置。")
    if not config.shared_folder.exists():
        raise ConfigError(f"shared_folder 不存在: {config.shared_folder}")
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.debug_dir.mkdir(parents=True, exist_ok=True)
    config.stage_dir.mkdir(parents=True, exist_ok=True)
    config.state_path.parent.mkdir(parents=True, exist_ok=True)
    config.run_output_path.parent.mkdir(parents=True, exist_ok=True)


def ensure_adb_available(config: DownloaderConfig) -> None:
    run_subprocess([config.adb_path, "version"], timeout=10.0)


def adb_connect_if_needed(config: DownloaderConfig) -> None:
    if not config.adb_connect:
        return
    run_subprocess([config.adb_path, "connect", config.adb_connect], timeout=15.0)


def adb_root_if_possible(config: DownloaderConfig, serial: str) -> None:
    try:
        run_subprocess(build_adb_base_args(config, serial) + ["root"], timeout=20.0)
        run_subprocess([config.adb_path, "wait-for-device"], timeout=30.0)
        adb_connect_if_needed(config)
    except DownloaderError:
        pass


def list_adb_devices(config: DownloaderConfig) -> list[str]:
    result = run_subprocess([config.adb_path, "devices"], timeout=10.0)
    stdout = result.stdout if isinstance(result.stdout, str) else result.stdout.decode("utf-8", errors="replace")
    devices: list[str] = []
    for line in stdout.splitlines():
        if "\tdevice" in line:
            devices.append(line.split("\t", 1)[0].strip())
    return devices


def detect_target_serial(config: DownloaderConfig) -> str:
    adb_connect_if_needed(config)
    devices = list_adb_devices(config)
    if config.adb_serial:
        if config.adb_serial not in devices:
            raise StepError(f"找不到指定设备序列号: {config.adb_serial}")
        return config.adb_serial
    if config.adb_connect:
        if config.adb_connect in devices:
            return config.adb_connect
        for candidate in devices:
            if config.adb_connect in candidate:
                return candidate
    if len(devices) == 1:
        return devices[0]
    if not devices:
        raise StepError("ADB 没有发现在线设备。请确认 MuMu 已启动并打开 ADB。")
    raise StepError(f"检测到多个设备，请在配置中填写 adb_serial。当前设备: {devices}")


def adb_capture_screenshot(config: DownloaderConfig, serial: str, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    result = run_subprocess(
        build_adb_base_args(config, serial) + ["exec-out", "screencap", "-p"],
        timeout=20.0,
        capture_output=True,
        text=False,
    )
    stdout = result.stdout if isinstance(result.stdout, bytes) else result.stdout.encode("utf-8")
    target_path.write_bytes(stdout)
    return target_path


def adb_shell(config: DownloaderConfig, serial: str, *shell_args: str, timeout: float = 15.0) -> str:
    result = run_subprocess(
        build_adb_base_args(config, serial) + ["shell", *shell_args],
        timeout=timeout,
        capture_output=True,
        text=True,
    )
    stdout = result.stdout if isinstance(result.stdout, str) else result.stdout.decode("utf-8", errors="replace")
    return stdout


def adb_start_activity(config: DownloaderConfig, serial: str, activity: str) -> None:
    if not config.app_package:
        raise ConfigError("app_package 未配置，无法打开指定页面。")
    component = f"{config.app_package}/{activity}"
    run_subprocess(
        build_adb_base_args(config, serial) + ["shell", "am", "start", "-n", component],
        timeout=20.0,
    )


def find_title_row_bounds(xml_text: str, title: str) -> tuple[int, int, int, int] | None:
    return find_clickable_ancestor_for_text(xml_text, title)


def take_device_snapshot(
    config: DownloaderConfig,
    serial: str,
    remote_dir: str,
    allowed_suffixes: list[str] | None = None,
) -> dict[str, DeviceFileSnapshotEntry]:
    suffixes = [item.lower() for item in (allowed_suffixes or [".mdl", *config.video_extensions])]
    case_items = [f"*{suffix}" for suffix in suffixes]
    case_clause = "|".join(case_items)
    shell_script = (
        f'if [ ! -d "{remote_dir}" ]; then exit 0; fi; '
        f'for f in "{remote_dir}"/*; do '
        f'[ -f "$f" ] || continue; '
        f'case "$f" in {case_clause}) stat -c "%n|%s|%Y" "$f" ;; esac; '
        f'done'
    )
    result = run_subprocess(
        build_adb_base_args(config, serial) + ["shell", shell_script],
        timeout=30.0,
        capture_output=True,
        text=True,
    )
    stdout = result.stdout if isinstance(result.stdout, str) else result.stdout.decode("utf-8", errors="replace")
    snapshot: dict[str, DeviceFileSnapshotEntry] = {}
    for line in stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 3:
            continue
        path_text, size_text, mtime_text = parts
        try:
            snapshot[path_text] = DeviceFileSnapshotEntry(
                path=path_text,
                size=int(size_text),
                mtime=int(mtime_text),
            )
        except ValueError:
            continue
    return snapshot


def wait_for_stable_device_files(
    config: DownloaderConfig,
    serial: str,
    remote_dir: str,
    baseline: dict[str, DeviceFileSnapshotEntry],
    timeout_seconds: float,
    poll_interval_seconds: float,
    stable_window_seconds: float,
) -> list[str]:
    deadline = time.monotonic() + timeout_seconds
    tracker: dict[str, tuple[tuple[int, int], float]] = {}
    stable_files: list[str] = []

    while time.monotonic() < deadline:
        current = take_device_snapshot(config, serial, remote_dir)
        changed = diff_device_snapshot_entries(baseline, current)
        now = time.monotonic()
        for key, entry in changed.items():
            signature = entry.signature()
            previous = tracker.get(key)
            if previous is None or previous[0] != signature:
                tracker[key] = (signature, now)
            elif now - previous[1] >= stable_window_seconds:
                stable_files.append(entry.path)
        if stable_files:
            return sorted(set(stable_files))
        time.sleep(poll_interval_seconds)
    return []


def get_current_focus_via_dumpsys(config: DownloaderConfig, serial: str) -> str:
    output = adb_shell(config, serial, "dumpsys", "window", "windows", timeout=25.0)
    for line in output.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            return line.strip()
    return ""


def save_debug_bundle(
    config: DownloaderConfig,
    serial: str,
    ui_session: "UiSession | None",
    label: str,
    extra_payload: dict[str, Any] | None = None,
) -> Path:
    debug_dir = build_debug_dir(config.debug_dir, label)
    adb_capture_screenshot(config, serial, debug_dir / "screen.png")
    hierarchy_path = debug_dir / "hierarchy.xml"
    if ui_session is not None:
        try:
            hierarchy_path.write_text(ui_session.dump_hierarchy(), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - 真实设备分支
            hierarchy_path.write_text(f"dump_hierarchy failed: {exc}", encoding="utf-8")
    else:
        hierarchy_path.write_text("", encoding="utf-8")
    payload = {
        "timestamp": _now_timestamp(),
        "focus": get_current_focus_via_dumpsys(config, serial),
        "extra": extra_payload or {},
    }
    atomic_write_json(debug_dir / "meta.json", payload)
    return debug_dir


def extract_text_candidates(xml_text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if not xml_text.strip():
        return candidates
    root = ET.fromstring(xml_text)
    for node in root.iter():
        text = (node.attrib.get("text") or "").strip()
        desc = (node.attrib.get("content-desc") or "").strip()
        resource_id = (node.attrib.get("resource-id") or "").strip()
        bounds = parse_bounds(node.attrib.get("bounds"))
        if bounds is None:
            continue
        candidates.append(
            {
                "text": text,
                "content_desc": desc,
                "resource_id": resource_id,
                "bounds": bounds,
                "clickable": node.attrib.get("clickable") == "true",
            }
        )
    return candidates


def find_candidate_by_keywords(
    xml_text: str,
    keywords: list[str],
    *,
    prefer_clickable: bool = True,
) -> dict[str, Any] | None:
    candidates = extract_text_candidates(xml_text)
    lowered_keywords = [item.lower() for item in keywords if item]
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        haystacks = [
            str(candidate.get("text") or "").lower(),
            str(candidate.get("content_desc") or "").lower(),
            str(candidate.get("resource_id") or "").lower(),
        ]
        if any(keyword in haystack for keyword in lowered_keywords for haystack in haystacks):
            matches.append(candidate)
    if not matches:
        return None
    if prefer_clickable:
        for item in matches:
            if item.get("clickable"):
                return item
    return matches[0]


def find_clickable_ancestor_for_text(xml_text: str, text_value: str) -> tuple[int, int, int, int] | None:
    """在 UI 树里找到指定文本所在节点的可点击父容器。"""

    if not xml_text.strip():
        return None
    root = ET.fromstring(xml_text)

    def visit(node: ET.Element, clickable_stack: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
        bounds = parse_bounds(node.attrib.get("bounds"))
        next_stack = list(clickable_stack)
        if bounds is not None and node.attrib.get("clickable") == "true":
            next_stack.append(bounds)
        node_text = (node.attrib.get("text") or "").strip()
        if node_text == text_value and next_stack:
            return next_stack[-1]
        for child in list(node):
            found = visit(child, next_stack)
            if found is not None:
                return found
        return None

    return visit(root, [])


def find_clickable_ancestor_for_resource_id(
    xml_text: str,
    resource_id: str,
    *,
    text_pattern: re.Pattern[str] | None = None,
) -> tuple[int, int, int, int] | None:
    """在 UI 树里找到指定 resource-id 所在节点的可点击父容器。"""

    if not xml_text.strip():
        return None
    root = ET.fromstring(xml_text)

    def visit(node: ET.Element, clickable_stack: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
        bounds = parse_bounds(node.attrib.get("bounds"))
        next_stack = list(clickable_stack)
        if bounds is not None and node.attrib.get("clickable") == "true":
            next_stack.append(bounds)

        node_resource_id = (node.attrib.get("resource-id") or "").strip()
        node_text = (node.attrib.get("text") or "").strip()
        if node_resource_id == resource_id and (text_pattern is None or text_pattern.fullmatch(node_text)):
            if bounds is not None and node.attrib.get("clickable") == "true":
                return bounds
            if next_stack:
                return next_stack[-1]

        for child in list(node):
            found = visit(child, next_stack)
            if found is not None:
                return found
        return None

    return visit(root, [])


def click_text_ancestor(ui_session: UiSession, text_value: str) -> bool:
    bounds = find_clickable_ancestor_for_text(ui_session.dump_hierarchy(), text_value)
    if bounds is None:
        return False
    x, y = bounds_center(bounds)
    ui_session.click(x, y)
    return True


def click_resource_id_ancestor(
    ui_session: "UiSession",
    resource_id: str,
    *,
    text_pattern: re.Pattern[str] | None = None,
) -> bool:
    bounds = find_clickable_ancestor_for_resource_id(
        ui_session.dump_hierarchy(),
        resource_id,
        text_pattern=text_pattern,
    )
    if bounds is None:
        return False
    x, y = bounds_center(bounds)
    ui_session.click(x, y)
    return True


def is_download_sheet_open(ui_session: "UiSession") -> bool:
    xml_text = ui_session.dump_hierarchy()
    title_candidate = find_candidate_by_keywords(xml_text, ["下载到本地"], prefer_clickable=False)
    start_candidate = find_candidate_by_keywords(xml_text, ["开始下载"], prefer_clickable=False)
    return title_candidate is not None and start_candidate is not None


def select_download_episodes(ui_session: "UiSession") -> bool:
    if ui_session.click_keywords(["全选"]):
        time.sleep(0.8)
        return True
    if click_resource_id_ancestor(
        ui_session,
        "com.phoenix.read:id/ivi",
        text_pattern=re.compile(r"\d+"),
    ):
        time.sleep(0.8)
        return True
    if click_text_ancestor(ui_session, "1"):
        time.sleep(0.8)
        return True
    return False


def finish_download_sheet(ui_session: "UiSession", config: DownloaderConfig) -> bool:
    if not is_download_sheet_open(ui_session):
        return False
    if not select_download_episodes(ui_session):
        return False
    if not ui_session.click_keywords(["开始下载"]):
        return False
    time.sleep(1.0)
    ui_session.click_keywords(config.keywords["confirm"])
    return True


class UiSession:
    """uiautomator2 会话封装。"""

    def __init__(self, config: DownloaderConfig, serial: str) -> None:
        self.config = config
        self.serial = serial
        u2 = require_uiautomator2()
        self.device = u2.connect(serial)
        self.device.settings["wait_timeout"] = max(3.0, config.timeouts.page_wait)

    def dump_hierarchy(self) -> str:
        return str(self.device.dump_hierarchy(pretty=True))

    def screenshot(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.device.screenshot(str(path))
        return path

    def app_current(self) -> dict[str, Any]:
        current = self.device.app_current()
        return dict(current) if isinstance(current, dict) else {}

    def window_size(self) -> tuple[int, int]:
        size = self.device.window_size()
        return int(size[0]), int(size[1])

    def click(self, x: int, y: int) -> None:
        self.device.click(x, y)

    def tap_fallback(self, fallback_name: str) -> bool:
        tap = self.config.fallback_taps.get(fallback_name)
        if isinstance(tap, list) and len(tap) == 2:
            self.click(int(tap[0]), int(tap[1]))
            return True
        return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.2) -> None:
        self.device.swipe(x1, y1, x2, y2, duration=duration)

    def press(self, key: str) -> None:
        self.device.press(key)

    def start_app(self) -> None:
        if not self.config.app_package:
            raise ConfigError("app_package 未配置，无法自动启动红果 App。")
        if self.config.app_activity:
            self.device.app_start(self.config.app_package, self.config.app_activity)
            self.device.wait_activity(self.config.app_activity, timeout=self.config.timeouts.app_launch)
        else:
            self.device.app_start(self.config.app_package)
        time.sleep(2.0)

    def click_keywords(self, keywords: list[str]) -> bool:
        for keyword in keywords:
            if not keyword:
                continue
            if self.device(text=keyword).click_exists(timeout=1.0):
                return True
            if self.device(description=keyword).click_exists(timeout=1.0):
                return True
        xml_text = self.dump_hierarchy()
        candidate = find_candidate_by_keywords(xml_text, keywords)
        if candidate is None:
            return False
        x, y = bounds_center(candidate["bounds"])
        self.click(x, y)
        return True

    def page_contains_keywords(self, keywords: list[str]) -> bool:
        xml_text = self.dump_hierarchy()
        return find_candidate_by_keywords(xml_text, keywords, prefer_clickable=False) is not None

    def get_text_by_resource_ids(self, resource_ids: list[str]) -> str:
        for resource_id in resource_ids:
            try:
                widget = self.device(resourceId=resource_id)
                if widget.exists:
                    text = str(widget.get_text() or "").strip()
                    if text:
                        return text
            except Exception:
                continue
        return ""

    def infer_title(self) -> str:
        explicit_title = self.get_text_by_resource_ids(self.config.title_resource_ids)
        if explicit_title and not EPISODE_TITLE_PATTERN.match(explicit_title):
            return explicit_title
        xml_text = self.dump_hierarchy()
        candidates = extract_text_candidates(xml_text)
        ignored = {part.lower() for values in self.config.keywords.values() for part in values}
        text_nodes: list[tuple[int, str]] = []
        for candidate in candidates:
            text = str(candidate.get("text") or "").strip()
            bounds = candidate.get("bounds")
            if not text or not bounds:
                continue
            lowered = text.lower()
            if lowered in ignored:
                continue
            if EPISODE_TITLE_PATTERN.match(text):
                continue
            if text.isdigit():
                continue
            left, top, right, bottom = bounds
            if len(text) < 2:
                continue
            area = max(1, (right - left) * (bottom - top))
            if top > 7000:
                continue
            text_nodes.append((area, text))
        text_nodes.sort(key=lambda item: (-item[0], len(item[1])))
        return text_nodes[0][1] if text_nodes else ""


def generic_rank_swipe(ui_session: UiSession) -> None:
    width, height = ui_session.window_size()
    start_x = width // 2
    start_y = int(height * 0.75)
    end_y = int(height * 0.35)
    ui_session.swipe(start_x, start_y, start_x, end_y, duration=0.2)
    time.sleep(1.5)


def generic_list_swipe(ui_session: UiSession) -> None:
    width, height = ui_session.window_size()
    start_x = width // 2
    start_y = int(height * 0.78)
    end_y = int(height * 0.32)
    ui_session.swipe(start_x, start_y, start_x, end_y, duration=0.2)
    time.sleep(1.0)


def ensure_download_management_page(ui_session: UiSession, config: DownloaderConfig, serial: str) -> None:
    adb_start_activity(config, serial, DOWNLOAD_MANAGEMENT_ACTIVITY)
    time.sleep(1.5)
    if not ui_session.page_contains_keywords(DOWNLOAD_MANAGEMENT_KEYWORDS):
        raise StepError("无法打开红果“我的下载”管理页。")


def find_title_in_downloads(
    ui_session: UiSession,
    title: str,
    *,
    max_swipes: int = 8,
) -> tuple[int, int, int, int] | None:
    for _ in range(max_swipes + 1):
        bounds = find_title_row_bounds(ui_session.dump_hierarchy(), title)
        if bounds is not None:
            return bounds
        generic_list_swipe(ui_session)
    return None


def delete_existing_download(ui_session: UiSession, config: DownloaderConfig, serial: str, title: str) -> bool:
    ensure_download_management_page(ui_session, config, serial)
    title_bounds = find_title_in_downloads(ui_session, title)
    if title_bounds is None:
        ui_session.press("back")
        time.sleep(1.0)
        return False

    if not ui_session.click_keywords(["编辑"]):
        raise StepError("我的下载页没有找到“编辑”按钮，无法删除旧下载。")
    time.sleep(1.0)

    title_bounds = find_title_in_downloads(ui_session, title)
    if title_bounds is None:
        raise StepError(f"进入编辑态后未找到已下载剧目: {title}")

    _, top, right, bottom = title_bounds
    ui_session.click(max(1, right - 18), (top + bottom) // 2)
    time.sleep(0.8)

    if not ui_session.click_keywords(["删除"]):
        raise StepError("编辑态没有找到“删除”按钮。")
    time.sleep(0.8)

    if ui_session.page_contains_keywords(["确定删除吗？"]):
        if not ui_session.click_keywords(["删除"]):
            raise StepError("删除确认框没有找到“删除”按钮。")
        time.sleep(1.2)

    ui_session.click_keywords(["完成"])
    time.sleep(0.6)
    ui_session.press("back")
    time.sleep(1.0)
    return True


def open_rank_page(ui_session: UiSession, config: DownloaderConfig) -> None:
    for attempt in range(8):
        if ui_session.page_contains_keywords(config.keywords["rank"]):
            return

        if ui_session.page_contains_keywords(THEATER_KEYWORDS):
            ui_session.click_keywords(THEATER_KEYWORDS)
            time.sleep(2.0)
            if ui_session.page_contains_keywords(config.keywords["rank"]):
                return
            if ui_session.click_keywords(config.keywords["rank"]):
                time.sleep(2.0)
                return

        if ui_session.click_keywords(config.keywords["rank"]):
            time.sleep(2.0)
            return
        if ui_session.tap_fallback("rank_tab"):
            time.sleep(2.0)
            return

        if attempt < 6:
            ui_session.press("back")
            time.sleep(1.2)
    raise StepError("无法进入排行榜页面。")


def open_rank_item(ui_session: UiSession, config: DownloaderConfig, rank: int) -> None:
    rank_items = config.fallback_taps.get("rank_items")
    if isinstance(rank_items, dict):
        tap = rank_items.get(str(rank))
        if isinstance(tap, list) and len(tap) == 2:
            ui_session.click(int(tap[0]), int(tap[1]))
            time.sleep(2.0)
            return

    rank_bounds = find_clickable_ancestor_for_text(ui_session.dump_hierarchy(), str(rank))
    if rank_bounds is not None:
        x, y = bounds_center(rank_bounds)
        ui_session.click(x, y)
        time.sleep(2.0)
        return

    if ui_session.click_keywords([str(rank)]):
        time.sleep(2.0)
        return

    if rank == 1 and ui_session.tap_fallback("first_rank_item"):
        time.sleep(2.0)
        return

    for _ in range(max(1, rank - 1)):
        generic_rank_swipe(ui_session)
        rank_bounds = find_clickable_ancestor_for_text(ui_session.dump_hierarchy(), str(rank))
        if rank_bounds is not None:
            x, y = bounds_center(rank_bounds)
            ui_session.click(x, y)
            time.sleep(2.0)
            return
        if ui_session.click_keywords([str(rank)]):
            time.sleep(2.0)
            return
    raise StepError(f"无法打开排行榜第 {rank} 条。建议在配置中补 rank_items 坐标。")


def trigger_download(ui_session: UiSession, config: DownloaderConfig) -> bool:
    if ui_session.tap_fallback("more_button"):
        time.sleep(1.0)
    elif ui_session.click_keywords(["更多"]):
        time.sleep(1.0)
    else:
        ui_session.click(1024, 82)
        time.sleep(1.0)

    download_keywords = ["下载到本地", *config.keywords["download"]]
    if ui_session.click_keywords(download_keywords):
        time.sleep(1.5)
        if finish_download_sheet(ui_session, config):
            return True
        ui_session.click_keywords(config.keywords["confirm"])
        return True

    if click_text_ancestor(ui_session, "选集"):
        time.sleep(1.5)
        if ui_session.click_keywords(download_keywords):
            time.sleep(1.5)
            if finish_download_sheet(ui_session, config):
                return True
            ui_session.click_keywords(config.keywords["confirm"])
            return True

    if ui_session.tap_fallback("download_button"):
        time.sleep(1.5)
        if finish_download_sheet(ui_session, config):
            return True
        ui_session.click_keywords(config.keywords["confirm"])
        return True
    return False


def return_to_rank_list(ui_session: UiSession) -> None:
    if ui_session.tap_fallback("back_button"):
        time.sleep(1.5)
        return
    ui_session.press("back")
    time.sleep(1.5)


def build_run_summary(state: RunState) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for record in state.tasks.values():
        counts[record.status] = counts.get(record.status, 0) + 1
    return {
        "updated_at": _now_timestamp(),
        "counts": counts,
        "tasks": [record.to_dict() for record in sorted(state.tasks.values(), key=lambda item: (item.rank, item.title))],
    }


def build_target_ranks(top_n: int, start_rank: int = 1, limit: int | None = None) -> list[int]:
    normalized_start = max(1, start_rank)
    normalized_end = max(normalized_start, top_n)
    ranks = list(range(normalized_start, normalized_end + 1))
    if limit is not None:
        ranks = ranks[: max(0, limit)]
    return ranks


def handle_check(config: DownloaderConfig) -> int:
    ensure_paths(config)
    ensure_adb_available(config)
    serial = detect_target_serial(config)
    ui_session = UiSession(config, serial)
    current = ui_session.app_current()
    focus = get_current_focus_via_dumpsys(config, serial)
    debug_dir = save_debug_bundle(
        config,
        serial,
        ui_session,
        "check",
        extra_payload={
            "serial": serial,
            "current_app": current,
            "focus": focus,
            "shared_folder": str(config.shared_folder),
            "output_dir": str(config.output_dir),
        },
    )
    print(f"check ok: serial={serial}")
    print(f"current app: {current}")
    print(f"focus: {focus}")
    print(f"debug bundle: {debug_dir}")
    return 0


def update_config_with_records(config_path: Path, records: dict[str, list[int]]) -> None:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    fallback_taps = dict(payload.get("fallback_taps") or {})
    for key, value in records.items():
        fallback_taps[key] = value
    payload["fallback_taps"] = fallback_taps
    atomic_write_json(config_path, payload)


def handle_calibrate(config: DownloaderConfig, records: list[tuple[str, int, int]]) -> int:
    ensure_paths(config)
    ensure_adb_available(config)
    serial = detect_target_serial(config)
    ui_session = UiSession(config, serial)
    debug_dir = save_debug_bundle(
        config,
        serial,
        ui_session,
        "calibrate",
        extra_payload={
            "serial": serial,
            "window_size": ui_session.window_size(),
            "current_app": ui_session.app_current(),
        },
    )
    if records:
        mapped = {name: [x, y] for name, x, y in records}
        update_config_with_records(config.config_path, mapped)
        print(f"已写回坐标: {mapped}")
    print(f"calibration bundle: {debug_dir}")
    return 0


def should_skip_record(config: DownloaderConfig, state: RunState, rank: int, title: str) -> bool:
    if not config.resume:
        return False
    existing = state.get(rank, title)
    if existing is None:
        return False
    return config.skip_success and existing.status == STATUS_SUCCESS


def run_single_rank(
    ui_session: UiSession,
    config: DownloaderConfig,
    serial: str,
    state: RunState,
    rank: int,
) -> TaskRecord:
    open_rank_item(ui_session, config, rank)
    title = ui_session.infer_title() or f"rank_{rank}"
    if should_skip_record(config, state, rank, title):
        record = state.get(rank, title)
        assert record is not None
        return_to_rank_list(ui_session)
        return record

    record = TaskRecord(rank=rank, title=title, status=STATUS_RUNNING)
    state.upsert(record)
    state.save()

    if config.delete_existing_before_download:
        try:
            delete_existing_download(ui_session, config, serial, title)
        except Exception as exc:
            if ui_session.app_current().get("activity") == DOWNLOAD_MANAGEMENT_ACTIVITY:
                ui_session.press("back")
                time.sleep(1.0)
            record.last_error = f"删除旧下载失败，继续重试新下载: {exc}"
            state.upsert(record)
            state.save()

    baseline = take_folder_snapshot(config.shared_folder or Path("."), config.video_extensions)
    baseline_device = take_device_snapshot(config, serial, config.device_download_dir)
    if not trigger_download(ui_session, config):
        debug_dir = save_debug_bundle(
            config,
            serial,
            ui_session,
            f"download-missing-rank-{rank}",
            extra_payload={"rank": rank, "title": title},
        )
        record.status = STATUS_FAILED
        record.last_error = "详情页没有找到下载/缓存入口。"
        record.last_debug_dir = str(debug_dir)
        state.upsert(record)
        state.save()
        return_to_rank_list(ui_session)
        return record

    record.status = STATUS_DOWNLOAD_TRIGGERED
    state.upsert(record)
    state.save()

    stable_device_files = wait_for_stable_device_files(
        config,
        serial,
        config.device_download_dir,
        baseline_device,
        timeout_seconds=config.timeouts.file_stable,
        poll_interval_seconds=config.timeouts.poll_interval,
        stable_window_seconds=config.timeouts.stable_window,
    )
    if stable_device_files:
        archived_files = pull_device_files(config, serial, stable_device_files, config.output_dir, title)
        record.status = STATUS_SUCCESS
        record.archived_files = [str(path) for path in archived_files]
        state.upsert(record)
        state.save()
        return_to_rank_list(ui_session)
        return record

    stable_files = wait_for_stable_files(
        config.shared_folder or Path("."),
        baseline,
        config.video_extensions,
        timeout_seconds=config.timeouts.file_stable,
        poll_interval_seconds=config.timeouts.poll_interval,
        stable_window_seconds=config.timeouts.stable_window,
    )
    if not stable_files:
        debug_dir = save_debug_bundle(
            config,
            serial,
            ui_session,
            f"no-file-rank-{rank}",
            extra_payload={"rank": rank, "title": title},
        )
        record.status = STATUS_FAILED
        record.last_error = "已触发下载，但共享目录未检测到稳定的新文件。"
        record.last_debug_dir = str(debug_dir)
        state.upsert(record)
        state.save()
        return_to_rank_list(ui_session)
        return record

    archived_files = archive_files(stable_files, config.output_dir, title, config.archive_mode)
    record.status = STATUS_SUCCESS
    record.archived_files = [str(path) for path in archived_files]
    state.upsert(record)
    state.save()
    return_to_rank_list(ui_session)
    return record


def handle_run(config: DownloaderConfig, limit: int | None = None, start_rank: int = 1) -> int:
    ensure_paths(config)
    ensure_adb_available(config)
    serial = detect_target_serial(config)
    adb_root_if_possible(config, serial)
    ui_session = UiSession(config, serial)
    ui_session.start_app()

    state = RunState.load(config.state_path)
    open_rank_page(ui_session, config)

    results: list[TaskRecord] = []
    for rank in build_target_ranks(config.top_n, start_rank=start_rank, limit=limit):
        try:
            record = run_single_rank(ui_session, config, serial, state, rank)
        except Exception as exc:
            debug_dir = save_debug_bundle(
                config,
                serial,
                ui_session,
                f"rank-{rank}-exception",
                extra_payload={"rank": rank, "error": str(exc)},
            )
            running_record = next(
                (
                    item
                    for item in state.tasks.values()
                    if item.rank == rank and item.status == STATUS_RUNNING
                ),
                None,
            )
            record = running_record or TaskRecord(rank=rank, title=f"rank_{rank}")
            record.status = STATUS_FAILED
            record.last_error = str(exc)
            record.last_debug_dir = str(debug_dir)
            state.upsert(record)
            state.save()
            try:
                return_to_rank_list(ui_session)
            except Exception:
                pass
        results.append(record)

    summary = build_run_summary(state)
    atomic_write_json(config.run_output_path, summary)
    print(json.dumps(summary["counts"], ensure_ascii=False))
    print(f"run summary: {config.run_output_path}")
    return 0


def handle_downloads(config: DownloaderConfig, action: str, title: str | None = None) -> int:
    ensure_paths(config)
    ensure_adb_available(config)
    serial = detect_target_serial(config)
    adb_root_if_possible(config, serial)
    ui_session = UiSession(config, serial)
    ui_session.start_app()

    ensure_download_management_page(ui_session, config, serial)
    if action == "open":
        print("已打开红果“我的下载”页面。")
        return 0
    if action == "delete":
        if not title:
            raise ConfigError("downloads delete 需要通过 --title 指定剧名。")
        deleted = delete_existing_download(ui_session, config, serial, title)
        if deleted:
            print(f"已删除下载: {title}")
            return 0
        raise StepError(f"我的下载页未找到该剧，未执行删除: {title}")
    raise ConfigError(f"未知 downloads 动作: {action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MuMu 红果官方缓存自动化脚本")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="配置文件路径")
    parser.add_argument("--state", default=None, help="覆盖状态文件路径")
    parser.add_argument("--run-output", default=None, help="覆盖运行结果文件路径")
    parser.add_argument("--debug-dir", default=None, help="覆盖调试输出目录")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="检查 ADB、设备和 UI 会话连通性")

    calibrate_parser = subparsers.add_parser("calibrate", help="保存截图/UI 树并可选写回兜底坐标")
    calibrate_parser.add_argument(
        "--record",
        nargs=3,
        action="append",
        metavar=("NAME", "X", "Y"),
        help="写回 fallback_taps，例如 --record rank_tab 100 200",
    )

    run_parser = subparsers.add_parser("run", help="执行排行榜自动缓存流程")
    run_parser.add_argument("--limit", type=int, default=None, help="本次只处理前 N 条，便于冒烟")
    run_parser.add_argument("--start-rank", type=int, default=1, help="从第几条排行榜开始处理，默认 1")

    downloads_parser = subparsers.add_parser("downloads", help="打开或管理红果“我的下载”页面")
    downloads_parser.add_argument("action", choices=["open", "delete"], help="open=打开我的下载，delete=删除指定已下载剧目")
    downloads_parser.add_argument("--title", default=None, help="delete 动作需要传入完整剧名")
    return parser


def load_runtime_config(args: argparse.Namespace) -> DownloaderConfig:
    config_path = make_path(args.config)
    state_path = make_path(args.state) if args.state else None
    run_output_path = make_path(args.run_output) if args.run_output else None
    debug_dir = make_path(args.debug_dir) if args.debug_dir else None
    return DownloaderConfig.from_file(
        config_path=config_path,
        state_path=state_path,
        run_output_path=run_output_path,
        debug_dir=debug_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_runtime_config(args)
        if args.command == "check":
            return handle_check(config)
        if args.command == "calibrate":
            records: list[tuple[str, int, int]] = []
            for item in args.record or []:
                name, x, y = item
                records.append((name, int(x), int(y)))
            return handle_calibrate(config, records)
        if args.command == "run":
            return handle_run(config, limit=args.limit, start_rank=args.start_rank)
        if args.command == "downloads":
            return handle_downloads(config, action=args.action, title=args.title)
        parser.error(f"未知命令: {args.command}")
    except DownloaderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断。", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
