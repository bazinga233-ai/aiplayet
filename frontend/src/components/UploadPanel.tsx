import { useId, useRef, useState } from "react";

type UploadPanelProps = {
  onUpload: (file: File, persist: boolean, assetType: "video" | "script") => Promise<void> | void;
};

function isAcceptedFile(file: File, assetType: "video" | "script") {
  const lowerName = file.name.toLowerCase();
  if (assetType === "script") {
    return file.type === "text/plain" || lowerName.endsWith(".txt");
  }
  return file.type === "video/mp4" || lowerName.endsWith(".mp4");
}

function rejectionMessage(assetType: "video" | "script") {
  return assetType === "script"
    ? "当前模式仅支持 txt 剧本，请切换后再拖入。"
    : "当前模式仅支持 mp4 视频，请切换后再拖入。";
}

export function UploadPanel({ onUpload }: UploadPanelProps) {
  const fileInputId = useId();
  const persistId = useId();
  const tempId = useId();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [assetType, setAssetType] = useState<"video" | "script">("video");
  const [persist, setPersist] = useState(true);
  const [pending, setPending] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const [dropNotice, setDropNotice] = useState<string | null>(null);

  const clearSelectedFile = () => {
    setFile(null);
    setDropNotice(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleIncomingFile = (nextFile: File | null) => {
    if (!nextFile) {
      return;
    }

    if (!isAcceptedFile(nextFile, assetType)) {
      setDropNotice(rejectionMessage(assetType));
      return;
    }

    setDropNotice(null);
    setFile(nextFile);
  };

  const handleSubmit = async () => {
    if (!file) {
      return;
    }

    setPending(true);
    try {
      await onUpload(file, persist, assetType);
      clearSelectedFile();
    } finally {
      setPending(false);
    }
  };

  const isScript = assetType === "script";
  const accept = isScript ? ".txt,text/plain" : "video/mp4";
  const pickerLabel = isScript ? "选择剧本" : "选择视频";
  const dropLabel = isScript ? "拖入或选择 txt 剧本" : "拖入或选择 mp4 视频";
  const dropTitle = file ? file.name : "把素材放进来，下一步就能开始处理";
  const dropHint = file
    ? isScript
      ? "确认后会自动上传，并立即开始爆款预测。"
      : "确认后会自动上传并入队处理。"
    : isScript
      ? "上传后会直接进入爆款预测，之后可以手动优化剧本。"
      : "上传后会直接入队，你也可以选择长期保存或临时处理。";
  const fileHint = file
    ? "已选中，可直接点击下方开始处理。"
    : isScript
      ? "也可以直接把 txt 剧本拖到上方区域。"
      : "也可以直接把视频拖到上方区域。";

  return (
    <section className="panel upload-panel">
      <div className="panel-head">
        <p className="panel-kicker">新建任务</p>
        <h2>上传素材</h2>
      </div>

      <div className="tab-row upload-kind-tabs" role="tablist" aria-label="上传素材类型">
        <button
          className={`tab-button ${assetType === "video" ? "is-active" : ""}`}
          onClick={() => {
            setAssetType("video");
            clearSelectedFile();
          }}
          role="tab"
          aria-selected={assetType === "video"}
          type="button"
        >
          视频 MP4
        </button>
        <button
          className={`tab-button ${assetType === "script" ? "is-active" : ""}`}
          onClick={() => {
            setAssetType("script");
            clearSelectedFile();
          }}
          role="tab"
          aria-selected={assetType === "script"}
          type="button"
        >
          剧本 TXT
        </button>
      </div>

      <div
        className={`upload-dropzone ${isDragActive ? "is-drag-active" : ""}`}
        data-testid="upload-dropzone"
        onDragEnter={(event) => {
          event.preventDefault();
          setIsDragActive(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) {
            return;
          }
          setIsDragActive(false);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
          setIsDragActive(true);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragActive(false);
          handleIncomingFile(event.dataTransfer.files?.[0] ?? null);
        }}
      >
        <input
          id={fileInputId}
          ref={fileInputRef}
          className="upload-dropzone-input"
          type="file"
          accept={accept}
          onChange={(event) => {
            handleIncomingFile(event.target.files?.[0] ?? null);
          }}
        />
        <label className="upload-dropzone-surface" htmlFor={fileInputId}>
          <span className="upload-dropzone-label">{file ? "已选择素材" : dropLabel}</span>
          <strong className="upload-dropzone-title">{dropTitle}</strong>
          <small>{dropHint}</small>
        </label>
        <div className="upload-dropzone-actions">
          <button
            type="button"
            className="secondary-button upload-dropzone-picker"
            onClick={() => fileInputRef.current?.click()}
          >
            {pickerLabel}
          </button>
          <span className="upload-dropzone-filehint">
            {fileHint}
          </span>
        </div>
        {dropNotice ? <p className="upload-dropzone-notice">{dropNotice}</p> : null}
      </div>

      <div className="mode-toggle" role="radiogroup" aria-label="上传模式">
        <label htmlFor={persistId}>
          <input
            id={persistId}
            type="radio"
            checked={persist}
            onChange={() => setPersist(true)}
          />
          长期保存
        </label>
        <label htmlFor={tempId}>
          <input
            id={tempId}
            type="radio"
            checked={!persist}
            onChange={() => setPersist(false)}
          />
          临时处理
        </label>
      </div>

      <button
        className="primary-button block-button"
        disabled={!file || pending}
        onClick={() => void handleSubmit()}
      >
        {pending ? "上传中..." : "上传并开始处理"}
      </button>
    </section>
  );
}
