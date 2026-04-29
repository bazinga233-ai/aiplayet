import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test } from "vitest";

import { QueuePanel } from "./QueuePanel";

afterEach(() => {
  cleanup();
});

function createVideoItem(index: number) {
  return {
    video_id: `video-${index}`,
    video_name: `${index}`,
    video_path: `videos/${index}.mp4`,
    stored_name: `${index}.mp4`,
    display_name: `${index}.mp4`,
    display_stem: `${index}`,
    has_output: index % 2 === 0,
    output_ready: index % 2 === 0,
    source_type: "catalog" as const,
    asset_type: "video" as const,
  };
}

test("paginates the expanded queue history to three items per page", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <QueuePanel
      items={Array.from({ length: 10 }, (_, index) => createVideoItem(index + 1))}
      tasks={[]}
      selectedId={null}
      onSelect={() => {}}
      onQueue={() => {}}
      onDeleteResults={() => {}}
      onDeleteVideo={() => {}}
    />,
  );

  const queueList = screen.getByTestId("queue-list");
  expect(queueList).toHaveAttribute("role", "list");
  expect(container.querySelector(".queue-meta")).toBeNull();
  expect(screen.getByText("第 1 / 4 页")).toBeInTheDocument();

  const firstItem = within(queueList).getByText("1").closest(".queue-item");
  expect(firstItem).not.toBeNull();
  expect(within(firstItem as HTMLElement).getByRole("button", { name: "开始处理" })).toBeInTheDocument();
  const completedItem = within(queueList).getByText("2").closest(".queue-item");
  expect(completedItem).not.toBeNull();
  const completedStatusPill = within(completedItem as HTMLElement).getByText("已有结果");
  expect(completedStatusPill).toHaveClass("queue-status-pill");
  expect(within(queueList).getByText("3")).toBeInTheDocument();
  expect(within(queueList).queryByText("4")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "下一页" }));

  expect(screen.getByText("第 2 / 4 页")).toBeInTheDocument();
  expect(within(queueList).getByText("4")).toBeInTheDocument();
  expect(within(queueList).getByText("5")).toBeInTheDocument();
  expect(within(queueList).getByText("6")).toBeInTheDocument();
  expect(within(queueList).queryByText("3")).not.toBeInTheDocument();
});

test("allows manual page navigation even when a later-page item is selected", async () => {
  const user = userEvent.setup();

  render(
    <QueuePanel
      items={Array.from({ length: 10 }, (_, index) => createVideoItem(index + 1))}
      tasks={[]}
      selectedId="video-5"
      onSelect={() => {}}
      onQueue={() => {}}
      onDeleteResults={() => {}}
      onDeleteVideo={() => {}}
    />,
  );

  const queueList = screen.getByTestId("queue-list");
  await screen.findByText("第 2 / 4 页");
  expect(within(queueList).getByText("4")).toBeInTheDocument();
  expect(within(queueList).getByText("5")).toBeInTheDocument();
  expect(within(queueList).getByText("6")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "上一页" }));

  expect(screen.getByText("第 1 / 4 页")).toBeInTheDocument();
  expect(within(queueList).getByText("1")).toBeInTheDocument();
  expect(within(queueList).getByText("2")).toBeInTheDocument();
  expect(within(queueList).getByText("3")).toBeInTheDocument();
  expect(within(queueList).queryByText("4")).not.toBeInTheDocument();
});

test("keeps the manual page after parent rerenders with a fresh items array", async () => {
  const user = userEvent.setup();
  const initialItems = Array.from({ length: 10 }, (_, index) => createVideoItem(index + 1));
  const { rerender } = render(
    <QueuePanel
      items={initialItems}
      tasks={[]}
      selectedId="video-5"
      onSelect={() => {}}
      onQueue={() => {}}
      onDeleteResults={() => {}}
      onDeleteVideo={() => {}}
    />,
  );

  const queueList = screen.getByTestId("queue-list");
  await screen.findByText("第 2 / 4 页");

  await user.click(screen.getByRole("button", { name: "上一页" }));
  expect(screen.getByText("第 1 / 4 页")).toBeInTheDocument();
  expect(within(queueList).getByText("1")).toBeInTheDocument();

  rerender(
    <QueuePanel
      items={Array.from({ length: 10 }, (_, index) => createVideoItem(index + 1))}
      tasks={[]}
      selectedId="video-5"
      onSelect={() => {}}
      onQueue={() => {}}
      onDeleteResults={() => {}}
      onDeleteVideo={() => {}}
    />,
  );

  expect(screen.getByText("第 1 / 4 页")).toBeInTheDocument();
  expect(within(queueList).getByText("1")).toBeInTheDocument();
  expect(within(queueList).getByText("2")).toBeInTheDocument();
  expect(within(queueList).getByText("3")).toBeInTheDocument();
  expect(within(queueList).queryByText("4")).not.toBeInTheDocument();
});

test("compresses pagination when there are many pages", async () => {
  render(
    <QueuePanel
      items={Array.from({ length: 30 }, (_, index) => createVideoItem(index + 1))}
      tasks={[]}
      selectedId="video-16"
      onSelect={() => {}}
      onQueue={() => {}}
      onDeleteResults={() => {}}
      onDeleteVideo={() => {}}
    />,
  );

  await screen.findByText("第 6 / 10 页");
  expect(screen.getByRole("button", { name: "1" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "5" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "6" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("button", { name: "7" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "10" })).toBeInTheDocument();
  expect(screen.getAllByText("...")).toHaveLength(2);
  expect(screen.queryByRole("button", { name: "2" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "9" })).not.toBeInTheDocument();
});
