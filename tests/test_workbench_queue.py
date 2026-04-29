import unittest

from backend.log_parser import parse_progress_line
from backend.task_queue import TaskQueue, TaskState


class WorkbenchLogParserTests(unittest.TestCase):
    def test_parse_highlighting_progress_line(self):
        update = parse_progress_line("[Step Highlight] 正在识别视频高光")

        self.assertIsNotNone(update)
        self.assertEqual(update.stage, "highlighting")

    def test_parse_multimodal_progress_line(self):
        update = parse_progress_line("  分析视频片段 [6/11] 135.00s-165.00s ...")

        self.assertIsNotNone(update)
        self.assertEqual(update.stage, "multimodal")
        self.assertEqual(update.current, 6)
        self.assertEqual(update.total, 11)

    def test_parse_scoring_progress_line(self):
        update = parse_progress_line("[Step Score] 正在进行剧本评分")

        self.assertIsNotNone(update)
        self.assertEqual(update.stage, "scoring")

    def test_parse_optimizing_progress_line(self):
        update = parse_progress_line("[Step Optimize] 正在根据评分优化剧本")

        self.assertIsNotNone(update)
        self.assertEqual(update.stage, "optimizing")


class WorkbenchTaskStateTests(unittest.TestCase):
    def test_task_state_starts_queued(self):
        task = TaskState(
            task_id="t1",
            video_id="v1",
            video_name="demo",
            video_path="demo.mp4",
        )

        self.assertEqual(task.status, "queued")
        self.assertEqual(task.stage, "queued")

    def test_queue_records_enqueued_tasks(self):
        queue = TaskQueue(
            video_lookup=lambda video_id: None,
            video_catalog=lambda: [],
            runner=lambda task, on_line: 0,
        )
        task = TaskState(
            task_id="t1",
            video_id="v1",
            video_name="demo",
            video_path="demo.mp4",
        )

        queue.enqueue(task)

        self.assertEqual(queue.current_task_id, None)
        self.assertEqual([item.task_id for item in queue.list_tasks()], ["t1"])

    def test_generate_task_auto_enqueues_highlight_task_only_after_success(self):
        queue = TaskQueue(
            video_lookup=lambda video_id: None,
            video_catalog=lambda: [],
            runner=lambda task, on_line: 0,
            start_immediately=False,
        )
        task = TaskState(
            task_id="t1",
            video_id="v1",
            video_name="demo",
            video_path="demo.mp4",
            task_type="generate",
        )

        queue.enqueue(task)
        queue.mark_running(task)
        queue._run_task(task)

        tasks = queue.list_tasks()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].task_id, "t1")
        self.assertEqual(tasks[0].status, "completed")
        self.assertEqual(tasks[1].task_type, "highlight")
        self.assertEqual(tasks[1].parent_task_id, "t1")
        self.assertEqual(tasks[1].video_id, "v1")
        self.assertEqual(tasks[1].status, "queued")
