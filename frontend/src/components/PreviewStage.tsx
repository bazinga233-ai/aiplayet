import { mediaUrl } from "../api/client";
import type { ResultPayload, TaskItem, VideoItem } from "../types";

type PreviewStageProps = {
  video: VideoItem | null;
  result?: ResultPayload | null;
  task: TaskItem | null;
  onQueue: (videoId: string) => Promise<void> | void;
};

export function PreviewStage({ video, result = null, task, onQueue }: PreviewStageProps) {
  const isScript = video?.asset_type === "script";
  const previewScript = isScript && result ? result.original_script ?? result.script : null;
  const previewScriptLabel = result?.original_script ? "原剧本预览" : "当前剧本预览";
  const taskTypeLabel = task
    ? task.task_type === "score"
      ? "评分任务"
      : task.task_type === "highlight"
        ? "爆款预测任务"
        : task.task_type === "optimize"
          ? "优化任务"
          : "生成任务"
    : null;
  const taskLabel = task ? `${taskTypeLabel} / ${task.status} / ${task.stage}` : "尚未入队";
  const stageHint = !video
    ? "先在左侧选择素材，主舞台会切到所选内容。"
    : video.output_ready
      ? isScript
        ? "中间主舞台显示原剧本，右侧剧本标签可切到最新优化版或原剧本。"
        : "当前视频已经有结果，右侧可以直接查看剧本、爆款预测器和评分。"
      : task?.status === "running" || task?.status === "queued"
        ? "任务正在处理中，结果区会随阶段推进持续刷新。"
        : isScript
          ? "点击下方按钮开始爆款预测，之后可以继续优化剧本。"
          : "点击下方按钮开始处理，系统会自动生成基础剧本并补充后续结果。";
  const previewStatusLabel = !video
    ? "等待选择"
    : video.output_ready
      ? "结果可查看"
      : task?.status === "running"
        ? "处理中"
        : task?.status === "queued"
          ? "已排队"
          : "待开始";
  const previewStatusTone = !video
    ? "idle"
    : video.output_ready
      ? "completed"
      : task?.status === "running"
        ? "running"
        : task?.status === "queued"
          ? "queued"
          : "idle";

  return (
    <section className="panel preview-stage">
      <div className="panel-head preview-stage-head">
        <div>
          <h2>{video?.display_stem ?? "选择一个素材查看详情"}</h2>
        </div>
        <span className={`status-pill status-${previewStatusTone} preview-status-pill`}>{previewStatusLabel}</span>
      </div>
      <p className="preview-stage-copy">{stageHint}</p>

      <div className="preview-frame" data-height-mode="viewport-compact" data-testid="preview-frame">
        {video && !isScript ? (
          <div className="preview-viewport" data-testid="preview-viewport" data-layout="fill">
            <video key={video.video_id} controls preload="metadata" src={mediaUrl(video.video_id)} />
          </div>
        ) : video && previewScript ? (
          <div className="preview-viewport preview-viewport-script" data-testid="preview-viewport" data-layout="fill">
            <div className="preview-script-shell" data-testid="preview-script-shell" data-scrollable="true">
              <div className="preview-script-head">
                <strong>{previewScriptLabel}</strong>
                <span>{video.display_name}</span>
              </div>
              <pre className="preview-script">{previewScript}</pre>
            </div>
          </div>
        ) : video ? (
          <div className="preview-viewport" data-testid="preview-viewport" data-layout="fill">
            <div className="empty-preview">
              <strong>剧本任务预览</strong>
              <span>{video.display_name}</span>
              <span>{task?.status === "running" ? "正在进行爆款预测或优化。" : "当前还没有可展示的剧本文本。"}</span>
            </div>
          </div>
        ) : (
          <div className="preview-viewport" data-testid="preview-viewport" data-layout="fill">
            <div className="empty-preview">中间主舞台会在这里同步展示视频或剧本任务状态。</div>
          </div>
        )}
      </div>

      <div className="preview-metadata" data-density="compact-adaptive">
        <div>
          <span className="meta-label">来源</span>
          <strong>{video ? `${video.asset_type === "script" ? "剧本" : "视频"} · ${video.source_type === "catalog" ? "历史素材" : "新上传"}` : "未选择"}</strong>
        </div>
        <div>
          <span className="meta-label">当前任务</span>
          <strong>{taskLabel}</strong>
        </div>
        <div>
          <span className="meta-label">结果状态</span>
          <strong>{video?.output_ready ? "可查看" : isScript ? "尚未预测" : "尚未生成"}</strong>
        </div>
      </div>

      {video ? (
        <button className="primary-button" onClick={() => void onQueue(video.video_id)}>
          {isScript ? "重新做爆款预测" : "处理当前视频"}
        </button>
      ) : null}
    </section>
  );
}
