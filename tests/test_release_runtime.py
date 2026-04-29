import importlib
import os
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

try:
    from backend import runtime
except ImportError as exc:  # pragma: no cover - expected before implementation
    runtime = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None

REPO_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def temporary_release_root():
    fixtures_root = Path.cwd() / ".tmp_testfixtures"
    fixtures_root.mkdir(exist_ok=True)
    root = fixtures_root / f"novalai_runtime_{uuid.uuid4().hex}"
    release_dir = root / "bundle"
    release_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield release_dir
    finally:
        shutil.rmtree(root, ignore_errors=True)


def binary_name(base_name: str) -> str:
    if os.name == "nt":
        return f"{base_name}.exe"
    return base_name


@contextmanager
def fresh_config_module():
    original = sys.modules.pop("backend.config", None)
    try:
        config = importlib.import_module("backend.config")
        yield config
    finally:
        sys.modules.pop("backend.config", None)
        if original is not None:
            sys.modules["backend.config"] = original


@contextmanager
def fresh_module(module_name: str):
    original = sys.modules.pop(module_name, None)
    try:
        module = importlib.import_module(module_name)
        yield module
    finally:
        sys.modules.pop(module_name, None)
        if original is not None:
            sys.modules[module_name] = original


class ReleaseRuntimeTests(unittest.TestCase):
    def setUp(self):
        if IMPORT_ERROR is not None:
            self.fail(f"backend.runtime import failed: {IMPORT_ERROR}")

    def test_dev_mode_root_resolves_to_repo_root(self):
        with patch.object(runtime.sys, "frozen", False, create=True):
            expected = REPO_ROOT
            self.assertEqual(runtime.get_runtime_root(), expected)

    def test_frozen_mode_root_resolves_to_executable_directory(self):
        with temporary_release_root() as executable_dir:
            executable_path = executable_dir / "novalai.exe"
            executable_path.write_bytes(b"stub")
            with (
                patch.object(runtime.sys, "frozen", True, create=True),
                patch.object(runtime.sys, "executable", str(executable_path), create=True),
            ):
                self.assertEqual(runtime.get_runtime_root(), executable_dir.resolve())

    def test_release_mode_media_tools_resolve_to_sibling_binaries(self):
        with temporary_release_root() as executable_dir:
            executable_path = executable_dir / "novalai.exe"
            executable_path.write_bytes(b"stub")
            with (
                patch.object(runtime.sys, "frozen", True, create=True),
                patch.object(runtime.sys, "executable", str(executable_path), create=True),
            ):
                self.assertEqual(
                    Path(runtime.get_ffmpeg_path()),
                    executable_dir / binary_name("ffmpeg"),
                )
                self.assertEqual(
                    Path(runtime.get_ffprobe_path()),
                    executable_dir / binary_name("ffprobe"),
                )

    def test_missing_release_assets_are_all_reported_as_invalid_layout(self):
        with temporary_release_root() as executable_dir:
            executable_path = executable_dir / "novalai.exe"
            executable_path.write_bytes(b"stub")
            with (
                patch.object(runtime.sys, "frozen", True, create=True),
                patch.object(runtime.sys, "executable", str(executable_path), create=True),
            ):
                valid, errors = runtime.validate_release_layout()
                self.assertFalse(valid)
                self.assertTrue(
                    any("frontend_dist" in item and "index.html" in item for item in errors)
                )
                self.assertTrue(any(Path(item).name == binary_name("ffmpeg") for item in errors))
                self.assertTrue(any(Path(item).name == binary_name("ffprobe") for item in errors))

    def test_media_tool_env_overrides_take_precedence(self):
        with temporary_release_root() as executable_dir:
            executable_path = executable_dir / "novalai.exe"
            executable_path.write_bytes(b"stub")
            with (
                patch.object(runtime.sys, "frozen", True, create=True),
                patch.object(runtime.sys, "executable", str(executable_path), create=True),
                patch.dict(
                    os.environ,
                    {
                        "NOVALAI_FFMPEG_PATH": "/custom/bin/ffmpeg",
                        "NOVALAI_FFPROBE_PATH": "/custom/bin/ffprobe",
                    },
                    clear=False,
                ),
            ):
                self.assertEqual(runtime.get_ffmpeg_path(), "/custom/bin/ffmpeg")
                self.assertEqual(runtime.get_ffprobe_path(), "/custom/bin/ffprobe")

    def test_backend_config_integration_dev_mode(self):
        with (
            patch.object(runtime.sys, "frozen", False, create=True),
            patch.dict(
                os.environ,
                {
                    "NOVALAI_FFMPEG_PATH": "",
                    "NOVALAI_FFPROBE_PATH": "",
                },
                clear=False,
            ),
        ):
            with fresh_config_module() as config:
                self.assertEqual(config.ROOT_DIR, REPO_ROOT)
                self.assertEqual(config.FFMPEG_PATH, "ffmpeg")
                self.assertEqual(config.FFPROBE_PATH, "ffprobe")
                self.assertTrue(config.RELEASE_LAYOUT_VALID)

    def test_backend_config_integration_frozen_mode_without_import_time_dir_creation(self):
        with temporary_release_root() as executable_dir:
            executable_path = executable_dir / "novalai.exe"
            executable_path.write_bytes(b"stub")
            frontend_dist = executable_dir / "frontend_dist"
            frontend_dist.mkdir(parents=True, exist_ok=True)
            (frontend_dist / "index.html").write_text("<html></html>", encoding="utf-8")
            (executable_dir / binary_name("ffmpeg")).write_bytes(b"ffmpeg")
            (executable_dir / binary_name("ffprobe")).write_bytes(b"ffprobe")

            with (
                patch.object(runtime.sys, "frozen", True, create=True),
                patch.object(runtime.sys, "executable", str(executable_path), create=True),
                patch.dict(
                    os.environ,
                    {
                        "NOVALAI_FFMPEG_PATH": "",
                        "NOVALAI_FFPROBE_PATH": "",
                    },
                    clear=False,
                ),
            ):
                with fresh_config_module() as config:
                    self.assertEqual(config.ROOT_DIR, executable_dir.resolve())
                    self.assertEqual(
                        Path(config.FFMPEG_PATH),
                        executable_dir / binary_name("ffmpeg"),
                    )
                    self.assertEqual(
                        Path(config.FFPROBE_PATH),
                        executable_dir / binary_name("ffprobe"),
                    )
                    self.assertTrue(config.RELEASE_LAYOUT_VALID)
                    self.assertFalse(config.VIDEOS_DIR.exists())
                    self.assertFalse(config.SCRIPTS_DIR.exists())
                    self.assertFalse(config.OUTPUT_DIR.exists())
                    self.assertFalse(config.TMP_UPLOADS_DIR.exists())
                    self.assertFalse(config.TMP_SCRIPT_UPLOADS_DIR.exists())

    def test_backend_config_import_fails_in_frozen_mode_when_layout_is_invalid(self):
        with temporary_release_root() as executable_dir:
            executable_path = executable_dir / "novalai.exe"
            executable_path.write_bytes(b"stub")
            with (
                patch.object(runtime.sys, "frozen", True, create=True),
                patch.object(runtime.sys, "executable", str(executable_path), create=True),
                patch.dict(
                    os.environ,
                    {
                        "NOVALAI_FFMPEG_PATH": "",
                        "NOVALAI_FFPROBE_PATH": "",
                    },
                    clear=False,
                ),
            ):
                with self.assertRaises(RuntimeError) as context:
                    with fresh_config_module():
                        pass
                error_text = str(context.exception)
                self.assertIn("Invalid release layout", error_text)
                self.assertIn("frontend_dist", error_text)
                self.assertIn(binary_name("ffmpeg"), error_text)
                self.assertIn(binary_name("ffprobe"), error_text)

    def test_highlight_proxy_command_uses_runtime_resolved_binary(self):
        import backend.models as models_module

        with patch.multiple(
            models_module,
            BestClimax=object,
            HighlightClip=object,
            create=True,
        ):
            with fresh_module("backend.highlights") as highlights_module:
                with (
                    patch("backend.highlights.run_checked_command") as run_mock,
                    patch("backend.highlights.FFMPEG_PATH", "X:/tools/ffmpeg.exe"),
                ):
                    highlights_module.build_highlight_proxy_video(
                        video_path="input.mp4",
                        start=1.0,
                        end=2.0,
                        output_path="proxy.mp4",
                    )
                cmd = run_mock.call_args.args[0]
                self.assertEqual(cmd[0], "X:/tools/ffmpeg.exe")
                vf_value = cmd[cmd.index("-vf") + 1]
                self.assertIn("scale=trunc(iw/2)*2:trunc(ih/2)*2", vf_value)

    def test_scoring_proxy_command_uses_runtime_resolved_binary(self):
        with fresh_module("backend.scoring") as scoring_module:
            with (
                patch("backend.scoring.run_checked_command") as run_mock,
                patch("backend.scoring.FFMPEG_PATH", "X:/tools/ffmpeg.exe"),
            ):
                scoring_module.build_score_proxy_video(
                    video_path="input.mp4",
                    output_path="proxy.mp4",
                )
            cmd = run_mock.call_args.args[0]
            self.assertEqual(cmd[0], "X:/tools/ffmpeg.exe")
            vf_value = cmd[cmd.index("-vf") + 1]
            self.assertIn("scale=trunc(iw/2)*2:trunc(ih/2)*2", vf_value)

    def test_pipeline_segment_proxy_command_uses_even_dimension_scale_filter(self):
        with fresh_module("backend.pipeline") as pipeline_module:
            with (
                patch("backend.pipeline.run_checked_command") as run_mock,
                patch("backend.pipeline.FFMPEG_PATH", "X:/tools/ffmpeg.exe"),
            ):
                pipeline_module.build_segment_proxy_video(
                    video_path="input.mp4",
                    start=0.0,
                    end=30.0,
                    output_path="proxy.mp4",
                )
            cmd = run_mock.call_args.args[0]
            self.assertEqual(cmd[0], "X:/tools/ffmpeg.exe")
            vf_value = cmd[cmd.index("-vf") + 1]
            self.assertIn("scale=trunc(iw/2)*2:trunc(ih/2)*2", vf_value)

    def test_viral_prediction_proxy_command_uses_runtime_resolved_binary(self):
        with fresh_module("backend.viral_prediction") as prediction_module:
            with (
                patch("backend.viral_prediction.run_checked_command") as run_mock,
                patch("backend.viral_prediction.FFMPEG_PATH", "X:/tools/ffmpeg.exe"),
            ):
                prediction_module.build_highlight_proxy_video(
                    video_path="input.mp4",
                    start=0.0,
                    end=12.0,
                    output_path="proxy.mp4",
                )
            cmd = run_mock.call_args.args[0]
            self.assertEqual(cmd[0], "X:/tools/ffmpeg.exe")
            vf_value = cmd[cmd.index("-vf") + 1]
            self.assertIn("scale=trunc(iw/2)*2:trunc(ih/2)*2", vf_value)


if __name__ == "__main__":
    unittest.main()
