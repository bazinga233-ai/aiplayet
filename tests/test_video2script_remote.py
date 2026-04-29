import unittest
from pathlib import Path

from backend.fs_cleanup import safe_unlink
import video2script


class NormalizeAsrResponseTests(unittest.TestCase):
    def test_default_asr_url_uses_local_placeholder(self):
        self.assertEqual(video2script.ASR_URL, "http://127.0.0.1:30116/recognition")

    def test_normalize_asr_response_accepts_segment_list(self):
        payload = {
            "segments": [
                {"text": "你好。", "start": 0.0, "end": 1.25},
                {"text": "再见。", "start": 1.25, "end": 2.5},
            ]
        }

        dialogues = video2script.normalize_asr_response(payload)

        self.assertEqual(
            dialogues,
            [
                {"start": 0.0, "end": 1.25, "text": "你好。"},
                {"start": 1.25, "end": 2.5, "text": "再见。"},
            ],
        )

    def test_normalize_asr_response_accepts_local_sentence_payload(self):
        payload = {
            "text": "您好，我是通通中国联通的医顾们，有什么可以帮您的吗？",
            "sentences": [
                {"text": "您好，", "start": 70, "end": 510},
                {"text": "我是通通中国联通的医顾们，", "start": 770, "end": 3650},
                {"text": "有什么可以帮您的吗？", "start": 3850, "end": 5335},
            ],
            "code": 0,
        }

        dialogues = video2script.normalize_asr_response(payload)

        self.assertEqual(
            dialogues,
            [
                {"start": 0.07, "end": 0.51, "text": "您好，"},
                {"start": 0.77, "end": 3.65, "text": "我是通通中国联通的医顾们，"},
                {"start": 3.85, "end": 5.33, "text": "有什么可以帮您的吗？"},
            ],
        )

    def test_normalize_asr_response_preserves_speaker_id_from_sentences(self):
        payload = {
            "text": "早啊，这么巧。对呀，这家的豆子特别香。",
            "sentences": [
                {"speaker_id": "SPEAKER_00", "text": "早啊，这么巧。", "start": 890, "end": 3830},
                {"speaker_id": "SPEAKER_01", "text": "对呀，这家的豆子特别香。", "start": 5650, "end": 9820},
            ],
            "code": 0,
        }

        dialogues = video2script.normalize_asr_response(payload)

        self.assertEqual(
            dialogues,
            [
                {"speaker_id": "SPEAKER_00", "start": 0.89, "end": 3.83, "text": "早啊，这么巧。"},
                {"speaker_id": "SPEAKER_01", "start": 5.65, "end": 9.82, "text": "对呀，这家的豆子特别香。"},
            ],
        )

    def test_normalize_asr_response_prefers_structured_sentences_over_text_timestamps(self):
        payload = {
            "text": "甲说。乙答。",
            "timestamp": [[0, 500], [500, 1000], [1000, 1500], [1500, 2000]],
            "sentences": [
                {"speaker_id": "SPEAKER_00", "text": "甲说。", "start": 0.0, "end": 1.0},
                {"speaker_id": "SPEAKER_01", "text": "乙答。", "start": 1.0, "end": 2.0},
            ],
            "code": 0,
        }

        dialogues = video2script.normalize_asr_response(payload)

        self.assertEqual(
            dialogues,
            [
                {"speaker_id": "SPEAKER_00", "start": 0.0, "end": 1.0, "text": "甲说。"},
                {"speaker_id": "SPEAKER_01", "start": 1.0, "end": 2.0, "text": "乙答。"},
            ],
        )

    def test_normalize_asr_response_infers_millisecond_segments_without_sentences_key(self):
        payload = {
            "segments": [
                {"speaker_id": "SPEAKER_00", "text": "你好。", "start": 890, "end": 3830},
                {"speaker_id": "SPEAKER_01", "text": "再见。", "start": 5650, "end": 9820},
            ]
        }

        dialogues = video2script.normalize_asr_response(payload)

        self.assertEqual(
            dialogues,
            [
                {"speaker_id": "SPEAKER_00", "start": 0.89, "end": 3.83, "text": "你好。"},
                {"speaker_id": "SPEAKER_01", "start": 5.65, "end": 9.82, "text": "再见。"},
            ],
        )

    def test_normalize_asr_response_falls_back_to_plain_text(self):
        payload = {"text": "只有整段文本"}

        dialogues = video2script.normalize_asr_response(payload)

        self.assertEqual(
            dialogues,
            [{"start": 0.0, "end": 0.0, "text": "只有整段文本"}],
        )


class CompletionResponseTests(unittest.TestCase):
    def test_extract_completion_text_reads_openai_style_payload(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "第一段"},
                            {"type": "text", "text": "第二段"},
                        ]
                    }
                }
            ]
        }

        text = video2script.extract_completion_text(payload)

        self.assertEqual(text, "第一段\n第二段")


class DescriptionSanitizationTests(unittest.TestCase):
    def test_sanitize_keyframe_description_removes_prompt_meta(self):
        raw = (
            "这个请求要求我描述一张图片，内容是一个短剧画面。\n"
            "需要包含四个要素：场景环境、人物、动作表情、氛围。\n"
            "1.  **场景环境**：这是一个豪华的室内场景。\n"
            "2.  **人物**：一名年轻女子。\n"
            "4.  **氛围**：整体氛围喜庆奢华。"
        )

        cleaned = video2script.sanitize_keyframe_description(raw)

        self.assertEqual(cleaned, "这是一个豪华的室内场景，一名年轻女子，整体氛围喜庆奢华。")

    def test_sanitize_keyframe_description_accepts_blank_input(self):
        self.assertEqual(video2script.sanitize_keyframe_description("   \n\t  "), "")

    def test_sanitize_keyframe_description_returns_empty_for_fully_filtered_meta(self):
        self.assertEqual(video2script.sanitize_keyframe_description("1. **人物**："), "")


class ChatPayloadTests(unittest.TestCase):
    def test_build_chat_completion_payload_flattens_extra_body_fields(self):
        payload = video2script.build_chat_completion_payload(
            [{"type": "text", "text": "你好"}],
            max_tokens=256,
        )

        self.assertEqual(payload["top_k"], 20)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertNotIn("extra_body", payload)

    def test_build_video_script_prompt_requests_direct_video_understanding(self):
        prompt = video2script.build_video_script_prompt(
            [
                {"start": 0.07, "end": 0.51, "text": "您好，"},
                {"start": 0.77, "end": 3.65, "text": "我是通通中国联通的医顾们。"},
            ]
        )

        self.assertIn("直接观看完整视频", prompt)
        self.assertIn("修正ASR中的明显错字", prompt)
        self.assertIn("不要复述底部字幕", prompt)
        self.assertIn("手机消息、聊天记录、招牌、牌匾", prompt)
        self.assertIn("[对白 0.07s-0.51s] 您好，", prompt)

    def test_build_video_script_prompt_includes_speaker_label_when_available(self):
        prompt = video2script.build_video_script_prompt(
            [
                {"speaker_id": "SPEAKER_00", "start": 0.07, "end": 0.51, "text": "您好，"},
                {"speaker_id": "SPEAKER_01", "start": 0.77, "end": 3.65, "text": "请问有什么可以帮您？"},
            ]
        )

        self.assertIn("同一 SPEAKER 标签可视为同一说话人", prompt)
        self.assertIn("[对白 SPEAKER_00 0.07s-0.51s] 您好，", prompt)

    def test_build_video_script_content_uses_video_url_input(self):
        video_path = video2script.OUTPUT_DIR / "_tmp_video_payload_test.mp4"
        video_path.write_bytes(b"fake-mp4")
        try:
            content = video2script.build_video_script_content(
                str(video_path),
                [{"start": 1.0, "end": 2.0, "text": "测试对白"}],
            )
        finally:
            if video_path.exists():
                safe_unlink(
                    video_path,
                    staging_root=video_path.parent / ".cleanup-staging",
                    best_effort=True,
                )

        self.assertEqual(content[0]["type"], "video_url")
        self.assertTrue(content[0]["video_url"]["url"].startswith("data:video/mp4;base64,"))
        self.assertEqual(content[1]["type"], "text")
        self.assertIn("测试对白", content[1]["text"])


class VideoSegmentationTests(unittest.TestCase):
    def test_default_segment_overlap_is_three_seconds(self):
        self.assertEqual(video2script.SEGMENT_OVERLAP, 3.0)

    def test_compute_segment_windows_uses_overlap(self):
        windows = video2script.compute_segment_windows(
            duration=65.0,
            segment_duration=30.0,
            overlap=3.0,
        )

        self.assertEqual(
            windows,
            [
                {"index": 1, "start": 0.0, "end": 30.0},
                {"index": 2, "start": 27.0, "end": 57.0},
                {"index": 3, "start": 54.0, "end": 65.0},
            ],
        )

    def test_slice_dialogues_for_window_keeps_intersecting_lines(self):
        dialogues = [
            {"start": 0.0, "end": 2.0, "text": "第一句"},
            {"start": 28.0, "end": 32.0, "text": "第二句"},
            {"start": 40.0, "end": 42.0, "text": "第三句"},
        ]

        sliced = video2script.slice_dialogues_for_window(
            dialogues,
            start=27.0,
            end=35.0,
        )

        self.assertEqual(
            sliced,
            [{"start": 28.0, "end": 32.0, "text": "第二句"}],
        )


class OutputPathTests(unittest.TestCase):
    def test_get_video_output_dir_returns_per_video_subdirectory(self):
        output_dir = video2script.get_video_output_dir("示例视频")

        self.assertEqual(output_dir, video2script.OUTPUT_DIR / "示例视频")


class ContextBudgetTests(unittest.TestCase):
    def test_script_context_budget_is_restored(self):
        self.assertEqual(video2script.SCRIPT_MAX_TOKENS, 4096)


class ScriptCleanupTests(unittest.TestCase):
    def test_build_merge_script_prompt_forbids_repeating_bottom_subtitles(self):
        prompt = video2script.build_merge_script_prompt(
            [
                {
                    "index": 1,
                    "start": 0.0,
                    "end": 10.0,
                    "draft": "【分场草稿】\n场景标题：客厅",
                }
            ]
        )

        self.assertIn("不要复述底部字幕", prompt)
        self.assertIn("手机消息、聊天记录、招牌、牌匾", prompt)

    def test_remove_bottom_subtitle_lines_keeps_plot_relevant_screen_text(self):
        script = (
            "# 短剧剧本：《测试》\n"
            "## 第1场\n"
            "**场景标题**：客厅\n"
            "**画面描述**：女人冲进客厅，底部字幕写着“你终于回来了”，她看向手机，手机消息显示“今晚八点见”，门口招牌写着“天海律师事务所”。\n"
            "**角色对白**：A：你终于回来了。\n"
        )

        cleaned = video2script.remove_bottom_subtitle_lines(script)

        self.assertNotIn("底部字幕写着", cleaned)
        self.assertNotIn("你终于回来了", cleaned.split("**画面描述**：", 1)[1].split("**角色对白**：", 1)[0])
        self.assertIn("手机消息显示“今晚八点见”", cleaned)
        self.assertIn("门口招牌写着“天海律师事务所”", cleaned)


if __name__ == "__main__":
    unittest.main()
