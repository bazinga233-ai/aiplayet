import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

const BASE_WIDTH = 1600;
const BASE_HEIGHT = 960;
const MIN_SCALE = 0.82;
const MAX_SCALE = 1.08;

type WorkbenchScaleTier = "compact" | "balanced" | "expanded";

type WorkbenchScaleState = {
  tier: WorkbenchScaleTier;
  style: CSSProperties;
};

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function px(value: number) {
  return `${Math.round(value)}px`;
}

function calculateWorkbenchScale(width: number, height: number): WorkbenchScaleState {
  const widthRatio = width / BASE_WIDTH;
  const heightRatio = height / BASE_HEIGHT;
  const uiScale = clamp(Math.min(widthRatio, heightRatio), MIN_SCALE, MAX_SCALE);
  const tier: WorkbenchScaleTier = uiScale < 0.94 ? "compact" : uiScale > 1.02 ? "expanded" : "balanced";

  const shellPadding = clamp(28 * uiScale, 16, 30);
  const layoutGap = clamp(18 * uiScale, 12, 22);
  const tightGap = clamp(12 * uiScale, 8, 14);
  const panelPadding = clamp(20 * uiScale, 16, 24);
  const panelRadius = clamp(26 * uiScale, 20, 28);
  const topBarGap = clamp(20 * uiScale, 12, 22);
  const topBarPaddingY = clamp(22 * uiScale, 14, 24);
  const topBarPaddingX = clamp(24 * uiScale, 16, 28);
  const topBarRadius = clamp(28 * uiScale, 22, 30);
  const leftColumnMin = clamp(286 * uiScale, 236, 310);
  const resultColumnMin = clamp(360 * uiScale, 300, 390);
  const topBarCenterMin = clamp(340 * uiScale, 280, 380);
  const statusCardMin = clamp(90 * uiScale, 78, 108);
  const resultActionCardMin = clamp(162 * uiScale, 150, 176);
  const previewFrameHeight = clamp(height - 360 * uiScale, 420, 760);
  const previewFrameInnerPadding = clamp(12 * uiScale, 10, 16);
  const previewMetaPaddingY = clamp(14 * uiScale, 10, 16);
  const previewMetaPaddingX = clamp(15 * uiScale, 12, 18);
  const scriptViewerMinHeight = clamp(previewFrameHeight * 0.56, 240, 420);
  const scriptViewerMaxHeight = clamp(previewFrameHeight * 0.9, 360, 640);
  const headingSize = clamp(34 * uiScale, 26, 38);
  const sectionHeadingSize = clamp(28 * uiScale, 24, 35);
  const bodyCopySize = clamp(14.5 * uiScale, 13, 16);
  const noteSize = clamp(14 * uiScale, 12.5, 15);
  const statusValueSize = clamp(19 * uiScale, 16, 21);
  const panelToggleTitleSize = clamp(19 * uiScale, 17, 21);
  const queueTitleSize = clamp(16.8 * uiScale, 15, 18);
  const uploadTitleSize = clamp(18.9 * uiScale, 16, 20);
  const featuredTitleSize = clamp(20.5 * uiScale, 18, 22);
  const scoreTotalSize = clamp(35 * uiScale, 30, 38);

  return {
    tier,
    style: {
      "--ui-scale": uiScale.toFixed(3),
      "--app-shell-padding": px(shellPadding),
      "--layout-gap": px(layoutGap),
      "--tight-gap": px(tightGap),
      "--panel-padding": px(panelPadding),
      "--panel-radius": px(panelRadius),
      "--topbar-gap": px(topBarGap),
      "--topbar-padding-y": px(topBarPaddingY),
      "--topbar-padding-x": px(topBarPaddingX),
      "--topbar-radius": px(topBarRadius),
      "--topbar-center-min": px(topBarCenterMin),
      "--left-column-min": px(leftColumnMin),
      "--result-column-min": px(resultColumnMin),
      "--status-card-min": px(statusCardMin),
      "--result-action-card-min": px(resultActionCardMin),
      "--preview-frame-height": px(previewFrameHeight),
      "--preview-frame-padding": px(previewFrameInnerPadding),
      "--preview-meta-padding-y": px(previewMetaPaddingY),
      "--preview-meta-padding-x": px(previewMetaPaddingX),
      "--script-viewer-min-height": px(scriptViewerMinHeight),
      "--script-viewer-max-height": px(scriptViewerMaxHeight),
      "--heading-size": px(headingSize),
      "--section-heading-size": px(sectionHeadingSize),
      "--body-copy-size": px(bodyCopySize),
      "--note-size": px(noteSize),
      "--status-value-size": px(statusValueSize),
      "--panel-toggle-title-size": px(panelToggleTitleSize),
      "--queue-title-size": px(queueTitleSize),
      "--upload-title-size": px(uploadTitleSize),
      "--featured-title-size": px(featuredTitleSize),
      "--score-total-size": px(scoreTotalSize),
    } as CSSProperties,
  };
}

function readViewportScale() {
  if (typeof window === "undefined") {
    return calculateWorkbenchScale(BASE_WIDTH, BASE_HEIGHT);
  }
  return calculateWorkbenchScale(window.innerWidth, window.innerHeight);
}

export function useWorkbenchScale() {
  const [scaleState, setScaleState] = useState<WorkbenchScaleState>(() => readViewportScale());

  useEffect(() => {
    const handleResize = () => {
      setScaleState(readViewportScale());
    };

    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  return scaleState;
}
