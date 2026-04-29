import contextlib
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock

import backend.server_entry as server_entry_module

try:
    import launcher
except ImportError as exc:  # pragma: no cover - expected before implementation
    launcher = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


STATE_FILE_NAME = "server.json"


@contextlib.contextmanager
def temporary_release_root():
    fixtures_root = Path.cwd() / ".tmp_testfixtures"
    fixtures_root.mkdir(exist_ok=True)
    root = fixtures_root / f"novalai_launcher_{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "Backend.stub").write_bytes(b"stub backend binary")
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def write_state_file(release_root: Path, payload: dict[str, object]) -> Path:
    state_dir = release_root / "backend_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / STATE_FILE_NAME
    state_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return state_file


@contextlib.contextmanager
def temporary_server_entry_fixture():
    fixtures_root = Path.cwd() / ".tmp_testfixtures"
    fixtures_root.mkdir(exist_ok=True)
    root = fixtures_root / f"novalai_server_entry_{uuid.uuid4().hex}"
    videos_dir = root / "videos"
    scripts_dir = root / "scripts"
    output_dir = root / "output"
    state_dir = root / "backend_state"
    state_file = state_dir / server_entry_module.STATE_FILE_NAME

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(server_entry_module, "VIDEOS_DIR", videos_dir, create=True))
        stack.enter_context(mock.patch.object(server_entry_module, "SCRIPTS_DIR", scripts_dir, create=True))
        stack.enter_context(mock.patch.object(server_entry_module, "OUTPUT_DIR", output_dir, create=True))
        stack.enter_context(mock.patch.object(server_entry_module, "BACKEND_STATE_PATH", state_dir, create=True))
        stack.enter_context(
            mock.patch.object(server_entry_module, "ensure_runtime_directories", side_effect=lambda: None)
        )
        try:
            yield {
                "root": root,
                "videos_dir": videos_dir,
                "scripts_dir": scripts_dir,
                "output_dir": output_dir,
                "state_dir": state_dir,
                "state_file": state_file,
            }
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ReleaseLauncherTests(unittest.TestCase):
    def setUp(self):
        if IMPORT_ERROR is not None:
            self.fail(f"launcher import failed: {IMPORT_ERROR}")

    def test_find_free_port_prefers_8001_and_increments_when_occupied(self):
        checked_ports: list[int] = []

        def fake_is_port_available(host: str, port: int) -> bool:
            checked_ports.append(port)
            return port == 8003

        with mock.patch.object(launcher, "is_port_available", side_effect=fake_is_port_available):
            port = launcher.find_free_port(host="127.0.0.1", start_port=8001, max_attempts=5)

        self.assertEqual(port, 8003)
        self.assertEqual(checked_ports, [8001, 8002, 8003])

    def test_launch_normalizes_wildcard_host_for_health_and_browser(self):
        with temporary_release_root() as release_root:
            process = mock.Mock()
            process.poll.return_value = None
            with (
                mock.patch.object(launcher, "BACKEND_EXECUTABLE_NAME", "Backend.stub"),
                mock.patch.object(launcher, "find_free_port", return_value=8001),
                mock.patch.object(launcher.subprocess, "Popen", return_value=process),
                mock.patch.object(launcher, "wait_for_backend_health", return_value=True) as health_mock,
                mock.patch.object(launcher.webbrowser, "open", return_value=True) as browser_mock,
            ):
                url = launcher.launch(
                    release_root=release_root,
                    host="0.0.0.0",
                    timeout_seconds=0.1,
                )

        self.assertEqual(url, "http://127.0.0.1:8001")
        health_mock.assert_called_once_with(
            "http://127.0.0.1:8001",
            timeout_seconds=0.1,
            interval_seconds=mock.ANY,
            process=process,
        )
        browser_mock.assert_called_once_with("http://127.0.0.1:8001")

    def test_launch_reuses_healthy_backend_from_state_file(self):
        with temporary_release_root() as release_root:
            write_state_file(
                release_root,
                {"pid": 4321, "port": 8123, "host": "::"},
            )

            with (
                mock.patch.object(launcher, "BACKEND_EXECUTABLE_NAME", "Backend.stub"),
                mock.patch.object(launcher, "pid_exists", return_value=True),
                mock.patch.object(launcher, "wait_for_backend_health", return_value=True) as health_mock,
                mock.patch.object(launcher.subprocess, "Popen") as popen_mock,
                mock.patch.object(launcher.webbrowser, "open", return_value=True) as browser_mock,
            ):
                url = launcher.launch(release_root=release_root, timeout_seconds=0.1)

        self.assertEqual(url, "http://127.0.0.1:8123")
        popen_mock.assert_not_called()
        health_mock.assert_called_once_with(
            "http://127.0.0.1:8123",
            timeout_seconds=0.1,
            interval_seconds=mock.ANY,
            process=None,
        )
        browser_mock.assert_called_once_with("http://127.0.0.1:8123")

    def test_launch_removes_stale_state_file_when_pid_is_gone(self):
        with temporary_release_root() as release_root:
            write_state_file(
                release_root,
                {"pid": 999999, "port": 8123, "host": "127.0.0.1"},
            )

            with (
                mock.patch.object(launcher, "BACKEND_EXECUTABLE_NAME", "Backend.stub"),
                mock.patch.object(launcher, "pid_exists", return_value=False),
                mock.patch.object(launcher, "cleanup_state_file") as cleanup_mock,
                mock.patch.object(launcher, "find_free_port", return_value=8001),
                mock.patch.object(launcher, "wait_for_backend_health", return_value=True),
                mock.patch.object(launcher.subprocess, "Popen") as popen_mock,
                mock.patch.object(launcher.webbrowser, "open", return_value=True),
            ):
                launcher.launch(release_root=release_root, timeout_seconds=0.1)

        cleanup_mock.assert_called_once_with(release_root)
        popen_mock.assert_called_once()

    def test_launch_opens_browser_only_after_health_check_succeeds(self):
        events: list[str] = []

        with temporary_release_root() as release_root:
            process = mock.Mock()
            process.poll.return_value = None
            with (
                mock.patch.object(launcher, "BACKEND_EXECUTABLE_NAME", "Backend.stub"),
                mock.patch.object(launcher, "find_free_port", return_value=8001),
                mock.patch.object(
                    launcher.subprocess,
                    "Popen",
                    side_effect=lambda *args, **kwargs: events.append("spawn") or process,
                ),
                mock.patch.object(
                    launcher,
                    "wait_for_backend_health",
                    side_effect=lambda *args, **kwargs: events.append("health") or True,
                ),
                mock.patch.object(
                    launcher.webbrowser,
                    "open",
                    side_effect=lambda url: events.append("browser") or True,
                ),
            ):
                launcher.launch(release_root=release_root, timeout_seconds=0.1)

        self.assertEqual(events, ["spawn", "health", "browser"])

    def test_launch_raises_clear_error_when_child_exits_before_health(self):
        with temporary_release_root() as release_root:
            process = mock.Mock()
            process.poll.return_value = 23
            with (
                mock.patch.object(launcher, "BACKEND_EXECUTABLE_NAME", "Backend.stub"),
                mock.patch.object(launcher, "find_free_port", return_value=8001),
                mock.patch.object(launcher.subprocess, "Popen", return_value=process),
                mock.patch.object(launcher, "is_backend_healthy", return_value=False),
                mock.patch.object(launcher.time, "sleep") as sleep_mock,
                mock.patch.object(launcher.webbrowser, "open") as browser_mock,
            ):
                with self.assertRaisesRegex(launcher.LauncherError, "exit code 23"):
                    launcher.launch(release_root=release_root, timeout_seconds=5.0)

        sleep_mock.assert_not_called()
        browser_mock.assert_not_called()

    def test_build_managed_browser_command_uses_app_mode_and_dedicated_profile(self):
        with temporary_release_root() as release_root:
            browser_path = release_root / "msedge.exe"
            browser_path.write_bytes(b"stub browser")
            command = launcher.build_managed_browser_command(
                browser_executable=browser_path,
                url="http://127.0.0.1:8001",
                profile_dir=release_root / ".workbench-browser-profile",
            )

        self.assertEqual(command[0], str(browser_path))
        self.assertIn("--new-window", command)
        self.assertIn("--no-first-run", command)
        self.assertIn("--disable-default-apps", command)
        self.assertIn("--app=http://127.0.0.1:8001", command)
        self.assertIn(
            f"--user-data-dir={release_root / '.workbench-browser-profile'}",
            command,
        )

    def test_launch_with_managed_browser_lifecycle_stops_owned_backend_after_window_exit(self):
        with temporary_release_root() as release_root:
            backend_process = mock.Mock()
            backend_process.poll.return_value = None
            backend_process.wait.return_value = 0
            browser_process = mock.Mock()
            browser_process.wait.return_value = 0

            with (
                mock.patch.object(launcher, "BACKEND_EXECUTABLE_NAME", "Backend.stub"),
                mock.patch.object(launcher, "find_free_port", return_value=8001),
                mock.patch.object(launcher, "wait_for_backend_health", return_value=True),
                mock.patch.object(launcher, "find_browser_executable", return_value=release_root / "msedge.exe"),
                mock.patch.object(launcher.subprocess, "Popen", side_effect=[backend_process, browser_process]),
            ):
                url = launcher.launch(
                    release_root=release_root,
                    timeout_seconds=0.1,
                    manage_browser_lifecycle=True,
                )

        self.assertEqual(url, "http://127.0.0.1:8001")
        browser_process.wait.assert_called_once()
        backend_process.terminate.assert_called_once()
        backend_process.wait.assert_called_once()

    def test_launch_with_managed_browser_lifecycle_stops_runtime_state_pid_when_wrapper_exits(self):
        with temporary_release_root() as release_root:
            backend_process = mock.Mock(pid=1234)
            backend_process.poll.return_value = 0
            browser_process = mock.Mock()
            browser_process.wait.return_value = 0

            with (
                mock.patch.object(launcher, "BACKEND_EXECUTABLE_NAME", "Backend.stub"),
                mock.patch.object(launcher, "find_free_port", return_value=8001),
                mock.patch.object(launcher, "wait_for_backend_health", return_value=True),
                mock.patch.object(launcher, "find_browser_executable", return_value=release_root / "msedge.exe"),
                mock.patch.object(
                    launcher,
                    "load_backend_state",
                    side_effect=[
                        None,
                        {"pid": 4321, "port": 8001, "host": "127.0.0.1"},
                    ],
                ),
                mock.patch.object(launcher, "pid_exists", return_value=True),
                mock.patch.object(launcher, "stop_pid") as stop_pid_mock,
                mock.patch.object(launcher.subprocess, "Popen", side_effect=[backend_process, browser_process]),
            ):
                url = launcher.launch(
                    release_root=release_root,
                    timeout_seconds=0.1,
                    manage_browser_lifecycle=True,
                )

        self.assertEqual(url, "http://127.0.0.1:8001")
        browser_process.wait.assert_called_once()
        stop_pid_mock.assert_called_once_with(4321, timeout_seconds=10.0)
        backend_process.terminate.assert_not_called()

    def test_launch_with_managed_browser_lifecycle_does_not_stop_reused_backend(self):
        with temporary_release_root() as release_root:
            write_state_file(
                release_root,
                {"pid": 4321, "port": 8123, "host": "127.0.0.1"},
            )
            browser_process = mock.Mock()
            browser_process.wait.return_value = 0

            with (
                mock.patch.object(launcher, "BACKEND_EXECUTABLE_NAME", "Backend.stub"),
                mock.patch.object(launcher, "pid_exists", return_value=True),
                mock.patch.object(launcher, "wait_for_backend_health", return_value=True),
                mock.patch.object(launcher, "find_browser_executable", return_value=release_root / "msedge.exe"),
                mock.patch.object(launcher.subprocess, "Popen", return_value=browser_process) as popen_mock,
            ):
                url = launcher.launch(
                    release_root=release_root,
                    timeout_seconds=0.1,
                    manage_browser_lifecycle=True,
                )

        self.assertEqual(url, "http://127.0.0.1:8123")
        browser_process.wait.assert_called_once()
        popen_mock.assert_called_once()

    def test_parse_args_rejects_negative_port(self):
        with self.assertRaises(SystemExit):
            launcher.parse_args(["--port", "-1"])

    def test_parse_args_rejects_port_above_range(self):
        with self.assertRaises(SystemExit):
            launcher.parse_args(["--port", "65536"])

    def test_main_uses_default_browser_mode(self):
        with mock.patch.object(launcher, "launch", return_value="http://127.0.0.1:8001") as launch_mock:
            exit_code = launcher.main(["--host", "127.0.0.1", "--port", "8001", "--timeout", "5"])

        self.assertEqual(exit_code, 0)
        launch_mock.assert_called_once_with(
            host="127.0.0.1",
            preferred_port=8001,
            timeout_seconds=5.0,
        )

    def test_find_free_port_rejects_invalid_start_port(self):
        with self.assertRaisesRegex(launcher.LauncherError, "Invalid port"):
            launcher.find_free_port(start_port=65536)

    def test_find_free_port_rejects_probe_overflow(self):
        with mock.patch.object(launcher, "is_port_available", return_value=False):
            with self.assertRaisesRegex(launcher.LauncherError, "No free port found"):
                launcher.find_free_port(start_port=65535, max_attempts=2)

    def test_is_port_available_uses_ipv6_family_for_ipv6_host(self):
        socket_mock = mock.MagicMock()
        socket_mock.bind.return_value = None
        socket_factory = mock.MagicMock()
        socket_factory.return_value.__enter__.return_value = socket_mock

        with mock.patch.object(launcher.socket, "socket", socket_factory):
            available = launcher.is_port_available("::1", 8001)

        self.assertTrue(available)
        socket_factory.assert_called_once_with(
            launcher.socket.AF_INET6,
            launcher.socket.SOCK_STREAM,
        )
        socket_mock.bind.assert_called_once_with(("::1", 8001))


class ServerEntryTests(unittest.TestCase):
    def test_invalid_release_layout_from_config_import_is_reported_by_main(self):
        with temporary_server_entry_fixture() as fixture:
            with mock.patch.object(
                server_entry_module,
                "CONFIG_IMPORT_ERROR",
                RuntimeError(
                    "Invalid release layout in frozen mode. Missing required runtime assets:\n"
                    "- missing/frontend_dist/index.html"
                ),
                create=True,
            ):
                with mock.patch.object(server_entry_module.uvicorn, "run") as uvicorn_run_mock:
                    with self.assertRaises(SystemExit) as context:
                        server_entry_module.main(["--host", "127.0.0.1", "--port", "8100"])

        self.assertIn("Invalid release layout", str(context.exception))
        self.assertIn("missing/frontend_dist/index.html", str(context.exception))
        self.assertFalse(fixture["state_file"].exists())
        uvicorn_run_mock.assert_not_called()

    def test_server_entry_writes_host_pid_and_port_state(self):
        with temporary_server_entry_fixture() as fixture:
            with mock.patch.object(server_entry_module, "RELEASE_LAYOUT_VALID", True, create=True):
                server_entry_module.write_backend_state("0.0.0.0", 8123)
                payload = json.loads(fixture["state_file"].read_text(encoding="utf-8"))

        self.assertEqual(payload["host"], "0.0.0.0")
        self.assertEqual(payload["port"], 8123)
        self.assertIsInstance(payload["pid"], int)


if __name__ == "__main__":
    unittest.main()
