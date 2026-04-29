# Windows EXE 发布版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the current short-drama workbench into a portable Windows release that starts via `启动.exe`, runs the backend as `Backend.exe`, serves the built frontend statically, and works on recipient machines without Python or Node installed.

**Architecture:** Introduce a release-aware runtime/config layer that resolves all paths relative to the packaged executables, refactor the generate pipeline so `Backend.exe` can invoke it without shelling out to `video2script.py`, then add a release server entrypoint, launcher, and PowerShell build pipeline that assembles the final release folder with frontend assets and FFmpeg binaries.

**Tech Stack:** Python 3.13, FastAPI, PyInstaller, PowerShell, React, Vite, unittest

---

## File Map

- `F:\local_code\novalai\backend\runtime.py`
  Responsibility: release/dev runtime detection, release root resolution, frontend static dir path, ffmpeg/ffprobe path helpers, release state file path.
- `F:\local_code\novalai\backend\config.py`
  Responsibility: expose runtime-aware root directories and service endpoints to the rest of the backend.
- `F:\local_code\novalai\backend\pipeline.py`
  Responsibility: importable generate pipeline entrypoint extracted from `video2script.py`, usable both by CLI and packaged backend.
- `F:\local_code\novalai\video2script.py`
  Responsibility: remain a CLI wrapper over the shared generate pipeline for developer usage.
- `F:\local_code\novalai\backend\runner.py`
  Responsibility: route generate/highlight/score/optimize tasks; switch generate from subprocess script execution to importable pipeline execution.
- `F:\local_code\novalai\backend\app.py`
  Responsibility: keep API routes and add static frontend hosting in release mode without breaking dev mode.
- `F:\local_code\novalai\backend\server_entry.py`
  Responsibility: packaged backend startup, resource self-check, backend state file write/cleanup, uvicorn bootstrap.
- `F:\local_code\novalai\launcher.py`
  Responsibility: packaged launcher for backend reuse/start, health polling, browser open, and error surfacing.
- `F:\local_code\novalai\packaging\backend.spec`
  Responsibility: PyInstaller spec for `Backend.exe`.
- `F:\local_code\novalai\packaging\launcher.spec`
  Responsibility: PyInstaller spec for `启动.exe`.
- `F:\local_code\novalai\scripts\build_release.ps1`
  Responsibility: build frontend, build both executables, copy assets/binaries, create release directory.
- `F:\local_code\novalai\README.md`
  Responsibility: document dev mode vs release mode startup and release build instructions.
- `F:\local_code\novalai\test_release_runtime.py`
  Responsibility: unit tests for runtime root/tool resolution and release directory checks.
- `F:\local_code\novalai\test_release_launcher.py`
  Responsibility: unit tests for launcher port selection, stale backend handling, and health polling.
- `F:\local_code\novalai\test_workbench_runner.py`
  Responsibility: verify generate runner uses callable pipeline and still clears stale score/original artifacts correctly.
- `F:\local_code\novalai\test_workbench_backend.py`
  Responsibility: verify release static hosting and health payload stay correct.

**Repository note:** this workspace currently has no usable `.git` history. Execute the tasks without adding commit steps unless a real git repo is restored later.

### Task 1: Add release-aware runtime and tool resolution

**Files:**
- Create: `F:\local_code\novalai\backend\runtime.py`
- Modify: `F:\local_code\novalai\backend\config.py`
- Modify: `F:\local_code\novalai\backend\highlights.py`
- Modify: `F:\local_code\novalai\backend\scoring.py`
- Test: `F:\local_code\novalai\test_release_runtime.py`

- [ ] Step 1: Write failing runtime tests covering:
  - dev mode root still resolves to repo root
  - frozen/release mode root resolves to executable directory
  - release mode ffmpeg/ffprobe helpers point to sibling binaries
  - missing `frontend_dist/index.html` is reported as invalid release layout

- [ ] Step 2: Run the runtime tests and confirm failure.

Run:
```powershell
python -m unittest test_release_runtime.py -v
```

Expected:
```text
FAIL or ERROR because release runtime helpers do not exist yet
```

- [ ] Step 3: Implement `backend/runtime.py` with:
  - `is_frozen_runtime()`
  - `get_runtime_root()`
  - `get_frontend_dist_dir()`
  - `get_ffmpeg_path()`
  - `get_ffprobe_path()`
  - `get_backend_state_path()`
  - `validate_release_layout()`
  - `ensure_runtime_dirs()`

- [ ] Step 4: Update `backend/config.py` to build `ROOT_DIR`, `VIDEOS_DIR`, `SCRIPTS_DIR`, `OUTPUT_DIR`, temp dirs, and media-tool paths from the runtime helpers instead of hardcoding source-tree assumptions.

- [ ] Step 5: Replace hardcoded `"ffmpeg"` usage in `backend/highlights.py` and `backend/scoring.py` with the runtime-resolved binary path, while keeping dev-mode PATH compatibility.

- [ ] Step 6: Re-run the runtime tests.

Run:
```powershell
python -m unittest test_release_runtime.py -v
```

Expected:
```text
OK
```

### Task 2: Refactor the generate pipeline for frozen backend execution

**Files:**
- Create: `F:\local_code\novalai\backend\pipeline.py`
- Modify: `F:\local_code\novalai\video2script.py`
- Modify: `F:\local_code\novalai\backend\runner.py`
- Modify: `F:\local_code\novalai\test_workbench_runner.py`

- [ ] Step 1: Add failing runner tests that prove packaged backend execution no longer depends on `sys.executable -u video2script.py`.

- [ ] Step 2: Run the focused runner tests and confirm failure.

Run:
```powershell
python -m unittest test_workbench_runner.py -v
```

Expected:
```text
FAIL because `run_video2script` still shells out to `video2script.py`
```

- [ ] Step 3: Extract the reusable generate pipeline from `video2script.py` into `backend/pipeline.py`.

Implementation target:
  - move the orchestration logic into a callable function such as `run_video_pipeline(video_path: str, on_line: Callable[[str], None] | None = None) -> int`
  - keep `video2script.py` as a thin CLI wrapper that parses args and calls the shared function
  - route log lines through the provided callback instead of relying only on `print()`
  - replace internal `ffmpeg` / `ffprobe` command construction with the runtime-resolved tool paths from Task 1 so packaged generate tasks do not depend on system PATH

- [ ] Step 4: Update `backend/runner.py` so generate tasks call the shared pipeline directly, then keep the current post-success cleanup of `score.json` and `script_original.txt`.

- [ ] Step 5: Re-run runner tests.

Run:
```powershell
python -m unittest test_workbench_runner.py -v
```

Expected:
```text
OK
```

- [ ] Step 6: Run the existing remote pipeline smoke test to ensure the CLI wrapper still works.

Run:
```powershell
python -m unittest test_video2script_remote.py -v
```

Expected:
```text
existing remote smoke tests still pass or fail only for external-service reachability
```

### Task 3: Serve the built frontend from the backend and add packaged backend entrypoint

**Files:**
- Create: `F:\local_code\novalai\backend\server_entry.py`
- Modify: `F:\local_code\novalai\backend\app.py`
- Modify: `F:\local_code\novalai\test_workbench_backend.py`

- [ ] Step 1: Add failing backend tests covering:
  - `/api/health` reports release-path status for `frontend_dist`, `ffmpeg`, and `ffprobe`
  - `/` serves `frontend_dist/index.html` when a frontend build is present
  - non-API SPA routes also fall back to `index.html`
  - `/api/*` routes still behave unchanged

- [ ] Step 2: Run the focused backend tests and confirm failure.

Run:
```powershell
python -m unittest test_workbench_backend.py -v
```

Expected:
```text
FAIL because static hosting and packaged health fields are not wired yet
```

- [ ] Step 3: Update `backend/app.py` to:
  - keep all existing API routes
  - add release-aware static asset mounting for `frontend_dist`
  - add SPA fallback for non-API paths
  - extend health payload with frontend and media-tool availability

- [ ] Step 4: Implement `backend/server_entry.py` so packaged startup:
  - parses `--host` and `--port`
  - validates the release layout before serving
  - ensures `videos/`, `scripts/`, and `output/` exist
  - writes a small backend state file with PID and port
  - starts uvicorn against `backend.app:app`

- [ ] Step 5: Re-run the backend tests.

Run:
```powershell
python -m unittest test_workbench_backend.py -v
```

Expected:
```text
OK
```

### Task 4: Build the launcher executable flow

**Files:**
- Create: `F:\local_code\novalai\launcher.py`
- Modify: `F:\local_code\novalai\backend\server_entry.py`
- Test: `F:\local_code\novalai\test_release_launcher.py`

- [ ] Step 1: Write failing launcher tests covering:
  - preferred port `8001`, then incremental fallback when occupied
  - reuse of a healthy backend recorded in the state file
  - stale state file cleanup when the PID no longer exists
  - browser open only after `/api/health` succeeds

- [ ] Step 2: Run the launcher tests and confirm failure.

Run:
```powershell
python -m unittest test_release_launcher.py -v
```

Expected:
```text
FAIL because launcher flow does not exist yet
```

- [ ] Step 3: Implement `launcher.py` with:
  - release-root detection
  - state-file lookup
  - free-port selection
  - `Backend.exe` spawn command construction
  - health polling with timeout
  - default-browser open
  - clear user-facing error messages for missing files or startup timeout

- [ ] Step 4: Adjust `backend/server_entry.py` if needed so the state file is written and cleaned up predictably enough for launcher reuse logic.

- [ ] Step 5: Re-run launcher tests.

Run:
```powershell
python -m unittest test_release_launcher.py -v
```

Expected:
```text
OK
```

### Task 5: Add the release packaging pipeline

**Files:**
- Create: `F:\local_code\novalai\packaging\backend.spec`
- Create: `F:\local_code\novalai\packaging\launcher.spec`
- Create: `F:\local_code\novalai\scripts\build_release.ps1`

- [ ] Step 1: Write `packaging/backend.spec` so PyInstaller produces `Backend.exe` with the backend package and any required hidden imports.

- [ ] Step 2: Write `packaging/launcher.spec` so PyInstaller produces `启动.exe`.

- [ ] Step 3: Write `scripts/build_release.ps1` to:
  - clear prior release output
  - run `frontend` production build
  - build `Backend.exe`
  - build `启动.exe`
  - create `novalai-release/`
  - copy `frontend/dist` into `frontend_dist/`
  - copy `ffmpeg.exe` and `ffprobe.exe`
  - create `videos/`, `scripts/`, and `output/`
  - fail fast with a clear message when the FFmpeg binary source directory is not provided

- [ ] Step 4: Decide and document the FFmpeg binary input contract for the build machine.

Recommended contract:
  - `scripts/build_release.ps1` accepts `-FfmpegDir <absolute-path>`
  - or reads `NOVALAI_FFMPEG_DIR`
  - the script validates that both `ffmpeg.exe` and `ffprobe.exe` exist before building PyInstaller artifacts

- [ ] Step 5: Run the frontend build once before the full packaging step.

Run:
```powershell
cd frontend
npm run build
```

Expected:
```text
Vite build succeeds and outputs `frontend/dist/`
```

- [ ] Step 6: Run the release build script.

Run:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -FfmpegDir C:\path\to\ffmpeg-bin
```

Expected:
```text
release folder is created with:
- 启动.exe
- Backend.exe
- ffmpeg.exe
- ffprobe.exe
- frontend_dist\
- videos\
- scripts\
- output\
```

### Task 6: Update documentation and verify the portable release end-to-end

**Files:**
- Modify: `F:\local_code\novalai\README.md`

- [ ] Step 1: Update `README.md` to separate:
  - developer startup via `run_workbench.bat`
  - release build generation
  - release folder contents
  - recipient-machine usage via `启动.exe`

- [ ] Step 2: Run the full Python test suite most relevant to the release changes.

Run:
```powershell
python -m unittest test_release_runtime.py test_release_launcher.py test_workbench_backend.py test_workbench_runner.py -v
```

Expected:
```text
OK
```

- [ ] Step 3: Run frontend tests to make sure static-build-related changes did not regress the UI.

Run:
```powershell
cd frontend
npm run test -- --run
```

Expected:
```text
all frontend tests pass
```

- [ ] Step 4: Manually smoke-test the packaged release on a machine without Python/Node in PATH.

Smoke checklist:
  - double-click `启动.exe`
  - browser opens to the workbench
  - `GET /api/health` returns `backend: ok`
  - upload one MP4 and verify generate -> score -> viral prediction still work
  - upload one TXT and verify script-mode tasks still work

- [ ] Step 5: Record any release-only issues found during the manual smoke test and fix them before declaring the release ready.

## Done Criteria

- `启动.exe` is the only user-facing entrypoint
- `Backend.exe` serves both `/api/*` and the built frontend
- release mode no longer depends on local Python or Node installation
- release mode no longer depends on system PATH for `ffmpeg` / `ffprobe`
- generate tasks work from the packaged backend without shelling out to `video2script.py`
- the assembled release folder matches the approved design doc
