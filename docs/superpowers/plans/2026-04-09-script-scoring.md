# Script Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an automatically triggered independent scoring task that evaluates generated scripts with the remote multimodal model and shows the saved score in the workbench UI.

**Architecture:** Keep `video2script.py` focused on generation. Add a backend scoring pipeline that runs as a separate `score` task after a successful `generate` task, saves `score.json` in the output directory, and extends `/api/results/{video_id}` plus the existing result panel to expose scoring state and content.

**Tech Stack:** Python 3.13, FastAPI, unittest, React, TypeScript, Vitest

---

### Task 1: Define task and score data contracts

**Files:**
- Create: `F:\local_code\novalai\backend\scoring.py`
- Modify: `F:\local_code\novalai\backend\models.py`
- Modify: `F:\local_code\novalai\frontend\src\types.ts`

- [ ] Step 1: Add failing backend and frontend expectations for score/task fields
- [ ] Step 2: Run focused tests to verify missing fields fail
- [ ] Step 3: Add minimal task and score dataclasses/types
- [ ] Step 4: Re-run focused tests

### Task 2: Add scoring task execution and persistence

**Files:**
- Create: `F:\local_code\novalai\backend\llm_client.py`
- Create: `F:\local_code\novalai\backend\scoring.py`
- Modify: `F:\local_code\novalai\backend\task_queue.py`
- Modify: `F:\local_code\novalai\backend\log_parser.py`
- Modify: `F:\local_code\novalai\backend\config.py`

- [ ] Step 1: Write failing queue/scoring tests for auto-enqueue and stage handling
- [ ] Step 2: Run the targeted backend tests and confirm they fail for the right reason
- [ ] Step 3: Implement shared LLM client and score task runner
- [ ] Step 4: Update queue orchestration to auto-create score tasks after generate success
- [ ] Step 5: Re-run targeted backend tests

### Task 3: Extend result aggregation and API responses

**Files:**
- Modify: `F:\local_code\novalai\backend\app.py`
- Modify: `F:\local_code\novalai\backend\catalog.py`
- Modify: `F:\local_code\novalai\test_workbench_backend.py`

- [ ] Step 1: Write failing API tests for `score` in `/api/results` and task metadata in `/api/tasks`
- [ ] Step 2: Run the targeted API tests and verify failure
- [ ] Step 3: Implement score loading and response serialization
- [ ] Step 4: Re-run the targeted API tests

### Task 4: Show score content and state in the frontend

**Files:**
- Modify: `F:\local_code\novalai\frontend\src\api\client.ts`
- Modify: `F:\local_code\novalai\frontend\src\hooks\useWorkbenchData.ts`
- Modify: `F:\local_code\novalai\frontend\src\components\ResultPanel.tsx`
- Modify: `F:\local_code\novalai\frontend\src\components\QueuePanel.tsx`
- Modify: `F:\local_code\novalai\frontend\src\components\TaskDrawer.tsx`
- Modify: `F:\local_code\novalai\frontend\src\components\PreviewStage.tsx`
- Modify: `F:\local_code\novalai\frontend\src\styles.css`
- Modify: `F:\local_code\novalai\frontend\src\App.test.tsx`
- Modify: `F:\local_code\novalai\frontend\src\components\TaskDrawer.test.tsx`

- [ ] Step 1: Write failing frontend tests for the score tab and scoring task labels
- [ ] Step 2: Run the targeted frontend tests and confirm failure
- [ ] Step 3: Implement score tab rendering and scoring-state labels
- [ ] Step 4: Re-run the targeted frontend tests

### Task 5: Verify the integrated flow

**Files:**
- Test only

- [ ] Step 1: Run backend tests covering queue plus API scoring behavior
- [ ] Step 2: Run frontend tests covering score rendering
- [ ] Step 3: Review resulting output for any remaining mismatches
