# Nova 工作台 EXE 发布版设计说明

- 日期：2026-04-13
- 项目：`F:\local_code\novalai`
- 状态：设计已确认，待进入实现计划

## 1. 目标

把当前短剧反推与情绪预测工作台打包为可分发的 Windows 发布版，使接收方在不安装 Python、Node.js 的前提下，双击即可启动并使用。

第一版目标如下：

- 产出可直接发送给他人的完整发布目录
- 对外入口统一为 `启动.exe`
- 后端服务独立为 `Backend.exe`
- 前端不再依赖 Vite 开发服务器，而是由后端直接托管构建后的静态文件
- 保持现有浏览器工作流，仍在默认浏览器中打开页面
- 保留现有本地数据目录：`videos/`、`scripts/`、`output/`
- 保持现有远端依赖方式：
  - ASR：`127.0.0.1:30116`
  - LLM：`127.0.0.1:8000`

## 2. 非目标

第一版明确不做以下事情：

- 不改造成 Electron、Tauri 或内嵌 WebView 桌面壳
- 不做安装器版 `setup.exe`
- 不支持离线 ASR 或离线大模型推理
- 不自动安装系统依赖或写注册表
- 不改变现有任务逻辑、评分逻辑、爆款预测逻辑本身
- 不兼容 macOS / Linux，仅面向 Windows 发布目录

## 3. 当前现状

当前项目启动方式为开发态双进程：

- [`run_workbench.bat`](/F:/local_code/novalai/run_workbench.bat) 启动 `uvicorn backend.app:app`
- 前端通过 `frontend/package.json` 中的 `npm run dev` 启动 Vite

当前结构对 EXE 发布不友好的点：

- 前后端需要 Python、Node 环境
- 前端是开发服务器，不适合分发
- [`backend/config.py`](/F:/local_code/novalai/backend/config.py) 默认按源码目录推导路径
- 媒体处理依赖 `ffmpeg`，同时代码中也存在 `ffprobe` 调用

适合 EXE 发布的现有基础：

- 前端 API 已使用同源相对路径，如 [`frontend/src/api/client.ts`](/F:/local_code/novalai/frontend/src/api/client.ts)
- 后端已有 `/api/health`，可用于启动探活
- 当前使用浏览器工作流，不必再引入桌面壳层

## 4. 采用方案

采用“浏览器界面 + 双 EXE + 绿色发布目录”的方案。

最终形态：

- `启动.exe` 负责启动与拉起浏览器
- `Backend.exe` 负责 API 服务与静态前端托管
- `frontend_dist/` 存放 Vite 构建结果
- 发布目录随包携带 `ffmpeg.exe` 与 `ffprobe.exe`

这是本项目当前最稳妥的方案，原因如下：

- 对现有前后端架构改动最小
- 不需要额外引入桌面端框架
- 更容易定位问题，浏览器、后端、资源目录职责明确
- 适合后续继续做绿色便携版和安装器版

## 5. 发布目录结构

确认后的第一版发布目录如下：

```text
novalai-release/
  启动.exe
  Backend.exe
  ffmpeg.exe
  ffprobe.exe
  frontend_dist/
  videos/
  scripts/
  output/
```

说明：

- `启动.exe` 是用户唯一需要双击的入口
- `Backend.exe` 不直接暴露给普通用户操作
- `frontend_dist/` 内应至少包含 `index.html` 和静态资源目录
- `videos/`、`scripts/`、`output/` 首次运行时若不存在应自动创建

## 6. 启动链路设计

### 6.1 用户视角

用户双击 `启动.exe` 后，期望行为如下：

1. 自动检查并处理旧的 `Backend.exe` 进程
2. 选择可用本地端口，优先 `8001`
3. 启动 `Backend.exe`
4. 轮询 `http://127.0.0.1:<port>/api/health`
5. 健康检查通过后，自动打开默认浏览器
6. 浏览器进入工作台主页

### 6.2 `启动.exe` 职责

`启动.exe` 只负责“编排”，不承载业务逻辑：

- 查找并清理同目录旧后端进程，避免端口占用
- 优先尝试端口 `8001`，如被占用则递增寻找下一个可用端口
- 以子进程方式启动 `Backend.exe --host 127.0.0.1 --port <port>`
- 轮询健康接口，设置合理超时，例如 `30~60` 秒
- 启动成功后使用系统默认浏览器打开首页
- 若启动失败，给出明确错误提示，例如：
  - `Backend.exe` 缺失
  - `frontend_dist/index.html` 缺失
  - 端口不可用
  - 后端启动超时

### 6.3 后端复用策略

第一版优先采用“发现已存在同目录后端则复用，否则启动新实例”的策略。若发现旧实例异常或无响应，再进行拉起。

这样做的原因：

- 减少重复启动
- 避免用户连续双击后打开多个窗口或多个后端
- 便于后续加单实例锁

## 7. `Backend.exe` 设计

### 7.1 角色定位

`Backend.exe` 是发布版核心服务进程，职责包括：

- 提供现有 `/api/*` 接口
- 托管前端静态资源
- 使用发布目录相对路径读写数据
- 校验运行所需文件和目录

### 7.2 发布版入口

新增独立入口文件，建议为：

- [`backend/server_entry.py`](/F:/local_code/novalai/backend/server_entry.py)

该入口用于 EXE 场景，不替换当前开发态 `uvicorn backend.app:app` 的方式。

建议行为：

- 解析命令行参数：`--host`、`--port`
- 根据 EXE 所在位置定位发布根目录
- 初始化发布态配置
- 校验关键资源
- 启动 uvicorn server

### 7.3 静态前端托管

`Backend.exe` 需要在发布态同时提供：

- `/api/*` 业务接口
- `/` 和前端资源文件

建议方式：

- 使用 FastAPI / Starlette 的静态文件能力托管 `frontend_dist/`
- 对非 `/api/*` 路径回退到 `frontend_dist/index.html`
- 保持前端现有相对 API 请求方式不变

这能让前端从开发态切换到发布态时几乎无需改动接口调用逻辑。

### 7.4 资源自检

后端启动时应检查：

- `frontend_dist/index.html` 是否存在
- `ffmpeg.exe` 是否存在
- `ffprobe.exe` 是否存在
- `videos/`、`scripts/`、`output/` 是否存在，不存在则创建

若关键文件缺失，应直接启动失败并打印明确错误。

## 8. 路径与配置策略

### 8.1 统一根目录

现有 [`backend/config.py`](/F:/local_code/novalai/backend/config.py) 使用源码根目录推导路径。发布版需扩展为“双模式”：

- 开发模式：继续以源码目录为根
- 发布模式：以 `Backend.exe` 所在目录为根

建议新增统一的根目录解析逻辑：

- 若检测到冻结态运行环境，则使用 `Path(sys.executable).resolve().parent`
- 否则继续使用当前源码根目录推导方式

### 8.2 目录约定

发布态固定约定以下目录：

- `videos/`
- `scripts/`
- `output/`
- `frontend_dist/`

相关业务代码全部从统一配置取值，不再写死源码相对路径。

### 8.3 远端依赖配置

现有环境变量能力继续保留：

- `NOVALAI_LLM_BASE_URL`
- `NOVALAI_LLM_API_KEY`
- `NOVALAI_LLM_MODEL_NAME`
- 以及 ASR 相关环境变量

第一版默认仍使用当前远端地址，接收方只要网络可达即可运行。

## 9. 媒体依赖打包策略

当前代码路径中存在对 `ffmpeg` 和 `ffprobe` 的调用，因此发布目录需要同时携带：

- `ffmpeg.exe`
- `ffprobe.exe`

后端在调用媒体处理命令时，发布态优先使用发布目录内的可执行文件路径，而不是依赖系统 `PATH`。

建议规则：

- 发布态：显式使用 `<release_root>/ffmpeg.exe` 和 `<release_root>/ffprobe.exe`
- 开发态：继续兼容系统环境变量中的 `ffmpeg` / `ffprobe`

这样能保证接收方机器无需额外安装 FFmpeg。

## 10. 打包实现方案

### 10.1 技术选择

发布版采用 PyInstaller。

原因：

- 当前主逻辑为 Python，改造成本最低
- 可分别产出 `启动.exe` 与 `Backend.exe`
- 适合先做绿色发布目录

### 10.2 前端构建

前端发布前先执行：

```powershell
cd frontend
npm run build
```

构建产物从当前 Vite 默认 `dist/` 复制或重命名为发布目录下的 `frontend_dist/`。

### 10.3 打包产物

建议新增以下打包相关文件：

- `launcher.py`
- `backend/server_entry.py`
- `packaging/backend.spec`
- `packaging/launcher.spec`
- `scripts/build_release.ps1`

其中：

- `launcher.py` 打包为 `启动.exe`
- `backend/server_entry.py` 打包为 `Backend.exe`
- `scripts/build_release.ps1` 统一执行前端构建、PyInstaller 打包、资源归集

### 10.4 发布脚本职责

`scripts/build_release.ps1` 建议完成以下事情：

1. 清理旧的 `release/` 或 `dist-release/`
2. 构建前端静态资源
3. 打包 `Backend.exe`
4. 打包 `启动.exe`
5. 复制 `frontend_dist/`
6. 复制 `ffmpeg.exe`、`ffprobe.exe`
7. 创建 `videos/`、`scripts/`、`output/`
8. 输出最终发布目录

## 11. 与现有代码的衔接方式

本方案是在现有代码上增量修改，不另起新项目。

主要改动面如下：

- 后端：
  - 新增发布入口
  - 扩展配置根目录解析
  - 新增静态资源托管
  - 媒体命令路径改为可配置
- 前端：
  - 基本无需改 API 调用方式
  - 只需确保构建产物可直接被后端托管
- 脚本：
  - 新增发布打包脚本
  - 现有开发启动脚本继续保留

这意味着：

- 开发态 `run_workbench.bat` 继续可用
- 发布态通过 `启动.exe` 使用
- 两套入口并存，但共享同一业务代码

## 12. 验证清单

实现完成后至少要验证以下场景：

### 12.1 启动验证

- 双击 `启动.exe` 后可以自动打开浏览器
- 浏览器首页可正常加载
- `/api/health` 返回正常
- 连续双击不会导致多个后端实例失控增长

### 12.2 功能验证

- 上传 MP4 后可创建任务
- 视频剧本生成正常
- 评分任务可正常触发与展示
- 爆款预测器可正常触发与展示
- 剧本优化任务可正常触发与展示
- 纯剧本模式上传 TXT 后可正常工作

### 12.3 文件验证

- `videos/` 中能看到上传视频
- `scripts/` 中能看到上传脚本
- `output/` 中能看到任务产物
- 删除结果、删除原视频等现有功能仍有效

### 12.4 环境验证

- 目标机器不安装 Python 也能启动
- 目标机器不安装 Node.js 也能启动
- 目标机器系统未配置 `ffmpeg` 也能运行
- 只要远端 ASR / LLM 网络可达，任务即可正常执行

## 13. 风险与处理

### 13.1 远端依赖不可达

风险：

- 接收方虽然可启动界面，但任务执行会失败

处理：

- 在健康检查或任务失败信息中明确展示远端服务调用错误

### 13.2 前端静态文件缺失

风险：

- 后端能起来，但页面打不开

处理：

- 启动阶段先校验 `frontend_dist/index.html`

### 13.3 FFmpeg 文件缺失

风险：

- 上传成功但媒体处理失败

处理：

- 后端启动阶段直接拦截，不进入可用状态

### 13.4 发布态路径与开发态路径混淆

风险：

- 读写目录落错位置，导致结果找不到

处理：

- 所有目录统一从配置模块取值
- 发布态增加日志，打印最终解析出的根目录

## 14. 实施顺序建议

建议实现顺序如下：

1. 补齐发布态配置与根目录解析
2. 新增 `Backend.exe` 入口并接入静态资源托管
3. 新增 `启动.exe` 入口与健康检查拉起逻辑
4. 接通 `ffmpeg.exe` / `ffprobe.exe` 的发布态路径
5. 增加前端构建与发布脚本
6. 产出完整发布目录并做端到端验证

## 15. 结论

本方案是在现有代码基础上的最小闭环发布方案：

- 继续保留浏览器工作流
- 不引入新的桌面框架
- 用 `启动.exe + Backend.exe + frontend_dist + FFmpeg` 形成完整绿色发布版
- 接收方无需安装 Python / Node，即可直接使用

下一步应基于本设计文档编写实施计划，再进入代码实现。
