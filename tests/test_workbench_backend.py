import contextlib
import shutil
import uuid
from io import BytesIO
from pathlib import Path
import unittest
from unittest import mock

import backend.app as backend_app_module
import backend.server_entry as server_entry_module
from fastapi.testclient import TestClient

from backend import catalog as catalog_module
from backend import uploads as uploads_module
from backend.app import app, create_queue_service
from backend.config import OUTPUT_DIR, TMP_UPLOADS_DIR, VIDEOS_DIR
from backend.fs_cleanup import safe_unlink


@contextlib.contextmanager
def temporary_catalog_fixture(*, asset_type: str = "video", with_score: bool = False, with_highlights: bool = False):
    fixtures_root = Path.cwd() / ".tmp_testfixtures"
    fixtures_root.mkdir(exist_ok=True)
    root = fixtures_root / f"novalai_catalog_{uuid.uuid4().hex}"
    videos_dir = root / "videos"
    scripts_dir = root / "scripts"
    outputs_dir = root / "output"
    videos_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)
    outputs_dir.mkdir()
    if asset_type == "script":
        asset_path = scripts_dir / "01.txt"
        asset_path.write_text("第一幕：原始剧本。", encoding="utf-8")
    else:
        asset_path = videos_dir / "01.mp4"
        asset_path.write_bytes(b"dummy video data")
    output_dir = outputs_dir / "01"
    output_dir.mkdir()
    if asset_type == "video":
        (output_dir / "dialogues.json").write_text("[]", encoding="utf-8")
        (output_dir / "segments.json").write_text("[]", encoding="utf-8")
        (output_dir / "script.txt").write_text("Sample script text.", encoding="utf-8")
    else:
        (output_dir / "script.txt").write_text("第一幕：最新优化版。", encoding="utf-8")
        (output_dir / "script_original.txt").write_text("第一幕：原始剧本。", encoding="utf-8")
    if with_score:
        (output_dir / "score.json").write_text(
            (
                '{"version":1,"video_id":"fixture-video","video_name":"01",'
                '"task_id":"score-01","parent_task_id":"generate-01",'
                '"generated_at":"2026-04-09T08:00:00Z",'
                '"model":{"base_url":"http://example.test/v1","model_name":"demo-model"},'
                '"total_score":82,"summary":"评分摘要",'
                '"dimensions":[{"key":"character","label":"人物","score":7,"max_score":8,"reason":"人物较清楚"}]}'
            ),
            encoding="utf-8",
        )
    if with_highlights:
        (output_dir / "highlights.json").write_text(
            (
                '{"version":1,"video_id":"fixture-video","video_name":"01",'
                '"task_id":"highlight-01","parent_task_id":"generate-01",'
                '"generated_at":"2026-04-09T08:10:00Z",'
                '"model":{"base_url":"http://example.test/v1","model_name":"demo-model"},'
                '"summary":"高光主要集中在中后段。",'
                '"highlights":[{"start":12.0,"end":18.0,"label":"爆点","reason":"第一次反转出现。"},{"start":45.0,"end":53.0,"label":"高潮","reason":"冲突达到峰值。"},{"start":70.0,"end":78.0,"label":"高燃","reason":"情绪和动作同时抬升。"}],'
                '"best_climax":{"start":45.0,"end":53.0,"title":"终极高潮","reason":"核心冲突在这里集中爆发。"}}'
            ),
            encoding="utf-8",
        )

    temp_uploads_dir = root / "tmp_uploads"
    temp_script_uploads_dir = root / "tmp_script_uploads"
    temp_uploads_dir.mkdir()
    temp_script_uploads_dir.mkdir()
    original_videos_root = catalog_module.VIDEOS_ROOT
    original_scripts_root = getattr(catalog_module, "SCRIPTS_ROOT", None)
    original_output_root = catalog_module.OUTPUT_ROOT
    original_tmp_uploads_root = catalog_module.TMP_UPLOADS_ROOT
    original_tmp_script_uploads_root = getattr(catalog_module, "TMP_SCRIPT_UPLOADS_ROOT", None)
    original_uploads_root = uploads_module.TMP_UPLOADS_ROOT
    original_script_uploads_root = getattr(uploads_module, "TMP_SCRIPT_UPLOADS_ROOT", None)
    catalog_module.VIDEOS_ROOT = videos_dir
    if original_scripts_root is not None:
        catalog_module.SCRIPTS_ROOT = scripts_dir
    catalog_module.OUTPUT_ROOT = outputs_dir
    catalog_module.TMP_UPLOADS_ROOT = temp_uploads_dir
    if original_tmp_script_uploads_root is not None:
        catalog_module.TMP_SCRIPT_UPLOADS_ROOT = temp_script_uploads_dir
    uploads_module.TMP_UPLOADS_ROOT = temp_uploads_dir
    if original_script_uploads_root is not None:
        uploads_module.TMP_SCRIPT_UPLOADS_ROOT = temp_script_uploads_dir
    try:
        yield {
            "root": root,
            "video_id": catalog_module.build_video_id(asset_path),
            "video_path": asset_path,
            "output_dir": output_dir,
            "temp_uploads_dir": temp_uploads_dir,
            "asset_type": asset_type,
        }
    finally:
        catalog_module.VIDEOS_ROOT = original_videos_root
        if original_scripts_root is not None:
            catalog_module.SCRIPTS_ROOT = original_scripts_root
        catalog_module.OUTPUT_ROOT = original_output_root
        catalog_module.TMP_UPLOADS_ROOT = original_tmp_uploads_root
        if original_tmp_script_uploads_root is not None:
            catalog_module.TMP_SCRIPT_UPLOADS_ROOT = original_tmp_script_uploads_root
        uploads_module.TMP_UPLOADS_ROOT = original_uploads_root
        if original_script_uploads_root is not None:
            uploads_module.TMP_SCRIPT_UPLOADS_ROOT = original_script_uploads_root
        shutil.rmtree(root, ignore_errors=True)


@contextlib.contextmanager
def temporary_queue_service(*, start_immediately: bool):
    original_queue_service = getattr(app.state, "queue_service", None)
    app.state.queue_service = create_queue_service(start_immediately=start_immediately)
    try:
        yield app.state.queue_service
    finally:
        app.state.queue_service = original_queue_service


@contextlib.contextmanager
def temporary_frontend_dist_fixture():
    fixtures_root = Path.cwd() / ".tmp_testfixtures"
    fixtures_root.mkdir(exist_ok=True)
    root = fixtures_root / f"novalai_frontend_{uuid.uuid4().hex}"
    frontend_dist = root / "frontend_dist"
    frontend_dist.mkdir(parents=True)
    index_html = frontend_dist / "index.html"
    index_html.write_text("<!doctype html><html><body>release frontend</body></html>", encoding="utf-8")
    favicon_svg = frontend_dist / "favicon.svg"
    favicon_svg.write_text(
        (
            "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\">"
            "<rect width=\"64\" height=\"64\" rx=\"16\" fill=\"#1f2937\"/>"
            "<path d=\"M18 46V18h8l12 16V18h8v28h-8L26 30v16z\" fill=\"#f59e0b\"/>"
            "</svg>"
        ),
        encoding="utf-8",
    )
    asset_dir = frontend_dist / "assets"
    asset_dir.mkdir()
    (asset_dir / "app.js").write_text("console.log('frontend');", encoding="utf-8")
    ffmpeg_path = root / "ffmpeg.exe"
    ffmpeg_path.write_text("ffmpeg", encoding="utf-8")
    ffprobe_path = root / "ffprobe.exe"
    ffprobe_path.write_text("ffprobe", encoding="utf-8")

    with contextlib.ExitStack() as stack:
        stack.enter_context(
            mock.patch.object(backend_app_module, "FRONTEND_DIST_DIR", frontend_dist, create=True)
        )
        stack.enter_context(
            mock.patch.object(backend_app_module, "FFMPEG_PATH", str(ffmpeg_path), create=True)
        )
        stack.enter_context(
            mock.patch.object(backend_app_module, "FFPROBE_PATH", str(ffprobe_path), create=True)
        )
        try:
            yield {
                "root": root,
                "frontend_dist": frontend_dist,
                "index_html": index_html,
                "favicon_svg": favicon_svg,
                "ffmpeg_path": ffmpeg_path,
                "ffprobe_path": ffprobe_path,
            }
        finally:
            shutil.rmtree(root, ignore_errors=True)


@contextlib.contextmanager
def temporary_server_entry_fixture():
    fixtures_root = Path.cwd() / ".tmp_testfixtures"
    fixtures_root.mkdir(exist_ok=True)
    root = fixtures_root / f"novalai_server_entry_{uuid.uuid4().hex}"
    videos_dir = root / "videos"
    scripts_dir = root / "scripts"
    output_dir = root / "output"
    state_dir = root / "backend_state"
    state_file = state_dir / server_entry_module.STATE_FILE_NAME

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(server_entry_module, "VIDEOS_DIR", videos_dir, create=True))
        stack.enter_context(mock.patch.object(server_entry_module, "SCRIPTS_DIR", scripts_dir, create=True))
        stack.enter_context(mock.patch.object(server_entry_module, "OUTPUT_DIR", output_dir, create=True))
        stack.enter_context(mock.patch.object(server_entry_module, "BACKEND_STATE_PATH", state_dir, create=True))
        stack.enter_context(
            mock.patch.object(server_entry_module, "ensure_runtime_directories", side_effect=lambda: None)
        )
        try:
            yield {
                "root": root,
                "videos_dir": videos_dir,
                "scripts_dir": scripts_dir,
                "output_dir": output_dir,
                "state_dir": state_dir,
                "state_file": state_file,
            }
        finally:
            shutil.rmtree(root, ignore_errors=True)


class WorkbenchHealthTests(unittest.TestCase):
    def test_health_reports_core_paths(self):
        with TestClient(app) as client:
            response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("backend"), "ok")
        self.assertIn("backend", payload)
        self.assertIn("paths", payload)
        self.assertIn("videos", payload["paths"])
        self.assertIn("output", payload["paths"])
        self.assertIn("tmp_uploads", payload["paths"])

        expected_paths = {
            "videos": str(VIDEOS_DIR),
            "output": str(OUTPUT_DIR),
            "tmp_uploads": str(TMP_UPLOADS_DIR),
        }

        for key, expected_path in expected_paths.items():
            entry = payload["paths"][key]
            self.assertEqual(entry.get("path"), expected_path)
            self.assertIsInstance(entry.get("exists"), bool)

    def test_health_reports_release_asset_paths(self):
        with temporary_frontend_dist_fixture() as fixture:
            safe_unlink(fixture["ffprobe_path"], staging_root=fixture["root"] / ".cleanup-staging")

            with TestClient(app) as client:
                response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        expected_paths = {
            "frontend_dist": (str(fixture["frontend_dist"]), True),
            "ffmpeg": (str(fixture["ffmpeg_path"]), True),
            "ffprobe": (str(fixture["ffprobe_path"]), False),
        }

        for key, (expected_path, expected_exists) in expected_paths.items():
            entry = payload["paths"][key]
            self.assertEqual(entry.get("path"), expected_path)
            self.assertEqual(entry.get("exists"), expected_exists)

    def test_health_uses_path_lookup_for_command_name_tools(self):
        with temporary_frontend_dist_fixture():
            with mock.patch.object(backend_app_module, "FFMPEG_PATH", "ffmpeg", create=True):
                with mock.patch.object(backend_app_module, "FFPROBE_PATH", "ffprobe", create=True):
                    with mock.patch.object(backend_app_module.shutil, "which") as which_mock:
                        which_mock.side_effect = lambda name: {
                            "ffmpeg": "/mock/bin/ffmpeg",
                            "ffprobe": None,
                        }.get(name)
                        with TestClient(app) as client:
                            response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["paths"]["ffmpeg"]["exists"])
        self.assertFalse(payload["paths"]["ffprobe"]["exists"])
        self.assertEqual(which_mock.call_args_list, [mock.call("ffmpeg"), mock.call("ffprobe")])


class WorkbenchFrontendServeTests(unittest.TestCase):
    def test_root_serves_frontend_index_when_present(self):
        with temporary_frontend_dist_fixture() as fixture:
            expected_html = fixture["index_html"].read_text(encoding="utf-8")
            with TestClient(app) as client:
                response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        self.assertEqual(response.text, expected_html)

    def test_non_api_spa_route_falls_back_to_frontend_index(self):
        with temporary_frontend_dist_fixture() as fixture:
            expected_html = fixture["index_html"].read_text(encoding="utf-8")
            with TestClient(app) as client:
                response = client.get("/workspace/projects/demo")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/html"))
        self.assertEqual(response.text, expected_html)

    def test_frontend_asset_is_served_from_frontend_dist(self):
        with temporary_frontend_dist_fixture() as fixture:
            expected_asset = (fixture["frontend_dist"] / "assets" / "app.js").read_text(encoding="utf-8")
            with TestClient(app) as client:
                response = client.get("/assets/app.js")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, expected_asset)

    def test_frontend_javascript_asset_uses_module_compatible_content_type(self):
        with temporary_frontend_dist_fixture():
            with TestClient(app) as client:
                response = client.get("/assets/app.js")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/javascript"))

    def test_favicon_request_serves_frontend_icon_when_present(self):
        with temporary_frontend_dist_fixture() as fixture:
            expected_icon = fixture["favicon_svg"].read_text(encoding="utf-8")
            with TestClient(app) as client:
                response = client.get("/favicon.ico")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("image/svg+xml"))
        self.assertEqual(response.text, expected_icon)

    def test_favicon_request_returns_204_when_icon_missing(self):
        with temporary_frontend_dist_fixture() as fixture:
            safe_unlink(fixture["favicon_svg"], staging_root=fixture["root"] / ".cleanup-staging")
            with TestClient(app) as client:
                response = client.get("/favicon.ico")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.text, "")

    def test_api_routes_remain_json_when_frontend_dist_exists(self):
        with temporary_frontend_dist_fixture():
            with TestClient(app) as client:
                health_response = client.get("/api/health")
                missing_response = client.get("/api/not-found")

        self.assertEqual(health_response.status_code, 200)
        self.assertTrue(health_response.headers["content-type"].startswith("application/json"))
        self.assertEqual(missing_response.status_code, 404)
        self.assertTrue(missing_response.headers["content-type"].startswith("application/json"))
        self.assertEqual(missing_response.json()["detail"], "Not Found")


class WorkbenchUploadTests(unittest.TestCase):
    def test_uploads_endpoint_persists_file_with_unique_name(self):
        with temporary_catalog_fixture():
            with TestClient(app) as client:
                response = client.post(
                    "/api/uploads?persist=false",
                    files={"file": ("sample.mp4", BytesIO(b"fake-video"), "video/mp4")},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("video_id", payload)
                self.assertEqual(payload["source_type"], "upload_temp")
                self.assertNotEqual(payload["stored_name"], "sample.mp4")
                self.assertEqual(payload["display_name"], "sample.mp4")
                self.assertEqual(payload["display_stem"], "sample")

                videos_response = client.get("/api/videos")
                self.assertEqual(videos_response.status_code, 200)
                uploaded_items = [
                    item
                    for item in videos_response.json()["items"]
                    if item["source_type"] == "upload_temp"
                ]
                self.assertEqual(len(uploaded_items), 1)
                upload_item = uploaded_items[0]
                self.assertEqual(upload_item["video_id"], payload["video_id"])
                self.assertEqual(upload_item["stored_name"], payload["stored_name"])
                self.assertEqual(upload_item["display_name"], payload["display_name"])
                self.assertEqual(upload_item["display_stem"], payload["display_stem"])
                self.assertNotEqual(upload_item["stored_name"], upload_item["display_name"])

    def test_script_uploads_endpoint_persists_text_asset(self):
        with temporary_catalog_fixture():
            with TestClient(app) as client:
                response = client.post(
                    "/api/script-uploads?persist=false",
                    files={"file": ("sample.txt", BytesIO("第一幕：测试剧本。".encode("utf-8")), "text/plain")},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["asset_type"], "script")
                self.assertEqual(payload["source_type"], "upload_temp")
                self.assertEqual(payload["display_name"], "sample.txt")
                self.assertEqual(payload["display_stem"], "sample")


class WorkbenchCatalogTests(unittest.TestCase):
    def test_videos_endpoint_reports_history_outputs(self):
        with temporary_catalog_fixture() as fixture:
            with TestClient(app) as client:
                response = client.get("/api/videos")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(len(payload["items"]), 1)
                item = payload["items"][0]
                self.assertEqual(item["video_name"], "01")
                self.assertEqual(item["video_id"], fixture["video_id"])
                self.assertTrue(item["has_output"])
                self.assertTrue(item["output_ready"])
                self.assertEqual(item["asset_type"], "video")

    def test_videos_endpoint_reports_script_assets(self):
        with temporary_catalog_fixture(asset_type="script") as fixture:
            with TestClient(app) as client:
                response = client.get("/api/videos")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(len(payload["items"]), 1)
                item = payload["items"][0]
                self.assertEqual(item["video_id"], fixture["video_id"])
                self.assertEqual(item["asset_type"], "script")
                self.assertTrue(item["has_output"])
                self.assertTrue(item["output_ready"])


class WorkbenchResultTests(unittest.TestCase):
    def test_results_endpoint_exposes_assets(self):
        with temporary_catalog_fixture() as fixture:
            with TestClient(app) as client:
                videos = client.get("/api/videos")
                self.assertEqual(videos.status_code, 200)
                payload = videos.json()
                self.assertEqual(len(payload["items"]), 1)
                self.assertEqual(payload["items"][0]["video_id"], fixture["video_id"])
                video_id = fixture["video_id"]

                response = client.get(f"/api/results/{video_id}")

                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["video"]["video_id"], video_id)
                self.assertIn("dialogues", body)
                self.assertIsInstance(body["dialogues"], list)
                self.assertIn("segments", body)
                self.assertIsInstance(body["segments"], list)
                self.assertIn("script", body)
                self.assertIsInstance(body["script"], str)
                self.assertEqual(body["media_url"], f"/api/media/{video_id}")
                self.assertIn("score", body)
                self.assertIsNone(body["score"])
                self.assertIn("highlights", body)
                self.assertIsNone(body["highlights"])
                self.assertEqual(body["asset_type"], "video")
                self.assertIsNone(body["original_script"])

    def test_results_endpoint_exposes_script_asset_without_media(self):
        with temporary_catalog_fixture(asset_type="script", with_highlights=True) as fixture:
            with TestClient(app) as client:
                response = client.get(f"/api/results/{fixture['video_id']}")

                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["asset_type"], "script")
                self.assertEqual(body["script"], "第一幕：最新优化版。")
                self.assertEqual(body["original_script"], "第一幕：原始剧本。")
                self.assertIsNone(body["media_url"])
                self.assertEqual(body["dialogues"], [])
                self.assertEqual(body["segments"], [])

    def test_results_endpoint_exposes_saved_score_and_highlights_payloads(self):
        with temporary_catalog_fixture(with_score=True, with_highlights=True) as fixture:
            with TestClient(app) as client:
                response = client.get(f"/api/results/{fixture['video_id']}")

                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertIsNotNone(body["score"])
                self.assertEqual(body["score"]["total_score"], 82)
                self.assertEqual(body["score"]["summary"], "评分摘要")
                self.assertEqual(body["score"]["dimensions"][0]["key"], "character")
                self.assertIsNotNone(body["highlights"])
                self.assertEqual(body["highlights"]["summary"], "高光主要集中在中后段。")
                self.assertEqual(body["highlights"]["best_opportunity"]["kind"], "高潮放大")
                self.assertEqual(body["highlights"]["opportunity_windows"][0]["kind"], "反转机会")

    def test_results_invalid_video_id_returns_404(self):
        with temporary_catalog_fixture():
            with TestClient(app) as client:
                response = client.get("/api/results/invalid-id-000")
                self.assertEqual(response.status_code, 404)

    def test_delete_results_removes_output_directory_only(self):
        with temporary_catalog_fixture() as fixture:
            with TestClient(app) as client:
                response = client.delete(f"/api/results/{fixture['video_id']}")

            self.assertEqual(response.status_code, 200)
            self.assertFalse(fixture["output_dir"].exists())
            self.assertTrue(fixture["video_path"].exists())

    def test_delete_results_for_running_video_returns_409(self):
        with temporary_catalog_fixture() as fixture:
            with temporary_queue_service(start_immediately=False) as queue_service:
                task = queue_service.enqueue_for_video(fixture["video_id"])
                queue_service.mark_running(task)

                with TestClient(app) as client:
                    response = client.delete(f"/api/results/{fixture['video_id']}")

                self.assertEqual(response.status_code, 409)
                self.assertTrue(fixture["output_dir"].exists())

    def test_delete_results_invalid_video_id_returns_404(self):
        with temporary_catalog_fixture():
            with TestClient(app) as client:
                response = client.delete("/api/results/invalid-id-000")

            self.assertEqual(response.status_code, 404)


class WorkbenchMediaTests(unittest.TestCase):
    def test_media_endpoint_streams_video(self):
        with temporary_catalog_fixture() as fixture:
            with TestClient(app) as client:
                videos = client.get("/api/videos")
                self.assertEqual(videos.status_code, 200)
                payload = videos.json()
                self.assertEqual(len(payload["items"]), 1)
                video_id = fixture["video_id"]

                response = client.get(
                    f"/api/media/{video_id}",
                    headers={"range": "bytes=0-0"},
                )

                self.assertIn(response.status_code, (200, 206))
                self.assertEqual(response.headers.get("content-type"), "video/mp4")


class WorkbenchDeleteVideoTests(unittest.TestCase):
    def test_delete_video_removes_source_meta_and_results(self):
        with temporary_catalog_fixture() as fixture:
            upload_dir = fixture["temp_uploads_dir"] / "upload_case"
            upload_dir.mkdir()
            upload_path = upload_dir / "uploaded-01.mp4"
            upload_path.write_bytes(b"uploaded video data")
            meta_path = upload_path.parent / f"{upload_path.name}{uploads_module.META_SUFFIX}"
            meta_path.write_text(
                '{"display_name":"原视频.mp4","display_stem":"原视频"}',
                encoding="utf-8",
            )
            upload_output_dir = catalog_module.OUTPUT_ROOT / upload_path.stem
            upload_output_dir.mkdir()
            (upload_output_dir / "dialogues.json").write_text("[]", encoding="utf-8")
            (upload_output_dir / "segments.json").write_text("[]", encoding="utf-8")
            (upload_output_dir / "script.txt").write_text("Sample script text.", encoding="utf-8")
            upload_video_id = catalog_module.build_video_id(upload_path)

            with TestClient(app) as client:
                response = client.delete(f"/api/videos/{upload_video_id}")

            self.assertEqual(response.status_code, 200)
            self.assertFalse(upload_path.exists())
            self.assertFalse(meta_path.exists())
            self.assertFalse(upload_output_dir.exists())
            self.assertFalse(upload_dir.exists())

    def test_delete_video_for_running_task_returns_409(self):
        with temporary_catalog_fixture() as fixture:
            with temporary_queue_service(start_immediately=False) as queue_service:
                task = queue_service.enqueue_for_video(fixture["video_id"])
                queue_service.mark_running(task)

                with TestClient(app) as client:
                    response = client.delete(f"/api/videos/{fixture['video_id']}")

                self.assertEqual(response.status_code, 409)
                self.assertTrue(fixture["video_path"].exists())

    def test_delete_video_invalid_video_id_returns_404(self):
        with temporary_catalog_fixture():
            with TestClient(app) as client:
                response = client.delete("/api/videos/invalid-id-000")

            self.assertEqual(response.status_code, 404)


class WorkbenchTaskApiTests(unittest.TestCase):
    def test_creating_task_returns_queued_task(self):
        with temporary_catalog_fixture():
            with temporary_queue_service(start_immediately=False):
                with TestClient(app) as client:
                    first_video = client.get("/api/videos").json()["items"][0]

                    response = client.post("/api/tasks", json={"video_id": first_video["video_id"]})

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertIn("task_id", payload)
                    self.assertEqual(payload["video_id"], first_video["video_id"])
                    self.assertEqual(payload["status"], "queued")
                    self.assertEqual(payload["stage"], "queued")
                    self.assertEqual(payload["task_type"], "generate")
                    self.assertIsNone(payload["parent_task_id"])

                    tasks_response = client.get("/api/tasks")
                    self.assertEqual(tasks_response.status_code, 200)
                    tasks = tasks_response.json()["items"]
                    self.assertEqual(len(tasks), 1)
                    self.assertEqual(tasks[0]["task_id"], payload["task_id"])
                    self.assertEqual(tasks[0]["task_type"], "generate")
                    self.assertIsNone(tasks[0]["parent_task_id"])

                    detail_response = client.get(f"/api/tasks/{payload['task_id']}")
                    self.assertEqual(detail_response.status_code, 200)
                    detail_payload = detail_response.json()
                    self.assertEqual(detail_payload["task_id"], payload["task_id"])
                    self.assertEqual(detail_payload["video_name"], first_video["video_name"])
                    self.assertEqual(detail_payload["task_type"], "generate")
                    self.assertIsNone(detail_payload["parent_task_id"])

    def test_creating_task_for_script_asset_returns_queued_highlight_task(self):
        with temporary_catalog_fixture(asset_type="script"):
            with temporary_queue_service(start_immediately=False):
                with TestClient(app) as client:
                    first_item = client.get("/api/videos").json()["items"][0]

                    response = client.post("/api/tasks", json={"video_id": first_item["video_id"]})

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["task_type"], "highlight")
                    self.assertEqual(payload["status"], "queued")

    def test_creating_manual_score_task_returns_queued_score_task(self):
        with temporary_catalog_fixture():
            with temporary_queue_service(start_immediately=False):
                with TestClient(app) as client:
                    first_video = client.get("/api/videos").json()["items"][0]

                    response = client.post(f"/api/tasks/{first_video['video_id']}/score")

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["video_id"], first_video["video_id"])
                    self.assertEqual(payload["status"], "queued")
                    self.assertEqual(payload["stage"], "queued")
                    self.assertEqual(payload["task_type"], "score")

    def test_creating_manual_highlight_task_returns_queued_highlight_task(self):
        with temporary_catalog_fixture():
            with temporary_queue_service(start_immediately=False):
                with TestClient(app) as client:
                    first_video = client.get("/api/videos").json()["items"][0]

                    response = client.post(f"/api/tasks/{first_video['video_id']}/highlight")

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["video_id"], first_video["video_id"])
                    self.assertEqual(payload["status"], "queued")
                    self.assertEqual(payload["stage"], "queued")
                    self.assertEqual(payload["task_type"], "highlight")

    def test_creating_optimize_task_requires_existing_highlights(self):
        with temporary_catalog_fixture():
            with temporary_queue_service(start_immediately=False):
                with TestClient(app) as client:
                    first_video = client.get("/api/videos").json()["items"][0]

                    response = client.post(f"/api/tasks/{first_video['video_id']}/optimize")

                    self.assertEqual(response.status_code, 409)

    def test_creating_optimize_task_returns_queued_task_when_highlights_exist(self):
        with temporary_catalog_fixture(with_highlights=True):
            with temporary_queue_service(start_immediately=False):
                with TestClient(app) as client:
                    first_video = client.get("/api/videos").json()["items"][0]

                    response = client.post(f"/api/tasks/{first_video['video_id']}/optimize")

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["video_id"], first_video["video_id"])
                    self.assertEqual(payload["status"], "queued")
                    self.assertEqual(payload["stage"], "queued")
                    self.assertEqual(payload["task_type"], "optimize")


class WorkbenchBatchTaskTests(unittest.TestCase):
    def test_run_all_enqueues_multiple_videos(self):
        with temporary_catalog_fixture():
            with temporary_queue_service(start_immediately=False):
                with TestClient(app) as client:
                    response = client.post("/api/tasks/run-all")

                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["enqueued"], 1)

                    tasks_response = client.get("/api/tasks")
                    self.assertEqual(tasks_response.status_code, 200)
                    self.assertEqual(len(tasks_response.json()["items"]), 1)


class WorkbenchServerEntryTests(unittest.TestCase):
    def test_invalid_release_layout_exits_before_state_write(self):
        with temporary_server_entry_fixture() as fixture:
            with mock.patch.object(server_entry_module, "RELEASE_LAYOUT_VALID", False, create=True):
                with mock.patch.object(
                    server_entry_module,
                    "RELEASE_LAYOUT_ERRORS",
                    ["missing/frontend_dist/index.html"],
                    create=True,
                ):
                    with mock.patch.object(server_entry_module.uvicorn, "run") as uvicorn_run_mock:
                        with self.assertRaises(SystemExit):
                            server_entry_module.main(["--host", "127.0.0.1", "--port", "8100"])
                        self.assertFalse(fixture["state_file"].exists())
                        uvicorn_run_mock.assert_not_called()

    def test_startup_failure_cleans_backend_state_file(self):
        with temporary_server_entry_fixture() as fixture:
            with mock.patch.object(server_entry_module, "RELEASE_LAYOUT_VALID", True, create=True):
                with mock.patch.object(server_entry_module.uvicorn, "run", side_effect=RuntimeError("bind failed")):
                    with self.assertRaisesRegex(RuntimeError, "bind failed"):
                        server_entry_module.main(["--host", "127.0.0.1", "--port", "8200"])
                    self.assertFalse(fixture["state_file"].exists())

    def test_normal_exit_cleans_backend_state_file(self):
        with temporary_server_entry_fixture() as fixture:
            with mock.patch.object(server_entry_module, "RELEASE_LAYOUT_VALID", True, create=True):
                with mock.patch.object(server_entry_module.uvicorn, "run") as uvicorn_run_mock:
                    exit_code = server_entry_module.main(["--host", "127.0.0.1", "--port", "8300"])
                    self.assertEqual(exit_code, 0)
                    self.assertFalse(fixture["state_file"].exists())
                    uvicorn_run_mock.assert_called_once_with("backend.app:app", host="127.0.0.1", port=8300)
