from pathlib import Path

from backend.config import OUTPUT_DIR
from backend.fs_cleanup import safe_unlink
from backend.viral_prediction import highlight_text_script, highlight_video_script, persist_highlight_payload
from backend.models import ASSET_TYPE_SCRIPT, TASK_TYPE_GENERATE, TASK_TYPE_HIGHLIGHT, TASK_TYPE_OPTIMIZE, TASK_TYPE_SCORE
from backend.optimization import optimize_video_script
from backend.pipeline import run_video_pipeline
from backend.scoring import clear_score_payload, persist_score_payload, score_video_script


def _reset_original_script(output_dir: Path) -> None:
    original_path = output_dir / "script_original.txt"
    if original_path.exists():
        safe_unlink(original_path, staging_root=output_dir / ".cleanup-staging")


def _ensure_original_script(output_dir: Path) -> None:
    script_path = output_dir / "script.txt"
    original_path = output_dir / "script_original.txt"
    if script_path.exists() and not original_path.exists():
        original_path.write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")


def _seed_script_output_from_source(task) -> None:
    if task.asset_type != ASSET_TYPE_SCRIPT:
        return
    output_dir = OUTPUT_DIR / task.video_name
    output_dir.mkdir(parents=True, exist_ok=True)
    script_text = Path(task.video_path).read_text(encoding="utf-8")
    script_path = output_dir / "script.txt"
    if not script_path.exists():
        script_path.write_text(script_text, encoding="utf-8")
    original_path = output_dir / "script_original.txt"
    if not original_path.exists():
        original_path.write_text(script_text, encoding="utf-8")


def run_video2script(task, on_line):
    exit_code = run_video_pipeline(task.video_path, on_line=on_line)
    if exit_code == 0:
        output_dir = OUTPUT_DIR / task.video_name
        clear_score_payload(output_dir)
        _reset_original_script(output_dir)
    return exit_code


def run_score_task(task, on_line):
    if task.asset_type == ASSET_TYPE_SCRIPT:
        raise RuntimeError("纯剧本素材不支持评分")
    on_line("[Step Score] 正在进行剧本评分")
    score = score_video_script(
        video_id=task.video_id,
        video_name=task.video_name,
        video_path=task.video_path,
        task_id=task.task_id,
        parent_task_id=task.parent_task_id,
    )
    score_path = persist_score_payload(score, OUTPUT_DIR / task.video_name)
    on_line(f"评分已保存: {score_path}")
    return 0


def run_highlight_task(task, on_line):
    on_line("[Step Highlight] 正在进行爆款预测")
    _seed_script_output_from_source(task)
    if task.asset_type == ASSET_TYPE_SCRIPT:
        highlights = highlight_text_script(
            video_id=task.video_id,
            video_name=task.video_name,
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
        )
    else:
        highlights = highlight_video_script(
            video_id=task.video_id,
            video_name=task.video_name,
            video_path=task.video_path,
            task_id=task.task_id,
            parent_task_id=task.parent_task_id,
            on_line=on_line,
        )
    highlight_path = persist_highlight_payload(highlights, OUTPUT_DIR / task.video_name)
    on_line(f"爆款预测结果已保存: {highlight_path}")
    return 0


def run_optimize_task(task, on_line):
    on_line("[Step Optimize] 正在根据爆款预测优化剧本")
    _seed_script_output_from_source(task)
    script = optimize_video_script(
        asset_type=task.asset_type,
        video_id=task.video_id,
        video_name=task.video_name,
        video_path=task.video_path,
        task_id=task.task_id,
        parent_task_id=task.parent_task_id,
    )
    output_dir = OUTPUT_DIR / task.video_name
    output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_original_script(output_dir)
    script_path = output_dir / "script.txt"
    script_path.write_text(script, encoding="utf-8")
    clear_score_payload(output_dir)
    on_line(f"优化剧本已保存: {script_path}")
    return 0


def run_task(task, on_line):
    if task.task_type == TASK_TYPE_GENERATE:
        return run_video2script(task, on_line)
    if task.task_type == TASK_TYPE_HIGHLIGHT:
        return run_highlight_task(task, on_line)
    if task.task_type == TASK_TYPE_SCORE:
        return run_score_task(task, on_line)
    if task.task_type == TASK_TYPE_OPTIMIZE:
        return run_optimize_task(task, on_line)
    raise ValueError(f"未知任务类型: {task.task_type}")
