import type { HealthPayload, TaskItem } from "../types";

type TopBarProps = {
  health: HealthPayload | null;
  tasks: TaskItem[];
  onRunAll: () => Promise<void> | void;
  onRefresh: () => Promise<void> | void;
};

function countByStatus(tasks: TaskItem[], status: TaskItem["status"]) {
  return tasks.filter((task) => task.status === status).length;
}

export function TopBar({ health, tasks, onRunAll, onRefresh }: TopBarProps) {
  const runningCount = countByStatus(tasks, "running");
  const queuedCount = countByStatus(tasks, "queued");
  const failedCount = countByStatus(tasks, "failed");
  const backendReady = health?.backend === "ok";

  return (
    <header className="top-bar" data-density="adaptive">
      <div className="top-bar-intro">
        <div className="title-cluster">
          <p className="eyebrow">Story Craft Studio</p>
          <div>
            <h1>短剧反推与情绪预测工作台</h1>
            <p className="subcopy">上传短剧视频，反推剧情结构，查看评分、爆款预测器与情绪预测结果。</p>
          </div>
        </div>
        <div className="top-bar-note">
          <span className={`signal-dot ${backendReady ? "is-online" : "is-offline"}`} aria-hidden="true" />
          <span>{backendReady ? "工作台已就绪，可直接开始处理。" : "服务未就绪，先检查后台连接。"}</span>
        </div>
      </div>

      <div className="top-bar-center">
        <div className="top-bar-status-caption">
          <span>当前概览</span>
          <small>把最关键的状态压成一排，主操作始终留在右侧。</small>
        </div>
        <div className="top-bar-status">
          <div className="status-card">
            <span className="status-label">工作台</span>
            <strong>{backendReady ? "在线" : "未就绪"}</strong>
          </div>
          <div className="status-card">
            <span className="status-label">待处理</span>
            <strong>{queuedCount}</strong>
          </div>
          <div className="status-card">
            <span className="status-label">处理中</span>
            <strong>{runningCount}</strong>
          </div>
          <div className="status-card">
            <span className="status-label">异常</span>
            <strong>{failedCount}</strong>
          </div>
        </div>
      </div>

      <div className="top-bar-actions">
        <button className="secondary-button" onClick={() => void onRefresh()}>
          刷新
        </button>
        <button className="primary-button" onClick={() => void onRunAll()}>
          跑全部
        </button>
      </div>
    </header>
  );
}
