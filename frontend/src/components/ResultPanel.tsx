import { useEffect, useLayoutEffect, useRef, useState } from "react";

import type { ResultPayload, TaskItem, VideoItem } from "../types";

type ResultPanelProps = {
  result: ResultPayload | null;
  video?: VideoItem | null;
  highlightTask: TaskItem | null;
  optimizeTask: TaskItem | null;
  onRunHighlight: (videoId: string) => Promise<void> | void;
  onOptimizeScript: (videoId: string) => Promise<void> | void;
  onRunScore: (videoId: string) => Promise<void> | void;
  scoreTask: TaskItem | null;
};

type TabKey = "dialogues" | "segments" | "script" | "highlights" | "score";
type ScriptViewMode = "latest" | "original";
type ActionTone = "idle" | "queued" | "running" | "completed" | "failed";

const VIDEO_PRIMARY_TABS: TabKey[] = ["script", "highlights", "score"];
const SCRIPT_PRIMARY_TABS: TabKey[] = ["script", "highlights"];
const ADVANCED_TABS: TabKey[] = ["dialogues", "segments"];
const RESULT_BODY_STACK_GAP = 8;

const TAB_LABELS: Record<TabKey, string> = {
  dialogues: "对白",
  segments: "分段",
  script: "剧本",
  highlights: "爆款预测器",
  score: "评分",
};

function sanitizeFilenamePart(value: string) {
  const sanitized = value.replace(/[\\/:*?"<>|]+/g, "-").trim();
  return sanitized || "script";
}

function buildScriptFilename(result: ResultPayload) {
  const stem = result.video.display_stem || result.video.video_name || "script";
  return `${sanitizeFilenamePart(stem)}_最新优化版剧本.txt`;
}

function buildOriginalScriptFilename(result: ResultPayload) {
  const stem = result.video.display_stem || result.video.video_name || "script";
  return `${sanitizeFilenamePart(stem)}_原剧本.txt`;
}

function formatTime(value: number) {
  return `${value.toFixed(1)}s`;
}

function formatTimeRange(start: number, end: number) {
  return `${formatTime(start)} - ${formatTime(end)}`;
}

function formatPosition(value: number, mode: "time" | "beat") {
  if (mode === "beat") {
    return `第 ${Math.round(value)} 段`;
  }
  return formatTime(value);
}

function formatPositionRange(start: number, end: number, mode: "time" | "beat") {
  if (mode === "beat") {
    return `${formatPosition(start, mode)} - ${formatPosition(end, mode)}`;
  }
  return formatTimeRange(start, end);
}

function getScriptText(result: ResultPayload, mode: ScriptViewMode) {
  if (mode === "original") {
    return result.original_script ?? result.script;
  }
  return result.script;
}

function isPendingTask(task: TaskItem | null) {
  return task?.status === "queued" || task?.status === "running";
}

function actionToneFromTask(task: TaskItem | null): ActionTone {
  if (task?.status === "queued") {
    return "queued";
  }
  if (task?.status === "running") {
    return "running";
  }
  if (task?.status === "failed") {
    return "failed";
  }
  if (task?.status === "completed") {
    return "completed";
  }
  return "idle";
}

function renderActionBoard(
  result: ResultPayload | null,
  video: VideoItem | null,
  highlightTask: TaskItem | null,
  optimizeTask: TaskItem | null,
  scoreTask: TaskItem | null,
  onRunHighlight: (videoId: string) => Promise<void> | void,
  onOptimizeScript: (videoId: string) => Promise<void> | void,
  onRunScore: (videoId: string) => Promise<void> | void,
) {
  const activeVideo = result?.video ?? video;
  if (!activeVideo) {
    return null;
  }

  const isScriptAsset = activeVideo.asset_type === "script";
  const hasScript = Boolean(result);
  const hasScore = Boolean(result?.score) && !isScriptAsset;
  const hasHighlights = Boolean(result?.highlights);
  const scorePending = isPendingTask(scoreTask);
  const highlightPending = isPendingTask(highlightTask);
  const optimizePending = isPendingTask(optimizeTask);
  const highlightButtonLabel = !hasScript ? "等待剧本" : highlightPending ? "预测中..." : hasHighlights ? "重新预测" : "开始预测";
  const highlightButtonDisabled = !hasScript || highlightPending || optimizePending;
  const scoreButtonLabel = !hasScript ? "等待剧本" : scorePending ? "评分中..." : hasScore ? "重新评分" : "开始评分";
  const scoreButtonDisabled = !hasScript || scorePending || optimizePending;
  const optimizeButtonLabel = optimizePending ? "优化中..." : "优化剧本";
  const optimizeButtonDisabled = !hasHighlights || optimizePending || highlightPending;

  const scoreTone: ActionTone = !hasScript ? "idle" : hasScore ? "completed" : actionToneFromTask(scoreTask);
  const scoreStatus = !hasScript ? "待剧本" : hasScore ? "已完成" : scorePending ? "处理中" : scoreTask?.status === "failed" ? "失败" : "待评分";

  const highlightTone: ActionTone = !hasScript ? "idle" : hasHighlights ? "completed" : actionToneFromTask(highlightTask);
  const highlightStatus = !hasScript
    ? "待剧本"
    : hasHighlights
    ? "已完成"
    : highlightTask?.status === "running"
      ? "预测中"
      : highlightTask?.status === "queued"
        ? "待预测"
        : highlightTask?.status === "failed"
          ? "失败"
          : "待预测";

  const optimizeTone: ActionTone =
    !hasScript
      ? "idle"
      : optimizePending || optimizeTask?.status === "failed"
        ? actionToneFromTask(optimizeTask)
        : hasHighlights
          ? "completed"
          : "idle";
  const optimizeStatus = !hasScript
    ? "待剧本"
    : optimizePending
    ? "优化中"
    : optimizeTask?.status === "failed"
      ? "失败"
      : hasHighlights
        ? optimizeTask?.status === "completed"
          ? "已优化"
          : "可执行"
        : "待开启";

  return (
    <section className="result-action-board" aria-label="任务操作">
      <div className="result-action-board-head">
        <p className="panel-kicker">任务操作</p>
      </div>

      <div className="result-action-grid">
        {!isScriptAsset ? (
          <article className={`result-action-card is-${scoreTone}`}>
            <div className="result-action-card-head">
              <div>
                <p className="result-action-kicker">评分</p>
                <h3>剧本评分</h3>
              </div>
              <span className={`status-pill status-${scoreTone}`}>{scoreStatus}</span>
            </div>
            <div className="result-action-card-footer">
              <button
                className="secondary-button"
                disabled={scoreButtonDisabled}
                onClick={() => void onRunScore(activeVideo.video_id)}
                type="button"
              >
                {scoreButtonLabel}
              </button>
            </div>
          </article>
        ) : null}

        <article className={`result-action-card is-${highlightTone}`}>
          <div className="result-action-card-head">
            <div>
              <p className="result-action-kicker">预测</p>
              <h3>爆款预测器</h3>
              </div>
              <span className={`status-pill status-${highlightTone}`}>{highlightStatus}</span>
            </div>
          <div className="result-action-card-footer">
            <button
              className="secondary-button"
              disabled={highlightButtonDisabled}
              onClick={() => void onRunHighlight(activeVideo.video_id)}
              type="button"
            >
              {highlightButtonLabel}
            </button>
          </div>
        </article>

        <article className={`result-action-card is-${optimizeTone}`}>
          <div className="result-action-card-head">
            <div>
              <p className="result-action-kicker">优化</p>
              <h3>剧本修订</h3>
              </div>
              <span className={`status-pill status-${optimizeTone}`}>{optimizeStatus}</span>
            </div>
          <div className="result-action-card-footer">
            <button
              className="secondary-button"
              disabled={optimizeButtonDisabled}
              onClick={() => void onOptimizeScript(activeVideo.video_id)}
              type="button"
            >
              {optimizeButtonLabel}
            </button>
          </div>
        </article>
      </div>
    </section>
  );
}

function renderScriptActionBoard(scriptToolbar: {
  notice: string | null;
  onCopyScript: () => Promise<void>;
  onDownloadScript: () => void;
}) {
  return (
    <section className="script-action-board" aria-label="剧本操作">
      <div className="script-action-board-head">
        <div className="script-action-copy">
          <p className="result-featured-kicker">剧本操作</p>
          <strong>复制与导出</strong>
        </div>
        <div className="script-toolbar script-toolbar-compact" role="toolbar" aria-label="剧本工具栏">
          <button className="ghost-button" onClick={() => void scriptToolbar.onCopyScript()} type="button">
            复制剧本
          </button>
          <button className="ghost-button" onClick={scriptToolbar.onDownloadScript} type="button">
            导出 TXT
          </button>
        </div>
      </div>
      {scriptToolbar.notice ? <p className="script-toolbar-feedback">{scriptToolbar.notice}</p> : null}
    </section>
  );
}

function renderHighlightPanel(result: ResultPayload | null, highlightTask: TaskItem | null) {
  if (!result) {
    return <p className="empty-state">剧本生成后，这里会显示爆款预测和关键窗口建议。</p>;
  }

  if (result.highlights) {
    const positionMode = result.highlights.position_mode ?? "time";
    const bestOpportunity = result.highlights.best_opportunity;

    return (
      <div className="result-scroll-shell">
        <div className="highlight-panel">
          <article className="highlight-summary-card viral-summary-card">
            <div className="highlight-best-copy">
              <div>
                <p className="highlight-kicker">爆款指数</p>
                <strong>{result.highlights.breakout_score} / 100</strong>
              </div>
              <span>{result.highlights.emotion_curve.length} 个分析节点</span>
            </div>
            <p>{result.highlights.summary}</p>
          </article>

          <article className="highlight-best-card">
            <div className="highlight-best-copy">
              <div>
                <p className="highlight-kicker">最佳修正点</p>
                <strong>{bestOpportunity?.kind ?? "暂无建议"}</strong>
              </div>
              {bestOpportunity ? <span>{formatPositionRange(bestOpportunity.start, bestOpportunity.end, positionMode)}</span> : null}
            </div>
            <p>{bestOpportunity?.reason ?? "当前没有明确的优先修正点。"}</p>
            {bestOpportunity ? <p className="viral-window-suggestion">{bestOpportunity.suggestion}</p> : null}
          </article>

          <section className="viral-window-section">
            <div className="highlight-item-head">
              <strong>下滑风险窗口</strong>
              <span>{result.highlights.risk_windows.length} 段</span>
            </div>
            <div className="highlight-list">
              {result.highlights.risk_windows.map((item, index) => (
                <article key={`${item.start}-${item.end}-${index}`} className="highlight-item-card">
                  <div className="highlight-item-head">
                    <strong>{item.kind}</strong>
                    <span>
                      {formatPositionRange(item.start, item.end, positionMode)} · 置信 {item.confidence}%
                    </span>
                  </div>
                  <p>{item.reason}</p>
                  <p className="viral-window-suggestion">{item.suggestion}</p>
                </article>
              ))}
              {result.highlights.risk_windows.length === 0 ? <p className="empty-state">暂无明显下滑风险。</p> : null}
            </div>
          </section>

          <section className="viral-window-section">
            <div className="highlight-item-head">
              <strong>放大机会窗口</strong>
              <span>{result.highlights.opportunity_windows.length} 段</span>
            </div>
            <div className="highlight-list">
              {result.highlights.opportunity_windows.map((item, index) => (
                <article key={`${item.start}-${item.end}-${index}`} className="highlight-item-card">
                  <div className="highlight-item-head">
                    <strong>{item.kind}</strong>
                    <span>
                      {formatPositionRange(item.start, item.end, positionMode)} · 置信 {item.confidence}%
                    </span>
                  </div>
                  <p>{item.reason}</p>
                  <p className="viral-window-suggestion">{item.suggestion}</p>
                </article>
              ))}
              {result.highlights.opportunity_windows.length === 0 ? <p className="empty-state">暂无明确放大机会。</p> : null}
            </div>
          </section>
        </div>
      </div>
    );
  }

  if (highlightTask?.status === "running" || highlightTask?.status === "queued") {
    return <p className="empty-state">爆款预测中，远端模型正在分析留存风险与放大机会。</p>;
  }

  if (highlightTask?.status === "failed") {
    return <p className="empty-state">爆款预测失败：{highlightTask.error_message ?? "请重新触发任务。"}</p>;
  }

  return <p className="empty-state">暂无爆款预测结果。</p>;
}

function renderScorePanel(
  result: ResultPayload | null,
  scoreTask: TaskItem | null,
) {
  if (!result) {
    return <p className="empty-state">剧本生成后，这里会显示自动评分结果。</p>;
  }

  const scorePending = isPendingTask(scoreTask);

  return (
    <div className="result-panel-stack">
      {result.score ? (
        <div className="result-scroll-shell">
          <div className="score-panel">
            <div className="score-summary">
              <div>
                <p className="score-kicker">总分</p>
                <strong>{result.score.total_score} / 100</strong>
              </div>
              <p>{result.score.summary}</p>
            </div>

            <div className="score-dimension-list">
              {result.score.dimensions.map((dimension) => (
                <article key={dimension.key} className="score-dimension-card">
                  <div className="score-dimension-head">
                    <strong>{dimension.label}</strong>
                    <span>
                      {dimension.score} / {dimension.max_score}
                    </span>
                  </div>
                  <p>{dimension.reason}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      ) : scorePending ? (
        <p className="empty-state">评分中，远端模型正在结合原视频与生成结果做打分。</p>
      ) : scoreTask?.status === "failed" ? (
        <p className="empty-state">评分失败：{scoreTask.error_message ?? "请重新触发评分任务。"}</p>
      ) : (
        <p className="empty-state">暂无评分结果。</p>
      )}
    </div>
  );
}

function renderTabPanel(
  tab: TabKey | null,
  result: ResultPayload | null,
  highlightTask: TaskItem | null,
  scoreTask: TaskItem | null,
  scriptView: ScriptViewMode,
  onScriptViewChange: (mode: ScriptViewMode) => void,
) {
  if (!result) {
    return <p className="empty-state">尚无可读结果，任务完成后这里会显示对白、分段和剧本。</p>;
  }

  if (!tab) {
    return <p className="empty-state">点击上方标签查看对应结果。</p>;
  }

  if (tab === "highlights") {
    return renderHighlightPanel(result, highlightTask);
  }

  if (tab === "score") {
    return renderScorePanel(result, scoreTask);
  }

  if (tab === "script") {
    const hasOriginal = Boolean(result.original_script);
    const activeText = getScriptText(result, scriptView);
    return (
      <div className="result-panel-stack script-panel-stack">
        <div className="tab-row tab-row-secondary script-version-row" role="tablist" aria-label="剧本版本切换">
          <button
            className={`tab-button ${scriptView === "latest" ? "is-active" : ""}`}
            onClick={() => onScriptViewChange("latest")}
            type="button"
          >
            最新优化版
          </button>
          <button
            className={`tab-button ${scriptView === "original" ? "is-active" : ""}`}
            disabled={!hasOriginal}
            onClick={() => onScriptViewChange("original")}
            type="button"
          >
            原剧本
          </button>
        </div>
        {!hasOriginal ? <p className="script-version-hint">当前结果缺少原剧本快照，暂时无法查看原剧本。</p> : null}
        <div className="result-scroll-shell result-scroll-shell-script" data-testid="script-viewer" data-scrollable="true">
          <pre className="result-script">{activeText}</pre>
        </div>
      </div>
    );
  }

  const payload = tab === "dialogues" ? result.dialogues : result.segments;
  const rawTitle = tab === "dialogues" ? "对白原文" : "结构分段";
  const rawHint =
    tab === "dialogues"
      ? "这里保留识别后的对白内容，方便核对和回看。"
      : "这里保留结构化分段结果，适合检查情节拆分是否完整。";
  return (
    <div className="result-panel-stack">
      <article className="result-raw-card">
        <p className="result-featured-kicker">原始结果</p>
        <h3>{rawTitle}</h3>
        <p>{rawHint}</p>
      </article>
      <div className="result-scroll-shell">
        <pre className="result-json">{JSON.stringify(payload, null, 2)}</pre>
      </div>
    </div>
  );
}

export function ResultPanel({
  result,
  video = null,
  highlightTask,
  optimizeTask,
  onRunHighlight,
  onOptimizeScript,
  onRunScore,
  scoreTask,
}: ResultPanelProps) {
  const resultBodyRef = useRef<HTMLDivElement | null>(null);
  const [tab, setTab] = useState<TabKey | null>(null);
  const [scriptView, setScriptView] = useState<ScriptViewMode>("latest");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [scriptNotice, setScriptNotice] = useState<string | null>(null);
  const activeAssetType = result?.asset_type ?? video?.asset_type ?? "video";
  const primaryTabs = activeAssetType === "script" ? SCRIPT_PRIMARY_TABS : VIDEO_PRIMARY_TABS;

  useEffect(() => {
    if (tab && !showAdvanced && ADVANCED_TABS.includes(tab)) {
      setTab(null);
    }
  }, [showAdvanced, tab]);

  useEffect(() => {
    setTab(null);
    setScriptView("latest");
  }, [result?.video.video_id]);

  useEffect(() => {
    setScriptNotice(null);
  }, [result?.video.video_id, result?.script, result?.original_script, scriptView]);

  useEffect(() => {
    if (!scriptNotice) {
      return;
    }

    const timer = window.setTimeout(() => {
      setScriptNotice(null);
    }, 2200);

    return () => window.clearTimeout(timer);
  }, [scriptNotice]);

  useLayoutEffect(() => {
    const resultBody = resultBodyRef.current;
    if (!resultBody) {
      return;
    }

    if (!result || !tab) {
      resultBody.style.setProperty("--result-display-align-offset", "0px");
      resultBody.style.removeProperty("--result-display-slot-height");
      resultBody.style.removeProperty("--result-script-viewer-height");
      return;
    }

    let frameId = 0;
    const mediaQuery = typeof window.matchMedia === "function" ? window.matchMedia("(min-width: 1181px)") : null;

    const syncOffset = () => {
      frameId = 0;
      const resultDisplaySlot = resultBody.querySelector<HTMLElement>(".result-display-slot");
      const scriptViewer = resultBody.querySelector<HTMLElement>('[data-testid="script-viewer"]');
      const scriptActionBoard = resultBody.querySelector<HTMLElement>(".script-action-board");

      if (!mediaQuery?.matches || !resultDisplaySlot) {
        resultBody.style.setProperty("--result-display-align-offset", "0px");
        resultBody.style.removeProperty("--result-display-slot-height");
        resultBody.style.removeProperty("--result-script-viewer-height");
        return;
      }

      if (tab === "highlights" || tab === "score") {
        resultBody.style.setProperty("--result-display-align-offset", "0px");
        resultBody.style.removeProperty("--result-display-slot-height");
        resultBody.style.removeProperty("--result-script-viewer-height");
        return;
      }

      const previewFrame = document.querySelector<HTMLElement>('[data-testid="preview-frame"]');
      if (!previewFrame) {
        resultBody.style.setProperty("--result-display-align-offset", "0px");
        resultBody.style.removeProperty("--result-display-slot-height");
        resultBody.style.removeProperty("--result-script-viewer-height");
        return;
      }

      const displaySlotRect = resultDisplaySlot.getBoundingClientRect();
      const previewRect = previewFrame.getBoundingClientRect();
      let nextDisplayHeight = Math.max(0, Math.round(previewRect.bottom - displaySlotRect.top));
      if (tab === "script" && scriptActionBoard) {
        const scriptActionBoardRect = scriptActionBoard.getBoundingClientRect();
        const expandedDisplayHeight = Math.max(
          0,
          Math.round(scriptActionBoardRect.top - displaySlotRect.top - RESULT_BODY_STACK_GAP),
        );
        nextDisplayHeight = Math.max(nextDisplayHeight, expandedDisplayHeight);
      }

      resultBody.style.setProperty("--result-display-align-offset", "0px");
      resultBody.style.setProperty("--result-display-slot-height", `${nextDisplayHeight}px`);

      if (tab !== "script" || !scriptViewer) {
        resultBody.style.removeProperty("--result-script-viewer-height");
        return;
      }

      const viewerRect = scriptViewer.getBoundingClientRect();
      let nextScriptHeight = Math.max(0, Math.round(previewRect.bottom - viewerRect.top));
      if (scriptActionBoard) {
        const scriptActionBoardRect = scriptActionBoard.getBoundingClientRect();
        const expandedScriptHeight = Math.max(
          0,
          Math.round(scriptActionBoardRect.top - viewerRect.top - RESULT_BODY_STACK_GAP),
        );
        nextScriptHeight = Math.max(nextScriptHeight, expandedScriptHeight);
      }

      resultBody.style.setProperty("--result-script-viewer-height", `${nextScriptHeight}px`);
    };

    const scheduleSync = () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      frameId = window.requestAnimationFrame(syncOffset);
    };

    scheduleSync();

    const previewFrame = document.querySelector<HTMLElement>('[data-testid="preview-frame"]');
    const resizeObserver =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            scheduleSync();
          })
        : null;

    resizeObserver?.observe(resultBody);
    const resultDisplaySlot = resultBody.querySelector<HTMLElement>(".result-display-slot");
    const scriptViewer = resultBody.querySelector<HTMLElement>('[data-testid="script-viewer"]');
    const scriptActionBoard = resultBody.querySelector<HTMLElement>(".script-action-board");
    if (previewFrame) {
      resizeObserver?.observe(previewFrame);
    }
    if (resultDisplaySlot) {
      resizeObserver?.observe(resultDisplaySlot);
    }
    if (scriptViewer) {
      resizeObserver?.observe(scriptViewer);
    }
    if (scriptActionBoard) {
      resizeObserver?.observe(scriptActionBoard);
    }

    window.addEventListener("resize", scheduleSync);

    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      resizeObserver?.disconnect();
      window.removeEventListener("resize", scheduleSync);
    };
  }, [tab, showAdvanced, result?.video.video_id, result?.script, result?.original_script, scriptView]);

  const handleCopyScript = async () => {
    if (!result) {
      return;
    }

    if (!navigator.clipboard?.writeText) {
      setScriptNotice("当前环境不支持一键复制，请直接导出 TXT。");
      return;
    }

    try {
      await navigator.clipboard.writeText(getScriptText(result, scriptView));
      setScriptNotice("已复制到剪贴板，可直接粘贴使用。");
    } catch {
      setScriptNotice("复制失败，请改用导出 TXT。");
    }
  };

  const handleDownloadScript = () => {
    if (!result) {
      return;
    }

    const exportText = getScriptText(result, scriptView);
    const filename = scriptView === "original" ? buildOriginalScriptFilename(result) : buildScriptFilename(result);
    const objectUrl = URL.createObjectURL(new Blob([exportText], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(objectUrl);
    setScriptNotice(`已导出 ${filename}`);
  };

  return (
    <section className="panel result-panel">
      <div className="panel-head">
        <p className="panel-kicker">结果面板</p>
        <h2>{activeAssetType === "script" ? "剧本 / 爆款预测器" : "对白 / 分段 / 剧本 / 爆款预测器 / 评分"}</h2>
      </div>

      <div className="result-tab-layout">
        <div className="tab-row" role="tablist" aria-label="结果标签">
          {primaryTabs.map((key) => (
            <button
              key={key}
              className={`tab-button ${tab === key ? "is-active" : ""}`}
              onClick={() => setTab(key)}
              role="tab"
              aria-selected={tab === key}
            >
              {TAB_LABELS[key]}
            </button>
          ))}
        </div>
        <button
          className={`ghost-button result-advanced-toggle ${showAdvanced ? "is-active" : ""}`}
          onClick={() => setShowAdvanced((current) => !current)}
          type="button"
        >
          {showAdvanced ? "收起高级信息" : "高级信息"}
        </button>
      </div>

      {showAdvanced ? (
        <div className="tab-row tab-row-secondary" role="tablist" aria-label="高级结果标签">
          {ADVANCED_TABS.map((key) => (
            <button
              key={key}
              className={`tab-button ${tab === key ? "is-active" : ""}`}
              onClick={() => setTab(key)}
              role="tab"
              aria-selected={tab === key}
            >
              {TAB_LABELS[key]}
            </button>
          ))}
        </div>
      ) : null}

      <div className="result-body" ref={resultBodyRef}>
        {renderActionBoard(
          result,
          video,
          highlightTask,
          optimizeTask,
          scoreTask,
          onRunHighlight,
          onOptimizeScript,
          onRunScore,
        )}
        <div className="result-display-slot">
          {renderTabPanel(
            tab,
            result,
          highlightTask,
          scoreTask,
          scriptView,
          setScriptView,
        )}
        </div>
        {tab === "script" && result ? renderScriptActionBoard({
          notice: scriptNotice,
          onCopyScript: handleCopyScript,
          onDownloadScript: handleDownloadScript,
        }) : null}
      </div>
    </section>
  );
}
