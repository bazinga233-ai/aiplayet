import json

from backend.config import OUTPUT_DIR
from backend.fs_cleanup import safe_unlink
from backend.llm_client import call_llm, encode_video_as_data_url
from backend.models import ASSET_TYPE_SCRIPT, ASSET_TYPE_VIDEO, HighlightPayload
from backend.scoring import build_score_proxy_video
from backend.viral_prediction import load_highlight_payload

OPTIMIZE_MAX_TOKENS = 4096
OPTIMIZE_TEMP_DIR = OUTPUT_DIR / "_optimize_tmp"


def _format_windows(title: str, windows: list) -> str:
    if not windows:
        return f"{title}：无\n"
    rows = [f"{title}："]
    for item in windows:
        rows.append(
            f"- {item.kind} | {item.start}-{item.end} | 理由：{item.reason} | 建议：{item.suggestion} | 置信度：{item.confidence}%"
        )
    return "\n".join(rows)


def build_optimize_prompt(
    *,
    asset_type: str,
    dialogues: list[dict],
    segments: list[dict],
    script: str,
    highlights: HighlightPayload,
    retry: bool = False,
) -> str:
    retry_notice = (
        "上一次输出为空或格式不合格。本次必须直接输出完整优化后的剧本正文，不能有解释、标题前言、Markdown 代码块。\n"
        if retry
        else ""
    )
    highlight_text = "\n\n".join(
        [
            f"爆款预测总结：{highlights.summary}",
            _format_windows("下滑风险窗口", highlights.risk_windows),
            _format_windows("放大机会窗口", highlights.opportunity_windows),
            (
                "最佳修正点："
                f"{highlights.best_opportunity.kind} | {highlights.best_opportunity.start}-{highlights.best_opportunity.end} | "
                f"理由：{highlights.best_opportunity.reason} | 建议：{highlights.best_opportunity.suggestion}"
                if highlights.best_opportunity
                else "最佳修正点：无"
            ),
        ]
    )
    if asset_type == ASSET_TYPE_SCRIPT:
        goals = """你的优化目标只围绕以下维度展开：
1. 节奏张力：减少中段疲软，增强推进感。
2. 信息密度：补足关键钩子、反转和承接。
3. 对白吸引力：让对白更自然、更有记忆点。
4. 逻辑连贯：避免为追求刺激而破坏人物与因果。"""
        hard_rules = """硬性要求：
1. 只根据当前剧本和爆款预测结果修剧本，不要脱离现有剧情框架乱改设定。
2. 输出必须是完整剧本，不是局部修改建议。
3. 保持当前剧本整体格式风格，继续使用剧本正文输出，不要解释修改过程。
4. 不要输出“优化说明”“修改点”“总结”等额外内容。"""
    else:
        goals = """你的优化目标只围绕以下三个维度展开：
1. 与原视频一致性：修正人物、事件、顺序、情绪、细节上的编错。
2. 信息完整性：补齐关键情节、转折、关系、结尾缺失。
3. 对白：让对白更贴近原视频表达，不要生硬改写。"""
        hard_rules = """硬性要求：
1. 只根据视频、对白、分段、当前剧本和爆款预测结果修剧本，不要凭空新增视频里没有的信息。
2. 输出必须是完整剧本，不是局部修改建议。
3. 保持当前剧本整体格式风格，继续使用剧本正文输出，不要解释修改过程。
4. 不要输出“优化说明”“修改点”“总结”等额外内容。"""

    return f"""你是短剧剧本优化编辑。请结合当前剧本和爆款预测结果，输出一份完整优化后的中文短剧剧本。

{goals}

{hard_rules}

{retry_notice}爆款预测依据：
{highlight_text}

对白 JSON：
{json.dumps(dialogues, ensure_ascii=False)}

分段 JSON：
{json.dumps(segments, ensure_ascii=False)}

当前剧本：
{script}
"""


def build_optimize_content(
    video_path: str,
    *,
    asset_type: str,
    dialogues: list[dict],
    segments: list[dict],
    script: str,
    highlights: HighlightPayload,
    retry: bool = False,
) -> list[dict]:
    prompt = build_optimize_prompt(
        asset_type=asset_type,
        dialogues=dialogues,
        segments=segments,
        script=script,
        highlights=highlights,
        retry=retry,
    )
    if asset_type == ASSET_TYPE_SCRIPT:
        return [{"type": "text", "text": prompt}]
    return [
        {"type": "video_url", "video_url": {"url": encode_video_as_data_url(video_path)}},
        {
            "type": "text",
            "text": prompt,
        },
    ]


def normalize_optimized_script(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    if not text:
        raise RuntimeError("优化剧本为空")
    return text


def optimize_video_script(
    *,
    asset_type: str,
    video_id: str,
    video_name: str,
    video_path: str,
    task_id: str,
    parent_task_id: str | None,
) -> str:
    output_dir = OUTPUT_DIR / video_name
    if asset_type == ASSET_TYPE_VIDEO:
        dialogues = json.loads((output_dir / "dialogues.json").read_text(encoding="utf-8"))
        segments = json.loads((output_dir / "segments.json").read_text(encoding="utf-8"))
    else:
        dialogues = []
        segments = []
    script = (output_dir / "script.txt").read_text(encoding="utf-8")
    highlights = load_highlight_payload(output_dir)
    if highlights is None:
        raise RuntimeError("优化剧本前必须先完成爆款预测")

    proxy_path = None
    try:
        if asset_type == ASSET_TYPE_VIDEO:
            OPTIMIZE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
            proxy_path = OPTIMIZE_TEMP_DIR / f"{video_name}_{task_id}_optimize_proxy.mp4"
            build_score_proxy_video(video_path, proxy_path)

        last_error: Exception | None = None
        for retry in (False, True):
            try:
                raw = call_llm(
                    build_optimize_content(
                        str(proxy_path or ""),
                        asset_type=asset_type,
                        dialogues=dialogues,
                        segments=segments,
                        script=script,
                        highlights=highlights,
                        retry=retry,
                    ),
                    max_tokens=OPTIMIZE_MAX_TOKENS,
                )
                return normalize_optimized_script(raw)
            except Exception as exc:  # noqa: BLE001
                last_error = exc

        assert last_error is not None
        raise RuntimeError(f"优化剧本失败: {last_error}") from last_error
    finally:
        if proxy_path is not None:
            safe_unlink(
                proxy_path,
                missing_ok=True,
                staging_root=OPTIMIZE_TEMP_DIR / ".cleanup-staging",
                best_effort=True,
            )
