import unittest

from backend import highlights as highlights_module


def build_valid_highlight_response():
    return {
        "summary": "高光主要集中在中后段。",
        "highlights": [
            {
                "start": 12.0,
                "end": 18.0,
                "label": "爆点",
                "reason": "第一次反转出现。",
            },
            {
                "start": 45.0,
                "end": 53.0,
                "label": "高潮",
                "reason": "冲突达到峰值。",
            },
            {
                "start": 70.0,
                "end": 78.0,
                "label": "高燃",
                "reason": "情绪和动作同时抬升。",
            },
        ],
        "best_climax": {
            "start": 45.0,
            "end": 53.0,
            "title": "终极高潮",
            "reason": "核心冲突在这里集中爆发。",
        },
    }


class WorkbenchHighlightTests(unittest.TestCase):
    def test_validate_highlight_payload_accepts_valid_payload(self):
        payload = build_valid_highlight_response()

        highlights = highlights_module.validate_highlight_payload(
            payload,
            video_id="video-1",
            video_name="demo",
            task_id="highlight-task-1",
            parent_task_id="generate-task-1",
        )

        self.assertEqual(len(highlights.highlights), 3)
        self.assertEqual(highlights.best_climax.title, "终极高潮")

    def test_validate_highlight_payload_rejects_best_climax_outside_highlights(self):
        payload = build_valid_highlight_response()
        payload["best_climax"] = {
            "start": 90.0,
            "end": 95.0,
            "title": "越界高潮",
            "reason": "不应该通过。",
        }

        with self.assertRaises(ValueError):
            highlights_module.validate_highlight_payload(
                payload,
                video_id="video-1",
                video_name="demo",
                task_id="highlight-task-1",
                parent_task_id="generate-task-1",
            )


if __name__ == "__main__":
    unittest.main()
