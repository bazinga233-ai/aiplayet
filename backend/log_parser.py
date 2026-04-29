import re
from dataclasses import dataclass


SEGMENTING_PATTERN = re.compile(r"生成视频片段 \[(\d+)/(\d+)\]")
MULTIMODAL_PATTERN = re.compile(r"分析视频片段 \[(\d+)/(\d+)\]")
HIGHLIGHTING_PATTERN = re.compile(r"分析(?:高光|爆款)片段 \[(\d+)/(\d+)\]")


@dataclass(frozen=True)
class ProgressUpdate:
    stage: str
    current: int | None = None
    total: int | None = None


def parse_progress_line(line: str) -> ProgressUpdate | None:
    if "[Step A]" in line or "调用 ASR 接口" in line:
        return ProgressUpdate(stage="asr")

    segmenting_match = SEGMENTING_PATTERN.search(line)
    if "[Step B]" in line or segmenting_match:
        if segmenting_match:
            return ProgressUpdate(
                stage="segmenting",
                current=int(segmenting_match.group(1)),
                total=int(segmenting_match.group(2)),
            )
        return ProgressUpdate(stage="segmenting")

    multimodal_match = MULTIMODAL_PATTERN.search(line)
    if multimodal_match:
        return ProgressUpdate(
            stage="multimodal",
            current=int(multimodal_match.group(1)),
            total=int(multimodal_match.group(2)),
        )

    if "[Step C]" in line or "整合剧本" in line:
        return ProgressUpdate(stage="merging")

    highlighting_match = HIGHLIGHTING_PATTERN.search(line)
    if "[Step Highlight]" in line or "正在识别视频高光" in line or "正在进行爆款预测" in line or highlighting_match:
        if highlighting_match:
            return ProgressUpdate(
                stage="highlighting",
                current=int(highlighting_match.group(1)),
                total=int(highlighting_match.group(2)),
            )
        return ProgressUpdate(stage="highlighting")

    if "[Step Score]" in line or "正在进行剧本评分" in line:
        return ProgressUpdate(stage="scoring")

    if "[Step Optimize]" in line or "正在根据爆款预测优化剧本" in line:
        return ProgressUpdate(stage="optimizing")

    if (
        "剧本已保存:" in line
        or "评分已保存:" in line
        or "高光已保存:" in line
        or "爆款预测结果已保存:" in line
        or "优化剧本已保存:" in line
    ):
        return ProgressUpdate(stage="done")

    return None
