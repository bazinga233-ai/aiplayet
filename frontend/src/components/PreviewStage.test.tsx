import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { ResultPayload, VideoItem } from "../types";
import { PreviewStage } from "./PreviewStage";

function createScriptVideo(): VideoItem {
  return {
    video_id: "script-01",
    video_name: "script-01",
    video_path: "scripts/script-01.txt",
    stored_name: "script-01.txt",
    display_name: "script-01.txt",
    display_stem: "script-01",
    has_output: true,
    output_ready: true,
    source_type: "catalog",
    asset_type: "script",
  };
}

function createScriptResult(overrides?: Partial<ResultPayload>): ResultPayload {
  return {
    video: createScriptVideo(),
    dialogues: [],
    segments: [],
    script: "第一幕：最新优化版。\n第二幕：新冲突。",
    original_script: "第一幕：原剧本。\n第二幕：旧冲突。",
    asset_type: "script",
    highlights: null,
    score: null,
    media_url: null,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("renders original script in the middle preview for script assets", () => {
  render(<PreviewStage video={createScriptVideo()} result={createScriptResult()} task={null} onQueue={async () => {}} />);

  const previewScriptShell = screen.getByTestId("preview-script-shell");
  expect(screen.getByText("中间主舞台显示原剧本，右侧剧本标签可切到最新优化版或原剧本。")).toBeInTheDocument();
  expect(screen.getByText("原剧本预览")).toBeInTheDocument();
  expect(previewScriptShell).toHaveTextContent("第一幕：原剧本。");
  expect(previewScriptShell).toHaveTextContent("第二幕：旧冲突。");
  expect(previewScriptShell).toHaveAttribute("data-scrollable", "true");
});

test("falls back to latest script when original script is unavailable", () => {
  render(
    <PreviewStage
      video={createScriptVideo()}
      result={createScriptResult({ original_script: null })}
      task={null}
      onQueue={async () => {}}
    />,
  );

  const previewScriptShell = screen.getByTestId("preview-script-shell");
  expect(screen.getByText("当前剧本预览")).toBeInTheDocument();
  expect(previewScriptShell).toHaveTextContent("第一幕：最新优化版。");
  expect(previewScriptShell).toHaveTextContent("第二幕：新冲突。");
});
