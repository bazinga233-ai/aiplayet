import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import userEvent from "@testing-library/user-event";

import type { ResultPayload } from "../types";
import { ResultPanel } from "./ResultPanel";

const stylesSource = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

function createPredictorPayload() {
  return {
    version: 2,
    video_id: "video-01",
    video_name: "01",
    task_id: "highlight-01",
    parent_task_id: "generate-01",
    generated_at: "2026-04-09T00:00:00Z",
    model: {
      base_url: "http://example.test/v1",
      model_name: "demo-model",
    },
    summary: "前中段有拉力，但 38s-45s 存在明显下滑风险。",
    breakout_score: 74,
    position_mode: "time" as const,
    emotion_curve: [
      { time: 12, tension: 68, risk: 20 },
      { time: 28, tension: 76, risk: 24 },
      { time: 41, tension: 42, risk: 81 },
    ],
    risk_windows: [
      {
        start: 38,
        end: 45,
        kind: "情绪下滑",
        reason: "信息推进变慢，画面刺激减弱。",
        suggestion: "建议在 40s 前后插入更明确的反转镜头。",
        confidence: 82,
      },
    ],
    opportunity_windows: [
      {
        start: 26,
        end: 31,
        kind: "反转机会",
        reason: "冲突铺垫已经完成，适合提前揭示信息。",
        suggestion: "建议将关键信息揭示前置 2-3 秒。",
        confidence: 78,
      },
    ],
    best_opportunity: {
      start: 38,
      end: 45,
      kind: "关键修正点",
      reason: "这是全片最明显的留存风险段。",
      suggestion: "建议在该区间前后插入高信息密度反转镜头。",
      confidence: 84,
    },
  };
}

function createResult(overrides?: Partial<ResultPayload>) {
  return {
    video: {
      video_id: "video-01",
      video_name: "01",
      video_path: "videos/01.mp4",
      stored_name: "01.mp4",
      display_name: "01.mp4",
      display_stem: "01",
      has_output: true,
      output_ready: true,
      source_type: "catalog",
      asset_type: "video",
    },
    dialogues: [],
    segments: [],
    script: "第一幕：主角登场。\n第二幕：冲突升级。\n第三幕：结尾收束。",
    original_script: null,
    asset_type: "video",
    highlights: null,
    score: null,
    media_url: "/api/media/video-01",
    ...overrides,
  } as ResultPayload;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("keeps result content hidden until a tag is clicked", async () => {
  const user = userEvent.setup();

  render(
    <ResultPanel
      result={createResult({
        highlights: createPredictorPayload(),
        score: {
          version: 1,
          video_id: "video-01",
          video_name: "01",
          task_id: "score-01",
          parent_task_id: "generate-01",
          generated_at: "2026-04-09T00:00:00Z",
          model: {
            base_url: "http://example.test/v1",
            model_name: "demo-model",
          },
          total_score: 72,
          summary: "需要优化。",
          dimensions: [
            {
              key: "video_faithfulness",
              label: "与原视频一致性",
              score: 10,
              max_score: 18,
              reason: "有偏差。",
            },
          ],
        },
      })}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
    />,
  );

  expect(screen.getByText("点击上方标签查看对应结果。")).toBeInTheDocument();
  expect(screen.queryByText("前中段有拉力，但 38s-45s 存在明显下滑风险。")).not.toBeInTheDocument();
  expect(screen.queryByText("需要优化。")).not.toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "评分" }));
  expect(screen.getByText("需要优化。")).toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "爆款预测器" }));
  expect(screen.getByText("前中段有拉力，但 38s-45s 存在明显下滑风险。")).toBeInTheDocument();
});

test("renders script content inside a scrollable viewer with a standalone toolbar panel", async () => {
  const user = userEvent.setup();

  render(
    <ResultPanel
      result={createResult()}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
    />,
  );

  await user.click(screen.getByRole("tab", { name: "剧本" }));

  const scriptViewer = screen.getByTestId("script-viewer");
  const scriptToolbarBoard = screen.getByRole("region", { name: "剧本操作" });
  expect(within(scriptViewer).queryByRole("button", { name: "复制剧本" })).not.toBeInTheDocument();
  expect(within(scriptViewer).queryByRole("button", { name: "导出 TXT" })).not.toBeInTheDocument();
  expect(within(scriptToolbarBoard).getByRole("button", { name: "复制剧本" })).toBeInTheDocument();
  expect(within(scriptToolbarBoard).getByRole("button", { name: "导出 TXT" })).toBeInTheDocument();
  const actionBoard = screen.getByRole("region", { name: "任务操作" });
  const resultDisplaySlot = document.querySelector(".result-display-slot") as HTMLElement | null;
  expect(scriptViewer).toHaveAttribute("data-scrollable", "true");
  expect(scriptViewer.className).toContain("result-scroll-shell-script");
  expect(scriptViewer).toHaveTextContent("第二幕：冲突升级。");
  expect(resultDisplaySlot).not.toBeNull();
  expect(resultDisplaySlot).not.toContainElement(scriptToolbarBoard);
  expect(scriptViewer.compareDocumentPosition(scriptToolbarBoard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(scriptViewer.compareDocumentPosition(actionBoard) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
});

test("pushes the script action board to the bottom edge of the result panel", async () => {
  const user = userEvent.setup();

  render(
    <ResultPanel
      result={createResult()}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
    />,
  );

  await user.click(screen.getByRole("tab", { name: "剧本" }));

  const scriptToolbarBoard = screen.getByRole("region", { name: "剧本操作" });
  expect(scriptToolbarBoard).toBeInTheDocument();
  expect(stylesSource).toMatch(/\.script-action-board\s*\{[^}]*margin-top:\s*auto;/s);
});

test("copies script from the toolbar and shows feedback", async () => {
  const user = userEvent.setup();
  const writeText = vi.fn(async () => {});
  Object.defineProperty(globalThis.navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });

  render(
    <ResultPanel
      result={createResult({
        score: {
          version: 1,
          video_id: "video-01",
          video_name: "01",
          task_id: "score-01",
          parent_task_id: "generate-01",
          generated_at: "2026-04-09T00:00:00Z",
          model: {
            base_url: "http://example.test/v1",
            model_name: "demo-model",
          },
          total_score: 72,
          summary: "需要优化。",
          dimensions: [
            {
              key: "video_faithfulness",
              label: "与原视频一致性",
              score: 10,
              max_score: 18,
              reason: "有偏差。",
            },
          ],
        },
      })}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
    />,
  );

  await user.click(screen.getByRole("tab", { name: "剧本" }));

  expect(screen.getByRole("button", { name: "复制剧本" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "导出 TXT" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "重新优化" })).not.toBeInTheDocument();
  expect(screen.getByText("任务操作")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "复制剧本" }));

  expect(writeText).toHaveBeenCalledWith("第一幕：主角登场。\n第二幕：冲突升级。\n第三幕：结尾收束。");
  expect(screen.getByText("已复制到剪贴板，可直接粘贴使用。")).toBeInTheDocument();
});

test("exports latest script as a named txt file", async () => {
  const user = userEvent.setup();
  const createObjectUrl = vi.fn(() => "blob:script");
  const revokeObjectUrl = vi.fn();
  const click = vi.fn();
  const appendChild = vi.spyOn(document.body, "appendChild");
  const removeChild = vi.spyOn(document.body, "removeChild");
  const originalCreateElement = document.createElement.bind(document);
  const anchor = originalCreateElement("a");
  anchor.click = click;

  vi.stubGlobal(
    "URL",
    Object.assign({}, URL, {
      createObjectURL: createObjectUrl,
      revokeObjectURL: revokeObjectUrl,
    }),
  );
  vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
    if (tagName === "a") {
      return anchor;
    }
    return originalCreateElement(tagName);
  });

  render(
    <ResultPanel
      result={createResult()}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
    />,
  );

  await user.click(screen.getByRole("tab", { name: "剧本" }));
  await user.click(screen.getByRole("button", { name: "导出 TXT" }));

  expect(createObjectUrl).toHaveBeenCalledTimes(1);
  expect(anchor.download).toBe("01_最新优化版剧本.txt");
  expect(anchor.href).toBe("blob:script");
  expect(click).toHaveBeenCalledTimes(1);
  expect(appendChild).toHaveBeenCalledWith(anchor);
  expect(removeChild).toHaveBeenCalledWith(anchor);
  expect(revokeObjectUrl).toHaveBeenCalledWith("blob:script");
});

test("keeps raw result tabs behind advanced info until expanded", async () => {
  const user = userEvent.setup();

  render(
    <ResultPanel
      result={createResult({
        dialogues: [{ text: "你好" }],
        segments: [{ summary: "第一段" }],
        script: "第一幕：主角登场。",
      })}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
    />,
  );

  expect(screen.queryByRole("tab", { name: "对白" })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "分段" })).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "高级信息" }));

  expect(screen.getByRole("tab", { name: "对白" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "分段" })).toBeInTheDocument();
});

test("renders highlight tab with best climax and highlight list", async () => {
  const user = userEvent.setup();

  render(
    <ResultPanel
      result={createResult({
        script: "第一幕：主角登场。",
        highlights: createPredictorPayload(),
      })}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
    />,
  );

  await user.click(screen.getByRole("tab", { name: "爆款预测器" }));

  expect(screen.getByText("爆款指数")).toBeInTheDocument();
  expect(screen.queryByText("情绪张力曲线")).not.toBeInTheDocument();
  expect(screen.getByText("最佳修正点")).toBeInTheDocument();
  expect(screen.getByText("关键修正点")).toBeInTheDocument();
  expect(screen.getByText("信息推进变慢，画面刺激减弱。")).toBeInTheDocument();
  expect(screen.getByText("冲突铺垫已经完成，适合提前揭示信息。")).toBeInTheDocument();
});

test("renders optimize and rescore buttons and triggers callbacks", async () => {
  const user = userEvent.setup();
  const onOptimizeScript = vi.fn(async () => {});
  const onRunScore = vi.fn(async () => {});
  const onRunHighlight = vi.fn(async () => {});

  render(
    <ResultPanel
      result={createResult({
        script: "第一幕：主角登场。",
        highlights: createPredictorPayload(),
        score: {
          version: 1,
          video_id: "video-01",
          video_name: "01",
          task_id: "score-01",
          parent_task_id: "generate-01",
          generated_at: "2026-04-09T00:00:00Z",
          model: {
            base_url: "http://example.test/v1",
            model_name: "demo-model",
          },
          total_score: 72,
          summary: "需要优化。",
          dimensions: [
            {
              key: "video_faithfulness",
              label: "与原视频一致性",
              score: 10,
              max_score: 18,
              reason: "有偏差。",
            },
          ],
        },
      })}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={onRunHighlight}
      onOptimizeScript={onOptimizeScript}
      onRunScore={onRunScore}
      scoreTask={null}
    />,
  );

  expect(screen.getByRole("region", { name: "任务操作" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重新预测" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重新评分" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "优化剧本" })).toBeInTheDocument();
  expect(screen.queryByText("先生成剧本，之后才能评分。")).not.toBeInTheDocument();
  expect(screen.queryByText("剧本完成后才能触发爆款预测。")).not.toBeInTheDocument();
  expect(screen.queryByText("需先完成爆款预测。")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "重新预测" }));
  expect(onRunHighlight).toHaveBeenCalledTimes(1);

  await user.click(screen.getByRole("button", { name: "优化剧本" }));
  expect(onOptimizeScript).toHaveBeenCalledTimes(1);

  await user.click(screen.getByRole("button", { name: "重新评分" }));
  expect(onRunScore).toHaveBeenCalledTimes(1);
});

test("supports switching between latest script and original script", async () => {
  const user = userEvent.setup();

  render(
    <ResultPanel
      result={createResult({
        asset_type: "video",
        original_script: "第一幕：原始剧本。\n第二幕：旧冲突。",
        script: "第一幕：最新优化版。\n第二幕：新冲突。",
      })}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
    />,
  );

  await user.click(screen.getByRole("tab", { name: "剧本" }));

  expect(screen.getByRole("button", { name: "最新优化版" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "原剧本" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "对比" })).not.toBeInTheDocument();
  expect(screen.getByText(/第一幕：最新优化版。/)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "原剧本" }));
  expect(screen.getByText(/第一幕：原始剧本。/)).toBeInTheDocument();
});

test("keeps script version buttons visible and disables original view when original script is missing", async () => {
  const user = userEvent.setup();

  render(
    <ResultPanel
      result={createResult({
        asset_type: "video",
        original_script: null,
        script: "第一幕：只有当前版本。",
      })}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
    />,
  );

  await user.click(screen.getByRole("tab", { name: "剧本" }));

  expect(screen.getByRole("button", { name: "最新优化版" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "原剧本" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "对比" })).not.toBeInTheDocument();
  expect(screen.getByRole("tablist", { name: "剧本版本切换" })).toHaveClass("script-version-row");
  expect(screen.getByText("当前结果缺少原剧本快照，暂时无法查看原剧本。")).toBeInTheDocument();
});

test("keeps display offset at zero when there is no readable result yet", () => {
  const resizeObserverCallbacks: ResizeObserverCallback[] = [];
  const originalMatchMedia = window.matchMedia;
  const previewFrame = document.createElement("div");
  previewFrame.dataset.testid = "preview-frame";
  document.body.appendChild(previewFrame);

  class ResizeObserverMock {
    private readonly callback: ResizeObserverCallback;

    constructor(callback: ResizeObserverCallback) {
      this.callback = callback;
      resizeObserverCallbacks.push(callback);
    }

    observe() {}

    disconnect() {}

    unobserve() {}
  }

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: true,
      media: "(min-width: 1181px)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  const rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.dataset.testid === "preview-frame") {
      return {
        x: 0,
        y: 160,
        width: 320,
        height: 240,
        top: 160,
        left: 0,
        bottom: 400,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    if (this.classList.contains("result-display-slot")) {
      return {
        x: 0,
        y: 240,
        width: 320,
        height: 180,
        top: 240,
        left: 0,
        bottom: 420,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    return {
      x: 0,
      y: 0,
      width: 320,
      height: 180,
      top: 0,
      left: 0,
      bottom: 180,
      right: 320,
      toJSON: () => ({}),
    } as DOMRect;
  });

  try {
    render(
      <ResultPanel
        result={null}
        video={createResult().video}
        highlightTask={null}
        optimizeTask={null}
        onRunHighlight={async () => {}}
        onOptimizeScript={async () => {}}
        onRunScore={async () => {}}
        scoreTask={null}
      />,
    );

    resizeObserverCallbacks.forEach((callback) => callback([], {} as ResizeObserver));
    const resultBody = document.querySelector(".result-body") as HTMLElement | null;
    expect(resultBody).not.toBeNull();
    expect(resultBody?.style.getPropertyValue("--result-display-align-offset")).toBe("0px");
  } finally {
    rectSpy.mockRestore();
    previewFrame.remove();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: originalMatchMedia,
    });
  }
});

test("extends the script viewer down to the toolbar while keeping the toolbar anchored", async () => {
  const user = userEvent.setup();
  const resizeObserverCallbacks: ResizeObserverCallback[] = [];
  const originalMatchMedia = window.matchMedia;
  const originalRequestAnimationFrame = window.requestAnimationFrame;
  const originalCancelAnimationFrame = window.cancelAnimationFrame;
  const previewFrame = document.createElement("div");
  previewFrame.dataset.testid = "preview-frame";
  document.body.appendChild(previewFrame);

  class ResizeObserverMock {
    private readonly callback: ResizeObserverCallback;

    constructor(callback: ResizeObserverCallback) {
      this.callback = callback;
      resizeObserverCallbacks.push(callback);
    }

    observe() {}

    disconnect() {}

    unobserve() {}
  }

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: true,
      media: "(min-width: 1181px)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  Object.defineProperty(window, "requestAnimationFrame", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }),
  });
  Object.defineProperty(window, "cancelAnimationFrame", {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  const rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.dataset.testid === "preview-frame") {
      return {
        x: 0,
        y: 160,
        width: 320,
        height: 320,
        top: 160,
        left: 0,
        bottom: 480,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    if (this.classList.contains("result-display-slot")) {
      return {
        x: 0,
        y: 250,
        width: 320,
        height: 230,
        top: 250,
        left: 0,
        bottom: 480,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    if (this.dataset.testid === "script-viewer") {
      return {
        x: 0,
        y: 310,
        width: 320,
        height: 170,
        top: 310,
        left: 0,
        bottom: 480,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    if (this.classList.contains("script-action-board")) {
      return {
        x: 0,
        y: 560,
        width: 320,
        height: 60,
        top: 560,
        left: 0,
        bottom: 620,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    return {
      x: 0,
      y: 0,
      width: 320,
      height: 180,
      top: 0,
      left: 0,
      bottom: 180,
      right: 320,
      toJSON: () => ({}),
    } as DOMRect;
  });

  try {
    render(
      <ResultPanel
        result={createResult()}
        highlightTask={null}
        optimizeTask={null}
        onRunHighlight={async () => {}}
        onOptimizeScript={async () => {}}
        onRunScore={async () => {}}
        scoreTask={null}
      />,
    );

    await user.click(screen.getByRole("tab", { name: "剧本" }));

    resizeObserverCallbacks.forEach((callback) => callback([], {} as ResizeObserver));
    resizeObserverCallbacks.forEach((callback) => callback([], {} as ResizeObserver));

    const resultBody = document.querySelector(".result-body") as HTMLElement | null;
    expect(resultBody).not.toBeNull();
    expect(resultBody?.style.getPropertyValue("--result-display-align-offset")).toBe("0px");
    expect(resultBody?.style.getPropertyValue("--result-display-slot-height")).toBe("302px");
    expect(resultBody?.style.getPropertyValue("--result-script-viewer-height")).toBe("242px");
  } finally {
    rectSpy.mockRestore();
    previewFrame.remove();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: originalMatchMedia,
    });
    Object.defineProperty(window, "requestAnimationFrame", {
      configurable: true,
      writable: true,
      value: originalRequestAnimationFrame,
    });
    Object.defineProperty(window, "cancelAnimationFrame", {
      configurable: true,
      writable: true,
      value: originalCancelAnimationFrame,
    });
  }
});

test("lets the highlight panel stretch to the result panel bottom on desktop", async () => {
  const user = userEvent.setup();
  const resizeObserverCallbacks: ResizeObserverCallback[] = [];
  const originalMatchMedia = window.matchMedia;
  const originalRequestAnimationFrame = window.requestAnimationFrame;
  const originalCancelAnimationFrame = window.cancelAnimationFrame;
  const previewFrame = document.createElement("div");
  previewFrame.dataset.testid = "preview-frame";
  document.body.appendChild(previewFrame);

  class ResizeObserverMock {
    private readonly callback: ResizeObserverCallback;

    constructor(callback: ResizeObserverCallback) {
      this.callback = callback;
      resizeObserverCallbacks.push(callback);
    }

    observe() {}

    disconnect() {}

    unobserve() {}
  }

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: true,
      media: "(min-width: 1181px)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  Object.defineProperty(window, "requestAnimationFrame", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }),
  });
  Object.defineProperty(window, "cancelAnimationFrame", {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  const rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.dataset.testid === "preview-frame") {
      return {
        x: 0,
        y: 160,
        width: 320,
        height: 320,
        top: 160,
        left: 0,
        bottom: 480,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    if (this.classList.contains("result-display-slot")) {
      return {
        x: 0,
        y: 250,
        width: 320,
        height: 180,
        top: 250,
        left: 0,
        bottom: 430,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    return {
      x: 0,
      y: 0,
      width: 320,
      height: 180,
      top: 0,
      left: 0,
      bottom: 180,
      right: 320,
      toJSON: () => ({}),
    } as DOMRect;
  });

  try {
    render(
      <ResultPanel
        result={createResult({
          highlights: createPredictorPayload(),
      })}
      highlightTask={null}
      optimizeTask={null}
      onRunHighlight={async () => {}}
      onOptimizeScript={async () => {}}
      onRunScore={async () => {}}
      scoreTask={null}
      />,
    );

    await user.click(screen.getByRole("tab", { name: "爆款预测器" }));

    resizeObserverCallbacks.forEach((callback) => callback([], {} as ResizeObserver));
    resizeObserverCallbacks.forEach((callback) => callback([], {} as ResizeObserver));

    const resultBody = document.querySelector(".result-body") as HTMLElement | null;
    expect(resultBody).not.toBeNull();
    expect(resultBody?.style.getPropertyValue("--result-display-slot-height")).toBe("");
    expect(resultBody?.style.getPropertyValue("--result-script-viewer-height")).toBe("");
  } finally {
    rectSpy.mockRestore();
    previewFrame.remove();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: originalMatchMedia,
    });
    Object.defineProperty(window, "requestAnimationFrame", {
      configurable: true,
      writable: true,
      value: originalRequestAnimationFrame,
    });
    Object.defineProperty(window, "cancelAnimationFrame", {
      configurable: true,
      writable: true,
      value: originalCancelAnimationFrame,
    });
  }
});

test("lets the score panel stretch to the result panel bottom on desktop", async () => {
  const user = userEvent.setup();
  const resizeObserverCallbacks: ResizeObserverCallback[] = [];
  const originalMatchMedia = window.matchMedia;
  const originalRequestAnimationFrame = window.requestAnimationFrame;
  const originalCancelAnimationFrame = window.cancelAnimationFrame;
  const previewFrame = document.createElement("div");
  previewFrame.dataset.testid = "preview-frame";
  document.body.appendChild(previewFrame);

  class ResizeObserverMock {
    private readonly callback: ResizeObserverCallback;

    constructor(callback: ResizeObserverCallback) {
      this.callback = callback;
      resizeObserverCallbacks.push(callback);
    }

    observe() {}

    disconnect() {}

    unobserve() {}
  }

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: true,
      media: "(min-width: 1181px)",
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  Object.defineProperty(window, "requestAnimationFrame", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    }),
  });
  Object.defineProperty(window, "cancelAnimationFrame", {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  const rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.dataset.testid === "preview-frame") {
      return {
        x: 0,
        y: 160,
        width: 320,
        height: 320,
        top: 160,
        left: 0,
        bottom: 480,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    if (this.classList.contains("result-display-slot")) {
      return {
        x: 0,
        y: 250,
        width: 320,
        height: 180,
        top: 250,
        left: 0,
        bottom: 430,
        right: 320,
        toJSON: () => ({}),
      } as DOMRect;
    }

    return {
      x: 0,
      y: 0,
      width: 320,
      height: 180,
      top: 0,
      left: 0,
      bottom: 180,
      right: 320,
      toJSON: () => ({}),
    } as DOMRect;
  });

  try {
    render(
      <ResultPanel
        result={createResult({
          score: {
            version: 1,
            video_id: "video-01",
            video_name: "01",
            task_id: "score-01",
            parent_task_id: "generate-01",
            generated_at: "2026-04-09T00:00:00Z",
            model: {
              base_url: "http://example.test/v1",
              model_name: "demo-model",
            },
            total_score: 72,
            summary: "需要优化。",
            dimensions: [
              {
                key: "video_faithfulness",
                label: "与原视频一致性",
                score: 10,
                max_score: 18,
                reason: "有偏差。",
              },
            ],
          },
        })}
        highlightTask={null}
        optimizeTask={null}
        onRunHighlight={async () => {}}
        onOptimizeScript={async () => {}}
        onRunScore={async () => {}}
        scoreTask={null}
      />,
    );

    await user.click(screen.getByRole("tab", { name: "评分" }));

    resizeObserverCallbacks.forEach((callback) => callback([], {} as ResizeObserver));
    resizeObserverCallbacks.forEach((callback) => callback([], {} as ResizeObserver));

    const resultBody = document.querySelector(".result-body") as HTMLElement | null;
    expect(resultBody).not.toBeNull();
    expect(resultBody?.style.getPropertyValue("--result-display-slot-height")).toBe("");
    expect(resultBody?.style.getPropertyValue("--result-script-viewer-height")).toBe("");
  } finally {
    rectSpy.mockRestore();
    previewFrame.remove();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: originalMatchMedia,
    });
    Object.defineProperty(window, "requestAnimationFrame", {
      configurable: true,
      writable: true,
      value: originalRequestAnimationFrame,
    });
    Object.defineProperty(window, "cancelAnimationFrame", {
      configurable: true,
      writable: true,
      value: originalCancelAnimationFrame,
    });
  }
});
