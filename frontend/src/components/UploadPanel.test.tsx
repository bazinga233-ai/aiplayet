import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import userEvent from "@testing-library/user-event";

import { UploadPanel } from "./UploadPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("shows an explicit picker button in the upload area", () => {
  render(<UploadPanel onUpload={vi.fn()} />);

  expect(screen.getByRole("button", { name: "选择视频" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "上传并开始处理" })).toBeDisabled();
  expect(screen.getByRole("tab", { name: "剧本 TXT" })).toBeInTheDocument();
});

test("uploads the selected file and clears the chooser state", async () => {
  const user = userEvent.setup();
  const onUpload = vi.fn().mockResolvedValue(undefined);
  const { container } = render(<UploadPanel onUpload={onUpload} />);
  const input = container.querySelector('input[type="file"]') as HTMLInputElement | null;

  expect(input).not.toBeNull();
  if (!input) {
    throw new Error("file input not found");
  }

  const file = new File(["demo"], "demo.mp4", { type: "video/mp4" });
  await user.upload(input, file);

  expect(screen.getByText("demo.mp4")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "上传并开始处理" })).toBeEnabled();

  await user.click(screen.getByRole("button", { name: "上传并开始处理" }));

  await waitFor(() => {
    expect(onUpload).toHaveBeenCalledWith(file, true, "video");
  });
  await waitFor(() => {
    expect(screen.getByText("把素材放进来，下一步就能开始处理")).toBeInTheDocument();
  });
});

test("uploads txt script files in script mode", async () => {
  const user = userEvent.setup();
  const onUpload = vi.fn().mockResolvedValue(undefined);
  const { container } = render(<UploadPanel onUpload={onUpload} />);

  await user.click(screen.getByRole("tab", { name: "剧本 TXT" }));

  const input = container.querySelector('input[type="file"]') as HTMLInputElement | null;
  expect(input).not.toBeNull();
  if (!input) {
    throw new Error("file input not found");
  }

  const file = new File(["第一幕：测试剧本。"], "demo.txt", { type: "text/plain" });
  await user.upload(input, file);
  await user.click(screen.getByRole("button", { name: "上传并开始处理" }));

  await waitFor(() => {
    expect(onUpload).toHaveBeenCalledWith(file, true, "script");
  });
});

test("accepts dropped mp4 files in video mode and uploads them", async () => {
  const user = userEvent.setup();
  const onUpload = vi.fn().mockResolvedValue(undefined);
  render(<UploadPanel onUpload={onUpload} />);

  const dropzone = screen.getByTestId("upload-dropzone");
  const file = new File(["demo"], "drag-demo.mp4", { type: "video/mp4" });

  fireEvent.dragOver(dropzone, {
    dataTransfer: {
      files: [file],
      items: [{ kind: "file", type: file.type, getAsFile: () => file }],
      types: ["Files"],
    },
  });
  fireEvent.drop(dropzone, {
    dataTransfer: {
      files: [file],
      items: [{ kind: "file", type: file.type, getAsFile: () => file }],
      types: ["Files"],
    },
  });

  expect(screen.getByText("drag-demo.mp4")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "上传并开始处理" })).toBeEnabled();

  await user.click(screen.getByRole("button", { name: "上传并开始处理" }));

  await waitFor(() => {
    expect(onUpload).toHaveBeenCalledWith(file, true, "video");
  });
});

test("ignores dropped txt files while staying in video mode", () => {
  const onUpload = vi.fn();
  render(<UploadPanel onUpload={onUpload} />);

  const dropzone = screen.getByTestId("upload-dropzone");
  const file = new File(["第一幕"], "wrong.txt", { type: "text/plain" });

  fireEvent.dragOver(dropzone, {
    dataTransfer: {
      files: [file],
      items: [{ kind: "file", type: file.type, getAsFile: () => file }],
      types: ["Files"],
    },
  });
  fireEvent.drop(dropzone, {
    dataTransfer: {
      files: [file],
      items: [{ kind: "file", type: file.type, getAsFile: () => file }],
      types: ["Files"],
    },
  });

  expect(screen.queryByText("wrong.txt")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "上传并开始处理" })).toBeDisabled();
  expect(screen.getByText("当前模式仅支持 mp4 视频，请切换后再拖入。")).toBeInTheDocument();
});
