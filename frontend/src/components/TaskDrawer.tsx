import { useEffect, useState } from "react";

import type { TaskItem, TaskStage } from "../types";

type TaskDrawerProps = {
  task: TaskItem | null;
};

const GENERATE_STAGE_ROWS: Array<{ key: TaskStage; label: string }> = [
  { key: "queued", label: "等待入场" },
  { key: "asr", label: "ASR 转写" },
  { key: "segmenting", label: "视频切片" },
  { key: "multimodal", label: "多模态分析" },
  { key: "merging", label: "剧本整合" },
  { key: "done", label: "完成归档" },
];

const SCORE_STAGE_ROWS: Array<{ key: TaskStage; label: string }> = [
  { key: "queued", label: "等待评分" },
  { key: "scoring", label: "剧本评分" },
  { key: "done", label: "评分归档" },
];

const HIGHLIGHT_STAGE_ROWS: Array<{ key: TaskStage; label: string }> = [
  { key: "queued", label: "等待预测" },
  { key: "highlighting", label: "爆款预测" },
  { key: "done", label: "预测归档" },
];

const OPTIMIZE_STAGE_ROWS: Array<{ key: TaskStage; label: string }> = [
  { key: "queued", label: "等待优化" },
  { key: "optimizing", label: "剧本优化" },
  { key: "done", label: "优化归档" },
];

function stageRowsForTask(task: TaskItem | null) {
  if (task?.task_type === "score") {
    return SCORE_STAGE_ROWS;
  }
  if (task?.task_type === "highlight") {
    return HIGHLIGHT_STAGE_ROWS;
  }
  if (task?.task_type === "optimize") {
    return OPTIMIZE_STAGE_ROWS;
  }
  return GENERATE_STAGE_ROWS;
}

function taskTypeLabel(task: TaskItem | null) {
  if (!task) {
    return "暂无任务";
  }
  if (task.task_type === "score") {
    return "评分任务";
  }
  if (task.task_type === "highlight") {
    return "爆款预测任务";
  }
  if (task.task_type === "optimize") {
    return "优化任务";
  }
  return "生成任务";
}

function stageRank(stageRows: Array<{ key: TaskStage; label: string }>, stage: TaskStage | null) {
  const index = stageRows.findIndex((item) => item.key === stage);
  return index >= 0 ? index : -1;
}

function currentStageLabel(stageRows: Array<{ key: TaskStage; label: string }>, stage: TaskStage | null) {
  return stageRows.find((item) => item.key === stage)?.label ?? stage ?? "暂无运行阶段";
}

export function TaskDrawer({ task }: TaskDrawerProps) {
  const [showLogs, setShowLogs] = useState(false);
  const stageRows = stageRowsForTask(task);
  const currentRank = stageRank(stageRows, task?.stage ?? null);
  const stageLabel = currentStageLabel(stageRows, task?.stage ?? null);

  useEffect(() => {
    setShowLogs(false);
  }, [task?.task_id]);

  return (
    <section className="panel task-drawer">
      <div className="panel-head">
        <p className="panel-kicker">当前任务状态</p>
        <h2>{task?.video_name ?? "暂无正在关注的任务"}</h2>
        <p className="task-drawer-copy">这里保留运行轨迹，便于盯进度或定位失败原因，正常查看结果时不需要一直关注。</p>
      </div>

      <div className="drawer-body drawer-body-static">
        <div className="drawer-header">
          <strong>{task ? `${taskTypeLabel(task)} / ${stageLabel}` : "暂无运行阶段"}</strong>
          <span className={`status-pill status-${task?.status ?? "idle"}`}>
            {task ? `${taskTypeLabel(task)} / ${task.status}` : "idle"}
          </span>
        </div>

        <div className="stage-grid">
          {stageRows.map((stage) => {
            const isActive = task?.stage === stage.key;
            const isDone = currentRank >= stageRank(stageRows, stage.key);
            return (
              <div
                key={stage.key}
                className={`stage-row ${isActive ? "is-active" : ""} ${isDone ? "is-done" : ""}`}
              >
                <span>{stage.label}</span>
                <small>
                  {isActive && task?.stage_progress
                    ? `${Math.round(task.stage_progress * 100)}%`
                    : isDone
                      ? "完成"
                      : "待命"}
                </small>
              </div>
            );
          })}
        </div>

        {task?.error_message ? <p className="task-error">{task.error_message}</p> : null}

        <div className="drawer-tools">
          <button
            className={`ghost-button task-log-toggle ${showLogs ? "is-active" : ""}`}
            onClick={() => setShowLogs((current) => !current)}
            type="button"
          >
            {showLogs ? "收起日志" : "查看日志"}
          </button>
          <span className="drawer-tools-copy">原始运行日志默认收起，需要排查时再展开查看。</span>
        </div>

        {showLogs ? (
          <div className="log-tail">
            <p>最近日志</p>
            <pre>{task?.logs_tail?.slice(-6).join("\n") || "暂无日志"}</pre>
          </div>
        ) : null}
      </div>
    </section>
  );
}
