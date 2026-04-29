"""
短剧视频反推剧本工具兼容入口。
核心实现位于 backend.pipeline，本模块仅保留 CLI 包装与测试兼容导出。
"""

from backend.pipeline import *  # noqa: F401,F403
from backend.pipeline import main as _pipeline_main


def main() -> int:
    return _pipeline_main()


if __name__ == "__main__":
    raise SystemExit(main())
