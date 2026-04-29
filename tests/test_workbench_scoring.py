import contextlib
import json
import shutil
import uuid
from pathlib import Path
import unittest
from unittest.mock import patch

from backend import scoring as scoring_module


@contextlib.contextmanager
def temporary_scoring_fixture():
    fixtures_root = Path.cwd() / ".tmp_testfixtures"
    fixtures_root.mkdir(exist_ok=True)
    root = fixtures_root / f"novalai_scoring_{uuid.uuid4().hex}"
    videos_dir = root / "videos"
    outputs_dir = root / "output"
    videos_dir.mkdir(parents=True)
    outputs_dir.mkdir()

    video_path = videos_dir / "demo.mp4"
    video_path.write_bytes(b"dummy video bytes")

    output_dir = outputs_dir / "demo"
    output_dir.mkdir()
    (output_dir / "dialogues.json").write_text('[{"text":"你好","start":0,"end":1}]', encoding="utf-8")
    (output_dir / "segments.json").write_text('[{"index":1,"draft":"片段草稿"}]', encoding="utf-8")
    (output_dir / "script.txt").write_text("示例剧本", encoding="utf-8")

    original_output_dir = scoring_module.OUTPUT_DIR
    scoring_module.OUTPUT_DIR = outputs_dir
    try:
        yield {
            "video_id": "video-1",
            "video_name": "demo",
            "video_path": str(video_path),
            "output_dir": output_dir,
        }
    finally:
        scoring_module.OUTPUT_DIR = original_output_dir
        shutil.rmtree(root, ignore_errors=True)


def build_valid_score_response():
    dimensions = []
    total = 0
    for key, label, max_score in scoring_module.SCORE_DIMENSIONS:
        score = max_score
        total += score
        dimensions.append(
            {
                "key": key,
                "label": label,
                "score": score,
                "max_score": max_score,
                "reason": f"{label}表现正常",
            }
        )
    return {
        "total_score": total,
        "summary": "整体表现正常",
        "dimensions": dimensions,
    }


class WorkbenchScoringTests(unittest.TestCase):
    def test_score_dimensions_drop_removed_dimensions_and_still_total_100(self):
        keys = [key for key, _, _ in scoring_module.SCORE_DIMENSIONS]
        labels = [label for _, label, _ in scoring_module.SCORE_DIMENSIONS]
        total = sum(max_score for _, _, max_score in scoring_module.SCORE_DIMENSIONS)

        self.assertNotIn("premise_theme", keys)
        self.assertNotIn("style_tone_theme", keys)
        self.assertNotIn("概念/立意", labels)
        self.assertNotIn("风格/语气/主题", labels)
        self.assertEqual(total, 100)

    def test_validate_score_payload_normalizes_mismatched_total_score(self):
        payload = build_valid_score_response()
        payload["total_score"] += 3

        score = scoring_module.validate_score_payload(
            payload,
            video_id="video-1",
            video_name="demo",
            task_id="score-task-1",
            parent_task_id="generate-task-1",
        )

        self.assertEqual(score.total_score, 100)

    def test_score_video_script_uses_proxy_video_instead_of_original(self):
        with temporary_scoring_fixture() as fixture:
            captured: dict[str, str] = {}

            def fake_encode_video_as_data_url(path: str) -> str:
                captured["encoded_path"] = path
                return path

            def fake_build_score_proxy_video(video_path: str, output_path: str):
                Path(output_path).write_bytes(b"proxy video bytes")

            with (
                patch(
                    "backend.scoring.encode_video_as_data_url",
                    side_effect=fake_encode_video_as_data_url,
                ),
                patch(
                    "backend.scoring.build_score_proxy_video",
                    side_effect=fake_build_score_proxy_video,
                ),
                patch(
                    "backend.scoring.call_llm",
                    return_value=json.dumps(build_valid_score_response(), ensure_ascii=False),
                ),
            ):
                score = scoring_module.score_video_script(
                    video_id=fixture["video_id"],
                    video_name=fixture["video_name"],
                    video_path=fixture["video_path"],
                    task_id="score-task-1",
                    parent_task_id="generate-task-1",
                )

            self.assertEqual(score.total_score, 100)
            self.assertNotEqual(captured["encoded_path"], fixture["video_path"])
            self.assertTrue(captured["encoded_path"].endswith("_score_proxy.mp4"))


if __name__ == "__main__":
    unittest.main()
