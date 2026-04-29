import shutil
import unittest
import uuid
from pathlib import Path

try:
    import release_ffmpeg
except ImportError as exc:  # pragma: no cover - expected before implementation
    release_ffmpeg = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


class ReleaseFfmpegRuntimeTests(unittest.TestCase):
    def setUp(self):
        if IMPORT_ERROR is not None:
            self.fail(f"release_ffmpeg import failed: {IMPORT_ERROR}")

        fixtures_root = Path.cwd() / ".tmp_testfixtures"
        fixtures_root.mkdir(exist_ok=True)
        self.root = fixtures_root / f"novalai_release_ffmpeg_{uuid.uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_dir = self.root / "ffmpeg-bin"
        self.ffmpeg_dir.mkdir()
        self.release_dir = self.root / "release"
        self.release_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_runtime_file(self, filename: str, content: bytes = b"stub") -> Path:
        path = self.ffmpeg_dir / filename
        path.write_bytes(content)
        return path

    def dependency_reader(self, mapping: dict[str, list[str]]):
        def reader(path: Path) -> list[str]:
            return mapping.get(path.name, [])

        return reader

    def test_collect_runtime_files_includes_shared_dlls(self):
        self.write_runtime_file("ffmpeg.exe")
        self.write_runtime_file("ffprobe.exe")
        avcodec = self.write_runtime_file("avcodec-58.dll")
        avformat = self.write_runtime_file("avformat-58.dll")

        files = release_ffmpeg.collect_runtime_files(
            self.ffmpeg_dir,
            dependency_reader=self.dependency_reader(
                {
                    "ffmpeg.exe": [avcodec.name],
                    "ffprobe.exe": [avformat.name],
                }
            ),
        )

        self.assertEqual(
            [path.name for path in files],
            ["ffmpeg.exe", "ffprobe.exe", avcodec.name, avformat.name],
        )

    def test_collect_runtime_files_allows_static_build_without_dlls(self):
        self.write_runtime_file("ffmpeg.exe")
        self.write_runtime_file("ffprobe.exe")

        files = release_ffmpeg.collect_runtime_files(self.ffmpeg_dir)

        self.assertEqual([path.name for path in files], ["ffmpeg.exe", "ffprobe.exe"])

    def test_copy_runtime_files_copies_binaries_and_dlls(self):
        self.write_runtime_file("ffmpeg.exe")
        self.write_runtime_file("ffprobe.exe")
        self.write_runtime_file("avcodec-58.dll")
        self.write_runtime_file("avutil-56.dll")

        copied = release_ffmpeg.copy_runtime_files(
            self.ffmpeg_dir,
            self.release_dir,
            dependency_reader=self.dependency_reader(
                {
                    "ffmpeg.exe": ["avcodec-58.dll"],
                    "ffprobe.exe": [],
                    "avcodec-58.dll": ["avutil-56.dll"],
                }
            ),
        )

        self.assertEqual(
            [path.name for path in copied],
            ["ffmpeg.exe", "ffprobe.exe", "avcodec-58.dll", "avutil-56.dll"],
        )
        for filename in ("ffmpeg.exe", "ffprobe.exe", "avcodec-58.dll", "avutil-56.dll"):
            self.assertTrue((self.release_dir / filename).exists(), filename)

    def test_collect_runtime_files_excludes_unreferenced_dlls_from_large_bin_directory(self):
        self.write_runtime_file("ffmpeg.exe")
        self.write_runtime_file("ffprobe.exe")
        self.write_runtime_file("avcodec-58.dll")
        self.write_runtime_file("avutil-56.dll")
        self.write_runtime_file("sqlite3.dll")

        files = release_ffmpeg.collect_runtime_files(
            self.ffmpeg_dir,
            dependency_reader=self.dependency_reader(
                {
                    "ffmpeg.exe": ["avcodec-58.dll"],
                    "ffprobe.exe": ["avutil-56.dll"],
                }
            ),
        )

        self.assertEqual(
            [path.name for path in files],
            ["ffmpeg.exe", "ffprobe.exe", "avcodec-58.dll", "avutil-56.dll"],
        )


if __name__ == "__main__":
    unittest.main()
