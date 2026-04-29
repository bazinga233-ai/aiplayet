# Script Optimize + Manual Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual `score` trigger and a new independent `optimize` task that rewrites the current `script.txt` using the score reasons from `与原视频一致性 / 信息完整性 / 对白`.

**Architecture:** Keep `generate`, `highlight`, `score`, and `optimize` as separate queue task types. `generate` still auto-enqueues `highlight`, but `score` becomes button-triggered. `optimize` reads current video/dialogues/segments/script/score, asks the remote model for a full rewritten script, overwrites `script.txt`, and clears stale `score.json`.

**Tech Stack:** FastAPI, Python dataclasses, existing queue runner, React + TypeScript + Vitest.

---

### Task 1: Backend Task Types And Queue

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/task_queue.py`
- Modify: `backend/log_parser.py`
- Test: `test_workbench_queue.py`

- [ ] Add failing tests for `optimize` task type, `optimizing` stage parsing, and `generate` no longer auto-enqueueing `score`
- [ ] Run the targeted backend tests and confirm failure
- [ ] Add `TASK_TYPE_OPTIMIZE` and queue helpers for manual `score` / `optimize`
- [ ] Update progress parsing for optimize logs
- [ ] Re-run targeted queue tests until green

### Task 2: Backend Optimize Execution And APIs

**Files:**
- Create: `backend/optimization.py`
- Modify: `backend/runner.py`
- Modify: `backend/app.py`
- Test: `test_workbench_backend.py`
- Test: `test_workbench_runner.py`

- [ ] Add failing tests for manual score endpoint, optimize endpoint, and optimize overwrite behavior
- [ ] Run the targeted backend tests and confirm failure
- [ ] Implement optimize prompt/execution/persistence and wire it into runner + API
- [ ] Clear stale `score.json` after optimize success
- [ ] Re-run targeted backend tests until green

### Task 3: Frontend Buttons And Task Visibility

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useWorkbenchData.ts`
- Modify: `frontend/src/components/ResultPanel.tsx`
- Modify: `frontend/src/components/TaskDrawer.tsx`
- Modify: `frontend/src/components/QueuePanel.tsx`
- Modify: `frontend/src/components/PreviewStage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/components/ResultPanel.test.tsx`
- Test: `frontend/src/App.test.tsx`
- Test: `frontend/src/components/TaskDrawer.test.tsx`

- [ ] Add failing frontend tests for `重新评分` and `优化剧本`
- [ ] Run the targeted frontend tests and confirm failure
- [ ] Add manual score / optimize client calls and surface latest optimize task state
- [ ] Render buttons, loading/disabled states, and optimize task labels
- [ ] Re-run targeted frontend tests until green

### Task 4: Final Verification

**Files:**
- Test only

- [ ] Run targeted backend suite for queue, runner, app, scoring, optimize
- [ ] Run frontend Vitest suite
- [ ] Run frontend build
- [ ] Report any residual risks, especially stale artifacts and unrelated Windows delete failures
