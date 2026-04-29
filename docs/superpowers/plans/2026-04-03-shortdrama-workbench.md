# Short Drama Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real local workbench for the short-drama reverse-script pipeline, with React UI, FastAPI APIs, upload support, serial task execution, stage progress, and history/result browsing.

**Architecture:** Keep `video2script.py` as the processing engine and wrap it with a small FastAPI backend that owns filesystem access, uploads, task queueing, subprocess execution, and result aggregation. Build a React + Vite frontend as the dual-column "command desk" UI that polls backend APIs for queue state, task progress, and generated outputs.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, python-multipart, unittest, React, Vite, TypeScript, Vitest, Testing Library, plain CSS with custom properties.

---

> **Repo note:** This workspace currently has no `.git` directory. Every commit step below is conditional: run it only if git is initialized before implementation; otherwise record `skip commit: repo has no .git`.

## File Structure

### Backend

- Create: `backend/__init__.py`
  Responsibility: package marker.
- Create: `backend/config.py`
  Responsibility: project paths, upload directories, polling constants, environment-derived settings.
- Create: `backend/models.py`
  Responsibility: Pydantic models and enums for videos, tasks, health, and results.
- Create: `backend/catalog.py`
  Responsibility: scan `videos/`, `tmp_uploads/`, and `output/`; resolve `video_id`; aggregate output metadata.
- Create: `backend/uploads.py`
  Responsibility: persist uploaded files with unique names and return normalized records.
- Create: `backend/log_parser.py`
  Responsibility: map `video2script.py` stdout lines to stage updates and progress counters.
- Create: `backend/task_queue.py`
  Responsibility: in-memory serial queue, task registry, state transitions, logs tail.
- Create: `backend/runner.py`
  Responsibility: run `video2script.py` as subprocess, stream stdout, update queue state.
- Create: `backend/app.py`
  Responsibility: FastAPI app, route registration, singleton service wiring, optional static frontend mount.

### Frontend

- Create: `frontend/package.json`
  Responsibility: Vite/React dependencies and scripts.
- Create: `frontend/tsconfig.json`
  Responsibility: TypeScript configuration.
- Create: `frontend/vite.config.ts`
  Responsibility: dev server config and proxy to backend.
- Create: `frontend/index.html`
  Responsibility: Vite HTML entry.
- Create: `frontend/src/main.tsx`
  Responsibility: React bootstrap.
- Create: `frontend/src/App.tsx`
  Responsibility: top-level page composition.
- Create: `frontend/src/types.ts`
  Responsibility: shared API response types used by the UI.
- Create: `frontend/src/api/client.ts`
  Responsibility: fetch wrappers for health, videos, uploads, tasks, results, and media URLs.
- Create: `frontend/src/hooks/useWorkbenchData.ts`
  Responsibility: polling, optimistic state, current selection, refresh triggers.
- Create: `frontend/src/components/TopBar.tsx`
  Responsibility: global actions and health badges.
- Create: `frontend/src/components/UploadPanel.tsx`
  Responsibility: drag/drop upload and save-mode selection.
- Create: `frontend/src/components/QueuePanel.tsx`
  Responsibility: video/history/queue list and current selection.
- Create: `frontend/src/components/TaskDrawer.tsx`
  Responsibility: collapsible stage progress drawer.
- Create: `frontend/src/components/PreviewStage.tsx`
  Responsibility: video player, timeline summary, current task summary.
- Create: `frontend/src/components/ResultPanel.tsx`
  Responsibility: tabbed `dialogues / segments / script` viewer.
- Create: `frontend/src/styles.css`
  Responsibility: design tokens, layout grid, theatrical workbench styling.

### Tests and Run Helpers

- Create: `test_workbench_backend.py`
  Responsibility: API-level tests for health, catalog, uploads, results.
- Create: `test_workbench_queue.py`
  Responsibility: queue state machine and log parser tests.
- Create: `frontend/src/App.test.tsx`
  Responsibility: shell render test for the dual-column workbench.
- Create: `frontend/src/components/TaskDrawer.test.tsx`
  Responsibility: drawer open/close and stage rendering test.
- Create: `run_workbench.bat`
  Responsibility: convenience launcher for backend + frontend dev servers on Windows.

## Task 1: Create the Backend Skeleton and Health Endpoint

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `backend/models.py`
- Create: `backend/app.py`
- Test: `test_workbench_backend.py`

- [ ] **Step 1: Write the failing backend health test**

```python
import unittest
from fastapi.testclient import TestClient

from backend.app import app


class WorkbenchHealthTests(unittest.TestCase):
    def test_health_reports_core_paths(self):
        client = TestClient(app)

        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("backend", payload)
        self.assertIn("paths", payload)
        self.assertIn("videos", payload["paths"])
        self.assertIn("output", payload["paths"])
```

- [ ] **Step 2: Run the health test to verify it fails**

Run: `python -m unittest test_workbench_backend.WorkbenchHealthTests.test_health_reports_core_paths -v`

Expected: FAIL with `ModuleNotFoundError` or missing `/api/health`.

- [ ] **Step 3: Create minimal backend config and app**

```python
# backend/config.py
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
VIDEOS_DIR = ROOT_DIR / "videos"
OUTPUT_DIR = ROOT_DIR / "output"
TMP_UPLOADS_DIR = ROOT_DIR / "tmp_uploads"
```

```python
# backend/app.py
from fastapi import FastAPI

from backend.config import OUTPUT_DIR, TMP_UPLOADS_DIR, VIDEOS_DIR

app = FastAPI(title="Nova Short Drama Workbench")


@app.get("/api/health")
def health():
    return {
        "backend": "ok",
        "paths": {
            "videos": {"path": str(VIDEOS_DIR), "exists": VIDEOS_DIR.exists()},
            "output": {"path": str(OUTPUT_DIR), "exists": OUTPUT_DIR.exists()},
            "tmp_uploads": {"path": str(TMP_UPLOADS_DIR), "exists": TMP_UPLOADS_DIR.exists()},
        },
    }
```

- [ ] **Step 4: Run the health test to verify it passes**

Run: `python -m unittest test_workbench_backend.WorkbenchHealthTests.test_health_reports_core_paths -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/__init__.py backend/config.py backend/models.py backend/app.py test_workbench_backend.py
git commit -m "feat: add workbench backend health endpoint"
```

If `.git` is absent: record `skip commit: repo has no .git`.

## Task 2: Implement Video Catalog and Result Aggregation

**Files:**
- Modify: `backend/models.py`
- Create: `backend/catalog.py`
- Modify: `backend/app.py`
- Modify: `test_workbench_backend.py`

- [ ] **Step 1: Add a failing test for listing videos and outputs**

```python
class WorkbenchCatalogTests(unittest.TestCase):
    def test_videos_endpoint_reports_history_outputs(self):
        client = TestClient(app)

        response = client.get("/api/videos")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(item["video_name"] == "01" for item in payload["items"]))
        first = payload["items"][0]
        self.assertIn("video_id", first)
        self.assertIn("has_output", first)
        self.assertIn("output_ready", first)
```

- [ ] **Step 2: Run the catalog test to verify it fails**

Run: `python -m unittest test_workbench_backend.WorkbenchCatalogTests.test_videos_endpoint_reports_history_outputs -v`

Expected: FAIL with missing `/api/videos`.

- [ ] **Step 3: Implement catalog scanning and `/api/videos`**

```python
# backend/catalog.py
from dataclasses import dataclass
from pathlib import Path
import hashlib

from backend.config import OUTPUT_DIR, VIDEOS_DIR


def build_video_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]


def list_videos():
    items = []
    for video_path in sorted(VIDEOS_DIR.glob("*.mp4")):
        video_name = video_path.stem
        output_dir = OUTPUT_DIR / video_name
        items.append(
            {
                "video_id": build_video_id(video_path),
                "video_name": video_name,
                "video_path": str(video_path),
                "has_output": output_dir.exists(),
                "output_ready": all(
                    (output_dir / filename).exists()
                    for filename in ("dialogues.json", "segments.json", "script.txt")
                ),
            }
        )
    return items
```

```python
# backend/app.py
from backend.catalog import list_videos


@app.get("/api/videos")
def get_videos():
    return {"items": list_videos()}
```

- [ ] **Step 4: Add result lookup helper and endpoint**

```python
def load_results_by_video_id(video_id: str):
    for item in list_videos():
        if item["video_id"] == video_id:
            output_dir = OUTPUT_DIR / item["video_name"]
            return item, output_dir
    raise KeyError(video_id)
```

```python
@app.get("/api/results/{video_id}")
def get_results(video_id: str):
    item, output_dir = load_results_by_video_id(video_id)
    return {
        "video": item,
        "dialogues": json.loads((output_dir / "dialogues.json").read_text(encoding="utf-8")),
        "segments": json.loads((output_dir / "segments.json").read_text(encoding="utf-8")),
        "script": (output_dir / "script.txt").read_text(encoding="utf-8"),
        "media_url": f"/api/media/{video_id}",
    }
```

- [ ] **Step 5: Add the media streaming endpoint**

```python
from fastapi.responses import FileResponse


@app.get("/api/media/{video_id}")
def get_media(video_id: str):
    item = find_video_by_id(video_id)
    return FileResponse(item["video_path"], media_type="video/mp4")
```

- [ ] **Step 6: Run backend tests**

Run: `python -m unittest test_workbench_backend.py -v`

Expected: PASS for health and catalog coverage.

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/catalog.py backend/app.py test_workbench_backend.py
git commit -m "feat: add workbench video catalog endpoints"
```

If `.git` is absent: record `skip commit: repo has no .git`.

## Task 3: Implement Upload Handling with Stable `video_id`

**Files:**
- Create: `backend/uploads.py`
- Modify: `backend/catalog.py`
- Modify: `backend/app.py`
- Modify: `test_workbench_backend.py`

- [ ] **Step 1: Write the failing upload test**

```python
from io import BytesIO


class WorkbenchUploadTests(unittest.TestCase):
    def test_uploads_endpoint_persists_file_with_unique_name(self):
        client = TestClient(app)

        response = client.post(
            "/api/uploads?persist=false",
            files={"file": ("sample.mp4", BytesIO(b"fake-video"), "video/mp4")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("video_id", payload)
        self.assertEqual(payload["source_type"], "upload_temp")
        self.assertNotEqual(payload["stored_name"], "sample.mp4")
```

- [ ] **Step 2: Run the upload test to verify it fails**

Run: `python -m unittest test_workbench_backend.WorkbenchUploadTests.test_uploads_endpoint_persists_file_with_unique_name -v`

Expected: FAIL with missing `/api/uploads`.

- [ ] **Step 3: Implement unique-name upload persistence**

```python
# backend/uploads.py
from pathlib import Path
from uuid import uuid4

from backend.config import TMP_UPLOADS_DIR, VIDEOS_DIR


def save_upload(file_name: str, file_bytes: bytes, persist: bool):
    target_root = VIDEOS_DIR if persist else TMP_UPLOADS_DIR / uuid4().hex
    target_root.mkdir(parents=True, exist_ok=True)
    stem = Path(file_name).stem
    suffix = Path(file_name).suffix or ".mp4"
    stored_name = f"{stem}-{uuid4().hex[:8]}{suffix}"
    target_path = target_root / stored_name
    target_path.write_bytes(file_bytes)
    return target_path
```

```python
@app.post("/api/uploads")
async def upload_video(file: UploadFile, persist: bool = True):
    file_bytes = await file.read()
    target_path = save_upload(file.filename, file_bytes, persist=persist)
    return build_video_record(target_path, source_type="upload_persist" if persist else "upload_temp")
```

- [ ] **Step 4: Teach the catalog to include temporary uploads**

```python
def iter_video_paths():
    yield from sorted(VIDEOS_DIR.glob("*.mp4"))
    if TMP_UPLOADS_DIR.exists():
        yield from sorted(TMP_UPLOADS_DIR.rglob("*.mp4"))
```

- [ ] **Step 5: Run backend tests**

Run: `python -m unittest test_workbench_backend.py -v`

Expected: PASS, including upload behavior.

- [ ] **Step 6: Commit**

```bash
git add backend/uploads.py backend/catalog.py backend/app.py test_workbench_backend.py
git commit -m "feat: add unique upload handling for workbench"
```

If `.git` is absent: record `skip commit: repo has no .git`.

## Task 4: Implement Log Parsing and Queue State Model

**Files:**
- Create: `backend/log_parser.py`
- Create: `backend/task_queue.py`
- Create: `test_workbench_queue.py`

- [ ] **Step 1: Write failing log-parser and queue tests**

```python
import unittest

from backend.log_parser import parse_progress_line
from backend.task_queue import TaskState


class WorkbenchLogParserTests(unittest.TestCase):
    def test_parse_multimodal_progress_line(self):
        update = parse_progress_line("  分析视频片段 [6/11] 135.00s-165.00s ...")
        self.assertEqual(update.stage, "multimodal")
        self.assertEqual(update.current, 6)
        self.assertEqual(update.total, 11)


class WorkbenchTaskStateTests(unittest.TestCase):
    def test_task_state_starts_queued(self):
        task = TaskState(task_id="t1", video_id="v1", video_name="demo", video_path="demo.mp4")
        self.assertEqual(task.status, "queued")
        self.assertEqual(task.stage, "queued")
```

- [ ] **Step 2: Run the queue tests to verify they fail**

Run: `python -m unittest test_workbench_queue.py -v`

Expected: FAIL with missing modules.

- [ ] **Step 3: Implement minimal parser and task dataclass**

```python
# backend/log_parser.py
import re
from dataclasses import dataclass


@dataclass
class ProgressUpdate:
    stage: str
    current: int | None = None
    total: int | None = None


def parse_progress_line(line: str) -> ProgressUpdate | None:
    if "[Step A]" in line or "调用 ASR 接口" in line:
        return ProgressUpdate(stage="asr")
    if "[Step B]" in line or "生成视频片段" in line:
        return ProgressUpdate(stage="segmenting")
    match = re.search(r"分析视频片段 \[(\d+)/(\d+)\]", line)
    if match:
        return ProgressUpdate(stage="multimodal", current=int(match.group(1)), total=int(match.group(2)))
    if "[Step C]" in line or "整合剧本" in line:
        return ProgressUpdate(stage="merging")
    if "剧本已保存:" in line:
        return ProgressUpdate(stage="done")
    return None
```

```python
# backend/task_queue.py
from dataclasses import dataclass, field


@dataclass
class TaskState:
    task_id: str
    video_id: str
    video_name: str
    video_path: str
    status: str = "queued"
    stage: str = "queued"
    stage_progress: float = 0.0
    logs_tail: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Add queue manager primitives**

```python
class TaskQueue:
    def __init__(self):
        self.items: list[TaskState] = []
        self.current_task_id: str | None = None

    def enqueue(self, task: TaskState) -> None:
        self.items.append(task)

    def list_tasks(self) -> list[TaskState]:
        return list(self.items)
```

- [ ] **Step 5: Run queue tests**

Run: `python -m unittest test_workbench_queue.py -v`

Expected: PASS for the parser and queue model basics.

- [ ] **Step 6: Commit**

```bash
git add backend/log_parser.py backend/task_queue.py test_workbench_queue.py
git commit -m "feat: add workbench queue state and log parser"
```

If `.git` is absent: record `skip commit: repo has no .git`.

## Task 5: Add the Serial Runner and Task APIs

**Files:**
- Create: `backend/runner.py`
- Modify: `backend/task_queue.py`
- Modify: `backend/app.py`
- Modify: `test_workbench_backend.py`
- Modify: `test_workbench_queue.py`

- [ ] **Step 1: Write the failing task API test**

```python
class WorkbenchTaskApiTests(unittest.TestCase):
    def test_creating_task_returns_queued_task(self):
        client = TestClient(app)
        first_video = client.get("/api/videos").json()["items"][0]

        response = client.post("/api/tasks", json={"video_id": first_video["video_id"]})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("task_id", payload)
        self.assertIn(payload["status"], {"queued", "running"})
```

- [ ] **Step 2: Run the task API test to verify it fails**

Run: `python -m unittest test_workbench_backend.WorkbenchTaskApiTests.test_creating_task_returns_queued_task -v`

Expected: FAIL with missing `/api/tasks`.

- [ ] **Step 3: Implement the subprocess runner**

```python
# backend/runner.py
import subprocess

from backend.log_parser import parse_progress_line


def run_video2script(task, on_line):
    process = subprocess.Popen(
        ["python", "video2script.py", task.video_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    assert process.stdout is not None
    for line in process.stdout:
        on_line(line.rstrip("\n"))
    return process.wait()
```

- [ ] **Step 4: Extend the queue with start/finish/fail transitions**

```python
def mark_running(self, task: TaskState) -> None:
    task.status = "running"


def append_log(self, task: TaskState, line: str) -> None:
    task.logs_tail.append(line)
    task.logs_tail[:] = task.logs_tail[-50:]
```

- [ ] **Step 5: Expose task endpoints**

```python
@app.post("/api/tasks")
def create_task(payload: CreateTaskRequest):
    task = queue_service.enqueue_for_video(payload.video_id)
    queue_service.maybe_start_next()
    return task


@app.get("/api/tasks")
def list_tasks():
    return {"items": queue_service.serialize_tasks()}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    return queue_service.serialize_task(task_id)
```

- [ ] **Step 6: Run backend and queue tests**

Run: `python -m unittest test_workbench_backend.py test_workbench_queue.py -v`

Expected: PASS for task creation and queue state tests.

- [ ] **Step 7: Commit**

```bash
git add backend/runner.py backend/task_queue.py backend/app.py test_workbench_backend.py test_workbench_queue.py
git commit -m "feat: add workbench task queue APIs"
```

If `.git` is absent: record `skip commit: repo has no .git`.

## Task 6: Scaffold the React + Vite Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: Initialize the React + TypeScript workspace**

Run: `npm create vite@latest frontend -- --template react-ts`

Expected: `frontend/` created with Vite React scaffold.

- [ ] **Step 2: Add the failing shell render test**

```tsx
import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders the dual-column workbench shell", () => {
  render(<App />);
  expect(screen.getByText("Nova 剧本反推工作台")).toBeInTheDocument();
  expect(screen.getByText("新建任务")).toBeInTheDocument();
  expect(screen.getByText("视频对照主视图")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run the frontend test to verify it fails**

Run: `npm --prefix .\frontend run test -- --run`

Expected: FAIL because the scaffolded `App.tsx` does not render the workbench shell.

- [ ] **Step 4: Replace the scaffold with the minimal shell**

```tsx
// frontend/src/App.tsx
export default function App() {
  return (
    <div className="app-shell">
      <header className="top-bar">Nova 剧本反推工作台</header>
      <main className="workbench-grid">
        <aside>新建任务</aside>
        <section>视频对照主视图</section>
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Add frontend scripts and proxy**

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest"
  }
}
```

```ts
// frontend/vite.config.ts
server: {
  proxy: {
    "/api": "http://127.0.0.1:8000"
  }
}
```

- [ ] **Step 6: Run frontend tests and build**

Run: `npm --prefix .\frontend run test -- --run`

Expected: PASS.

Run: `npm --prefix .\frontend run build`

Expected: PASS with `dist/` output.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src/main.tsx frontend/src/App.tsx frontend/src/types.ts frontend/src/api/client.ts frontend/src/styles.css frontend/src/App.test.tsx
git commit -m "feat: scaffold workbench frontend"
```

If `.git` is absent: record `skip commit: repo has no .git`.

## Task 7: Build the Left Column UI with Tests

**Files:**
- Create: `frontend/src/components/TopBar.tsx`
- Create: `frontend/src/components/UploadPanel.tsx`
- Create: `frontend/src/components/QueuePanel.tsx`
- Create: `frontend/src/components/TaskDrawer.tsx`
- Create: `frontend/src/components/TaskDrawer.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write the failing drawer interaction test**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { TaskDrawer } from "./TaskDrawer";

test("shows stage rows after expanding the drawer", () => {
  render(<TaskDrawer open={false} task={{ stage: "multimodal", steps: [] }} onToggle={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: /当前任务状态/i }));
  expect(screen.getByText("多模态分析")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the drawer test to verify it fails**

Run: `npm --prefix .\frontend run test -- --run`

Expected: FAIL with missing component or missing labels.

- [ ] **Step 3: Implement left-column components**

```tsx
// QueuePanel.tsx
export function QueuePanel({ items, selectedId, onSelect }) {
  return items.map((item) => (
    <button key={item.video_id} data-active={item.video_id === selectedId} onClick={() => onSelect(item.video_id)}>
      {item.video_name}
    </button>
  ));
}
```

```tsx
// TaskDrawer.tsx
export function TaskDrawer({ open, task, onToggle }) {
  return (
    <section>
      <button onClick={onToggle}>当前任务状态</button>
      {open && <div>{task.stage === "multimodal" ? "多模态分析" : task.stage}</div>}
    </section>
  );
}
```

- [ ] **Step 4: Compose the left column into `App.tsx`**

```tsx
<aside className="left-column">
  <UploadPanel />
  <QueuePanel />
  <TaskDrawer />
</aside>
```

- [ ] **Step 5: Run frontend tests**

Run: `npm --prefix .\frontend run test -- --run`

Expected: PASS for the workbench shell and drawer interaction.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/TopBar.tsx frontend/src/components/UploadPanel.tsx frontend/src/components/QueuePanel.tsx frontend/src/components/TaskDrawer.tsx frontend/src/components/TaskDrawer.test.tsx frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: add workbench left column UI"
```

If `.git` is absent: record `skip commit: repo has no .git`.

## Task 8: Build the Right Column, API Polling, and Real Data Wiring

**Files:**
- Create: `frontend/src/components/PreviewStage.tsx`
- Create: `frontend/src/components/ResultPanel.tsx`
- Create: `frontend/src/hooks/useWorkbenchData.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write the failing real-data render test**

```tsx
test("shows result tabs for the selected video", async () => {
  render(<App />);
  expect(await screen.findByText("对白")).toBeInTheDocument();
  expect(screen.getByText("分段")).toBeInTheDocument();
  expect(screen.getByText("剧本")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the frontend test to verify it fails**

Run: `npm --prefix .\frontend run test -- --run`

Expected: FAIL because the right column is not wired.

- [ ] **Step 3: Add typed API client functions**

```ts
export async function fetchVideos() {
  const response = await fetch("/api/videos");
  return response.json();
}

export async function uploadVideo(file: File, persist: boolean) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`/api/uploads?persist=${persist}`, {
    method: "POST",
    body: formData,
  });
  return response.json();
}

export async function createTask(videoId: string) {
  const response = await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId }),
  });
  return response.json();
}

export async function fetchResults(videoId: string) {
  const response = await fetch(`/api/results/${videoId}`);
  return response.json();
}

export function mediaUrl(videoId: string) {
  return `/api/media/${videoId}`;
}
```

- [ ] **Step 4: Add polling hook**

```ts
export function useWorkbenchData() {
  const [videos, setVideos] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
  const [selectedResult, setSelectedResult] = useState(null);

  useEffect(() => {
    const tick = async () => {
      const nextVideos = (await fetchVideos()).items;
      setVideos(nextVideos);
      setTasks((await fetchTasks()).items);
      if (selectedVideoId) {
        setSelectedResult(await fetchResults(selectedVideoId));
      }
    };
    tick();
    const timer = window.setInterval(tick, 2000);
    return () => window.clearInterval(timer);
  }, [selectedVideoId]);
}
```

- [ ] **Step 5: Wire uploads and selection to the shared hook**

```tsx
<UploadPanel
  onUpload={async (file, persist) => {
    const uploaded = await uploadVideo(file, persist);
    await createTask(uploaded.video_id);
    await refreshNow();
  }}
/>
```

- [ ] **Step 6: Implement the right-column components**

```tsx
<section className="right-column">
  <PreviewStage video={selectedVideo} task={currentTask} />
  <ResultPanel result={selectedResult} />
</section>
```

- [ ] **Step 7: Run frontend tests and build**

Run: `npm --prefix .\frontend run test -- --run`

Expected: PASS.

Run: `npm --prefix .\frontend run build`

Expected: PASS with updated bundle.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/PreviewStage.tsx frontend/src/components/ResultPanel.tsx frontend/src/hooks/useWorkbenchData.ts frontend/src/api/client.ts frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: wire workbench right column to backend data"
```

If `.git` is absent: record `skip commit: repo has no .git`.

## Task 9: Add Batch Actions, Run Helper, and Full Verification

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/task_queue.py`
- Create: `run_workbench.bat`
- Modify: `test_workbench_backend.py`

- [ ] **Step 1: Write the failing batch-run test**

```python
class WorkbenchBatchTaskTests(unittest.TestCase):
    def test_run_all_enqueues_multiple_videos(self):
        client = TestClient(app)

        response = client.post("/api/tasks/run-all")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["enqueued"], 1)
```

- [ ] **Step 2: Run the batch-run test to verify it fails**

Run: `python -m unittest test_workbench_backend.WorkbenchBatchTaskTests.test_run_all_enqueues_multiple_videos -v`

Expected: FAIL with missing `/api/tasks/run-all`.

- [ ] **Step 3: Implement batch enqueue and convenience launcher**

```python
@app.post("/api/tasks/run-all")
def run_all():
    count = queue_service.enqueue_all_known_videos()
    queue_service.maybe_start_next()
    return {"enqueued": count}
```

```bat
@echo off
start cmd /k "python -m uvicorn backend.app:app --reload"
start cmd /k "npm --prefix frontend run dev"
```

- [ ] **Step 4: Run all Python tests**

Run: `python -m unittest test_workbench_backend.py test_workbench_queue.py -v`

Expected: PASS.

- [ ] **Step 5: Run all frontend checks**

Run: `npm --prefix .\frontend run test -- --run`

Expected: PASS.

Run: `npm --prefix .\frontend run build`

Expected: PASS.

- [ ] **Step 6: Manual smoke verification**

Run:

```bash
python -m uvicorn backend.app:app --reload
npm --prefix .\frontend run dev
```

Verify:

- health badge loads
- existing `videos/` history appears
- existing `output/` results load
- upload panel accepts a file
- single task can be queued
- `跑全部` enqueues multiple videos
- stage progress changes from `ASR` to `剧本整合`
- completed task shows `dialogues / segments / script`

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/task_queue.py run_workbench.bat test_workbench_backend.py
git commit -m "feat: finish short drama workbench first version"
```

If `.git` is absent: record `skip commit: repo has no .git`.
