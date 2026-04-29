import json
from datetime import datetime, timezone
from pathlib import Path

from backend.config import FFMPEG_PATH, LLM_BASE_URL, LLM_MODEL_NAME, OUTPUT_DIR
from backend.fs_cleanup import safe_unlink
from backend.llm_client import call_llm, encode_video_as_data_url
from backend.media_tools import build_proxy_video_filter, run_checked_command
from backend.models import BestClimax, HighlightClip, HighlightPayload

HIGHLIGHT_VERSION = 1
HIGHLIGHT_SEGMENT_MAX_TOKENS = 1024
HIGHLIGHT_FINAL_MAX_TOKENS = 2048
HIGHLIGHT_PROXY_WIDTH = 512
HIGHLIGHT_PROXY_FPS = 8
HIGHLIGHT_PROXY_CRF = 32
HIGHLIGHT_TEMP_DIR = OUTPUT_DIR / "_highlight_tmp"
HIGHLIGHT_LABELS = {"爆点", "高燃", "高潮"}


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_highlight_payload(output_dir: Path) -> HighlightPayload | None:
    highlight_path = output_dir / "highlights.json"
    if not highlight_path.exists():
        return None

    payload = json.loads(highlight_path.read_text(encoding="utf-8"))
    highlights = [
        HighlightClip(
            start=item["start"],
            end=item["end"],
            label=item["label"],
            reason=item["reason"],
        )
        for item in payload["highlights"]
    ]
    best_climax = BestClimax(
        start=payload["best_climax"]["start"],
        end=payload["best_climax"]["end"],
        title=payload["best_climax"]["title"],
        reason=payload["best_climax"]["reason"],
    )
    return HighlightPayload(
        version=payload["version"],
        video_id=payload["video_id"],
        video_name=payload["video_name"],
        task_id=payload["task_id"],
        parent_task_id=payload.get("parent_task_id"),
        generated_at=payload["generated_at"],
        model=payload["model"],
        summary=payload["summary"],
        highlights=highlights,
        best_climax=best_climax,
    )


def _parse_json_text(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    return json.loads(text)


def _coerce_time(value) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError("时间字段非数字")
    return round(float(value), 2)


def _overlaps(left_start: float, left_end: float, right_start: float, right_end: float) -> bool:
    return max(left_start, right_start) < min(left_end, right_end)


def _slice_dialogues(dialogues: list[dict], start: float, end: float) -> list[dict]:
    return [
        dialogue
        for dialogue in dialogues
        if float(dialogue.get("end", 0)) > start and float(dialogue.get("start", 0)) < end
    ]


def build_highlight_proxy_video(video_path: str, start: float, end: float, output_path: str):
    duration = max(end - start, 0.1)
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-ss",
        str(start),
        "-i",
        video_path,
        "-t",
        str(duration),
        "-an",
        "-vf",
        build_proxy_video_filter(HIGHLIGHT_PROXY_WIDTH, HIGHLIGHT_PROXY_FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(HIGHLIGHT_PROXY_CRF),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]
    run_checked_command(cmd, error_label="高光代理视频转码")


def build_segment_candidate_prompt(segment: dict, dialogues: list[dict], script: str, retry: bool = False) -> str:
    retry_notice = (
        "上一次输出不是合法 JSON。本次必须只输出一个合法 JSON 对象，不能有解释、标题、Markdown 或代码块。\n"
        if retry
        else ""
    )
    return f"""你是短视频高光策划。请观看当前视频片段，并结合该片段对白、片段草稿和完整剧本，判断这个片段是否属于全片中的高光候选。

候选标签只允许三类：
- 爆点：信息反转、关键信息揭示、突发事件
- 高燃：情绪、动作、节奏显著抬升
- 高潮：冲突、情绪或命运推进达到峰值

要求：
1. 你只判断“当前片段”是否值得进入全片高光候选。
2. 如果不是候选，`is_candidate` 填 `false`，`label` 填 `none`。
3. 如果是候选，`label` 只能填 `爆点`、`高燃`、`高潮` 之一。
4. `intensity` 必须是 0-10 的整数。
5. 只输出 JSON。

{retry_notice}片段时间：{segment['start']:.2f}s - {segment['end']:.2f}s
片段草稿：
{segment.get('draft', '')}

片段对白：
{json.dumps(dialogues, ensure_ascii=False)}

完整剧本：
{script}

输出格式：
{{
  "is_candidate": true,
  "label": "高潮",
  "intensity": 9,
  "reason": "一句中文理由"
}}
"""


def build_segment_candidate_content(video_path: str, segment: dict, dialogues: list[dict], script: str, retry: bool = False) -> list[dict]:
    return [
        {"type": "video_url", "video_url": {"url": encode_video_as_data_url(video_path)}},
        {"type": "text", "text": build_segment_candidate_prompt(segment, dialogues, script, retry=retry)},
    ]


def validate_segment_candidate(payload: dict, segment: dict) -> dict:
    is_candidate = payload.get("is_candidate")
    label = payload.get("label")
    intensity = payload.get("intensity")
    reason = payload.get("reason")

    if not isinstance(is_candidate, bool):
        raise ValueError("is_candidate 非布尔值")
    if not isinstance(label, str):
        raise ValueError("label 缺失")
    if label not in HIGHLIGHT_LABELS | {"none"}:
        raise ValueError("label 非法")
    if not isinstance(intensity, int) or intensity < 0 or intensity > 10:
        raise ValueError("intensity 非法")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason 缺失")
    if is_candidate and label == "none":
        raise ValueError("候选片段不能使用 none 标签")
    if not is_candidate:
        label = "none"

    return {
        "index": int(segment["index"]),
        "start": _coerce_time(segment["start"]),
        "end": _coerce_time(segment["end"]),
        "draft": segment.get("draft", ""),
        "is_candidate": is_candidate,
        "label": label,
        "intensity": intensity,
        "reason": reason.strip(),
    }


def build_finalize_highlight_prompt(candidates: list[dict], script: str, retry: bool = False) -> str:
    retry_notice = (
        "上一次输出不是合法 JSON。本次必须只输出一个合法 JSON 对象，不能有解释、标题、Markdown 或代码块。\n"
        if retry
        else ""
    )
    return f"""你是短视频高光策划总编。下面给你全片的高光候选片段列表，它们已经结合视频、对白和剧本判定过。

请你输出最终结果：
1. 选出 3-5 个最值得展示的高光片段
2. 每个片段只允许使用 `爆点`、`高燃`、`高潮` 三种标签之一
3. 片段必须按时间升序
4. 给出一句全片高光总结 `summary`
5. 额外选出 1 个 `best_climax`，必须和某个高光片段时间重叠
6. 只输出 JSON

{retry_notice}候选片段：
{json.dumps(candidates, ensure_ascii=False)}

完整剧本：
{script}

输出格式：
{{
  "summary": "一句总评",
  "highlights": [
    {{
      "start": 12.0,
      "end": 18.0,
      "label": "爆点",
      "reason": "一句中文理由"
    }}
  ],
  "best_climax": {{
    "start": 45.0,
    "end": 53.0,
    "title": "最佳高潮点标题",
    "reason": "一句中文理由"
  }}
}}
"""


def validate_highlight_payload(payload: dict, *, video_id: str, video_name: str, task_id: str, parent_task_id: str | None) -> HighlightPayload:
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary 缺失")

    raw_highlights = payload.get("highlights")
    if not isinstance(raw_highlights, list):
        raise ValueError("highlights 缺失")
    if len(raw_highlights) < 3 or len(raw_highlights) > 5:
        raise ValueError("highlights 数量必须在 3 到 5 之间")

    highlights: list[HighlightClip] = []
    for item in raw_highlights:
        if not isinstance(item, dict):
            raise ValueError("highlight 条目非法")
        start = _coerce_time(item.get("start"))
        end = _coerce_time(item.get("end"))
        label = item.get("label")
        reason = item.get("reason")
        if start >= end:
            raise ValueError("highlight 时间范围非法")
        if not isinstance(label, str) or label not in HIGHLIGHT_LABELS:
            raise ValueError("highlight label 非法")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("highlight reason 缺失")
        highlights.append(
            HighlightClip(
                start=start,
                end=end,
                label=label,
                reason=reason.strip(),
            )
        )

    highlights.sort(key=lambda item: (item.start, item.end))

    raw_best_climax = payload.get("best_climax")
    if not isinstance(raw_best_climax, dict):
        raise ValueError("best_climax 缺失")

    best_start = _coerce_time(raw_best_climax.get("start"))
    best_end = _coerce_time(raw_best_climax.get("end"))
    best_title = raw_best_climax.get("title")
    best_reason = raw_best_climax.get("reason")

    if best_start >= best_end:
        raise ValueError("best_climax 时间范围非法")
    if not isinstance(best_title, str) or not best_title.strip():
        raise ValueError("best_climax title 缺失")
    if not isinstance(best_reason, str) or not best_reason.strip():
        raise ValueError("best_climax reason 缺失")
    if not any(_overlaps(best_start, best_end, item.start, item.end) for item in highlights):
        raise ValueError("best_climax 必须与高光片段重叠")

    best_climax = BestClimax(
        start=best_start,
        end=best_end,
        title=best_title.strip(),
        reason=best_reason.strip(),
    )

    return HighlightPayload(
        version=HIGHLIGHT_VERSION,
        video_id=video_id,
        video_name=video_name,
        task_id=task_id,
        parent_task_id=parent_task_id,
        generated_at=_utc_now(),
        model={
            "base_url": LLM_BASE_URL,
            "model_name": LLM_MODEL_NAME,
        },
        summary=summary.strip(),
        highlights=highlights,
        best_climax=best_climax,
    )


def identify_highlight_candidates(*, video_name: str, video_path: str, task_id: str, segments: list[dict], dialogues: list[dict], script: str, on_line=None) -> list[dict]:
    HIGHLIGHT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    candidates = []

    for index, segment in enumerate(segments, start=1):
        start = _coerce_time(segment["start"])
        end = _coerce_time(segment["end"])
        if on_line:
            on_line(f"  分析高光片段 [{index}/{len(segments)}] {start:.2f}s-{end:.2f}s ...")

        proxy_path = HIGHLIGHT_TEMP_DIR / f"{video_name}_{task_id}_{index:02d}_highlight_proxy.mp4"
        try:
            build_highlight_proxy_video(video_path, start, end, str(proxy_path))
            segment_dialogues = _slice_dialogues(dialogues, start, end)

            last_error: Exception | None = None
            candidate: dict | None = None
            for retry in (False, True):
                try:
                    raw = call_llm(
                        build_segment_candidate_content(
                            str(proxy_path),
                            segment,
                            segment_dialogues,
                            script,
                            retry=retry,
                        ),
                        max_tokens=HIGHLIGHT_SEGMENT_MAX_TOKENS,
                    )
                    payload = _parse_json_text(raw)
                    candidate = validate_segment_candidate(payload, segment)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc

            if candidate is None:
                assert last_error is not None
                raise RuntimeError(f"高光候选解析失败: {last_error}") from last_error

            candidates.append(candidate)
            if on_line:
                label = candidate["label"] if candidate["is_candidate"] else "非候选"
                on_line(f"    → 片段判定: {label} / 强度 {candidate['intensity']}")
        finally:
            safe_unlink(
                proxy_path,
                missing_ok=True,
                staging_root=HIGHLIGHT_TEMP_DIR / ".cleanup-staging",
                best_effort=True,
            )

    return candidates


def highlight_video_script(*, video_id: str, video_name: str, video_path: str, task_id: str, parent_task_id: str | None, on_line=None) -> HighlightPayload:
    output_dir = OUTPUT_DIR / video_name
    dialogues = json.loads((output_dir / "dialogues.json").read_text(encoding="utf-8"))
    segments = json.loads((output_dir / "segments.json").read_text(encoding="utf-8"))
    script = (output_dir / "script.txt").read_text(encoding="utf-8")

    if not isinstance(segments, list) or len(segments) < 3:
        raise ValueError("高光识别至少需要 3 个分段片段")

    candidates = identify_highlight_candidates(
        video_name=video_name,
        video_path=video_path,
        task_id=task_id,
        segments=segments,
        dialogues=dialogues,
        script=script,
        on_line=on_line,
    )

    last_error: Exception | None = None
    for retry in (False, True):
        try:
            raw = call_llm(
                [{"type": "text", "text": build_finalize_highlight_prompt(candidates, script, retry=retry)}],
                max_tokens=HIGHLIGHT_FINAL_MAX_TOKENS,
            )
            payload = _parse_json_text(raw)
            return validate_highlight_payload(
                payload,
                video_id=video_id,
                video_name=video_name,
                task_id=task_id,
                parent_task_id=parent_task_id,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    assert last_error is not None
    raise RuntimeError(f"高光结果解析失败: {last_error}") from last_error


def persist_highlight_payload(highlights: HighlightPayload, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    highlight_path = output_dir / "highlights.json"
    temp_path = output_dir / "highlights.json.tmp"
    temp_path.write_text(
        json.dumps(highlights.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(highlight_path)
    return highlight_path
