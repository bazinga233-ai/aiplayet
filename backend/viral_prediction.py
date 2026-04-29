import json
from datetime import datetime, timezone
from pathlib import Path

from backend.config import FFMPEG_PATH
from backend.config import LLM_BASE_URL, LLM_MODEL_NAME, OUTPUT_DIR
from backend.fs_cleanup import safe_unlink
from backend.llm_client import call_llm, encode_video_as_data_url
from backend.media_tools import build_proxy_video_filter, run_checked_command
from backend.models import BestOpportunity, EmotionPoint, HighlightPayload, PredictionWindow

HIGHLIGHT_VERSION = 2
SEGMENT_MAX_TOKENS = 1400
FINAL_MAX_TOKENS = 2200
PROXY_WIDTH = 512
PROXY_FPS = 8
PROXY_CRF = 32
TEMP_DIR = OUTPUT_DIR / "_highlight_tmp"
LEGACY_LABELS = {"爆点", "高燃", "高潮"}
MAX_WINDOWS_PER_GROUP = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _coerce_percent(value, *, field_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field_name} 非整数")
    if value < 0 or value > 100:
        raise ValueError(f"{field_name} 越界")
    return value


def _coerce_text(value, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 缺失")
    return value.strip()


def _overlaps(left_start: float, left_end: float, right_start: float, right_end: float) -> bool:
    return max(left_start, right_start) < min(left_end, right_end)


def _slice_dialogues(dialogues: list[dict], start: float, end: float) -> list[dict]:
    return [
        dialogue
        for dialogue in dialogues
        if float(dialogue.get("end", 0)) > start and float(dialogue.get("start", 0)) < end
    ]


def _segment_midpoint(start: float, end: float) -> float:
    return round((start + end) / 2, 2)


def _window_from_dict(item: dict, *, field_name: str) -> PredictionWindow:
    if not isinstance(item, dict):
        raise ValueError(f"{field_name} 条目非法")
    start = _coerce_time(item.get("start"))
    end = _coerce_time(item.get("end"))
    if start >= end:
        raise ValueError(f"{field_name} 时间范围非法")
    return PredictionWindow(
        start=start,
        end=end,
        kind=_coerce_text(item.get("kind"), field_name=f"{field_name}.kind"),
        reason=_coerce_text(item.get("reason"), field_name=f"{field_name}.reason"),
        suggestion=_coerce_text(item.get("suggestion"), field_name=f"{field_name}.suggestion"),
        confidence=_coerce_percent(item.get("confidence"), field_name=f"{field_name}.confidence"),
    )


def _best_from_dict(item: dict | None) -> BestOpportunity | None:
    if item is None:
        return None
    if not isinstance(item, dict):
        raise ValueError("best_opportunity 非法")
    start = _coerce_time(item.get("start"))
    end = _coerce_time(item.get("end"))
    if start >= end:
        raise ValueError("best_opportunity 时间范围非法")
    return BestOpportunity(
        start=start,
        end=end,
        kind=_coerce_text(item.get("kind"), field_name="best_opportunity.kind"),
        reason=_coerce_text(item.get("reason"), field_name="best_opportunity.reason"),
        suggestion=_coerce_text(item.get("suggestion"), field_name="best_opportunity.suggestion"),
        confidence=_coerce_percent(item.get("confidence"), field_name="best_opportunity.confidence"),
    )


def _legacy_kind(label: str) -> str:
    return {"爆点": "反转机会", "高燃": "高燃放大", "高潮": "高潮放大"}.get(label, "内容机会")


def _legacy_tension(label: str) -> int:
    return {"高潮": 88, "高燃": 80, "爆点": 76}.get(label, 60)


def _legacy_suggestion(label: str) -> str:
    return {
        "爆点": "建议在该区间前后强化反转铺垫和信息揭示。",
        "高燃": "建议在该区间强化节奏、动作或视听冲击。",
        "高潮": "建议在该区间继续放大冲突与情绪峰值。",
    }.get(label, "建议补充更强的剧情刺激点。")


def _ensure_model_dict(model: dict | None) -> dict:
    if not isinstance(model, dict):
        raise ValueError("model 缺失")
    base_url = _coerce_text(model.get("base_url"), field_name="model.base_url")
    model_name = _coerce_text(model.get("model_name"), field_name="model.model_name")
    return {
        "base_url": base_url,
        "model_name": model_name,
    }


def _load_legacy_highlight_payload(payload: dict) -> HighlightPayload:
    if not isinstance(payload, dict):
        raise ValueError("legacy highlights payload 非法")

    raw_highlights = payload.get("highlights")
    if not isinstance(raw_highlights, list) or not raw_highlights:
        raise ValueError("legacy highlights 缺失")

    opportunity_windows: list[PredictionWindow] = []
    emotion_curve: list[EmotionPoint] = []
    tensions: list[int] = []

    for index, item in enumerate(raw_highlights):
        if not isinstance(item, dict):
            raise ValueError("legacy highlight 条目非法")
        start = _coerce_time(item.get("start"))
        end = _coerce_time(item.get("end"))
        if start >= end:
            raise ValueError("legacy highlight 时间范围非法")
        label = _coerce_text(item.get("label"), field_name=f"highlights[{index}].label")
        if label not in LEGACY_LABELS:
            raise ValueError("legacy highlight label 非法")
        reason = _coerce_text(item.get("reason"), field_name=f"highlights[{index}].reason")
        tension = _legacy_tension(label)
        tensions.append(tension)
        emotion_curve.append(
            EmotionPoint(
                time=_segment_midpoint(start, end),
                tension=tension,
                risk=max(0, 100 - tension),
            )
        )
        opportunity_windows.append(
            PredictionWindow(
                start=start,
                end=end,
                kind=_legacy_kind(label),
                reason=reason,
                suggestion=_legacy_suggestion(label),
                confidence=min(95, tension),
            )
        )

    best_payload = payload.get("best_climax")
    if not isinstance(best_payload, dict):
        raise ValueError("best_climax 缺失")

    best_start = _coerce_time(best_payload.get("start"))
    best_end = _coerce_time(best_payload.get("end"))
    if best_start >= best_end:
        raise ValueError("best_climax 时间范围非法")
    best_reason = _coerce_text(best_payload.get("reason"), field_name="best_climax.reason")
    matched_label = "高潮"
    for item in raw_highlights:
        if _overlaps(best_start, best_end, float(item["start"]), float(item["end"])):
            matched_label = str(item["label"])
            break

    best_opportunity = BestOpportunity(
        start=best_start,
        end=best_end,
        kind=_legacy_kind(matched_label),
        reason=best_reason,
        suggestion=_legacy_suggestion(matched_label),
        confidence=min(98, _legacy_tension(matched_label) + 4),
    )

    breakout_score = int(round(sum(tensions) / len(tensions)))
    return HighlightPayload(
        version=HIGHLIGHT_VERSION,
        video_id=_coerce_text(payload.get("video_id"), field_name="video_id"),
        video_name=_coerce_text(payload.get("video_name"), field_name="video_name"),
        task_id=_coerce_text(payload.get("task_id"), field_name="task_id"),
        parent_task_id=payload.get("parent_task_id"),
        generated_at=_coerce_text(payload.get("generated_at"), field_name="generated_at"),
        model=_ensure_model_dict(payload.get("model")),
        summary=_coerce_text(payload.get("summary"), field_name="summary"),
        breakout_score=breakout_score,
        position_mode="time",
        emotion_curve=sorted(emotion_curve, key=lambda item: item.time),
        risk_windows=[],
        opportunity_windows=sorted(opportunity_windows, key=lambda item: (item.start, item.end)),
        best_opportunity=best_opportunity,
    )


def load_highlight_payload(output_dir: Path) -> HighlightPayload | None:
    highlight_path = output_dir / "highlights.json"
    if not highlight_path.exists():
        return None

    payload = json.loads(highlight_path.read_text(encoding="utf-8"))
    if payload is None:
        return None

    if isinstance(payload, dict) and "breakout_score" in payload:
        return validate_highlight_payload(payload)

    return _load_legacy_highlight_payload(payload)


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
        build_proxy_video_filter(PROXY_WIDTH, PROXY_FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(PROXY_CRF),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]
    run_checked_command(cmd, error_label="爆款预测代理视频转码")


def build_segment_prediction_prompt(segment: dict, dialogues: list[dict], script: str, retry: bool = False) -> str:
    retry_notice = (
        "上一次输出不是合法 JSON。本次必须只输出一个合法 JSON 对象，不能有解释、标题、Markdown 或代码块。\n"
        if retry
        else ""
    )
    return f"""你是短剧“爆款预测器”的逐段分析师。请观看当前视频片段，并结合该片段对白、片段草稿和完整剧本，判断这个片段对情绪张力与留存的影响。

要求：
1. 只分析“当前片段”，不要评价全片。
2. `tension`、`drop_risk`、`info_density`、`confidence` 都必须是 0-100 的整数。
3. `event_type` 用简短中文概括，例如：铺垫、反转、冲突升级、情绪爆发、解释说明、收束、过渡、揭示。
4. `risk_reason` 说明为什么这里会或不会出现情绪/留存下滑。
5. `opportunity_reason` 说明这一段最值得放大的创作机会点。
6. `suggestion` 只给一条最具体、可执行的建议。
7. 只输出 JSON。

{retry_notice}片段时间：{segment['start']:.2f}s - {segment['end']:.2f}s
片段草稿：
{segment.get('draft', '')}

片段对白：
{json.dumps(dialogues, ensure_ascii=False)}

完整剧本：
{script}

输出格式：
{{
  "tension": 68,
  "drop_risk": 24,
  "info_density": 70,
  "event_type": "冲突升级",
  "risk_reason": "一句中文理由",
  "opportunity_reason": "一句中文理由",
  "suggestion": "一句中文建议",
  "confidence": 82
}}
"""


def build_segment_prediction_content(
    video_path: str,
    segment: dict,
    dialogues: list[dict],
    script: str,
    retry: bool = False,
) -> list[dict]:
    return [
        {"type": "video_url", "video_url": {"url": encode_video_as_data_url(video_path)}},
        {"type": "text", "text": build_segment_prediction_prompt(segment, dialogues, script, retry=retry)},
    ]


def validate_segment_prediction(payload: dict, segment: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("segment prediction 非法")

    return {
        "index": int(segment["index"]),
        "start": _coerce_time(segment["start"]),
        "end": _coerce_time(segment["end"]),
        "draft": str(segment.get("draft", "")).strip(),
        "tension": _coerce_percent(payload.get("tension"), field_name="tension"),
        "drop_risk": _coerce_percent(payload.get("drop_risk"), field_name="drop_risk"),
        "info_density": _coerce_percent(payload.get("info_density"), field_name="info_density"),
        "event_type": _coerce_text(payload.get("event_type"), field_name="event_type"),
        "risk_reason": _coerce_text(payload.get("risk_reason"), field_name="risk_reason"),
        "opportunity_reason": _coerce_text(payload.get("opportunity_reason"), field_name="opportunity_reason"),
        "suggestion": _coerce_text(payload.get("suggestion"), field_name="suggestion"),
        "confidence": _coerce_percent(payload.get("confidence"), field_name="confidence"),
    }


def build_finalize_prediction_prompt(predictions: list[dict], script: str, retry: bool = False) -> str:
    retry_notice = (
        "上一次输出不是合法 JSON。本次必须只输出一个合法 JSON 对象，不能有解释、标题、Markdown 或代码块。\n"
        if retry
        else ""
    )
    return f"""你是短剧“爆款预测器”的总编。下面给你全片逐段分析结果，它们已经结合视频、对白和剧本判定过。

请你输出最终预测结果：
1. 给一句整体总结 `summary`
2. 给一个 0-100 的 `breakout_score`
3. 输出 0-3 个 `risk_windows`，表示观众情绪或留存容易下滑的窗口
4. 输出 0-3 个 `opportunity_windows`，表示最值得强化或前置的窗口
5. 输出 1 个 `best_opportunity`，没有就填 null
6. 所有窗口都必须使用真实秒数，且 `start < end`
7. `kind` 要简短，例如：情绪下滑、信息停滞、反转机会、高潮放大、关键修正点
8. `reason` 和 `suggestion` 必须具体，可直接指导创作
9. `confidence` 必须是 0-100 的整数
10. 只输出 JSON

{retry_notice}逐段分析：
{json.dumps(predictions, ensure_ascii=False)}

完整剧本：
{script}

输出格式：
{{
  "summary": "一句总评",
  "breakout_score": 74,
  "risk_windows": [
    {{
      "start": 38.0,
      "end": 45.0,
      "kind": "情绪下滑",
      "reason": "一句中文理由",
      "suggestion": "一句中文建议",
      "confidence": 82
    }}
  ],
  "opportunity_windows": [
    {{
      "start": 26.0,
      "end": 31.0,
      "kind": "反转机会",
      "reason": "一句中文理由",
      "suggestion": "一句中文建议",
      "confidence": 78
    }}
  ],
  "best_opportunity": {{
    "start": 38.0,
    "end": 45.0,
    "kind": "关键修正点",
    "reason": "一句中文理由",
    "suggestion": "一句中文建议",
    "confidence": 84
  }}
}}
"""


def _validate_window_group(raw_windows: object, *, field_name: str) -> list[PredictionWindow]:
    if raw_windows is None:
        return []
    if not isinstance(raw_windows, list):
        raise ValueError(f"{field_name} 缺失")
    if len(raw_windows) > MAX_WINDOWS_PER_GROUP:
        raise ValueError(f"{field_name} 数量超限")

    windows = [_window_from_dict(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(raw_windows)]
    return sorted(windows, key=lambda item: (item.start, item.end))


def validate_highlight_payload(
    payload: dict,
    *,
    video_id: str | None = None,
    video_name: str | None = None,
    task_id: str | None = None,
    parent_task_id: str | None = None,
    position_mode: str | None = None,
) -> HighlightPayload:
    if not isinstance(payload, dict):
        raise ValueError("highlight payload 非法")

    summary = _coerce_text(payload.get("summary"), field_name="summary")
    breakout_score = _coerce_percent(payload.get("breakout_score"), field_name="breakout_score")

    raw_curve = payload.get("emotion_curve")
    if not isinstance(raw_curve, list):
        raise ValueError("emotion_curve 缺失")

    emotion_curve = []
    for index, item in enumerate(raw_curve):
        if not isinstance(item, dict):
            raise ValueError("emotion_curve 条目非法")
        emotion_curve.append(
            EmotionPoint(
                time=_coerce_time(item.get("time")),
                tension=_coerce_percent(item.get("tension"), field_name=f"emotion_curve[{index}].tension"),
                risk=_coerce_percent(item.get("risk"), field_name=f"emotion_curve[{index}].risk"),
            )
        )
    emotion_curve.sort(key=lambda item: item.time)

    risk_windows = _validate_window_group(payload.get("risk_windows"), field_name="risk_windows")
    opportunity_windows = _validate_window_group(payload.get("opportunity_windows"), field_name="opportunity_windows")
    best_opportunity = _best_from_dict(payload.get("best_opportunity"))

    related_windows = [*risk_windows, *opportunity_windows]
    if best_opportunity and related_windows and not any(
        _overlaps(best_opportunity.start, best_opportunity.end, item.start, item.end) for item in related_windows
    ):
        raise ValueError("best_opportunity 必须与某个窗口重叠")

    return HighlightPayload(
        version=HIGHLIGHT_VERSION,
        video_id=video_id or _coerce_text(payload.get("video_id"), field_name="video_id"),
        video_name=video_name or _coerce_text(payload.get("video_name"), field_name="video_name"),
        task_id=task_id or _coerce_text(payload.get("task_id"), field_name="task_id"),
        parent_task_id=parent_task_id if task_id is not None else payload.get("parent_task_id"),
        generated_at=_coerce_text(payload.get("generated_at"), field_name="generated_at") if task_id is None else _utc_now(),
        model=_ensure_model_dict(
            payload.get("model")
            if task_id is None
            else {
                "base_url": LLM_BASE_URL,
                "model_name": LLM_MODEL_NAME,
            }
        ),
        summary=summary,
        breakout_score=breakout_score,
        position_mode=position_mode or payload.get("position_mode") or "time",
        emotion_curve=emotion_curve,
        risk_windows=risk_windows,
        opportunity_windows=opportunity_windows,
        best_opportunity=best_opportunity,
    )


def analyze_segment_predictions(
    *,
    video_name: str,
    video_path: str,
    task_id: str,
    segments: list[dict],
    dialogues: list[dict],
    script: str,
    on_line=None,
) -> list[dict]:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    predictions = []

    for index, segment in enumerate(segments, start=1):
        start = _coerce_time(segment["start"])
        end = _coerce_time(segment["end"])
        if on_line:
            on_line(f"  分析爆款片段 [{index}/{len(segments)}] {start:.2f}s-{end:.2f}s ...")

        proxy_path = TEMP_DIR / f"{video_name}_{task_id}_{index:02d}_highlight_proxy.mp4"
        try:
            build_highlight_proxy_video(video_path, start, end, str(proxy_path))
            segment_dialogues = _slice_dialogues(dialogues, start, end)

            last_error: Exception | None = None
            prediction: dict | None = None
            for retry in (False, True):
                try:
                    raw = call_llm(
                        build_segment_prediction_content(
                            str(proxy_path),
                            segment,
                            segment_dialogues,
                            script,
                            retry=retry,
                        ),
                        max_tokens=SEGMENT_MAX_TOKENS,
                    )
                    prediction = validate_segment_prediction(_parse_json_text(raw), segment)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc

            if prediction is None:
                assert last_error is not None
                raise RuntimeError(f"爆款片段解析失败: {last_error}") from last_error

            predictions.append(prediction)
            if on_line:
                on_line(
                    f"    → 张力 {prediction['tension']} / 风险 {prediction['drop_risk']} / 类型 {prediction['event_type']}"
                )
        finally:
            safe_unlink(
                proxy_path,
                missing_ok=True,
                staging_root=TEMP_DIR / ".cleanup-staging",
                best_effort=True,
            )

    return predictions


def highlight_video_script(
    *,
    video_id: str,
    video_name: str,
    video_path: str,
    task_id: str,
    parent_task_id: str | None,
    on_line=None,
) -> HighlightPayload:
    output_dir = OUTPUT_DIR / video_name
    dialogues = json.loads((output_dir / "dialogues.json").read_text(encoding="utf-8"))
    segments = json.loads((output_dir / "segments.json").read_text(encoding="utf-8"))
    script = (output_dir / "script.txt").read_text(encoding="utf-8")

    if not isinstance(segments, list) or not segments:
        raise ValueError("爆款预测至少需要 1 个分段片段")

    predictions = analyze_segment_predictions(
        video_name=video_name,
        video_path=video_path,
        task_id=task_id,
        segments=segments,
        dialogues=dialogues,
        script=script,
        on_line=on_line,
    )

    emotion_curve = [
        EmotionPoint(
            time=_segment_midpoint(item["start"], item["end"]),
            tension=item["tension"],
            risk=item["drop_risk"],
        )
        for item in predictions
    ]

    last_error: Exception | None = None
    for retry in (False, True):
        try:
            raw = call_llm(
                [{"type": "text", "text": build_finalize_prediction_prompt(predictions, script, retry=retry)}],
                max_tokens=FINAL_MAX_TOKENS,
            )
            payload = _parse_json_text(raw)
            payload["emotion_curve"] = [item.to_dict() for item in emotion_curve]
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
    raise RuntimeError(f"爆款预测结果解析失败: {last_error}") from last_error


def _split_script_beats(script: str) -> list[dict]:
    raw_blocks = [line.strip() for line in script.splitlines() if line.strip()]
    if not raw_blocks:
        raise ValueError("剧本内容为空，无法进行爆款预测")
    beats = []
    for index, content in enumerate(raw_blocks, start=1):
        beats.append({"index": index, "content": content})
    return beats


def build_script_prediction_prompt(beats: list[dict], script: str, retry: bool = False) -> str:
    retry_notice = (
        "上一次输出不是合法 JSON。本次必须只输出一个合法 JSON 对象，不能有解释、标题、Markdown 或代码块。\n"
        if retry
        else ""
    )
    return f"""你是短剧“爆款预测器”的文本版分析师。下面只有剧本文本，没有原视频。请根据剧情推进、冲突强度、信息密度、对白吸引力和反转设置，对这份剧本做爆款预测。

要求：
1. 以“段落/节拍”为位置单位，不要输出秒数。
2. `position_mode` 固定输出 `beat`。
3. `emotion_curve` 里的 `time` 使用节拍序号，例如第 1 段就填 1。
4. `risk_windows`、`opportunity_windows`、`best_opportunity` 的 `start`、`end` 也使用节拍序号。
5. `tension`、`risk`、`breakout_score`、`confidence` 都必须是 0-100 的整数。
6. 只输出 JSON。

{retry_notice}剧本节拍：
{json.dumps(beats, ensure_ascii=False)}

完整剧本：
{script}

输出格式：
{{
  "position_mode": "beat",
  "summary": "一句总评",
  "breakout_score": 74,
  "emotion_curve": [
    {{"time": 1, "tension": 60, "risk": 20}}
  ],
  "risk_windows": [
    {{
      "start": 3,
      "end": 4,
      "kind": "信息停滞",
      "reason": "一句中文理由",
      "suggestion": "一句中文建议",
      "confidence": 82
    }}
  ],
  "opportunity_windows": [
    {{
      "start": 4,
      "end": 5,
      "kind": "反转机会",
      "reason": "一句中文理由",
      "suggestion": "一句中文建议",
      "confidence": 78
    }}
  ],
  "best_opportunity": {{
    "start": 4,
    "end": 5,
    "kind": "关键修正点",
    "reason": "一句中文理由",
    "suggestion": "一句中文建议",
    "confidence": 84
  }}
}}
"""


def highlight_text_script(
    *,
    video_id: str,
    video_name: str,
    task_id: str,
    parent_task_id: str | None,
) -> HighlightPayload:
    output_dir = OUTPUT_DIR / video_name
    script = (output_dir / "script.txt").read_text(encoding="utf-8")
    beats = _split_script_beats(script)

    last_error: Exception | None = None
    for retry in (False, True):
        try:
            raw = call_llm(
                [{"type": "text", "text": build_script_prediction_prompt(beats, script, retry=retry)}],
                max_tokens=FINAL_MAX_TOKENS,
            )
            payload = _parse_json_text(raw)
            return validate_highlight_payload(
                payload,
                video_id=video_id,
                video_name=video_name,
                task_id=task_id,
                parent_task_id=parent_task_id,
                position_mode="beat",
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    assert last_error is not None
    raise RuntimeError(f"文本爆款预测结果解析失败: {last_error}") from last_error


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
