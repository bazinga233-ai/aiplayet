import unittest

from backend.models import BestOpportunity, EmotionPoint, HighlightPayload, PredictionWindow

import backend.optimization as optimization_module


def build_highlight_payload(position_mode: str = "time") -> HighlightPayload:
    return HighlightPayload(
        version=2,
        video_id="video-1",
        video_name="demo",
        task_id="highlight-1",
        parent_task_id="generate-1" if position_mode == "time" else None,
        generated_at="2026-04-09T10:00:00Z",
        model={"base_url": "http://example.test/v1", "model_name": "demo-model"},
        summary="中段张力下滑，反转机会偏后。",
        breakout_score=71,
        position_mode=position_mode,
        emotion_curve=[
            EmotionPoint(time=1.0, tension=64, risk=20),
            EmotionPoint(time=2.0, tension=45, risk=72),
        ],
        risk_windows=[
            PredictionWindow(
                start=2.0,
                end=3.0,
                kind="情绪下滑" if position_mode == "time" else "信息停滞",
                reason="中段推进明显放缓。",
                suggestion="提前抛出关键信息。",
                confidence=82,
            )
        ],
        opportunity_windows=[
            PredictionWindow(
                start=3.0,
                end=4.0,
                kind="反转机会",
                reason="冲突已经铺垫到位。",
                suggestion="在这里插入反转。",
                confidence=78,
            )
        ],
        best_opportunity=BestOpportunity(
            start=3.0,
            end=4.0,
            kind="关键修正点",
            reason="这是全稿最值得强化的位置。",
            suggestion="在此补足反转与对白刺激。",
            confidence=84,
        ),
    )


class WorkbenchOptimizationTests(unittest.TestCase):
    def test_build_optimize_prompt_uses_highlight_windows_for_video_assets(self):
        prompt = optimization_module.build_optimize_prompt(
            asset_type="video",
            dialogues=[{"text": "你好"}],
            segments=[{"summary": "第一段"}],
            script="旧剧本",
            highlights=build_highlight_payload(),
        )

        self.assertIn("与原视频一致性", prompt)
        self.assertIn("信息完整性", prompt)
        self.assertIn("对白", prompt)
        self.assertIn("中段张力下滑，反转机会偏后。", prompt)
        self.assertIn("中段推进明显放缓。", prompt)
        self.assertIn("在这里插入反转。", prompt)
        self.assertNotIn("评分", prompt)

    def test_build_optimize_prompt_uses_script_specific_goals_for_text_assets(self):
        prompt = optimization_module.build_optimize_prompt(
            asset_type="script",
            dialogues=[],
            segments=[],
            script="旧剧本",
            highlights=build_highlight_payload(position_mode="beat"),
        )

        self.assertIn("节奏张力", prompt)
        self.assertIn("信息密度", prompt)
        self.assertIn("对白吸引力", prompt)
        self.assertNotIn("与原视频一致性", prompt)
        self.assertIn("中段推进明显放缓。", prompt)


if __name__ == "__main__":
    unittest.main()
