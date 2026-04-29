import argparse
import ctypes
import ipaddress
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
LOOPBACK_CLIENT_HOST = "127.0.0.1"
PREFERRED_PORT = 8001
MAX_PORT_ATTEMPTS = 100
STARTUP_TIMEOUT_SECONDS = 30.0
HEALTH_POLL_INTERVAL_SECONDS = 0.5
BACKEND_EXECUTABLE_NAME = "Backend.exe"
STATE_FILE_NAME = "server.json"
MIN_PORT = 1
MAX_PORT = 65535
WILDCARD_BIND_HOSTS = {"0.0.0.0", "::", "[::]", "*", ""}
BROWSER_EXECUTABLE_NAMES = ("msedge.exe", "chrome.exe", "brave.exe")


class LauncherError(RuntimeError):
    pass


def validate_port_number(port: int, field_name: str = "port") -> int:
    if not MIN_PORT <= port <= MAX_PORT:
        raise LauncherError(f"Invalid port for {field_name}: {port}. Expected {MIN_PORT}-{MAX_PORT}.")
    return port


def _parse_port_argument(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Port must be an integer.") from exc
    if not MIN_PORT <= port <= MAX_PORT:
        raise argparse.ArgumentTypeError(f"Port must be between {MIN_PORT} and {MAX_PORT}.")
    return port


def get_release_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_backend_executable_path(release_root: Path | None = None) -> Path:
    root = Path(release_root).resolve() if release_root is not None else get_release_root()
    return root / BACKEND_EXECUTABLE_NAME


def get_backend_state_file_path(release_root: Path | None = None) -> Path:
    root = Path(release_root).resolve() if release_root is not None else get_release_root()
    return root / "backend_state" / STATE_FILE_NAME


def get_browser_profile_dir(release_root: Path | None = None) -> Path:
    root = Path(release_root).resolve() if release_root is not None else get_release_root()
    return root / ".workbench-browser-profile"


def load_backend_state(release_root: Path | None = None) -> dict[str, object] | None:
    state_file = get_backend_state_file_path(release_root)
    if not state_file.exists():
        return None

    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cleanup_state_file(release_root)
        return None

    if not isinstance(payload, dict):
        cleanup_state_file(release_root)
        return None
    return payload


def cleanup_state_file(release_root: Path | None = None) -> None:
    state_file = get_backend_state_file_path(release_root)
    try:
        state_file.unlink()
    except PermissionError:
        tombstone = state_file.with_name(f"{state_file.stem}.{time.time_ns()}.stale")
        os.chmod(state_file, 0o666)
        state_file.replace(tombstone)
        try:
            tombstone.unlink()
        except OSError:
            pass
    except FileNotFoundError:
        return


def get_backend_runtime_pid(release_root: Path | None = None) -> int | None:
    state = load_backend_state(release_root)
    if not isinstance(state, dict):
        return None
    pid = state.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return None
    return pid


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information,
        False,
        pid,
    )
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def wait_for_pid_exit(
    pid: int,
    timeout_seconds: float = 10.0,
    interval_seconds: float = 0.2,
) -> bool:
    if pid <= 0:
        return True
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not pid_exists(pid):
            return True
        time.sleep(interval_seconds)
    return not pid_exists(pid)


def get_socket_family_for_host(host: str) -> int:
    normalized = str(host or "").strip()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return socket.AF_INET
    if address.version == 6:
        return socket.AF_INET6
    return socket.AF_INET


def is_port_available(host: str, port: int) -> bool:
    family = get_socket_family_for_host(host)
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(
    host: str = DEFAULT_HOST,
    start_port: int = PREFERRED_PORT,
    max_attempts: int = MAX_PORT_ATTEMPTS,
) -> int:
    validate_port_number(start_port, field_name="start port")
    for offset in range(max_attempts):
        port = start_port + offset
        if port > MAX_PORT:
            break
        if is_port_available(host, port):
            return port
    raise LauncherError(
        f"No free port found starting at {start_port} after {max_attempts} attempts."
    )


def build_backend_command(backend_executable: Path, host: str, port: int) -> list[str]:
    validate_port_number(port)
    return [str(backend_executable), "--host", host, "--port", str(port)]


def normalize_client_host(host: str) -> str:
    normalized = str(host or "").strip()
    if normalized in WILDCARD_BIND_HOSTS:
        return LOOPBACK_CLIENT_HOST
    return normalized


def _format_url_host(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def build_base_url(host: str, port: int) -> str:
    validate_port_number(port)
    client_host = normalize_client_host(host)
    return f"http://{_format_url_host(client_host)}:{port}"


def is_backend_healthy(base_url: str) -> bool:
    health_url = f"{base_url.rstrip('/')}/api/health"
    try:
        with urllib.request.urlopen(health_url, timeout=2.0) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return payload.get("backend") == "ok"


def wait_for_backend_health(
    base_url: str,
    timeout_seconds: float = STARTUP_TIMEOUT_SECONDS,
    interval_seconds: float = HEALTH_POLL_INTERVAL_SECONDS,
    process=None,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if is_backend_healthy(base_url):
            return True
        if process is not None:
            exit_code = process.poll()
            if exit_code is not None:
                raise LauncherError(
                    f"{BACKEND_EXECUTABLE_NAME} exited before /api/health succeeded "
                    f"(exit code {exit_code})."
                )
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_seconds)


def find_browser_executable() -> Path | None:
    for executable_name in BROWSER_EXECUTABLE_NAMES:
        resolved = shutil.which(executable_name)
        if resolved:
            return Path(resolved).resolve()

    if os.name != "nt":
        return None

    local_app_data = Path(os.getenv("LOCALAPPDATA", ""))
    program_files = Path(os.getenv("ProgramFiles", ""))
    program_files_x86 = Path(os.getenv("ProgramFiles(x86)", ""))
    candidates = (
        program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        local_app_data / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local_app_data / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        program_files / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        program_files_x86 / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def build_managed_browser_command(
    browser_executable: Path,
    url: str,
    profile_dir: Path,
) -> list[str]:
    return [
        str(browser_executable),
        f"--user-data-dir={profile_dir}",
        "--new-window",
        "--no-first-run",
        "--disable-default-apps",
        "--no-default-browser-check",
        f"--app={url}",
    ]


def open_managed_browser(url: str, release_root: Path | None = None):
    browser_executable = find_browser_executable()
    if browser_executable is None:
        raise LauncherError(
            "No supported browser was found for managed window mode. "
            "Install Microsoft Edge, Google Chrome, or Brave."
        )

    root = Path(release_root).resolve() if release_root is not None else get_release_root()
    profile_dir = get_browser_profile_dir(root)
    profile_dir.mkdir(parents=True, exist_ok=True)
    command = build_managed_browser_command(browser_executable, url, profile_dir)
    try:
        return subprocess.Popen(command, cwd=str(root))
    except OSError as exc:
        raise LauncherError(
            f"Failed to start managed browser window from {browser_executable}: {exc}"
        ) from exc


def open_browser(url: str) -> None:
    webbrowser.open(url)


def stop_pid(pid: int, timeout_seconds: float = 10.0) -> None:
    if pid <= 0 or not pid_exists(pid):
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass
        if wait_for_pid_exit(pid, timeout_seconds=timeout_seconds):
            return
        raise subprocess.TimeoutExpired(cmd=["taskkill", "/PID", str(pid)], timeout=timeout_seconds)

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    if wait_for_pid_exit(pid, timeout_seconds=timeout_seconds):
        return
    os.kill(pid, signal.SIGKILL)
    if not wait_for_pid_exit(pid, timeout_seconds=timeout_seconds):
        raise subprocess.TimeoutExpired(cmd=["kill", str(pid)], timeout=timeout_seconds)


def stop_process(process, timeout_seconds: float = 10.0) -> None:
    if process is None:
        return
    try:
        if process.poll() is not None:
            return
    except Exception:
        return

    pid = getattr(process, "pid", None)
    if os.name == "nt" and isinstance(pid, int) and pid > 0:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            process.wait(timeout=timeout_seconds)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass

    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)


def stop_backend_process(
    process,
    runtime_pid: int | None = None,
    timeout_seconds: float = 10.0,
) -> None:
    if isinstance(runtime_pid, int) and runtime_pid > 0 and pid_exists(runtime_pid):
        stop_pid(runtime_pid, timeout_seconds=timeout_seconds)
        return
    stop_process(process, timeout_seconds=timeout_seconds)


def _resolve_state_url(
    state: dict[str, object],
    default_host: str,
) -> tuple[int | None, str]:
    try:
        port = validate_port_number(int(state["port"]), field_name="state port")
    except (KeyError, TypeError, ValueError, LauncherError):
        return None, build_base_url(default_host, PREFERRED_PORT)

    state_host = str(state.get("host") or default_host)
    return port, build_base_url(state_host, port)


def launch(
    release_root: Path | None = None,
    host: str = DEFAULT_HOST,
    preferred_port: int = PREFERRED_PORT,
    timeout_seconds: float = STARTUP_TIMEOUT_SECONDS,
    interval_seconds: float = HEALTH_POLL_INTERVAL_SECONDS,
    manage_browser_lifecycle: bool = False,
) -> str:
    root = Path(release_root).resolve() if release_root is not None else get_release_root()
    validate_port_number(preferred_port, field_name="preferred port")
    backend_executable = get_backend_executable_path(root)
    if not backend_executable.exists():
        raise LauncherError(
            f"Missing {BACKEND_EXECUTABLE_NAME} in release folder: {backend_executable}"
        )

    started_backend_process = None
    backend_owned_by_launcher = False
    owned_backend_runtime_pid = None
    state = load_backend_state(root)
    if state is not None:
        port, state_url = _resolve_state_url(state, host)
        pid = state.get("pid")
        if port is not None and isinstance(pid, int) and pid_exists(pid):
            if wait_for_backend_health(
                state_url,
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
                process=None,
            ):
                if manage_browser_lifecycle:
                    browser_process = open_managed_browser(state_url, root)
                    browser_process.wait()
                else:
                    open_browser(state_url)
                return state_url
        cleanup_state_file(root)

    port = find_free_port(host=host, start_port=preferred_port)
    command = build_backend_command(backend_executable, host, port)

    try:
        process = subprocess.Popen(command, cwd=str(root))
        started_backend_process = process
        backend_owned_by_launcher = True
    except OSError as exc:
        raise LauncherError(
            f"Failed to start {BACKEND_EXECUTABLE_NAME} from {backend_executable}: {exc}"
        ) from exc

    try:
        base_url = build_base_url(host, port)
        if not wait_for_backend_health(
            base_url,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
            process=process,
        ):
            raise LauncherError(
                "Backend startup timed out after "
                f"{timeout_seconds:.0f} seconds. Check {BACKEND_EXECUTABLE_NAME}, "
                "frontend_dist, ffmpeg.exe, and ffprobe.exe in the release folder."
            )

        owned_backend_runtime_pid = get_backend_runtime_pid(root)
        if manage_browser_lifecycle:
            browser_process = open_managed_browser(base_url, root)
            browser_process.wait()
            if backend_owned_by_launcher:
                stop_backend_process(
                    process,
                    runtime_pid=owned_backend_runtime_pid,
                )
        else:
            open_browser(base_url)
        return base_url
    except Exception:
        if backend_owned_by_launcher:
            stop_backend_process(
                process,
                runtime_pid=owned_backend_runtime_pid,
            )
        raise


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Nova Workbench release launcher")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=_parse_port_argument, default=PREFERRED_PORT)
    parser.add_argument("--timeout", type=float, default=STARTUP_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        launch(
            host=args.host,
            preferred_port=args.port,
            timeout_seconds=args.timeout,
        )
    except LauncherError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
