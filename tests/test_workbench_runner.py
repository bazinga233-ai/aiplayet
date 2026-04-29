import unittest
from pathlib import Path
import shutil
import uuid
from unittest.mock import patch

import backend.pipeline as pipeline
from backend.scoring import load_score_payload
from backend.runner import run_task, run_video2script
from backend.task_queue import TaskState


class WorkbenchRunnerTests(unittest.TestCase):
    def test_run_video2script_uses_shared_pipeline_directly(self):
        task = TaskState(
            task_id="t1",
            video_id="v1",
            video_name="demo",
            video_path="demo.mp4",
        )
        collected = []
        sink = collected.append
        callback_holder = {}

        def fake_pipeline(video_path, on_line=None):
            callback_holder["video_path"] = video_path
            callback_holder["on_line"] = on_line
            on_line("line one")
            on_line("line two")
            return 0

        with patch("backend.runner.run_video_pipeline", side_effect=fake_pipeline) as pipeline_mock:
            exit_code = run_video2script(task, sink)

        self.assertEqual(exit_code, 0)
        self.assertEqual(collected, ["line one", "line two"])
        self.assertEqual(callback_holder["video_path"], "demo.mp4")
        self.assertIs(callback_holder["on_line"], sink)
        pipeline_mock.assert_called_once()

    def test_run_video2script_triggers_cleanup_only_after_success(self):
        task = TaskState(
            task_id="t2",
            video_id="v2",
            video_name="demo",
            video_path="demo.mp4",
        )
        output_root = Path.cwd() / ".tmp_testfixtures" / f"novalai_runner_generate_{uuid.uuid4().hex}"
        expected_output_dir = output_root / "demo"

        with patch("backend.runner.OUTPUT_DIR", output_root), patch(
            "backend.runner.run_video_pipeline", return_value=0
        ) as pipeline_mock, patch("backend.runner.clear_score_payload") as clear_score_mock, patch(
            "backend.runner._reset_original_script"
        ) as reset_original_mock:
            exit_code = run_video2script(task, lambda _line: None)

        self.assertEqual(exit_code, 0)
        pipeline_mock.assert_called_once()
        clear_score_mock.assert_called_once_with(expected_output_dir)
        reset_original_mock.assert_called_once_with(expected_output_dir)

    def test_run_video2script_skips_cleanup_after_failure(self):
        task = TaskState(
            task_id="t3",
            video_id="v3",
            video_name="demo",
            video_path="demo.mp4",
        )

        with patch("backend.runner.run_video_pipeline", return_value=1) as pipeline_mock, patch(
            "backend.runner.clear_score_payload"
        ) as clear_score_mock, patch("backend.runner._reset_original_script") as reset_original_mock:
            exit_code = run_video2script(task, lambda _line: None)

        self.assertEqual(exit_code, 1)
        pipeline_mock.assert_called_once()
        clear_score_mock.assert_not_called()
        reset_original_mock.assert_not_called()

    def test_run_video2script_failed_regenerate_does_not_expose_mixed_outputs(self):
        task = TaskState(
            task_id="t4",
            video_id="v4",
            video_name="demo",
            video_path="demo.mp4",
        )

        fixtures_root = Path.cwd() / ".tmp_testfixtures"
        fixtures_root.mkdir(exist_ok=True)
        output_root = fixtures_root / f"novalai_runner_regenerate_{uuid.uuid4().hex}"
        output_root.mkdir()
        try:
            video_output_dir = output_root / "demo"
            video_output_dir.mkdir()
            (video_output_dir / "script.txt").write_text("旧剧本", encoding="utf-8")
            (video_output_dir / "dialogues.json").write_text('[{"text":"旧对白"}]', encoding="utf-8")
            (video_output_dir / "segments.json").write_text('[{"draft":"旧分段"}]', encoding="utf-8")

            fake_segments = [{"index": 1, "start": 0.0, "end": 10.0, "video_path": "missing.mp4"}]
            logs = []
            with patch("backend.pipeline.OUTPUT_DIR", output_root), patch(
                "backend.pipeline.ensure_dirs"
            ), patch("backend.pipeline.extract_audio"), patch(
                "backend.pipeline.transcribe_audio",
                return_value=[{"start": 0.0, "end": 1.0, "text": "新对白"}],
            ), patch(
                "backend.pipeline.create_video_segments",
                return_value=fake_segments,
            ), patch(
                "backend.pipeline.analyze_video_segments",
                return_value=[
                    {
                        "index": 1,
                        "start": 0.0,
                        "end": 10.0,
                        "dialogue_count": 1,
                        "draft": "新分段",
                        "video_path": "missing.mp4",
                    }
                ],
            ), patch(
                "backend.pipeline.generate_script",
                side_effect=RuntimeError("mock-generate-failure"),
            ):
                exit_code = run_video2script(task, logs.append)

            self.assertEqual(exit_code, 1)
            self.assertEqual((video_output_dir / "script.txt").read_text(encoding="utf-8"), "旧剧本")
            self.assertEqual(
                (video_output_dir / "dialogues.json").read_text(encoding="utf-8"),
                '[{"text":"旧对白"}]',
            )
            self.assertEqual(
                (video_output_dir / "segments.json").read_text(encoding="utf-8"),
                '[{"draft":"旧分段"}]',
            )
            self.assertTrue(any("mock-generate-failure" in line for line in logs))
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_run_video2script_commit_failure_restores_previous_ready_outputs(self):
        task = TaskState(
            task_id="t5",
            video_id="v5",
            video_name="demo",
            video_path="demo.mp4",
        )

        fixtures_root = Path.cwd() / ".tmp_testfixtures"
        fixtures_root.mkdir(exist_ok=True)
        output_root = fixtures_root / f"novalai_runner_commit_{uuid.uuid4().hex}"
        output_root.mkdir()
        try:
            video_output_dir = output_root / "demo"
            video_output_dir.mkdir()
            (video_output_dir / "script.txt").write_text("旧剧本", encoding="utf-8")
            (video_output_dir / "dialogues.json").write_text('[{"text":"旧对白"}]', encoding="utf-8")
            (video_output_dir / "segments.json").write_text('[{"draft":"旧分段"}]', encoding="utf-8")

            fake_segments = [{"index": 1, "start": 0.0, "end": 10.0, "video_path": "missing.mp4"}]
            original_write_output = pipeline._write_output_file
            failed_once = {"value": False}

            def flaky_write_output(path, content):
                if (
                    path.parent == video_output_dir
                    and path.name == "script.txt"
                    and content == "新剧本"
                    and not failed_once["value"]
                ):
                    failed_once["value"] = True
                    raise RuntimeError("mock-commit-failure")
                return original_write_output(path, content)

            logs = []
            with patch("backend.pipeline.OUTPUT_DIR", output_root), patch(
                "backend.pipeline.ensure_dirs"
            ), patch("backend.pipeline.extract_audio"), patch(
                "backend.pipeline.transcribe_audio",
                return_value=[{"start": 0.0, "end": 1.0, "text": "新对白"}],
            ), patch(
                "backend.pipeline.create_video_segments",
                return_value=fake_segments,
            ), patch(
                "backend.pipeline.analyze_video_segments",
                return_value=[
                    {
                        "index": 1,
                        "start": 0.0,
                        "end": 10.0,
                        "dialogue_count": 1,
                        "draft": "新分段",
                        "video_path": "missing.mp4",
                    }
                ],
            ), patch(
                "backend.pipeline.generate_script",
                return_value="新剧本",
            ), patch(
                "backend.pipeline._write_output_file",
                side_effect=flaky_write_output,
            ):
                exit_code = run_video2script(task, logs.append)

            self.assertEqual(exit_code, 1)
            self.assertEqual((video_output_dir / "script.txt").read_text(encoding="utf-8"), "旧剧本")
            self.assertEqual(
                (video_output_dir / "dialogues.json").read_text(encoding="utf-8"),
                '[{"text":"旧对白"}]',
            )
            self.assertEqual(
                (video_output_dir / "segments.json").read_text(encoding="utf-8"),
                '[{"draft":"旧分段"}]',
            )
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_run_video2script_commit_failure_for_new_output_dir_keeps_results_unready(self):
        task = TaskState(
            task_id="t6",
            video_id="v6",
            video_name="demo",
            video_path="demo.mp4",
        )

        fixtures_root = Path.cwd() / ".tmp_testfixtures"
        fixtures_root.mkdir(exist_ok=True)
        output_root = fixtures_root / f"novalai_runner_commit_new_{uuid.uuid4().hex}"
        output_root.mkdir()
        try:
            video_output_dir = output_root / "demo"
            fake_segments = [{"index": 1, "start": 0.0, "end": 10.0, "video_path": "missing.mp4"}]
            original_write_output = pipeline._write_output_file
            failed_once = {"value": False}

            def flaky_write_output(path, content):
                if (
                    path.parent == video_output_dir
                    and path.name == "segments.json"
                    and "新分段" in content
                    and not failed_once["value"]
                ):
                    failed_once["value"] = True
                    raise RuntimeError("mock-commit-failure-new")
                return original_write_output(path, content)

            logs = []
            with patch("backend.pipeline.OUTPUT_DIR", output_root), patch(
                "backend.pipeline.ensure_dirs"
            ), patch("backend.pipeline.extract_audio"), patch(
                "backend.pipeline.transcribe_audio",
                return_value=[{"start": 0.0, "end": 1.0, "text": "新对白"}],
            ), patch(
                "backend.pipeline.create_video_segments",
                return_value=fake_segments,
            ), patch(
                "backend.pipeline.analyze_video_segments",
                return_value=[
                    {
                        "index": 1,
                        "start": 0.0,
                        "end": 10.0,
                        "dialogue_count": 1,
                        "draft": "新分段",
                        "video_path": "missing.mp4",
                    }
                ],
            ), patch(
                "backend.pipeline.generate_script",
                return_value="新剧本",
            ), patch(
                "backend.pipeline._write_output_file",
                side_effect=flaky_write_output,
            ):
                exit_code = run_video2script(task, logs.append)

            self.assertEqual(exit_code, 1)
            self.assertFalse(
                all((video_output_dir / filename).exists() for filename in ("dialogues.json", "segments.json", "script.txt"))
            )
        finally:
            shutil.rmtree(output_root, ignore_errors=True)

    def test_run_task_optimizes_script_and_removes_stale_score(self):
        task = TaskState(
            task_id="opt-1",
            video_id="v1",
            video_name="demo",
            video_path="demo.mp4",
            asset_type="video",
            task_type="optimize",
            parent_task_id="highlight-1",
        )

        fixtures_root = Path.cwd() / ".tmp_testfixtures"
        fixtures_root.mkdir(exist_ok=True)
        output_root = fixtures_root / f"novalai_runner_{uuid.uuid4().hex}"
        output_root.mkdir()
        try:
            video_output_dir = output_root / "demo"
            video_output_dir.mkdir()
            (video_output_dir / "script.txt").write_text("旧剧本", encoding="utf-8")
            (video_output_dir / "score.json").write_text('{"stale":true}', encoding="utf-8")
            (video_output_dir / "highlights.json").write_text("null", encoding="utf-8")

            logs = []
            with patch("backend.runner.OUTPUT_DIR", output_root), patch(
                "backend.runner.optimize_video_script",
                return_value="# 短剧剧本：《新标题》\n## 第1场\n**场景标题**：客厅",
            ):
                exit_code = run_task(task, logs.append)

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                (video_output_dir / "script.txt").read_text(encoding="utf-8"),
                "# 短剧剧本：《新标题》\n## 第1场\n**场景标题**：客厅",
            )
            self.assertEqual((video_output_dir / "script_original.txt").read_text(encoding="utf-8"), "旧剧本")
            self.assertIsNone(load_score_payload(video_output_dir))
            self.assertTrue(any("正在根据爆款预测优化剧本" in line for line in logs))
            self.assertTrue(any("优化剧本已保存:" in line for line in logs))
        finally:
            shutil.rmtree(output_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
