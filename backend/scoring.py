import json
from datetime import datetime, timezone
from pathlib import Path

from backend.config import FFMPEG_PATH, LLM_BASE_URL, LLM_MODEL_NAME, OUTPUT_DIR
from backend.fs_cleanup import safe_unlink
from backend.llm_client import call_llm, encode_video_as_data_url
from backend.media_tools import build_proxy_video_filter, run_checked_command
from backend.models import ScoreDimension, ScorePayload

SCORE_VERSION = 2
SCORE_MAX_TOKENS = 4096
SCORE_PROXY_WIDTH = 512
SCORE_PROXY_FPS = 8
SCORE_PROXY_CRF = 32

SCORE_DIMENSIONS: list[tuple[str, str, int]] = [
    ("video_faithfulness", "与原视频一致性", 22),
    ("information_completeness", "信息完整性", 15),
    ("plot_causality", "情节/因果", 10),
    ("structure", "结构", 10),
    ("character", "人物", 8),
    ("conflict", "冲突", 8),
    ("dialogue", "对白", 10),
    ("pacing", "节奏", 6),
    ("logic", "逻辑/自洽", 6),
    ("ending_overall_effect", "结尾/整体效果", 3),
    ("craft_format", "工艺/格式", 2),
]

SCORE_DIMENSIONS_BY_KEY = {key: (label, max_score) for key, label, max_score in SCORE_DIMENSIONS}
SCORE_TOTAL = sum(max_score for _, _, max_score in SCORE_DIMENSIONS)
if SCORE_TOTAL != 100:
    raise ValueError(f"评分维度总分必须为 100，当前为 {SCORE_TOTAL}")

SCORE_TEMP_DIR = OUTPUT_DIR / "_score_tmp"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def get_score_path(video_name: str) -> Path:
    return OUTPUT_DIR / video_name / "score.json"


def clear_score_payload(output_dir: Path) -> None:
    score_path = output_dir / "score.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    score_path.write_text("null", encoding="utf-8")


def load_score_payload(output_dir: Path) -> ScorePayload | None:
    score_path = output_dir / "score.json"
    if not score_path.exists():
        return None

    payload = json.loads(score_path.read_text(encoding="utf-8"))
    if payload is None:
        return None
    dimensions = [
        ScoreDimension(
            key=item["key"],
            label=item["label"],
            score=item["score"],
            max_score=item["max_score"],
            reason=item["reason"],
        )
        for item in payload["dimensions"]
    ]
    return ScorePayload(
        version=payload["version"],
        video_id=payload["video_id"],
        video_name=payload["video_name"],
        task_id=payload["task_id"],
        parent_task_id=payload.get("parent_task_id"),
        generated_at=payload["generated_at"],
        model=payload["model"],
        total_score=payload["total_score"],
        summary=payload["summary"],
        dimensions=dimensions,
    )


def build_score_prompt(dialogues: list[dict], segments: list[dict], script: str, retry: bool = False) -> str:
    dimensions_text = "\n".join(
        f"- {key} | {label} | 满分 {max_score}"
        for key, label, max_score in SCORE_DIMENSIONS
    )
    retry_notice = (
        "上一次输出不是合法 JSON。本次必须仅输出一个合法 JSON 对象，不能有解释、标题、Markdown 或代码块。\n"
        if retry
        else ""
    )
    return f"""你是短剧剧本评审。请同时观看视频，并结合对白、分段和最终剧本，对生成结果进行 100 分制评分。

评分目标不是评原创编剧比赛，而是评估“生成剧本是否正确、完整、可读地还原原视频”。

重点要求：
1. 与原视频一致性：检查人物、事件、顺序、情绪、细节是否编错。
2. 信息完整性：检查关键情节、转折、关系、结尾是否遗漏。
3. 权重必须严格使用下表，不能改维度、不能改满分。
4. 每个维度都必须给出 `key`、`label`、`score`、`max_score`、`reason`。
5. `total_score` 必须等于所有维度得分之和。
6. 只输出 JSON，不要输出任何额外说明。

{retry_notice}固定维度与满分：
{dimensions_text}

对白 JSON：
{json.dumps(dialogues, ensure_ascii=False)}

分段 JSON：
{json.dumps(segments, ensure_ascii=False)}

最终剧本：
{script}

输出格式：
{{
  "total_score": 0,
  "summary": "总评",
  "dimensions": [
    {{
      "key": "video_faithfulness",
      "label": "与原视频一致性",
      "score": 0,
      "max_score": 22,
      "reason": "理由"
    }}
  ]
}}
"""


def build_score_content(video_path: str, dialogues: list[dict], segments: list[dict], script: str, retry: bool = False) -> list[dict]:
    return [
        {"type": "video_url", "video_url": {"url": encode_video_as_data_url(video_path)}},
        {"type": "text", "text": build_score_prompt(dialogues, segments, script, retry=retry)},
    ]


def build_score_proxy_video(video_path: str, output_path: str):
    """生成低码率无音频评分代理视频，避免评分阶段直传原始大文件。"""
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i",
        video_path,
        "-an",
        "-vf",
        build_proxy_video_filter(SCORE_PROXY_WIDTH, SCORE_PROXY_FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(SCORE_PROXY_CRF),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]
    run_checked_command(cmd, error_label="评分代理视频转码")


def _parse_json_text(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    return json.loads(text)


def validate_score_payload(payload: dict, *, video_id: str, video_name: str, task_id: str, parent_task_id: str | None) -> ScorePayload:
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary 缺失")

    raw_total_score = payload.get("total_score")
    if not isinstance(raw_total_score, int):
        raise ValueError("total_score 非整数")

    raw_dimensions = payload.get("dimensions")
    if not isinstance(raw_dimensions, list):
        raise ValueError("dimensions 缺失")

    normalized: list[ScoreDimension] = []
    raw_by_key = {}
    for item in raw_dimensions:
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            raw_by_key[item["key"]] = item

    for key, label, max_score in SCORE_DIMENSIONS:
        item = raw_by_key.get(key)
        if item is None:
            raise ValueError(f"缺少评分维度: {key}")
        score = item.get("score")
        reason = item.get("reason")
        if not isinstance(score, int):
            raise ValueError(f"{key} score 非整数")
        if score < 0 or score > max_score:
            raise ValueError(f"{key} score 越界")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{key} reason 缺失")
        item_label = item.get("label")
        item_max_score = item.get("max_score")
        if item_label != label:
            raise ValueError(f"{key} label 不匹配")
        if item_max_score != max_score:
            raise ValueError(f"{key} max_score 不匹配")
        normalized.append(
            ScoreDimension(
                key=key,
                label=label,
                score=score,
                max_score=max_score,
                reason=reason.strip(),
            )
        )

    total_score = sum(item.score for item in normalized)

    return ScorePayload(
        version=SCORE_VERSION,
        video_id=video_id,
        video_name=video_name,
        task_id=task_id,
        parent_task_id=parent_task_id,
        generated_at=_utc_now(),
        model={
            "base_url": LLM_BASE_URL,
            "model_name": LLM_MODEL_NAME,
        },
        total_score=total_score,
        summary=summary.strip(),
        dimensions=normalized,
    )


def score_video_script(*, video_id: str, video_name: str, video_path: str, task_id: str, parent_task_id: str | None) -> ScorePayload:
    output_dir = OUTPUT_DIR / video_name
    dialogues_path = output_dir / "dialogues.json"
    segments_path = output_dir / "segments.json"
    script_path = output_dir / "script.txt"

    dialogues = json.loads(dialogues_path.read_text(encoding="utf-8"))
    segments = json.loads(segments_path.read_text(encoding="utf-8"))
    script = script_path.read_text(encoding="utf-8")

    SCORE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    proxy_path = SCORE_TEMP_DIR / f"{video_name}_{task_id}_score_proxy.mp4"
    try:
        build_score_proxy_video(video_path, proxy_path)

        last_error: Exception | None = None
        for retry in (False, True):
            try:
                raw = call_llm(
                    build_score_content(str(proxy_path), dialogues, segments, script, retry=retry),
                    max_tokens=SCORE_MAX_TOKENS,
                )
                payload = _parse_json_text(raw)
                return validate_score_payload(
                    payload,
                    video_id=video_id,
                    video_name=video_name,
                    task_id=task_id,
                    parent_task_id=parent_task_id,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc

        assert last_error is not None
        raise RuntimeError(f"评分结果解析失败: {last_error}") from last_error
    finally:
        safe_unlink(
            proxy_path,
            missing_ok=True,
            staging_root=SCORE_TEMP_DIR / ".cleanup-staging",
            best_effort=True,
        )


def persist_score_payload(score: ScorePayload, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    score_path = output_dir / "score.json"
    temp_path = output_dir / "score.json.tmp"
    temp_path.write_text(
        json.dumps(score.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(score_path)
    return score_path
