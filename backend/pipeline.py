"""
短剧视频反推剧本工具
方案：远端 ASR（HTTP）+ 分段视频直传远端多模态大模型（OpenAI 兼容接口）
"""

import argparse
import base64
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

from backend.config import (
    FFMPEG_PATH,
    FFPROBE_PATH,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_CHAT_COMPLETIONS_URL,
    LLM_MODEL_NAME,
    LLM_TIMEOUT,
    OUTPUT_DIR,
    ROOT_DIR,
    VIDEOS_DIR,
    ensure_runtime_directories,
)
from backend.fs_cleanup import safe_rmdir, safe_remove_tree, safe_unlink
from backend.media_tools import build_proxy_video_filter, run_checked_command

ASR_URL = os.getenv("NOVALAI_ASR_URL", "http://127.0.0.1:30116/recognition")
ASR_TIMEOUT = 600

SCRIPT_MAX_TOKENS = 4096
SEGMENT_SCRIPT_MAX_TOKENS = 1024

KEYFRAME_INTERVAL = 5
SCENE_THRESHOLD = 30.0
SEGMENT_DURATION = 30.0
SEGMENT_OVERLAP = 3.0
SEGMENT_PROXY_WIDTH = 512
SEGMENT_PROXY_FPS = 8
SEGMENT_PROXY_CRF = 32

VIDEO_DIR = VIDEOS_DIR
TEMP_DIR = Path(tempfile.gettempdir()) / "novalai_temp"
PIPELINE_OUTPUT_FILES = ("dialogues.json", "segments.json", "script.txt")


def ensure_dirs() -> None:
    ensure_runtime_directories()
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def get_video_output_dir(video_name: str) -> Path:
    return OUTPUT_DIR / video_name


def _emit(on_line: Callable[[str], None] | None, message: str) -> None:
    if on_line is not None:
        on_line(message)
        return
    print(message, flush=True)


def _create_output_stage_dir(video_name: str) -> Path:
    stage_dir = TEMP_DIR / f"{video_name}_output_{uuid.uuid4().hex}"
    stage_dir.mkdir(parents=True, exist_ok=False)
    return stage_dir


def _write_stage_file(stage_dir: Path, file_name: str, content: str) -> None:
    (stage_dir / file_name).write_text(content, encoding="utf-8")


def _write_output_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _snapshot_output_dir(output_dir: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    if not output_dir.exists():
        return snapshot
    for child in output_dir.iterdir():
        if child.is_file():
            snapshot[child.name] = child.read_text(encoding="utf-8")
    return snapshot


def _remove_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        safe_remove_tree(output_dir, staging_root=OUTPUT_DIR / ".cleanup-staging")


def _restore_output_dir(output_dir: Path, snapshot: dict[str, str]) -> None:
    _remove_output_dir(output_dir)
    if not snapshot:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name, content in snapshot.items():
        _write_output_file(output_dir / file_name, content)


def _build_publish_payload(stage_dir: Path, previous_snapshot: dict[str, str]) -> dict[str, str]:
    payload = {
        file_name: content
        for file_name, content in previous_snapshot.items()
        if file_name not in PIPELINE_OUTPUT_FILES
    }
    for file_name in PIPELINE_OUTPUT_FILES:
        staged_path = stage_dir / file_name
        if staged_path.exists():
            payload[file_name] = staged_path.read_text(encoding="utf-8")
    return payload


def _commit_staged_outputs(stage_dir: Path, output_dir: Path) -> None:
    previous_snapshot = _snapshot_output_dir(output_dir)
    publish_payload = _build_publish_payload(stage_dir, previous_snapshot)
    try:
        _remove_output_dir(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for file_name, content in publish_payload.items():
            _write_output_file(output_dir / file_name, content)
    except Exception:
        _restore_output_dir(output_dir, previous_snapshot)
        raise


def extract_audio(video_path: str, audio_path: str, on_line: Callable[[str], None] | None = None) -> None:
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        audio_path,
    ]
    run_checked_command(cmd, error_label="音频提取")
    _emit(on_line, f"  音频提取完成: {audio_path}")


def split_text_with_timestamps(text: str, timestamps: list[Any]) -> list[dict]:
    sentences = re.split(r"([。！？])", text)
    dialogues = []
    char_idx = 0
    index = 0

    while index < len(sentences):
        sentence = sentences[index]
        if index + 1 < len(sentences) and re.match(r"^[。！？]$", sentences[index + 1]):
            sentence += sentences[index + 1]
            index += 2
        else:
            index += 1

        sentence = sentence.strip()
        if not sentence:
            continue

        pure_chars = re.sub(r"[，。！？、；：“”\"'（）\s]", "", sentence)
        char_count = len(pure_chars)

        if timestamps and char_idx < len(timestamps) and char_count > 0:
            start_ms, _ = _coerce_timestamp_pair(timestamps[char_idx])
            _, end_ms = _coerce_timestamp_pair(
                timestamps[min(char_idx + char_count - 1, len(timestamps) - 1)]
            )
            start = round(start_ms / 1000.0, 2)
            end = round(end_ms / 1000.0, 2)
        else:
            start = 0.0
            end = 0.0

        char_idx += char_count
        dialogues.append({"start": start, "end": end, "text": sentence})

    return dialogues


def _coerce_timestamp_pair(value: Any) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return float(value[0]), float(value[1])
    if isinstance(value, dict):
        start = value.get("start", value.get("bg", value.get("start_ms", 0)))
        end = value.get("end", value.get("ed", value.get("end_ms", start)))
        return float(start), float(end)
    raise ValueError(f"无法解析时间戳: {value!r}")


def _extract_speaker_id(segment: dict) -> str | None:
    for key in ("speaker_id", "speaker", "speakerId", "spk"):
        value = segment.get(key)
        if value in (None, ""):
            continue
        return str(value).strip()
    return None


def _extract_text_value(payload: Any) -> str | None:
    if isinstance(payload, str):
        text = payload.strip()
        return text or None
    if isinstance(payload, dict):
        for key in ("text", "sentence", "content", "result", "transcript"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            text = _extract_text_value(value)
            if text:
                return text
        return None
    if isinstance(payload, list):
        texts = []
        for item in payload:
            text = _extract_text_value(item)
            if text:
                texts.append(text)
        if texts:
            return "\n".join(texts)
    return None


def _find_text_and_timestamps(payload: Any) -> tuple[str, list[Any]] | None:
    if isinstance(payload, dict):
        text = payload.get("text")
        timestamps = payload.get("timestamp", payload.get("timestamps"))
        if isinstance(text, str) and isinstance(timestamps, list):
            return text.strip(), timestamps
        for value in payload.values():
            found = _find_text_and_timestamps(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_text_and_timestamps(item)
            if found:
                return found
    return None


def _extract_segment_text(segment: dict) -> str:
    for key in ("text", "sentence", "content", "result"):
        value = segment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _find_raw_segment_time(segment: dict, is_end: bool) -> tuple[str, float] | None:
    keys = (
        [("end", False), ("end_time", False), ("finish", False), ("to", False), ("ed", True), ("end_ms", True)]
        if is_end
        else [("start", False), ("start_time", False), ("begin", False), ("from", False), ("bg", True), ("start_ms", True)]
    )

    for key, as_ms in keys:
        value = segment.get(key)
        if value in (None, ""):
            continue
        return key, float(value)
    return None


def _infer_segment_time_unit(segment_list: list[dict], source_key: str | None) -> str:
    explicit_ms_keys = {"bg", "ed", "start_ms", "end_ms"}
    max_value = 0.0
    max_duration = 0.0

    for segment in segment_list:
        start = _find_raw_segment_time(segment, is_end=False)
        end = _find_raw_segment_time(segment, is_end=True)

        for time_point in (start, end):
            if time_point is None:
                continue
            key, value = time_point
            if key in explicit_ms_keys:
                return "milliseconds"
            max_value = max(max_value, abs(value))

        if start is not None and end is not None:
            max_duration = max(max_duration, end[1] - start[1])

    if max_value >= 1000:
        return "milliseconds"
    if source_key in {"sentences", "chunks"} and max_duration >= 20:
        return "milliseconds"
    return "seconds"


def _extract_segment_time(segment: dict, is_end: bool, time_unit: str = "seconds") -> float:
    raw_time = _find_raw_segment_time(segment, is_end=is_end)
    if raw_time is None:
        return 0.0

    key, number = raw_time
    if key in {"bg", "ed", "start_ms", "end_ms"} or time_unit == "milliseconds":
        number = number / 1000.0
    return round(number, 2)


def _build_dialogue_entry(*, text: str, start: float, end: float, speaker_id: str | None = None) -> dict:
    dialogue = {
        "start": round(start, 2),
        "end": round(end, 2),
        "text": text,
    }
    if speaker_id:
        dialogue["speaker_id"] = speaker_id
    return dialogue


def _looks_like_segment_list(payload: Any) -> bool:
    return (
        isinstance(payload, list)
        and payload
        and all(isinstance(item, dict) for item in payload)
        and any(_extract_segment_text(item) for item in payload)
    )


def _find_segment_list(payload: Any) -> tuple[list[dict], str | None] | None:
    if _looks_like_segment_list(payload):
        return payload, None
    if isinstance(payload, dict):
        for key in ("segments", "sentences", "chunks", "data", "result", "results", "output"):
            if key not in payload:
                continue
            found = _find_segment_list(payload[key])
            if found:
                segments, source_key = found
                return segments, source_key or key
        for value in payload.values():
            found = _find_segment_list(value)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_segment_list(item)
            if found:
                return found
    return None


def normalize_asr_response(payload: Any) -> list[dict]:
    segments = _find_segment_list(payload)
    if segments:
        segment_list, source_key = segments
        time_unit = _infer_segment_time_unit(segment_list, source_key)
        dialogues = []
        for segment in segment_list:
            text = _extract_segment_text(segment)
            if not text:
                continue
            dialogues.append(
                _build_dialogue_entry(
                    text=text,
                    start=_extract_segment_time(segment, is_end=False, time_unit=time_unit),
                    end=_extract_segment_time(segment, is_end=True, time_unit=time_unit),
                    speaker_id=_extract_speaker_id(segment),
                )
            )
        if dialogues:
            return dialogues

    text_with_timestamps = _find_text_and_timestamps(payload)
    if text_with_timestamps:
        text, timestamps = text_with_timestamps
        dialogues = split_text_with_timestamps(text, timestamps)
        if dialogues:
            return dialogues

    text = _extract_text_value(payload)
    if text:
        return [{"start": 0.0, "end": 0.0, "text": text}]
    raise ValueError(f"无法解析 ASR 返回结果: {payload!r}")


def read_http_response(response) -> Any:
    raw = response.read()
    charset = response.headers.get_content_charset() or "utf-8"
    text = raw.decode(charset, errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def build_multipart_body(field_name: str, file_path: str, mime_type: str) -> tuple[str, bytes]:
    boundary = f"----novalai-{uuid.uuid4().hex}"
    filename = Path(file_path).name
    file_bytes = Path(file_path).read_bytes()
    body = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
        ).encode("utf-8"),
        f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return f"multipart/form-data; boundary={boundary}", b"".join(body)


def post_multipart_file(
    url: str,
    field_name: str,
    file_path: str,
    mime_type: str,
    timeout: int,
    headers: dict[str, str] | None = None,
) -> Any:
    content_type, body = build_multipart_body(field_name, file_path, mime_type)
    request_headers = {"Content-Type": content_type}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return read_http_response(response)
    except urllib.error.HTTPError as exc:
        detail = read_http_response(exc)
        raise RuntimeError(f"HTTP {exc.code} 调用失败: {detail}") from exc


def transcribe_audio(audio_path: str, on_line: Callable[[str], None] | None = None) -> list[dict]:
    _emit(on_line, f"  调用 ASR 接口: {ASR_URL}")
    payload = post_multipart_file(
        ASR_URL,
        field_name="audio",
        file_path=audio_path,
        mime_type="audio/wav",
        timeout=ASR_TIMEOUT,
        headers={"accept": "application/json"},
    )
    dialogues = normalize_asr_response(payload)
    for dialogue in dialogues:
        speaker_id = str(dialogue.get("speaker_id", "")).strip()
        speaker_prefix = f"{speaker_id} " if speaker_id else ""
        _emit(on_line, f"    [{speaker_prefix}{dialogue['start']:.1f}s - {dialogue['end']:.1f}s] {dialogue['text']}")
    _emit(on_line, f"  语音识别完成，共 {len(dialogues)} 段对白")
    return dialogues


def get_video_duration(video_path: str) -> float:
    cmd = [
        FFPROBE_PATH,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = run_checked_command(cmd, error_label="视频时长探测")
    return float(result.stdout.strip())


def compute_segment_windows(duration: float, segment_duration: float, overlap: float) -> list[dict]:
    if duration <= 0:
        return []
    if segment_duration <= 0:
        raise ValueError("segment_duration 必须大于 0")
    if overlap < 0:
        raise ValueError("overlap 不能小于 0")
    step = segment_duration - overlap
    if step <= 0:
        raise ValueError("overlap 必须小于 segment_duration")

    windows = []
    start = 0.0
    index = 1
    while start < duration:
        end = min(start + segment_duration, duration)
        windows.append({"index": index, "start": round(start, 2), "end": round(end, 2)})
        if end >= duration:
            break
        start = round(start + step, 2)
        index += 1
    return windows


def slice_dialogues_for_window(dialogues: list[dict], start: float, end: float) -> list[dict]:
    return [
        dialogue
        for dialogue in dialogues
        if float(dialogue["end"]) > start and float(dialogue["start"]) < end
    ]


def build_segment_proxy_video(video_path: str, start: float, end: float, output_path: str) -> None:
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
        build_proxy_video_filter(SEGMENT_PROXY_WIDTH, SEGMENT_PROXY_FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        str(SEGMENT_PROXY_CRF),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output_path,
    ]
    run_checked_command(cmd, error_label="视频切段转码")


def create_video_segments(
    video_path: str,
    video_name: str,
    on_line: Callable[[str], None] | None = None,
) -> list[dict]:
    duration = get_video_duration(video_path)
    segment_dir = TEMP_DIR / f"{video_name}_segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    windows = compute_segment_windows(duration=duration, segment_duration=SEGMENT_DURATION, overlap=SEGMENT_OVERLAP)
    _emit(on_line, f"  视频分段完成计划，共 {len(windows)} 段")

    segments = []
    for window in windows:
        segment_path = segment_dir / f"{video_name}_part_{window['index']:02d}.mp4"
        _emit(
            on_line,
            f"  生成视频片段 [{window['index']}/{len(windows)}] "
            f"{window['start']:.2f}s-{window['end']:.2f}s ...",
        )
        build_segment_proxy_video(
            video_path=video_path,
            start=window["start"],
            end=window["end"],
            output_path=str(segment_path),
        )
        segments.append({**window, "video_path": str(segment_path)})
    return segments


def encode_file_as_data_url(file_path: str, mime_type: str) -> str:
    file_bytes = Path(file_path).read_bytes()
    encoded = base64.b64encode(file_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def encode_video_as_data_url(video_path: str) -> str:
    return encode_file_as_data_url(video_path, mime_type="video/mp4")


def extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()
    return str(content).strip()


def sanitize_keyframe_description(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^(这个(请求|用户)|需要包含|限制条件|现在将这些|草稿|精简与润色|整合描述|分析图片内容)", line):
            continue
        line = re.sub(r"^\d+\.\s*", "", line)
        line = line.replace("**", "").strip()
        if "：" in line:
            prefix, suffix = line.split("：", 1)
            if prefix.strip() in {
                "场景环境",
                "人物",
                "穿着",
                "人物动作和表情",
                "动作和表情",
                "画面氛围",
                "氛围",
            }:
                line = suffix.strip()
        if not line or re.match(r"^[\-\*\u2022]", line):
            continue
        lines.append(line.rstrip("，,。.;；:： "))

    cleaned = "，".join(lines)
    cleaned = re.sub(r"\s+", " ", cleaned).strip("， ")
    if not cleaned:
        return ""
    if len(cleaned) > 120:
        cleaned = cleaned[:120].rstrip("，,。.;；:： ") + "。"
    elif cleaned[-1] not in "。！？!?":
        cleaned += "。"
    return cleaned


def extract_completion_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                message = first_choice.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    text = extract_message_text(content)
                    if text:
                        return text
                text = first_choice.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    text = _extract_text_value(payload)
    if text:
        return text
    raise ValueError(f"无法解析大模型返回结果: {payload!r}")


def post_json(url: str, payload: dict, timeout: int, headers: dict[str, str] | None = None) -> Any:
    request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return read_http_response(response)
    except urllib.error.HTTPError as exc:
        detail = read_http_response(exc)
        raise RuntimeError(f"HTTP {exc.code} 调用失败: {detail}") from exc


def build_chat_completion_payload(content: list[dict], max_tokens: int) -> dict:
    return {
        "model": LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "top_p": 0.95,
        "presence_penalty": 0.1,
        "top_k": 20,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def call_llm(content: list[dict], max_tokens: int) -> str:
    payload = build_chat_completion_payload(content, max_tokens=max_tokens)
    response = post_json(
        LLM_CHAT_COMPLETIONS_URL,
        payload,
        timeout=LLM_TIMEOUT,
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
    )
    return extract_completion_text(response)


def format_timestamp(seconds: float) -> str:
    text = f"{seconds:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def build_dialogue_timeline(dialogues: list[dict]) -> str:
    if not dialogues:
        return "（无对白，请主要依据画面判断剧情）"
    return "\n".join(
        (
            f"[对白 {dialogue['speaker_id']} {format_timestamp(dialogue['start'])}s-{format_timestamp(dialogue['end'])}s] {dialogue['text']}"
            if dialogue.get("speaker_id")
            else f"[对白 {format_timestamp(dialogue['start'])}s-{format_timestamp(dialogue['end'])}s] {dialogue['text']}"
        )
        for dialogue in dialogues
    )


def build_video_script_prompt(dialogues: list[dict], start: float | None = None, end: float | None = None) -> str:
    clip_range = ""
    if start is not None and end is not None:
        clip_range = f"当前视频片段时间范围：{format_timestamp(start)}s-{format_timestamp(end)}s。\n"
    return f"""你是一个专业的短剧编剧。请直接观看完整视频，并结合提供的ASR对白时间轴，输出这个视频片段的中文短剧分场草稿。

要求：
1. 以视频画面为主理解剧情，不要凭空补充画面中没有的信息。
2. 修正ASR中的明显错字、明显误断句、明显称谓错误，但不要改变原意。
3. 如果片段中发生场景切换，可以拆成多个小场，但总量保持精简。
4. 优先识别人物关系、动作、情绪变化和剧情推进，不要只做静态画面描述。
5. 画面描述不要复述底部字幕、底部配文、口播字幕；但手机消息、聊天记录、招牌、牌匾等影响剧情理解的画面内文字可以保留。
6. 输出格式必须为：
【片段信息】
- 时间范围：
- 剧情摘要：
- 出场人物：
【分场草稿】
按“场景标题 / 画面描述 / 角色对白”输出。
7. 直接输出结果，不要解释你的分析过程，不要说“根据视频”。
8. 如果对白时间轴里出现 SPEAKER 标签，同一 SPEAKER 标签可视为同一说话人，并结合画面判断其对应人物身份。

{clip_range}对白时间轴：
{build_dialogue_timeline(dialogues)}
"""


def build_video_script_content(
    video_path: str,
    dialogues: list[dict],
    start: float | None = None,
    end: float | None = None,
) -> list[dict]:
    return [
        {"type": "video_url", "video_url": {"url": encode_video_as_data_url(video_path)}},
        {"type": "text", "text": build_video_script_prompt(dialogues, start=start, end=end)},
    ]


def analyze_video_segments(
    segments: list[dict],
    dialogues: list[dict],
    on_line: Callable[[str], None] | None = None,
) -> list[dict]:
    analyzed = []
    for segment in segments:
        segment_dialogues = slice_dialogues_for_window(dialogues, start=segment["start"], end=segment["end"])
        _emit(
            on_line,
            f"  分析视频片段 [{segment['index']}/{len(segments)}] "
            f"{segment['start']:.2f}s-{segment['end']:.2f}s ...",
        )
        draft = call_llm(
            build_video_script_content(
                segment["video_path"],
                segment_dialogues,
                start=segment["start"],
                end=segment["end"],
            ),
            max_tokens=SEGMENT_SCRIPT_MAX_TOKENS,
        )
        analyzed.append(
            {
                **segment,
                "dialogue_count": len(segment_dialogues),
                "draft": draft.strip(),
            }
        )
        _emit(on_line, f"    → 已生成片段草稿，长度 {len(draft.strip())} 字")
    return analyzed


def _clean_description_clause(clause: str) -> str:
    return clause.strip().strip("，,；;。！？!? ")


def _is_bottom_subtitle_clause(clause: str) -> bool:
    normalized = _clean_description_clause(clause)
    if not normalized:
        return False
    return bool(
        re.search(
            r"(底部字幕|画面底部字幕|屏幕底部字幕|下方字幕|画面下方字幕|屏幕下方字幕|底部配文|下方配文|口播字幕|旁白字幕)",
            normalized,
        )
        or re.match(r"^(字幕|画面字幕|屏幕字幕)(显示|写着|写道|为|是|内容为|内容是)", normalized)
    )


def _cleanup_description_text(text: str) -> str:
    parts = [_clean_description_clause(part) for part in re.split(r"[，；;]", text)]
    kept = [part for part in parts if part and not _is_bottom_subtitle_clause(part)]
    if not kept:
        return ""
    cleaned = "，".join(kept).strip("， ")
    if cleaned and cleaned[-1] not in "。！？!?":
        cleaned += "。"
    return cleaned


def remove_bottom_subtitle_lines(script: str) -> str:
    cleaned_lines = []
    for raw_line in script.splitlines():
        if raw_line.startswith("**画面描述**："):
            prefix, description = raw_line.split("：", 1)
            cleaned_description = _cleanup_description_text(description)
            cleaned_lines.append(f"{prefix}：{cleaned_description}")
            continue
        cleaned_lines.append(raw_line)
    return "\n".join(cleaned_lines).strip()


def build_merge_script_prompt(segment_drafts: list[dict]) -> str:
    parts = []
    for segment in segment_drafts:
        parts.append(
            (
                f"### 片段 {segment['index']} "
                f"({format_timestamp(segment['start'])}s-{format_timestamp(segment['end'])}s)\n"
                f"{segment['draft']}"
            )
        )
    segment_text = "\n\n".join(parts)
    return f"""你是一个专业的短剧编剧。以下是同一部短剧按时间切分后得到的分段视频理解草稿，相邻片段之间存在少量时间重叠。

请将这些分段草稿去重、合并、补足衔接，整理成一份完整的中文短剧剧本。

要求：
1. 输出完整成稿，不要截断，不要停在半句话。
2. 统一角色称谓、人物关系和场景命名。
3. 遇到相邻片段的重复内容，只保留一次最完整、最通顺的表达。
4. 允许根据视频理解修正ASR中的明显错误，但不要改写剧情走向。
5. 最终剧本中的画面描述不要复述底部字幕、底部配文、口播字幕；但手机消息、聊天记录、招牌、牌匾等影响剧情理解的画面内文字可以保留。
6. 最终格式：
# 短剧剧本：《标题》
## 第X场
**场景标题**：
**画面描述**：
**角色对白**：
7. 只输出最终剧本，不要额外解释。

分段草稿：
{segment_text}
"""


def generate_script(segment_drafts: list[dict], on_line: Callable[[str], None] | None = None) -> str:
    _emit(on_line, "  整合剧本...")
    script = call_llm(
        [{"type": "text", "text": build_merge_script_prompt(segment_drafts)}],
        max_tokens=SCRIPT_MAX_TOKENS,
    )
    return remove_bottom_subtitle_lines(script.strip())


def _cleanup_generated_artifacts(video_name: str, audio_path: Path, segments: list[dict]) -> None:
    for segment in segments:
        segment_path = Path(segment["video_path"])
        safe_unlink(
            segment_path,
            missing_ok=True,
            staging_root=TEMP_DIR / ".cleanup-staging",
            best_effort=True,
        )

    segment_dir = TEMP_DIR / f"{video_name}_segments"
    if segment_dir.exists():
        safe_rmdir(
            segment_dir,
            staging_root=TEMP_DIR / ".cleanup-staging",
            best_effort=True,
        )

    if audio_path.exists():
        safe_unlink(
            audio_path,
            missing_ok=True,
            staging_root=TEMP_DIR / ".cleanup-staging",
            best_effort=True,
        )


def _cleanup_stage_dir(stage_dir: Path | None) -> None:
    if stage_dir is None or not stage_dir.exists():
        return
    for file_name in PIPELINE_OUTPUT_FILES:
        staged_path = stage_dir / file_name
        safe_unlink(
            staged_path,
            missing_ok=True,
            staging_root=TEMP_DIR / ".cleanup-staging",
            best_effort=True,
        )
    safe_rmdir(
        stage_dir,
        staging_root=TEMP_DIR / ".cleanup-staging",
        best_effort=True,
    )


def run_video_pipeline(video_path: str, on_line: Callable[[str], None] | None = None) -> int:
    resolved_video_path = str(Path(video_path).resolve())
    video_name = Path(resolved_video_path).stem
    audio_path = TEMP_DIR / f"{video_name}.wav"
    segments: list[dict] = []
    stage_dir: Path | None = None

    try:
        _emit(on_line, "=" * 60)
        _emit(on_line, f"处理视频: {video_name}")
        _emit(on_line, "=" * 60)

        ensure_dirs()
        video_output_dir = get_video_output_dir(video_name)
        video_output_dir.mkdir(parents=True, exist_ok=True)
        stage_dir = _create_output_stage_dir(video_name)

        _emit(on_line, "[Step A] 提取音频并转文字...")
        extract_audio(resolved_video_path, str(audio_path), on_line=on_line)
        dialogues = transcribe_audio(str(audio_path), on_line=on_line)
        _write_stage_file(
            stage_dir,
            "dialogues.json",
            json.dumps(dialogues, ensure_ascii=False, indent=2),
        )

        _emit(on_line, "[Step B] 切分视频并直传大模型...")
        segments = create_video_segments(resolved_video_path, video_name, on_line=on_line)
        segment_drafts = analyze_video_segments(segments, dialogues, on_line=on_line)
        segments_save = [
            {
                "index": item["index"],
                "start": item["start"],
                "end": item["end"],
                "dialogue_count": item["dialogue_count"],
                "draft": item["draft"],
            }
            for item in segment_drafts
        ]
        _write_stage_file(
            stage_dir,
            "segments.json",
            json.dumps(segments_save, ensure_ascii=False, indent=2),
        )

        _emit(on_line, "[Step C] 生成剧本...")
        script = generate_script(segment_drafts, on_line=on_line)
        _write_stage_file(stage_dir, "script.txt", script)
        _commit_staged_outputs(stage_dir, video_output_dir)
        output_path = video_output_dir / "script.txt"
        _emit(on_line, f"剧本已保存: {output_path}")
        return 0
    except Exception as exc:
        _emit(on_line, f"生成失败: {exc}")
        return 1
    finally:
        _cleanup_generated_artifacts(video_name, audio_path, segments)
        _cleanup_stage_dir(stage_dir)


def process_video(video_path: str, on_line: Callable[[str], None] | None = None) -> str:
    exit_code = run_video_pipeline(video_path, on_line=on_line)
    if exit_code != 0:
        raise RuntimeError(f"视频处理失败: {video_path}")
    output_path = get_video_output_dir(Path(video_path).stem) / "script.txt"
    return output_path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="短剧视频反推剧本")
    parser.add_argument("video", nargs="?", help="视频文件路径，不指定则处理 videos/ 下所有 mp4")
    args = parser.parse_args()

    if args.video:
        return run_video_pipeline(args.video, on_line=print)

    videos = sorted(VIDEO_DIR.glob("*.mp4"))
    if not videos:
        print("未找到视频文件")
        return 0

    for video in videos:
        exit_code = run_video_pipeline(str(video), on_line=print)
        if exit_code != 0:
            return exit_code
    return 0


__all__ = [
    "ASR_TIMEOUT",
    "ASR_URL",
    "FFMPEG_PATH",
    "FFPROBE_PATH",
    "KEYFRAME_INTERVAL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_CHAT_COMPLETIONS_URL",
    "LLM_MODEL_NAME",
    "LLM_TIMEOUT",
    "OUTPUT_DIR",
    "ROOT_DIR",
    "SCRIPT_MAX_TOKENS",
    "SCENE_THRESHOLD",
    "SEGMENT_DURATION",
    "SEGMENT_OVERLAP",
    "SEGMENT_PROXY_CRF",
    "SEGMENT_PROXY_FPS",
    "SEGMENT_PROXY_WIDTH",
    "SEGMENT_SCRIPT_MAX_TOKENS",
    "TEMP_DIR",
    "VIDEO_DIR",
    "analyze_video_segments",
    "build_chat_completion_payload",
    "build_merge_script_prompt",
    "build_multipart_body",
    "build_video_script_content",
    "build_video_script_prompt",
    "call_llm",
    "compute_segment_windows",
    "create_video_segments",
    "encode_file_as_data_url",
    "encode_video_as_data_url",
    "ensure_dirs",
    "extract_audio",
    "extract_completion_text",
    "extract_message_text",
    "format_timestamp",
    "generate_script",
    "get_video_output_dir",
    "get_video_duration",
    "main",
    "normalize_asr_response",
    "post_json",
    "post_multipart_file",
    "process_video",
    "read_http_response",
    "remove_bottom_subtitle_lines",
    "run_video_pipeline",
    "sanitize_keyframe_description",
    "slice_dialogues_for_window",
    "split_text_with_timestamps",
    "transcribe_audio",
]
