"""远端 ASR HTTP 服务烟雾测试。"""

import argparse
from pathlib import Path

import video2script


def main():
    parser = argparse.ArgumentParser(description="测试远端 ASR HTTP 接口")
    parser.add_argument("audio", help="待识别的 wav 音频路径")
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    print(f"calling asr: {video2script.ASR_URL}")
    payload = video2script.post_multipart_file(
        video2script.ASR_URL,
        field_name="audio",
        file_path=str(audio_path),
        mime_type="audio/wav",
        timeout=video2script.ASR_TIMEOUT,
        headers={"accept": "application/json"},
    )
    dialogues = video2script.normalize_asr_response(payload)

    print(f"dialogue count: {len(dialogues)}")
    for dialogue in dialogues:
        speaker_id = str(dialogue.get("speaker_id", "")).strip()
        speaker_prefix = f"{speaker_id} " if speaker_id else ""
        print(f"[{speaker_prefix}{dialogue['start']:.2f}s - {dialogue['end']:.2f}s] {dialogue['text']}")


if __name__ == "__main__":
    main()
