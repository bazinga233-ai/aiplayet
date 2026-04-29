import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from backend.config import (
    LLM_API_KEY,
    LLM_CHAT_COMPLETIONS_URL,
    LLM_MODEL_NAME,
    LLM_TIMEOUT,
)


def read_http_response(response) -> Any:
    raw = response.read()
    charset = response.headers.get_content_charset() or "utf-8"
    text = raw.decode(charset, errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def post_json(url: str, payload: dict, timeout: int, headers: dict[str, str] | None = None) -> Any:
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
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


def encode_file_as_data_url(file_path: str | Path, mime_type: str) -> str:
    file_bytes = Path(file_path).read_bytes()
    encoded = base64.b64encode(file_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def encode_video_as_data_url(video_path: str | Path) -> str:
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

    raise ValueError(f"无法解析大模型返回结果: {payload!r}")


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
