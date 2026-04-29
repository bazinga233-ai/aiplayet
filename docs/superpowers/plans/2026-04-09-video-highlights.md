# Video Highlights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an automatic `highlight` task that identifies structured video highlights and exposes them in the workbench UI.

**Architecture:** Reuse the existing post-generate pipeline and output directory structure. Add a dedicated backend highlight module plus task type, persist `highlights.json`, expose it through `/api/results`, and render it in a new frontend result tab.

**Tech Stack:** FastAPI, Python dataclasses, existing OpenAI-compatible multimodal backend, React, TypeScript, Vitest, unittest

---

### Task 1: Add Failing Backend Tests For Highlight Flow

**Files:**
- Modify: `F:\local_code\novalai\test_workbench_queue.py`
- Modify: `F:\local_code\novalai\test_workbench_backend.py`

- [ ] **Step 1: Write the failing queue test**

Add a test asserting that a completed `generate` task enqueues both `highlight` and `score`, in that order.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest test_workbench_queue.py`
Expected: FAIL because `highlight` task type does not exist yet.

- [ ] **Step 3: Write the failing API result test**

Add a test asserting that `/api/results/{video_id}` returns a `highlights` field and can read a saved `highlights.json`.

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m unittest test_workbench_backend.py`
Expected: FAIL because highlights are not yet loaded.

### Task 2: Add Failing Frontend Test For Highlight Tab

**Files:**
- Modify: `F:\local_code\novalai\frontend\src\App.test.tsx`
- Modify: `F:\local_code\novalai\frontend\src\components\ResultPanel.test.tsx`

- [ ] **Step 1: Write the failing result rendering test**

Add a test asserting that `高光` tab exists and renders `最佳高潮点` plus the highlight list.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test -- --run src/App.test.tsx src/components/ResultPanel.test.tsx`
Expected: FAIL because the tab and payload types do not exist.

### Task 3: Implement Backend Highlight Models And Persistence

**Files:**
- Modify: `F:\local_code\novalai\backend\models.py`
- Create: `F:\local_code\novalai\backend\highlights.py`
- Modify: `F:\local_code\novalai\backend\app.py`

- [ ] **Step 1: Add highlight payload dataclasses**
- [ ] **Step 2: Add load/validate/persist helpers in `backend/highlights.py`**
- [ ] **Step 3: Expose `highlights` in `/api/results/{video_id}`**
- [ ] **Step 4: Run backend tests**

Run: `python -m unittest test_workbench_backend.py`

### Task 4: Implement Highlight Task Execution

**Files:**
- Modify: `F:\local_code\novalai\backend\runner.py`
- Modify: `F:\local_code\novalai\backend\task_queue.py`
- Modify: `F:\local_code\novalai\backend\log_parser.py`

- [ ] **Step 1: Add `highlight` task type and `highlighting` stage support**
- [ ] **Step 2: Insert `highlight` and `score` follow-up tasks after successful generate**
- [ ] **Step 3: Implement highlight runner call and log lines**
- [ ] **Step 4: Run queue tests**

Run: `python -m unittest test_workbench_queue.py test_workbench_runner.py`

### Task 5: Implement Highlight Recognition Logic

**Files:**
- Create: `F:\local_code\novalai\backend\highlights.py`
- Reuse patterns from: `F:\local_code\novalai\backend\scoring.py`

- [ ] **Step 1: Implement segment-level candidate identification with multimodal input**
- [ ] **Step 2: Implement candidate merge/finalization call**
- [ ] **Step 3: Validate output shape and best climax overlap**
- [ ] **Step 4: Add targeted backend tests**

Run: `python -m unittest test_workbench_highlights.py`
Expected: PASS after implementation

### Task 6: Implement Frontend Highlight Types And UI

**Files:**
- Modify: `F:\local_code\novalai\frontend\src\types.ts`
- Modify: `F:\local_code\novalai\frontend\src\components\ResultPanel.tsx`
- Modify: `F:\local_code\novalai\frontend\src\components\TaskDrawer.tsx`
- Modify: `F:\local_code\novalai\frontend\src\components\QueuePanel.tsx`
- Modify: `F:\local_code\novalai\frontend\src\App.test.tsx`
- Modify: `F:\local_code\novalai\frontend\src\components\ResultPanel.test.tsx`

- [ ] **Step 1: Add `HighlightPayload` and `highlight` task/stage types**
- [ ] **Step 2: Add `高光` tab and render cards**
- [ ] **Step 3: Add task and queue labels for highlight jobs**
- [ ] **Step 4: Run frontend tests**

Run: `npm run test -- --run src/App.test.tsx src/components/TaskDrawer.test.tsx src/components/ResultPanel.test.tsx`

### Task 7: Final Verification

**Files:**
- Verify affected files above

- [ ] **Step 1: Run backend targeted verification**

Run: `python -m unittest test_workbench_queue.py test_workbench_runner.py test_workbench_backend.py test_workbench_scoring.py`

- [ ] **Step 2: Run frontend targeted verification**

Run: `npm run test -- --run src/App.test.tsx src/components/TaskDrawer.test.tsx src/components/ResultPanel.test.tsx`

- [ ] **Step 3: Run production build**

Run: `npm run build`
