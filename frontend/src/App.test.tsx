import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import userEvent from "@testing-library/user-event";

import App from "./App";

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

function createJsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function createDomRect(height: number): DOMRect {
  return {
    x: 0,
    y: 0,
    width: 0,
    height,
    top: 0,
    left: 0,
    bottom: height,
    right: 0,
    toJSON: () => ({}),
  } as DOMRect;
}

function setViewportSize(width: number, height: number) {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: width,
  });
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    writable: true,
    value: height,
  });
}

function installFetchMock() {
  const state = {
    hasVideo: true,
    hasOutput: true,
  };

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";

    if (url.endsWith("/api/health")) {
      return createJsonResponse({
        backend: "ok",
        paths: {
          videos: { path: "F:/videos", exists: true },
          output: { path: "F:/output", exists: true },
          tmp_uploads: { path: "F:/tmp_uploads", exists: true },
        },
      });
    }

    if (url.endsWith("/api/videos")) {
      return createJsonResponse({
        items: state.hasVideo
          ? [
              {
                video_id: "video-01",
                video_name: "01",
                video_path: "videos/01.mp4",
                stored_name: "01.mp4",
                display_name: "01.mp4",
                display_stem: "01",
                has_output: state.hasOutput,
                output_ready: state.hasOutput,
                source_type: "catalog",
                asset_type: "video",
              },
            ]
          : [],
      });
    }

    if (url.endsWith("/api/tasks")) {
      return createJsonResponse({
        items: [
          {
            task_id: "task-01",
            video_id: "video-01",
            video_name: "01",
            video_path: "videos/01.mp4",
            source_type: "catalog",
            task_type: "generate",
            parent_task_id: null,
            status: "completed",
            stage: "done",
            stage_progress: 1,
            created_at: "2026-04-07T00:00:00Z",
            started_at: "2026-04-07T00:00:01Z",
            finished_at: "2026-04-07T00:00:10Z",
            error_message: null,
            logs_tail: ["剧本已保存: output/01/script.txt"],
            stage_current: null,
            stage_total: null,
          },
          {
            task_id: "task-02",
            video_id: "video-01",
            video_name: "01",
            video_path: "videos/01.mp4",
            source_type: "catalog",
            task_type: "score",
            parent_task_id: "task-01",
            status: "completed",
            stage: "done",
            stage_progress: 1,
            created_at: "2026-04-07T00:00:11Z",
            started_at: "2026-04-07T00:00:12Z",
            finished_at: "2026-04-07T00:00:15Z",
            error_message: null,
            logs_tail: ["评分已保存: output/01/score.json"],
            stage_current: null,
            stage_total: null,
          },
        ],
      });
    }

    if (url.endsWith("/api/tasks/video-01/score") && method === "POST") {
      return createJsonResponse({
        task_id: "task-score-manual",
        video_id: "video-01",
        video_name: "01",
        video_path: "videos/01.mp4",
        source_type: "catalog",
        task_type: "score",
        parent_task_id: null,
        status: "queued",
        stage: "queued",
        stage_progress: 0,
        created_at: "2026-04-07T00:01:00Z",
        started_at: null,
        finished_at: null,
        error_message: null,
        logs_tail: [],
        stage_current: null,
        stage_total: null,
      });
    }

    if (url.endsWith("/api/tasks/video-01/highlight") && method === "POST") {
      return createJsonResponse({
        task_id: "task-highlight-manual",
        video_id: "video-01",
        video_name: "01",
        video_path: "videos/01.mp4",
        source_type: "catalog",
        task_type: "highlight",
        parent_task_id: "task-01",
        status: "queued",
        stage: "queued",
        stage_progress: 0,
        created_at: "2026-04-07T00:01:30Z",
        started_at: null,
        finished_at: null,
        error_message: null,
        logs_tail: [],
        stage_current: null,
        stage_total: null,
      });
    }

    if (url.endsWith("/api/tasks/video-01/optimize") && method === "POST") {
      return createJsonResponse({
        task_id: "task-optimize-manual",
        video_id: "video-01",
        video_name: "01",
        video_path: "videos/01.mp4",
        source_type: "catalog",
        task_type: "optimize",
        parent_task_id: "task-02",
        status: "queued",
        stage: "queued",
        stage_progress: 0,
        created_at: "2026-04-07T00:02:00Z",
        started_at: null,
        finished_at: null,
        error_message: null,
        logs_tail: [],
        stage_current: null,
        stage_total: null,
      });
    }

    if (url.endsWith("/api/results/video-01") && method === "DELETE") {
      state.hasOutput = false;
      return createJsonResponse({
        deleted: "results",
        video_id: "video-01",
        video_name: "01",
      });
    }

    if (url.endsWith("/api/results/video-01")) {
      if (!state.hasVideo || !state.hasOutput) {
        return new Response("results not ready", { status: 409 });
      }

      return createJsonResponse({
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
        dialogues: [{ text: "你好" }],
        segments: [{ summary: "第一段" }],
        script: "第一幕：主角登场。",
        original_script: null,
        asset_type: "video",
        highlights: createPredictorPayload(),
        score: {
          version: 1,
          video_id: "video-01",
          video_name: "01",
          task_id: "task-02",
          parent_task_id: "task-01",
          generated_at: "2026-04-07T00:00:15Z",
          model: {
            base_url: "http://example.test/v1",
            model_name: "demo-model",
          },
          total_score: 82,
          summary: "整体完成度较好。",
          dimensions: [
            {
              key: "character",
              label: "人物",
              score: 7,
              max_score: 8,
              reason: "人物动机清楚。",
            },
          ],
        },
        media_url: "/api/media/video-01",
      });
    }

    if (url.endsWith("/api/videos/video-01") && method === "DELETE") {
      state.hasVideo = false;
      state.hasOutput = false;
      return createJsonResponse({
        deleted: "video",
        video_id: "video-01",
        video_name: "01",
      });
    }

    return new Response("not found", { status: 404 });
  });

  vi.stubGlobal("fetch", fetchMock);
}

describe("App", () => {
  beforeEach(() => {
    setViewportSize(1600, 960);
    installFetchMock();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  test("renders the dual-column workbench shell", async () => {
    const { container } = render(<App />);

    expect(screen.getByText("短剧反推与情绪预测工作台")).toBeInTheDocument();
    expect(screen.getByText("新建任务")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择视频" })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("01").length).toBeGreaterThan(0);
    });
    const appShell = container.firstElementChild as HTMLElement;
    expect(appShell).toHaveAttribute("data-scroll-mode", "page");
    expect(screen.getByRole("button", { name: "处理当前视频" })).toBeInTheDocument();
  });

  test("shows result tabs for the selected video", async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("剧本");
    expect(await screen.findByRole("region", { name: "任务操作" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新预测" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "剧本" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "爆款预测器" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "评分" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "对白" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "分段" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "高级信息" }));
    expect(screen.getByRole("tab", { name: "对白" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "分段" })).toBeInTheDocument();
  });

  test("renders saved score content in the score tab", async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("评分");
    await user.click(screen.getByRole("tab", { name: "评分" }));

    await screen.findAllByText(/82\s*\/\s*100/);
    expect(screen.getAllByText(/82\s*\/\s*100/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("整体完成度较好。").length).toBeGreaterThan(0);
    expect(screen.getByText("人物")).toBeInTheDocument();
    expect(screen.getByText("7 / 8")).toBeInTheDocument();
  });

  test("clicking rerun score triggers the manual score endpoint", async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("region", { name: "任务操作" });
    await user.click(screen.getByRole("button", { name: "重新评分" }));

    expect(fetch).toHaveBeenCalledWith("/api/tasks/video-01/score", expect.objectContaining({ method: "POST" }));
  });

  test("clicking rerun highlight triggers the manual highlight endpoint", async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("region", { name: "任务操作" });
    await user.click(screen.getByRole("button", { name: "重新预测" }));

    expect(fetch).toHaveBeenCalledWith("/api/tasks/video-01/highlight", expect.objectContaining({ method: "POST" }));
  });

  test("clicking optimize script triggers the optimize endpoint", async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("region", { name: "任务操作" });
    await screen.findByRole("button", { name: "优化剧本" });
    await user.click(screen.getByRole("button", { name: "优化剧本" }));

    expect(fetch).toHaveBeenCalledWith("/api/tasks/video-01/optimize", expect.objectContaining({ method: "POST" }));
  });

  test("renders three evenly filled panels with a full-width stage viewport", async () => {
    const { container } = render(<App />);

    await screen.findByRole("button", { name: "处理当前视频" });

    const dashboardLayout = container.querySelector(".dashboard-layout");
    const stageColumn = screen.getByTestId("stage-column");
    const resultColumn = screen.getByTestId("result-column");
    const previewFrame = screen.getByTestId("preview-frame");
    const previewViewport = screen.getByTestId("preview-viewport");
    const topBar = screen.getByRole("banner");

    expect(dashboardLayout).not.toBeNull();
    expect(dashboardLayout).toContainElement(stageColumn);
    expect(dashboardLayout).toContainElement(resultColumn);
    expect(within(stageColumn).getByText("01")).toBeInTheDocument();
    expect(within(resultColumn).getByText("对白 / 分段 / 剧本 / 爆款预测器 / 评分")).toBeInTheDocument();
    expect(previewFrame).toHaveAttribute("data-height-mode", "viewport-compact");
    expect(previewViewport).toHaveAttribute("data-layout", "fill");
    expect(topBar).toHaveAttribute("data-density", "adaptive");
  });

  test("applies smaller desktop scale variables on lower-resolution displays", async () => {
    setViewportSize(1366, 768);

    const { container } = render(<App />);

    await screen.findByRole("button", { name: "处理当前视频" });

    const appShell = container.firstElementChild as HTMLElement;
    expect(appShell.classList.contains("app-shell")).toBe(true);

    const uiScale = Number.parseFloat(appShell.style.getPropertyValue("--ui-scale"));
    const leftColumnMin = Number.parseFloat(appShell.style.getPropertyValue("--left-column-min"));
    const resultColumnMin = Number.parseFloat(appShell.style.getPropertyValue("--result-column-min"));
    const resultActionCardMin = Number.parseFloat(appShell.style.getPropertyValue("--result-action-card-min"));
    const previewHeight = Number.parseFloat(appShell.style.getPropertyValue("--preview-frame-height"));

    expect(uiScale).toBeGreaterThan(0);
    expect(uiScale).toBeLessThan(1);
    expect(leftColumnMin).toBeGreaterThan(0);
    expect(leftColumnMin).toBeLessThan(resultColumnMin);
    expect(resultActionCardMin).toBeGreaterThan(0);
    expect(previewHeight).toBeGreaterThan(0);
    expect(previewHeight).toBeLessThan(560);
  });

  test("updates scale variables when the desktop viewport becomes larger", async () => {
    setViewportSize(1366, 768);

    const { container } = render(<App />);

    await screen.findByRole("button", { name: "处理当前视频" });

    const appShell = container.firstElementChild as HTMLElement;
    const compactScale = Number.parseFloat(appShell.style.getPropertyValue("--ui-scale"));
    const compactPreviewHeight = Number.parseFloat(appShell.style.getPropertyValue("--preview-frame-height"));

    setViewportSize(1920, 1080);
    window.dispatchEvent(new Event("resize"));

    await waitFor(() => {
      const expandedScale = Number.parseFloat(appShell.style.getPropertyValue("--ui-scale"));
      expect(expandedScale).toBeGreaterThan(compactScale);
    });

    const expandedScale = Number.parseFloat(appShell.style.getPropertyValue("--ui-scale"));
    const expandedPreviewHeight = Number.parseFloat(appShell.style.getPropertyValue("--preview-frame-height"));

    expect(expandedScale).toBeGreaterThan(compactScale);
    expect(expandedPreviewHeight).toBeGreaterThan(compactPreviewHeight);
  });

  test("deletes generated results and refreshes the selected video state", async () => {
    const user = userEvent.setup();
    render(<App />);

    const deleteResultsButton = await screen.findByRole("button", { name: "删结果" });
    await user.click(deleteResultsButton);

    await waitFor(() => {
      expect(screen.getByText("尚无可读结果，任务完成后这里会显示对白、分段和剧本。")).toBeInTheDocument();
    });
    expect(screen.getByText("尚未生成")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "任务操作" })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/results/video-01", expect.objectContaining({ method: "DELETE" }));
  });

  test("deletes the original video after confirmation and clears the right side", async () => {
    const user = userEvent.setup();
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<App />);

    const deleteVideoButton = await screen.findByRole("button", { name: "全删" });
    await user.click(deleteVideoButton);

    await waitFor(() => {
      expect(screen.getByText("选择一个素材查看详情")).toBeInTheDocument();
    });
    expect(screen.getByText("先在左侧选择素材，主舞台会切到所选内容。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "删结果" })).not.toBeInTheDocument();
    expect(confirmMock).toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith("/api/videos/video-01", expect.objectContaining({ method: "DELETE" }));
  });

  test("keeps current task expanded while queue history can be collapsed", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect((await screen.findAllByText("剧本评分")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "查看日志" })).toBeInTheDocument();
    expect(screen.queryByText("最近日志")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "当前任务状态" })).not.toBeInTheDocument();

    const queueToggle = screen.getByRole("button", { name: "队列与历史" });
    await user.click(queueToggle);

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "删结果" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "查看日志" })).toBeInTheDocument();
  });

  test("does not resize the stage or result columns when queue history expands on desktop", async () => {
    const user = userEvent.setup();
    const resizeObserverCallbacks: ResizeObserverCallback[] = [];
    const originalMatchMedia = window.matchMedia;
    let leftColumnHeight = 540;

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
      if (this.classList.contains("left-column")) {
        return createDomRect(leftColumnHeight);
      }
      return createDomRect(320);
    });

    try {
      render(<App />);

      const queueToggle = await screen.findByRole("button", { name: "队列与历史" });
      const stageColumn = screen.getByTestId("stage-column");
      const resultColumn = screen.getByTestId("result-column");

      expect(stageColumn.style.height).toBe("");
      expect(resultColumn.style.height).toBe("");

      await user.click(queueToggle);
      leftColumnHeight = 760;
      resizeObserverCallbacks.forEach((callback) => callback([], {} as ResizeObserver));

      await waitFor(() => {
        expect(stageColumn.style.height).toBe("");
        expect(resultColumn.style.height).toBe("");
      });
    } finally {
      rectSpy.mockRestore();
      Object.defineProperty(window, "matchMedia", {
        configurable: true,
        writable: true,
        value: originalMatchMedia,
      });
    }
  });

  test("locks the result column to the synced workspace height on desktop", () => {
    expect(stylesSource).toMatch(
      /\.result-column\s*\{[^}]*min-height:\s*var\(--result-column-target-height,\s*0px\);[^}]*height:\s*var\(--result-column-target-height,\s*auto\);/s,
    );
  });

  test("prefers the running highlight task over a later queued score task", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";

      if (url.endsWith("/api/health")) {
        return createJsonResponse({
          backend: "ok",
          paths: {
            videos: { path: "F:/videos", exists: true },
            output: { path: "F:/output", exists: true },
            tmp_uploads: { path: "F:/tmp_uploads", exists: true },
          },
        });
      }

      if (url.endsWith("/api/videos")) {
        return createJsonResponse({
          items: [
            {
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
          ],
        });
      }

      if (url.endsWith("/api/tasks")) {
        return createJsonResponse({
          items: [
            {
              task_id: "task-generate",
              video_id: "video-01",
              video_name: "01",
              video_path: "videos/01.mp4",
              source_type: "catalog",
              task_type: "generate",
              parent_task_id: null,
              status: "completed",
              stage: "done",
              stage_progress: 1,
              created_at: "2026-04-07T00:00:00Z",
              started_at: "2026-04-07T00:00:01Z",
              finished_at: "2026-04-07T00:00:10Z",
              error_message: null,
              logs_tail: ["剧本已保存: output/01/script.txt"],
              stage_current: null,
              stage_total: null,
            },
            {
              task_id: "task-highlight",
              video_id: "video-01",
              video_name: "01",
              video_path: "videos/01.mp4",
              source_type: "catalog",
              task_type: "highlight",
              parent_task_id: "task-generate",
              status: "running",
              stage: "highlighting",
              stage_progress: 0.5,
              created_at: "2026-04-07T00:00:11Z",
              started_at: "2026-04-07T00:00:12Z",
              finished_at: null,
              error_message: null,
              logs_tail: ["[Step Highlight] 正在进行爆款预测"],
              stage_current: 1,
              stage_total: 2,
            },
            {
              task_id: "task-score",
              video_id: "video-01",
              video_name: "01",
              video_path: "videos/01.mp4",
              source_type: "catalog",
              task_type: "score",
              parent_task_id: "task-generate",
              status: "queued",
              stage: "queued",
              stage_progress: 0,
              created_at: "2026-04-07T00:00:13Z",
              started_at: null,
              finished_at: null,
              error_message: null,
              logs_tail: [],
              stage_current: null,
              stage_total: null,
            },
          ],
        });
      }

      if (url.endsWith("/api/results/video-01") && method === "GET") {
        return createJsonResponse({
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
          dialogues: [{ text: "你好" }],
          segments: [{ summary: "第一段" }],
          script: "第一幕：主角登场。",
          original_script: null,
          asset_type: "video",
          highlights: null,
          score: null,
          media_url: "/api/media/video-01",
        });
      }

      return new Response("not found", { status: 404 });
    });

    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    expect(await screen.findByText("爆款预测任务 / running")).toBeInTheDocument();
    expect(screen.getByText("爆款预测中")).toBeInTheDocument();
    expect(screen.queryByText(/\[Step Highlight\] 正在进行爆款预测/)).not.toBeInTheDocument();
  });
});
