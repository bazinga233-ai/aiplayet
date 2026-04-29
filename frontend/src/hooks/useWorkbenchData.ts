import { startTransition, useCallback, useEffect, useMemo, useState } from "react";

import {
  createHighlightTask,
  createTask,
  createOptimizeTask,
  createScoreTask,
  deleteResults as requestDeleteResults,
  deleteVideo as requestDeleteVideo,
  fetchHealth,
  fetchResults,
  fetchTasks,
  fetchVideos,
  runAllTasks,
  uploadScript,
  uploadVideo,
} from "../api/client";
import type { ResultPayload, TaskItem, VideoItem } from "../types";

const POLL_INTERVAL_MS = 2000;

function sortVideos(videos: VideoItem[]) {
  return [...videos].sort((left, right) => right.video_name.localeCompare(left.video_name, "zh-CN"));
}

function pickMostRelevantTask(tasks: TaskItem[]) {
  const runningTask = [...tasks].reverse().find((task) => task.status === "running");
  if (runningTask) {
    return runningTask;
  }

  const queuedTask = [...tasks].reverse().find((task) => task.status === "queued");
  if (queuedTask) {
    return queuedTask;
  }

  return tasks.length > 0 ? tasks[tasks.length - 1] : null;
}

type RefreshOptions = {
  suppressAutoSelect?: boolean;
};

export function useWorkbenchData() {
  const [health, setHealth] = useState<Awaited<ReturnType<typeof fetchHealth>> | null>(null);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
  const [selectedResult, setSelectedResult] = useState<ResultPayload | null>(null);
  const [allowAutoSelect, setAllowAutoSelect] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selectedVideo = useMemo(
    () => videos.find((item) => item.video_id === selectedVideoId) ?? null,
    [selectedVideoId, videos],
  );

  const currentTask = useMemo(() => {
    if (!selectedVideoId) {
      return tasks.find((task) => task.status === "running") ?? null;
    }

    const matching = tasks.filter((task) => task.video_id === selectedVideoId);
    return pickMostRelevantTask(matching);
  }, [selectedVideoId, tasks]);

  const latestScoreTask = useMemo(() => {
    if (!selectedVideoId) {
      return null;
    }

    const matching = tasks.filter(
      (task) => task.video_id === selectedVideoId && task.task_type === "score",
    );
    return matching.length > 0 ? matching[matching.length - 1] : null;
  }, [selectedVideoId, tasks]);

  const latestHighlightTask = useMemo(() => {
    if (!selectedVideoId) {
      return null;
    }

    const matching = tasks.filter(
      (task) => task.video_id === selectedVideoId && task.task_type === "highlight",
    );
    return matching.length > 0 ? matching[matching.length - 1] : null;
  }, [selectedVideoId, tasks]);

  const latestOptimizeTask = useMemo(() => {
    if (!selectedVideoId) {
      return null;
    }

    const matching = tasks.filter(
      (task) => task.video_id === selectedVideoId && task.task_type === "optimize",
    );
    return matching.length > 0 ? matching[matching.length - 1] : null;
  }, [selectedVideoId, tasks]);

  const refreshNow = useCallback(async (options?: RefreshOptions) => {
    try {
      const [nextHealth, nextVideosPayload, nextTasksPayload] = await Promise.all([
        fetchHealth(),
        fetchVideos(),
        fetchTasks(),
      ]);

      const nextVideos = sortVideos(nextVideosPayload.items);
      const nextTasks = nextTasksPayload.items;

      startTransition(() => {
        setHealth(nextHealth);
        setVideos(nextVideos);
        setTasks(nextTasks);
        setError(null);
        setLoading(false);
      });

      const fallbackVideoId =
        selectedVideoId && nextVideos.some((item) => item.video_id === selectedVideoId)
          ? selectedVideoId
          : allowAutoSelect && !options?.suppressAutoSelect
            ? nextVideos[0]?.video_id ?? null
            : null;

      if (fallbackVideoId !== selectedVideoId) {
        startTransition(() => {
          setSelectedVideoId(fallbackVideoId);
        });
      }

      const activeVideoId = fallbackVideoId ?? selectedVideoId;
      const activeVideo = nextVideos.find((item) => item.video_id === activeVideoId) ?? null;

      if (activeVideo?.output_ready) {
        const result = await fetchResults(activeVideo.video_id);
        startTransition(() => {
          setSelectedResult(result);
        });
      } else {
        startTransition(() => {
          setSelectedResult(null);
        });
      }
    } catch (refreshError) {
      startTransition(() => {
        setLoading(false);
        setError(refreshError instanceof Error ? refreshError.message : "加载失败");
      });
    }
  }, [allowAutoSelect, selectedVideoId]);

  const selectVideo = useCallback((videoId: string | null) => {
    startTransition(() => {
      setAllowAutoSelect(true);
      setSelectedVideoId(videoId);
    });
  }, []);

  useEffect(() => {
    void refreshNow();
    const timer = window.setInterval(() => {
      void refreshNow();
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [refreshNow]);

  const queueVideo = useCallback(
    async (videoId: string) => {
      await createTask(videoId);
      await refreshNow();
      selectVideo(videoId);
    },
    [refreshNow, selectVideo],
  );

  const uploadAndQueue = useCallback(
    async (file: File, persist: boolean, assetType: "video" | "script") => {
      const uploaded = assetType === "script" ? await uploadScript(file, persist) : await uploadVideo(file, persist);
      await createTask(uploaded.video_id);
      await refreshNow();
      selectVideo(uploaded.video_id);
    },
    [refreshNow, selectVideo],
  );

  const queueAll = useCallback(async () => {
    await runAllTasks();
    await refreshNow();
  }, [refreshNow]);

  const runScore = useCallback(
    async (videoId: string) => {
      await createScoreTask(videoId);
      await refreshNow();
      selectVideo(videoId);
    },
    [refreshNow, selectVideo],
  );

  const runHighlight = useCallback(
    async (videoId: string) => {
      await createHighlightTask(videoId);
      await refreshNow();
      selectVideo(videoId);
    },
    [refreshNow, selectVideo],
  );

  const optimizeScript = useCallback(
    async (videoId: string) => {
      await createOptimizeTask(videoId);
      await refreshNow();
      selectVideo(videoId);
    },
    [refreshNow, selectVideo],
  );

  const deleteResults = useCallback(
    async (videoId: string) => {
      await requestDeleteResults(videoId);
      await refreshNow();
    },
    [refreshNow],
  );

  const deleteVideo = useCallback(
    async (videoId: string) => {
      await requestDeleteVideo(videoId);

      if (selectedVideoId === videoId) {
        startTransition(() => {
          setAllowAutoSelect(false);
          setSelectedVideoId(null);
          setSelectedResult(null);
        });
        await refreshNow({ suppressAutoSelect: true });
        return;
      }

      await refreshNow();
    },
    [refreshNow, selectedVideoId],
  );

  return {
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
    loading,
    error,
    setSelectedVideoId: selectVideo,
    refreshNow,
    queueVideo,
    uploadAndQueue,
    queueAll,
    runHighlight,
    runScore,
    optimizeScript,
    deleteResults,
    deleteVideo,
  };
}
