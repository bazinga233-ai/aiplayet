import subprocess
from collections.abc import Sequence
from os import PathLike


def build_proxy_video_filter(max_width: int, fps: int) -> str:
    return (
        f"scale={max_width}:-2:force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
        f"fps={fps}"
    )


def run_checked_command(
    cmd: Sequence[str | PathLike[str]],
    *,
    error_label: str,
) -> subprocess.CompletedProcess[str]:
    normalized_cmd = [str(part) for part in cmd]
    try:
        return subprocess.run(
            normalized_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr_text = (exc.stderr or "").strip()
        stdout_text = (exc.stdout or "").strip()
        detail = stderr_text or stdout_text or str(exc)
        detail_lines = [line.strip() for line in detail.splitlines() if line.strip()]
        condensed_detail = " | ".join(detail_lines[-6:]) if detail_lines else str(exc)
        raise RuntimeError(f"{error_label}失败: {condensed_detail}") from exc
