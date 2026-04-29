"""MuMu 红果下载脚本的纯 Python 测试。"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "mumu_hongguo_downloader.py"
SPEC = importlib.util.spec_from_file_location("mumu_hongguo_downloader", MODULE_PATH)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

TEMP_ROOT = Path(__file__).resolve().parents[1] / "output" / "test_tmp" / "hongguo_downloader"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def make_case_dir() -> Path:
    case_dir = TEMP_ROOT / uuid.uuid4().hex
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


class HongguoDownloaderTests(unittest.TestCase):
    def test_sanitize_name_replaces_invalid_characters(self) -> None:
        self.assertEqual(MODULE.sanitize_name('剧名:第一集/合集?'), "剧名_第一集_合集_")

    def test_parse_bounds_returns_centerable_tuple(self) -> None:
        bounds = MODULE.parse_bounds("[10,20][110,220]")
        self.assertEqual(bounds, (10, 20, 110, 220))
        self.assertEqual(MODULE.bounds_center(bounds), (60, 120))

    def test_find_clickable_ancestor_for_text(self) -> None:
        xml_text = """
        <hierarchy>
          <node text="" clickable="true" bounds="[10,20][110,220]">
            <node text="1" clickable="false" bounds="[20,30][40,50]" />
          </node>
        </hierarchy>
        """
        self.assertEqual(
            MODULE.find_clickable_ancestor_for_text(xml_text, "1"),
            (10, 20, 110, 220),
        )

    def test_diff_snapshot_entries_detects_new_and_changed_files(self) -> None:
        root = make_case_dir()
        try:
            old_file = root / "a.mp4"
            old_file.write_bytes(b"1")
            baseline = MODULE.take_folder_snapshot(root, [".mp4"])
            old_file.write_bytes(b"12")
            new_file = root / "b.mp4"
            new_file.write_bytes(b"123")
            current = MODULE.take_folder_snapshot(root, [".mp4"])
            changed = MODULE.diff_snapshot_entries(baseline, current)
            self.assertEqual(set(changed), {str(old_file.resolve()), str(new_file.resolve())})
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_run_state_roundtrip(self) -> None:
        root = make_case_dir()
        try:
            state_path = root / "state.json"
            state = MODULE.RunState(state_path)
            record = MODULE.TaskRecord(rank=1, title="测试剧", status=MODULE.STATUS_SUCCESS)
            state.upsert(record)
            state.save()

            loaded = MODULE.RunState.load(state_path)
            loaded_record = loaded.get(1, "测试剧")
            self.assertIsNotNone(loaded_record)
            self.assertEqual(loaded_record.status, MODULE.STATUS_SUCCESS)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_config_loader_applies_defaults(self) -> None:
        temp_root = make_case_dir()
        try:
            shared = temp_root / "shared"
            shared.mkdir()
            payload = {
                "shared_folder": str(shared),
                "output_dir": str(temp_root / "output"),
            }
            config_path = temp_root / "config.json"
            config_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            config = MODULE.DownloaderConfig.from_file(config_path)
            self.assertEqual(config.top_n, 10)
            self.assertEqual(config.archive_mode, "copy")
            self.assertFalse(config.delete_existing_before_download)
            self.assertIn("下载", config.keywords["download"])
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_config_loader_reads_delete_existing_before_download(self) -> None:
        temp_root = make_case_dir()
        try:
            shared = temp_root / "shared"
            shared.mkdir()
            payload = {
                "shared_folder": str(shared),
                "output_dir": str(temp_root / "output"),
                "delete_existing_before_download": True,
            }
            config_path = temp_root / "config.json"
            config_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            config = MODULE.DownloaderConfig.from_file(config_path)
            self.assertTrue(config.delete_existing_before_download)
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_build_run_summary_counts_status(self) -> None:
        root = make_case_dir()
        try:
            state = MODULE.RunState(root / "state.json")
            state.upsert(MODULE.TaskRecord(rank=1, title="A", status=MODULE.STATUS_SUCCESS))
            state.upsert(MODULE.TaskRecord(rank=2, title="B", status=MODULE.STATUS_FAILED))
            summary = MODULE.build_run_summary(state)
            self.assertEqual(summary["counts"][MODULE.STATUS_SUCCESS], 1)
            self.assertEqual(summary["counts"][MODULE.STATUS_FAILED], 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_build_target_ranks_supports_start_rank_and_limit(self) -> None:
        self.assertEqual(MODULE.build_target_ranks(top_n=10, start_rank=2, limit=1), [2])
        self.assertEqual(MODULE.build_target_ranks(top_n=5, start_rank=3, limit=None), [3, 4, 5])

    def test_build_pulled_video_name_converts_mdl_to_mp4(self) -> None:
        self.assertEqual(
            MODULE.build_pulled_video_name("/sdcard/Android/data/com.phoenix.read/files/ttvideo_offline/abc123.mdl"),
            "abc123.mp4",
        )
        self.assertEqual(
            MODULE.build_pulled_video_name("/sdcard/Android/data/com.phoenix.read/files/ttvideo_offline/abc123.mp4"),
            "abc123.mp4",
        )

    def test_find_title_row_bounds_returns_clickable_download_row(self) -> None:
        xml_text = """
        <hierarchy>
          <node text="" clickable="false" bounds="[0,0][1080,320]">
            <node text="" clickable="true" bounds="[140,166][1045,285]">
              <node text="嫡女一身反骨，偏嫁高门当主母" clickable="false" bounds="[161,166][958,204]" />
            </node>
          </node>
        </hierarchy>
        """
        self.assertEqual(
            MODULE.find_title_row_bounds(xml_text, "嫡女一身反骨，偏嫁高门当主母"),
            (140, 166, 1045, 285),
        )

    def test_validate_video_file_raises_when_ffmpeg_decode_fails(self) -> None:
        original_run_subprocess = MODULE.run_subprocess
        try:
            def fake_run_subprocess(*_args, **_kwargs):
                raise MODULE.StepError("Invalid NAL unit size")

            MODULE.run_subprocess = fake_run_subprocess
            with self.assertRaisesRegex(MODULE.StepError, "视频文件无法正常解码"):
                MODULE.validate_video_file(Path("broken.mp4"))
        finally:
            MODULE.run_subprocess = original_run_subprocess

    def test_run_subprocess_replaces_undecodable_output(self) -> None:
        result = MODULE.run_subprocess(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(bytes([0xA5]))",
            ]
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "\ufffd")

    def test_trigger_download_selects_episodes_before_starting_download(self) -> None:
        class FakeUiSession:
            def __init__(self) -> None:
                self.keyword_clicks: list[tuple[str, ...]] = []
                self.coordinate_clicks: list[tuple[int, int]] = []

            def tap_fallback(self, _name: str) -> bool:
                return False

            def click_keywords(self, keywords: list[str]) -> bool:
                self.keyword_clicks.append(tuple(keywords))
                if "更多" in keywords:
                    return True
                if "下载到本地" in keywords or "下载" in keywords:
                    return True
                if "全选" in keywords:
                    return True
                if "开始下载" in keywords:
                    return True
                return False

            def click(self, x: int, y: int) -> None:
                self.coordinate_clicks.append((x, y))

            def dump_hierarchy(self) -> str:
                return """
                <hierarchy>
                  <node text="下载到本地" resource-id="com.phoenix.read:id/title" clickable="false" bounds="[460,611][620,654]" />
                  <node text="全选" resource-id="com.phoenix.read:id/jx" clickable="true" bounds="[996,613][1052,651]" />
                  <node text="开始下载" resource-id="com.phoenix.read:id/crr" clickable="true" bounds="[550,1843][1052,1906]" />
                </hierarchy>
                """

        config = MODULE.DownloaderConfig(
            config_path=Path("config.json"),
            shared_folder=Path("."),
            keywords={
                "rank": ["排行榜"],
                "download": ["下载"],
                "confirm": ["确定"],
            },
        )
        ui_session = FakeUiSession()

        self.assertTrue(MODULE.trigger_download(ui_session, config))

        self.assertIn(("全选",), ui_session.keyword_clicks)
        self.assertIn(("开始下载",), ui_session.keyword_clicks)

    def test_open_rank_page_recovers_from_play_page_with_multiple_back_presses(self) -> None:
        class FakeUiSession:
            def __init__(self) -> None:
                self.back_presses = 0
                self.in_theater = False
                self.keyword_clicks: list[tuple[str, ...]] = []

            def page_contains_keywords(self, keywords: list[str]) -> bool:
                if "剧场" in keywords or "找剧" in keywords:
                    return self.back_presses >= 5 and not self.in_theater
                if "排行榜" in keywords:
                    return self.in_theater
                return False

            def click_keywords(self, keywords: list[str]) -> bool:
                self.keyword_clicks.append(tuple(keywords))
                if "剧场" in keywords or "找剧" in keywords:
                    if self.back_presses >= 5:
                        self.in_theater = True
                        return True
                    return False
                if "排行榜" in keywords:
                    return self.in_theater
                return False

            def tap_fallback(self, _name: str) -> bool:
                return False

            def press(self, key: str) -> None:
                if key == "back":
                    self.back_presses += 1

        config = MODULE.DownloaderConfig(
            config_path=Path("config.json"),
            shared_folder=Path("."),
            keywords={
                "rank": ["排行榜"],
                "download": ["下载"],
                "confirm": ["确定"],
            },
        )
        ui_session = FakeUiSession()

        MODULE.open_rank_page(ui_session, config)

        self.assertGreaterEqual(ui_session.back_presses, 5)
        self.assertIn(tuple(MODULE.THEATER_KEYWORDS), ui_session.keyword_clicks)


if __name__ == "__main__":
    unittest.main()
