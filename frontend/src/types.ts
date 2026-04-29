export type HealthPathEntry = {
  path: string;
  exists: boolean;
};

export type HealthPayload = {
  backend: string;
  paths: Record<string, HealthPathEntry>;
};

export type VideoItem = {
  video_id: string;
  video_name: string;
  video_path: string;
  stored_name: string;
  display_name: string;
  display_stem: string;
  has_output: boolean;
  output_ready: boolean;
  source_type: string;
  asset_type: "video" | "script";
};

export type TaskStage =
  | "queued"
  | "asr"
  | "segmenting"
  | "multimodal"
  | "merging"
  | "highlighting"
  | "optimizing"
  | "scoring"
  | "done"
  | "failed";

export type TaskStatus = "queued" | "running" | "completed" | "failed";

export type TaskItem = {
  task_id: string;
  video_id: string;
  video_name: string;
  video_path: string;
  source_type: string;
  task_type: "generate" | "highlight" | "score" | "optimize";
  parent_task_id: string | null;
  status: TaskStatus;
  stage: TaskStage;
  stage_progress: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  logs_tail: string[];
  stage_current: number | null;
  stage_total: number | null;
};

export type EmotionPoint = {
  time: number;
  tension: number;
  risk: number;
};

export type PredictionWindow = {
  start: number;
  end: number;
  kind: string;
  reason: string;
  suggestion: string;
  confidence: number;
};

export type BestOpportunity = {
  start: number;
  end: number;
  kind: string;
  reason: string;
  suggestion: string;
  confidence: number;
};

export type HighlightPayload = {
  version: number;
  video_id: string;
  video_name: string;
  task_id: string;
  parent_task_id: string | null;
  generated_at: string;
  model: {
    base_url: string;
    model_name: string;
  };
  summary: string;
  breakout_score: number;
  position_mode: "time" | "beat";
  emotion_curve: EmotionPoint[];
  risk_windows: PredictionWindow[];
  opportunity_windows: PredictionWindow[];
  best_opportunity: BestOpportunity | null;
};

export type ScoreDimension = {
  key: string;
  label: string;
  score: number;
  max_score: number;
  reason: string;
};

export type ScorePayload = {
  version: number;
  video_id: string;
  video_name: string;
  task_id: string;
  parent_task_id: string | null;
  generated_at: string;
  model: {
    base_url: string;
    model_name: string;
  };
  total_score: number;
  summary: string;
  dimensions: ScoreDimension[];
};

export type ResultPayload = {
  video: VideoItem;
  dialogues: Array<Record<string, unknown>>;
  segments: Array<Record<string, unknown>>;
  script: string;
  original_script: string | null;
  asset_type: "video" | "script";
  highlights: HighlightPayload | null;
  score: ScorePayload | null;
  media_url: string | null;
};

export type WorkbenchSnapshot = {
  health: HealthPayload | null;
  videos: VideoItem[];
  tasks: TaskItem[];
  selectedVideoId: string | null;
  selectedVideo: VideoItem | null;
  selectedResult: ResultPayload | null;
  currentTask: TaskItem | null;
  loading: boolean;
  error: string | null;
};
