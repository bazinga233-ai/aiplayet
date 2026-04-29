import type { HealthPayload, ResultPayload, TaskItem, VideoItem } from "../types";

type JsonHeaders = Record<string, string>;

async function readJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function fetchHealth() {
  return readJson<HealthPayload>("/api/health");
}

export async function fetchVideos() {
  return readJson<{ items: VideoItem[] }>("/api/videos");
}

export async function fetchTasks() {
  return readJson<{ items: TaskItem[] }>("/api/tasks");
}

export async function fetchTask(taskId: string) {
  return readJson<TaskItem>(`/api/tasks/${taskId}`);
}

export async function uploadVideo(file: File, persist: boolean) {
  const formData = new FormData();
  formData.append("file", file);
  return readJson<VideoItem>(`/api/uploads?persist=${persist}`, {
    method: "POST",
    body: formData,
  });
}

export async function uploadScript(file: File, persist: boolean) {
  const formData = new FormData();
  formData.append("file", file);
  return readJson<VideoItem>(`/api/script-uploads?persist=${persist}`, {
    method: "POST",
    body: formData,
  });
}

export async function createTask(videoId: string) {
  const headers: JsonHeaders = { "Content-Type": "application/json" };
  return readJson<TaskItem>("/api/tasks", {
    method: "POST",
    headers,
    body: JSON.stringify({ video_id: videoId }),
  });
}

export async function createScoreTask(videoId: string) {
  return readJson<TaskItem>(`/api/tasks/${videoId}/score`, {
    method: "POST",
  });
}

export async function createHighlightTask(videoId: string) {
  return readJson<TaskItem>(`/api/tasks/${videoId}/highlight`, {
    method: "POST",
  });
}

export async function createOptimizeTask(videoId: string) {
  return readJson<TaskItem>(`/api/tasks/${videoId}/optimize`, {
    method: "POST",
  });
}

export async function runAllTasks() {
  return readJson<{ enqueued: number }>("/api/tasks/run-all", {
    method: "POST",
  });
}

export async function fetchResults(videoId: string) {
  return readJson<ResultPayload>(`/api/results/${videoId}`);
}

export async function deleteResults(videoId: string) {
  return readJson<{ deleted: string; video_id: string; video_name: string }>(`/api/results/${videoId}`, {
    method: "DELETE",
  });
}

export async function deleteVideo(videoId: string) {
  return readJson<{ deleted: string; video_id: string; video_name: string }>(`/api/videos/${videoId}`, {
    method: "DELETE",
  });
}

export function mediaUrl(videoId: string) {
  return `/api/media/${videoId}`;
}
