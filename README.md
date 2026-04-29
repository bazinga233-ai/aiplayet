# AI Playlet

AI Playlet 是一个本地短剧视频分析工作台，用于把短视频素材整理成对白、分段、剧本、评分和高光分析结果。项目同时保留命令行处理入口和本地 Web 工作台，适合在开发机上批量处理素材、复盘剧情结构、评估内容质量。

## 解决的问题

短剧素材复盘通常需要反复观看视频、手工听写台词、记录画面变化、整理剧情节点，再把这些信息组织成可读剧本。这个项目把这些步骤串成一条本地流水线：先抽取音频和视频片段，再调用 ASR 与多模态模型，最后把识别结果、时间线和画面理解结果合成为结构化文件和剧本文本。

## 核心流程

主流程位于 `backend/pipeline.py`，兼容入口是 `video2script.py`。处理一个视频时，系统会先用 FFmpeg 抽取音频，再调用 ASR 服务生成带时间戳的对白；随后按规则切分视频、抽取关键画面并调用兼容 OpenAI Chat Completions 的多模态模型分析内容；最后把对白、分段、视觉分析和模型输出整合为 `dialogues.json`、`segments.json` 和 `script.txt`。当前实现是串行流水线，不包含显式多 Agent 调度；长链推理主要体现在跨 ASR、视频切片、多模态分析和剧本整合的多阶段信息汇总。

## 目录结构

```text
.
├─ backend/                  # FastAPI 后端与视频处理流水线
├─ frontend/                 # React + Vite 本地工作台
├─ scripts/                  # 发布构建、端口工具、红果下载辅助脚本
├─ tests/                    # Python 后端测试与前端组件测试
├─ docs/                     # 设计说明和历史实现计划
├─ packaging/                # PyInstaller 打包配置
├─ video2script.py           # 命令行兼容入口
├─ launcher.py               # 发布版/源码级启动器
├─ run_workbench.bat         # 本地工作台启动脚本
└─ README.md
```

运行时目录不会提交到仓库：

```text
videos/                      # 本地视频素材
output/                      # 生成结果
tmp_uploads/                 # 上传临时文件
tmp_script_uploads/          # 剧本上传临时文件
backend_state/               # 后端运行状态
```

## 环境要求

- Python 3.13
- Node.js 20+ 和 npm 10+
- FFmpeg / FFprobe
- 可访问的 ASR 服务
- 兼容 OpenAI Chat Completions 的多模态模型服务

Python 依赖目前没有统一锁定文件，开发环境需要按运行报错安装所需包，例如 `fastapi`、`uvicorn`、`funasr`、`modelscope`、`torch`、`opencv-python` 等。前端依赖由 `frontend/package.json` 和 `frontend/package-lock.json` 管理。

## 配置

仓库不再硬编码内网服务地址、私有模型路径或本机目录。运行前通过环境变量配置服务地址：

```powershell
$env:NOVALAI_ASR_URL = "http://127.0.0.1:30116/recognition"
$env:NOVALAI_LLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:NOVALAI_LLM_API_KEY = "EMPTY"
$env:NOVALAI_LLM_MODEL_NAME = "qwen-vl"
$env:NOVALAI_LLM_TIMEOUT = "3600"
```

FFmpeg 路径默认从运行环境或发布目录解析。构建发布包时可用：

```powershell
$env:NOVALAI_FFMPEG_DIR = "C:\path\to\ffmpeg\bin"
$env:NOVALAI_PYTHON_EXE = "C:\path\to\python.exe"
```

红果/MuMu 下载辅助脚本的真实配置文件 `scripts/hongguo_downloader_config.json` 已被 `.gitignore` 排除。复制示例文件后按本机环境修改：

```powershell
Copy-Item scripts\hongguo_downloader_config.example.json scripts\hongguo_downloader_config.json
```

## 命令行用法

处理单个视频：

```powershell
python video2script.py videos\01.mp4
```

处理 `videos/` 下全部 `.mp4`：

```powershell
python video2script.py
```

ASR 冒烟测试：

```powershell
python -m tests.test_asr <audio.wav>
```

## 本地工作台

一键启动：

```powershell
run_workbench.bat
```

手动启动后端：

```powershell
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001 --reload
```

手动启动前端：

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

浏览器打开：

```text
http://127.0.0.1:5173
```

## 输出结果

每个视频的结果默认写入：

```text
output/<video_name>/
├─ dialogues.json
├─ segments.json
├─ script.txt
├─ score.json              # 可选，评分结果
└─ highlights.json         # 可选，高光/爆款预测结果
```

## 后端接口

常用接口：

- `GET /api/health`
- `GET /api/videos`
- `POST /api/uploads`
- `GET /api/results/{video_id}`
- `GET /api/media/{video_id}`
- `POST /api/tasks`
- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/run-all`

健康检查：

```powershell
curl http://127.0.0.1:8001/api/health
```

创建任务：

```powershell
curl -X POST http://127.0.0.1:8001/api/tasks ^
  -H "Content-Type: application/json" ^
  -d "{\"video_id\":\"<video_id>\"}"
```

## 测试

后端重点测试：

```powershell
python -m unittest tests.test_workbench_backend tests.test_workbench_queue -v
```

视频处理兼容测试：

```powershell
python -m unittest tests.test_video2script_remote tests.test_media_tools -v
```

前端测试：

```powershell
cd frontend
npm run test -- --run
```

## 发布构建

生成发布目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -FfmpegDir C:\path\to\ffmpeg\bin
```

发布产物目录：

```text
novalai-release/
├─ 启动.exe
├─ Backend.exe
├─ ffmpeg.exe
├─ ffprobe.exe
├─ frontend_dist/
├─ videos/
├─ scripts/
├─ output/
└─ backend_state/
```

发布包不需要目标机器安装 Python 或 Node。目标机器仍需能访问配置的 ASR 和多模态模型服务。

## 敏感信息约定

- 不提交 `videos/`、`output/`、`build/`、`dist/`、`novalai-release/`、`node_modules/`。
- 不提交真实服务地址、访问 Token、私有模型路径、本机用户名目录或下载器真实配置。
- 新增配置优先使用环境变量或 `*.example.*` 示例文件。
- 示例地址统一使用 `127.0.0.1` 或占位路径，真实地址只保存在本机环境中。

## 常见问题

如果运行时报 `UnicodeDecodeError: 'gbk' codec can't decode...`，通常是 Windows 默认编码在读取 FFmpeg/ADB 输出时解码失败。当前子进程封装已统一使用 UTF-8 并用替换字符处理异常字节；若仍出现类似错误，优先检查是否有新的 `subprocess.run(..., text=True)` 调用没有指定 `encoding`。

如果前端能打开但列表为空，检查后端是否启动、`/api/health` 是否返回 200、`videos/` 下是否有 `.mp4` 文件，以及 `output/` 是否可写。

如果任务一直不动，检查 FFmpeg、ASR 服务、LLM 服务和环境变量配置是否可用。
