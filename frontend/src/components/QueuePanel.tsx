import { useEffect, useRef, useState } from "react";

import type { TaskItem, VideoItem } from "../types";

type QueuePanelProps = {
  items: VideoItem[];
  tasks: TaskItem[];
  selectedId: string | null;
  onSelect: (videoId: string) => void;
  onQueue: (videoId: string) => Promise<void> | void;
  onDeleteResults: (videoId: string) => Promise<void> | void;
  onDeleteVideo: (videoId: string) => Promise<void> | void;
};

const PAGE_SIZE = 3;
const PAGINATION_EDGE_COUNT = 1;
const PAGINATION_SIBLING_COUNT = 1;

type PaginationToken =
  | {
      kind: "page";
      value: number;
    }
  | {
      kind: "ellipsis";
      key: string;
    };

function resolveLatestTask(tasks: TaskItem[], videoId: string) {
  const matching = tasks.filter((task) => task.video_id === videoId);
  const runningTask = [...matching].reverse().find((task) => task.status === "running");
  if (runningTask) {
    return runningTask;
  }

  const queuedTask = [...matching].reverse().find((task) => task.status === "queued");
  if (queuedTask) {
    return queuedTask;
  }

  return matching.length > 0 ? matching[matching.length - 1] : null;
}

function statusLabel(video: VideoItem, task: TaskItem | null) {
  if (task?.status === "queued" || task?.status === "running" || task?.status === "failed") {
    if (task.task_type === "highlight") {
      const highlightMap: Record<string, string> = {
        queued: "待运行爆款预测",
        running: "爆款预测中",
        failed: "爆款预测失败",
      };
      return highlightMap[task.status] ?? task.status;
    }

    if (task.task_type === "score") {
      const scoreMap: Record<string, string> = {
        queued: "待评分",
        running: "评分中",
        failed: "评分失败",
      };
      return scoreMap[task.status] ?? task.status;
    }

    if (task.task_type === "optimize") {
      const optimizeMap: Record<string, string> = {
        queued: "待优化剧本",
        running: "优化剧本中",
        failed: "优化剧本失败",
      };
      return optimizeMap[task.status] ?? task.status;
    }

    const generateMap: Record<string, string> = {
      queued: "排队中",
      running: "运行中",
      failed: "失败",
    };
    return generateMap[task.status] ?? task.status;
  }

  if (video.output_ready) {
    if (task?.task_type === "highlight" && task.status === "completed") {
      return "已生成爆款预测";
    }

    if (task?.task_type === "score" && task.status === "completed") {
      return "已评分";
    }

    if (task?.task_type === "optimize" && task.status === "completed") {
      return "剧本已优化";
    }

    if (task?.status === "completed") {
      return "已完成";
    }

    return "已有结果";
  }

  return video.asset_type === "script" ? "待预测" : "待处理";
}

function statusTone(video: VideoItem, task: TaskItem | null) {
  if (task?.status === "queued" || task?.status === "running" || task?.status === "failed") {
    return task.status;
  }

  return video.output_ready ? "completed" : "idle";
}

function buildPaginationTokens(page: number, pageCount: number): PaginationToken[] {
  if (pageCount <= 1) {
    return [{ kind: "page", value: 1 }];
  }

  const pages = new Set<number>();
  for (let value = 1; value <= Math.min(PAGINATION_EDGE_COUNT, pageCount); value += 1) {
    pages.add(value);
  }
  for (let value = Math.max(pageCount - PAGINATION_EDGE_COUNT + 1, 1); value <= pageCount; value += 1) {
    pages.add(value);
  }
  for (let value = Math.max(page - PAGINATION_SIBLING_COUNT, 1); value <= Math.min(page + PAGINATION_SIBLING_COUNT, pageCount); value += 1) {
    pages.add(value);
  }

  const orderedPages = [...pages].sort((left, right) => left - right);
  const tokens: PaginationToken[] = [];

  orderedPages.forEach((value, index) => {
    if (index > 0) {
      const previousValue = orderedPages[index - 1];
      if (value - previousValue === 2) {
        tokens.push({ kind: "page", value: previousValue + 1 });
      } else if (value - previousValue > 2) {
        tokens.push({ kind: "ellipsis", key: `${previousValue}-${value}` });
      }
    }

    tokens.push({ kind: "page", value });
  });

  return tokens;
}

export function QueuePanel({
  items,
  tasks,
  selectedId,
  onSelect,
  onQueue,
  onDeleteResults,
  onDeleteVideo,
}: QueuePanelProps) {
  const [open, setOpen] = useState(true);
  const [page, setPage] = useState(1);
  const lastAutoAlignedSelectionRef = useRef<string | null>(null);
  const readyCount = items.filter((item) => item.output_ready).length;
  const pageCount = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const pageStart = (page - 1) * PAGE_SIZE;
  const visibleItems = items.slice(pageStart, pageStart + PAGE_SIZE);
  const paginationTokens = buildPaginationTokens(page, pageCount);

  useEffect(() => {
    if (page > pageCount) {
      setPage(pageCount);
    }
  }, [page, pageCount]);

  useEffect(() => {
    if (!selectedId) {
      lastAutoAlignedSelectionRef.current = null;
      return;
    }

    const selectedIndex = items.findIndex((item) => item.video_id === selectedId);
    if (selectedIndex < 0) {
      return;
    }

    if (lastAutoAlignedSelectionRef.current === selectedId) {
      return;
    }

    const targetPage = Math.floor(selectedIndex / PAGE_SIZE) + 1;
    lastAutoAlignedSelectionRef.current = selectedId;
    setPage(targetPage);
  }, [items, selectedId]);

  return (
    <section className="panel queue-panel">
      <button
        className="drawer-toggle panel-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label="队列与历史"
      >
        <span className="panel-toggle-copy">
          <span className="panel-kicker">队列与历史</span>
          <strong>素材总览</strong>
        </span>
        <span className="panel-toggle-meta">{open ? "收起" : `展开 ${items.length} 条`}</span>
      </button>

      {open ? (
        <div className="queue-panel-body">
          <div className="queue-summary-row">
            <span>{items.length} 个素材</span>
            <span>{readyCount} 个已有结果</span>
          </div>

          <div className="queue-list" role="list" data-testid="queue-list">
          {visibleItems.map((item) => {
            const latestTask = resolveLatestTask(tasks, item.video_id);
            const isRunning = latestTask?.status === "running";
            const sourceLabel = item.source_type === "catalog" ? "历史素材" : "新上传";
            const isScript = item.asset_type === "script";
            const primaryActionLabel = isScript
              ? item.output_ready
                ? "重新预测"
                : "开始预测"
              : item.output_ready
                ? "重新处理"
                : "开始处理";
            return (
              <article
                key={item.video_id}
                className={`queue-item ${selectedId === item.video_id ? "is-selected" : ""}`}
                onClick={() => onSelect(item.video_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(item.video_id);
                  }
                }}
              >
                <div className="queue-item-head">
                  <div className="queue-title-stack">
                    <div className="queue-title-row">
                      <strong>{item.display_stem || item.video_name}</strong>
                      <span className="source-pill">{isScript ? `剧本 · ${sourceLabel}` : `视频 · ${sourceLabel}`}</span>
                    </div>
                    <p>
                      {item.output_ready
                        ? "已有结果，可直接查看或继续优化。"
                        : isScript
                          ? "上传后会先做爆款预测，之后可继续优化剧本。"
                          : "尚未生成结果，处理后会自动更新到右侧。"}
                    </p>
                  </div>
                  <span className={`status-pill queue-status-pill status-${statusTone(item, latestTask)}`}>
                    {statusLabel(item, latestTask)}
                  </span>
                </div>
                <div className="queue-actions">
                  <button
                    className="ghost-button"
                    onClick={(event) => {
                      event.stopPropagation();
                      void onQueue(item.video_id);
                    }}
                  >
                    {primaryActionLabel}
                  </button>
                  <button
                    className="ghost-button"
                    disabled={!item.has_output || isRunning}
                    onClick={(event) => {
                      event.stopPropagation();
                      void onDeleteResults(item.video_id);
                    }}
                  >
                    删结果
                  </button>
                  <button
                    className="ghost-button danger-button"
                    disabled={isRunning}
                    onClick={(event) => {
                      event.stopPropagation();
                      if (!window.confirm(isScript ? "确认删除原剧本文件和全部生成结果吗？" : "确认删除原视频、评分和全部生成结果吗？")) {
                        return;
                      }
                      void onDeleteVideo(item.video_id);
                    }}
                  >
                    全删
                  </button>
                </div>
              </article>
            );
          })}
          </div>

          {pageCount > 1 ? (
            <nav className="queue-pagination" aria-label="队列分页">
              <span className="queue-pagination-summary">
                第 {page} / {pageCount} 页
              </span>
              <div className="queue-pagination-actions">
                <button
                  className="ghost-button"
                  disabled={page === 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  type="button"
                >
                  上一页
                </button>
                {paginationTokens.map((token) =>
                  token.kind === "page" ? (
                    <button
                      key={token.value}
                      aria-current={page === token.value ? "page" : undefined}
                      className={`ghost-button queue-page-button ${page === token.value ? "is-active" : ""}`}
                      onClick={() => setPage(token.value)}
                      type="button"
                    >
                      {token.value}
                    </button>
                  ) : (
                    <span key={token.key} className="queue-page-ellipsis" aria-hidden="true">
                      ...
                    </span>
                  ),
                )}
                <button
                  className="ghost-button"
                  disabled={page === pageCount}
                  onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                  type="button"
                >
                  下一页
                </button>
              </div>
            </nav>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
