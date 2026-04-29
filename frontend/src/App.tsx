import { useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { PreviewStage } from "./components/PreviewStage";
import { QueuePanel } from "./components/QueuePanel";
import { ResultPanel } from "./components/ResultPanel";
import { TaskDrawer } from "./components/TaskDrawer";
import { TopBar } from "./components/TopBar";
import { UploadPanel } from "./components/UploadPanel";
import { useWorkbenchData } from "./hooks/useWorkbenchData";
import { useWorkbenchScale } from "./hooks/useWorkbenchScale";

export default function App() {
  const { style: scaleStyle, tier: scaleTier } = useWorkbenchScale();
  const layoutRef = useRef<HTMLElement | null>(null);
  const bannerRef = useRef<HTMLDivElement | null>(null);
  const leftColumnRef = useRef<HTMLElement | null>(null);
  const stageColumnRef = useRef<HTMLElement | null>(null);
  const [resultColumnStyle, setResultColumnStyle] = useState<CSSProperties>({});
  const {
    health,
    videos,
    tasks,
    selectedVideoId,
    selectedVideo,
    selectedResult,
    currentTask,
    latestHighlightTask,
    latestOptimizeTask,
    latestScoreTask,
    setSelectedVideoId,
    refreshNow,
    queueVideo,
    uploadAndQueue,
    queueAll,
    runHighlight,
    runScore,
    optimizeScript,
    deleteResults,
    deleteVideo,
  } = useWorkbenchData();

  useLayoutEffect(() => {
    const layout = layoutRef.current;
    const banner = bannerRef.current;
    const leftColumn = leftColumnRef.current;
    const stageColumn = stageColumnRef.current;
    if (!layout || !banner || !leftColumn || !stageColumn) {
      return;
    }

    let frameId = 0;
    const mediaQuery = typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 1181px)") : null;

    const syncResultColumnHeight = () => {
      frameId = 0;
      if (!mediaQuery?.matches) {
        setResultColumnStyle({});
        return;
      }

      const computedStyle = window.getComputedStyle(layout);
      const layoutGap = Number.parseFloat(computedStyle.rowGap || computedStyle.gap || "0") || 0;
      const bannerHeight = banner.getBoundingClientRect().height;
      const workspaceHeight = stageColumn.getBoundingClientRect().height;
      const baseHeight = bannerHeight + workspaceHeight + layoutGap;

      if (baseHeight <= 0) {
        setResultColumnStyle({});
        return;
      }

      setResultColumnStyle({
        "--result-column-target-height": `${baseHeight}px`,
      } as CSSProperties);
    };

    const scheduleSync = () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      frameId = window.requestAnimationFrame(syncResultColumnHeight);
    };

    scheduleSync();

    const resizeObserver =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            scheduleSync();
          })
        : null;

    resizeObserver?.observe(banner);
    resizeObserver?.observe(leftColumn);
    resizeObserver?.observe(stageColumn);

    window.addEventListener("resize", scheduleSync);

    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      resizeObserver?.disconnect();
      window.removeEventListener("resize", scheduleSync);
    };
  }, [selectedVideoId, selectedResult?.script, videos.length, tasks.length]);

  return (
    <div className="app-shell" data-testid="app-shell" data-scale-tier={scaleTier} data-scroll-mode="page" style={scaleStyle}>
      <div className="backdrop-glow backdrop-left" />
      <div className="backdrop-glow backdrop-right" />

      <main className="dashboard-layout" ref={layoutRef}>
        <div className="workbench-banner" ref={bannerRef}>
          <TopBar health={health} tasks={tasks} onRunAll={queueAll} onRefresh={refreshNow} />
        </div>
        <aside className="left-column" ref={leftColumnRef}>
          <UploadPanel onUpload={uploadAndQueue} />
          <QueuePanel
            items={videos}
            tasks={tasks}
            selectedId={selectedVideoId}
            onSelect={setSelectedVideoId}
            onQueue={queueVideo}
            onDeleteResults={deleteResults}
            onDeleteVideo={deleteVideo}
          />
          <TaskDrawer task={currentTask} />
        </aside>

        <section className="stage-column" data-testid="stage-column" ref={stageColumnRef}>
          <PreviewStage video={selectedVideo} result={selectedResult} task={currentTask} onQueue={queueVideo} />
        </section>

        <section className="result-column" data-testid="result-column" style={resultColumnStyle}>
          <ResultPanel
            result={selectedResult}
            video={selectedVideo}
            highlightTask={latestHighlightTask}
            optimizeTask={latestOptimizeTask}
            onRunHighlight={runHighlight}
            onOptimizeScript={optimizeScript}
            onRunScore={runScore}
            scoreTask={latestScoreTask}
          />
        </section>
      </main>
    </div>
  );
}
