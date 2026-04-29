import unittest
from pathlib import Path

from backend.viral_prediction import load_highlight_payload

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "viral_prediction"


class ViralPredictionPayloadTests(unittest.TestCase):
    def test_loads_new_predictor_payload(self):
        output_dir = FIXTURE_ROOT / "new"

        payload = load_highlight_payload(output_dir)

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload.breakout_score, 74)
        self.assertEqual(len(payload.emotion_curve), 2)
        self.assertEqual(payload.risk_windows[0].kind, "情绪下滑")
        self.assertEqual(payload.best_opportunity.kind, "关键修正点")

    def test_converts_legacy_highlight_payload(self):
        output_dir = FIXTURE_ROOT / "legacy"

        payload = load_highlight_payload(output_dir)

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload.version, 2)
        self.assertGreaterEqual(payload.breakout_score, 60)
        self.assertEqual(len(payload.opportunity_windows), 2)
        self.assertEqual(payload.best_opportunity.start, 45.0)
        self.assertEqual(payload.best_opportunity.kind, "高潮放大")
        self.assertEqual(payload.risk_windows, [])


if __name__ == "__main__":
    unittest.main()
