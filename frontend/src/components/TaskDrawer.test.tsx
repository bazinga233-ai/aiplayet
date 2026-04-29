import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import userEvent from "@testing-library/user-event";

import { TaskDrawer } from "./TaskDrawer";

afterEach(() => {
  cleanup();
});

test("shows stage rows without requiring expansion", () => {
  render(
    <TaskDrawer
      task={{
        task_id: "task-1",
        video_id: "video-1",
        video_name: "demo",
        video_path: "demo.mp4",
        source_type: "catalog",
        task_type: "score",
        parent_task_id: "task-parent",
        status: "running",
        stage: "scoring",
        stage_progress: 0.5,
        created_at: "2026-04-07T00:00:00Z",
        started_at: "2026-04-07T00:00:01Z",
        finished_at: null,
        error_message: null,
        logs_tail: [],
        stage_current: 1,
        stage_total: 2,
      }}
    />,
  );

  expect(screen.getByText("当前任务状态")).toBeInTheDocument();
  expect(screen.getByText("剧本评分")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "查看日志" })).toBeInTheDocument();
  expect(screen.queryByText("最近日志")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /当前任务状态/i })).not.toBeInTheDocument();
});

test("reveals logs only after explicitly opening them", async () => {
  const user = userEvent.setup();

  render(
    <TaskDrawer
      task={
        {
          task_id: "task-2",
          video_id: "video-1",
          video_name: "demo",
          video_path: "demo.mp4",
          source_type: "catalog",
          task_type: "highlight",
          parent_task_id: "task-parent",
          status: "running",
          stage: "highlighting",
          stage_progress: 0.5,
          created_at: "2026-04-09T00:00:00Z",
          started_at: "2026-04-09T00:00:01Z",
          finished_at: null,
          error_message: null,
          logs_tail: ["[Step Highlight] 正在进行爆款预测"],
          stage_current: 1,
          stage_total: 2,
        } as never
      }
    />,
  );

  expect(screen.queryByText("最近日志")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "查看日志" }));
  expect(screen.getByText("最近日志")).toBeInTheDocument();
  expect(screen.getByText("[Step Highlight] 正在进行爆款预测")).toBeInTheDocument();
});

test("shows highlight task stages", () => {
  render(
    <TaskDrawer
      task={
        {
          task_id: "task-2",
          video_id: "video-1",
          video_name: "demo",
          video_path: "demo.mp4",
          source_type: "catalog",
          task_type: "highlight",
          parent_task_id: "task-parent",
          status: "running",
          stage: "highlighting",
          stage_progress: 0.5,
          created_at: "2026-04-09T00:00:00Z",
          started_at: "2026-04-09T00:00:01Z",
          finished_at: null,
          error_message: null,
          logs_tail: ["[Step Highlight] 正在进行爆款预测"],
          stage_current: 1,
          stage_total: 2,
        } as never
      }
    />,
  );

  expect(screen.getByText("爆款预测")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "查看日志" })).toBeInTheDocument();
});

test("shows optimize task stages", () => {
  render(
    <TaskDrawer
      task={
        {
          task_id: "task-3",
          video_id: "video-1",
          video_name: "demo",
          video_path: "demo.mp4",
          source_type: "catalog",
          task_type: "optimize",
          parent_task_id: "score-task",
          status: "running",
          stage: "optimizing",
          stage_progress: 0.5,
          created_at: "2026-04-09T00:00:00Z",
          started_at: "2026-04-09T00:00:01Z",
          finished_at: null,
          error_message: null,
          logs_tail: ["[Step Optimize] 正在根据评分优化剧本"],
          stage_current: null,
          stage_total: null,
        } as never
      }
    />,
  );

  expect(screen.getByText("剧本优化")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "查看日志" })).toBeInTheDocument();
});
