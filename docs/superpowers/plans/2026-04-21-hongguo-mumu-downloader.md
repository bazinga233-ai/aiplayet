# MuMu 红果排行榜自动缓存 Implementation Plan

> **For implementers:** 先按阶段完成，再进入下一个阶段。每个阶段都先做最小验证，不要把页面导航、下载检测、共享目录整理一次性糅在同一个提交里。

**Goal:** 在 MuMu 模拟器中自动操作红果免费短剧 App，进入排行榜，处理前 10 部短剧，触发 App 内官方缓存/下载入口，并将 MuMu 共享目录里宿主机可见的文件整理到 `output/hongguo_videos`。

**Architecture:** 用一个独立 Python 脚本承载全链路，底层分成配置/状态、ADB 能力、`uiautomator2` 会话、排行榜导航、下载控制、共享目录监测和调试证据保存几个模块；先打稳“连通 + 校准 + 证据留存”，再接入排行榜和下载流程。

**Tech Stack:** Python 3.13, `subprocess`, `pathlib`, `json`, `uiautomator2`, Android Debug Bridge (`adb`)

**Spec:** [2026-04-21-hongguo-mumu-downloader-design.md](F:/local_code/aiplaylet/docs/superpowers/specs/2026-04-21-hongguo-mumu-downloader-design.md)

**Repository note:** 当前工作区不是 git 仓库。执行计划时不要依赖 commit/checkout 流程。

---

## Phase 0: Documentation Discovery

### Sources consulted

- Local design spec:
  - [docs/superpowers/specs/2026-04-21-hongguo-mumu-downloader-design.md](F:/local_code/aiplaylet/docs/superpowers/specs/2026-04-21-hongguo-mumu-downloader-design.md)
- Existing repo pattern references:
  - [launcher.py](F:/local_code/aiplaylet/launcher.py)
  - [scripts/build_release.ps1](F:/local_code/aiplaylet/scripts/build_release.ps1)
  - [docs/superpowers/plans/2026-04-13-exe-release.md](F:/local_code/aiplaylet/docs/superpowers/plans/2026-04-13-exe-release.md)
- Primary external docs:
  - `uiautomator2` official README: `https://github.com/openatx/uiautomator2/blob/master/README.md`
  - Android `adb` docs: `https://developer.android.com/tools/adb`
  - Android `dumpsys` docs: `https://developer.android.com/tools/dumpsys`

### Allowed APIs and commands

Use only these documented capabilities unless later docs discovery proves another API exists:

- `u2.connect(serial)` / `u2.connect()`
- `d.app_start(package)` and `d.app_start(package, activity)`
- `d.app_current()`
- `d.wait_activity(activity, timeout=...)`
- `d.window_size()`
- `d.click(x, y)`, `d.swipe(...)`, `d.press(...)`
- `d(text=...)`, `d(description=...)`, `d(resourceId=...)`
- selector actions like `.click()`, `.click_exists(timeout=...)`, `.exists`, `.get_text()`
- `d.screenshot(...)`
- `d.dump_hierarchy(pretty=True, max_depth=...)`
- `d.settings['wait_timeout']`
- `adb devices`
- `adb connect <host:port>`
- `adb exec-out screencap -p`
- `adb shell dumpsys ...`
- `adb shell input tap x y`
- `adb shell input swipe ...`

### Anti-patterns to avoid

- 不要用 `watch_context` 作为核心弹窗处理机制。官方 README 已标注 deprecated，且建议在点击前主动检查弹窗。
- 不要假设红果 App 一定存在稳定 `resource-id`；主流程要允许文本选择器失败后回退到坐标。
- 不要把截图、UI dump、状态持久化做成“失败后才初始化”；调试目录和状态文件要在启动阶段就创建。
- 不要读取 App 私有缓存目录或假设共享目录等于 App 下载目录。
- 不要把 MuMu 共享目录的具体宿主机路径写死在代码里；只从配置读取。

### Phase 0 verification checklist

- [ ] Implementation owner can point to the external docs above for every `uiautomator2` and `adb` API they plan to use.
- [ ] No undocumented library API is introduced in the plan or code sketch.
- [ ] The plan explicitly keeps DRM/private-cache export out of scope.

---

## File Map

- `F:\local_code\aiplaylet\scripts\mumu_hongguo_downloader.py`
  Responsibility: 主入口、参数解析、流程编排、错误汇总。
- `F:\local_code\aiplaylet\scripts\hongguo_downloader_config.json`
  Responsibility: MuMu 设备、App 包名、共享目录、关键词、坐标兜底和超时配置。
- `F:\local_code\aiplaylet\tests\test_hongguo_downloader.py`
  Responsibility: 纯 Python 辅助逻辑测试，例如配置解析、状态读写、共享目录稳定判定。
- `F:\local_code\aiplaylet\output\hongguo_download_state.json`
  Responsibility: 断点续跑状态。
- `F:\local_code\aiplaylet\output\hongguo_download_run.json`
  Responsibility: 本次运行结果汇总。
- `F:\local_code\aiplaylet\output\hongguo_download_debug\`
  Responsibility: 截图、UI dump、失败日志。

---

## Phase 1: Scaffold Config, State, and CLI Surface

**What to implement**

先搭出脚本骨架和纯本地模块，不依赖真机连接：

- 创建 `scripts/mumu_hongguo_downloader.py`
- 定义 dataclass 或等价结构：
  - `DownloaderConfig`
  - `TaskRecord`
  - `RunState`
- 增加 CLI 子命令或模式：
  - `check`
  - `calibrate`
  - `run`
- 实现配置加载、默认值填充、路径标准化、状态文件读写、调试目录创建。

**Documentation references**

- 参考 [launcher.py](F:/local_code/aiplaylet/launcher.py) 的参数解析、路径解析和 JSON 状态读写风格。
- 参考 [scripts/build_release.ps1](F:/local_code/aiplaylet/scripts/build_release.ps1) 的“先校验输入路径，再进入主流程”的防御式风格。

**Verification checklist**

- [ ] `python scripts/mumu_hongguo_downloader.py --help` 能展示主命令帮助。
- [ ] `check` 模式在缺少配置时给出可读错误，而不是 traceback。
- [ ] 状态文件不存在时能初始化；存在损坏 JSON 时能安全报错或重建。
- [ ] `output/hongguo_download_debug/` 和状态文件父目录会自动创建。

**Anti-pattern guards**

- 不要在这一阶段引入任何 ADB 或 `uiautomator2` 调用。
- 不要把模式选择写成布尔旗标地狱；保持 `check/calibrate/run` 清晰分支。

---

## Phase 2: Add Device Connectivity and Diagnostics Layer

**What to implement**

实现底层设备能力，但只做到“连得上、看得见、能留下证据”：

- `ensure_adb_available()`
- `connect_device(config)`
- `list_devices()`
- `capture_adb_screenshot(...)`
- `get_current_focus_via_dumpsys(...)`
- `save_debug_bundle(...)`
- `connect_uiautomator_session(config)`

这个阶段只打通设备连接、截图、当前前台页面检测、UI dump 保存，不碰红果业务流程。

**Documentation references**

- Android `adb` docs for `adb exec-out screencap -p` and general device command usage:
  - `https://developer.android.com/tools/adb`
- Android `dumpsys` docs for inspecting device state:
  - `https://developer.android.com/tools/dumpsys`
- `uiautomator2` README for:
  - `u2.connect(...)`
  - `d.app_current()`
  - `d.screenshot(...)`
  - `d.dump_hierarchy(...)`

**Verification checklist**

- [ ] `python scripts/mumu_hongguo_downloader.py check` 能确认 `adb` 可执行。
- [ ] 有 MuMu 在线时，脚本能识别目标设备序列号或 `adb connect` 地址。
- [ ] 能保存一张截图到 `output/hongguo_download_debug/`。
- [ ] 能保存一份 UI hierarchy XML 到 `output/hongguo_download_debug/`。
- [ ] 能输出当前前台 `package/activity`。

**Anti-pattern guards**

- 不要把 `adb` 命令拼接成单个 shell 字符串后再交给系统解析；优先用参数数组。
- 不要假设 `uiautomator2` 初始化必然成功；要给出安装/连接失败提示。
- 不要把截图只依赖 `uiautomator2`；保留 ADB 截图能力，便于会话失效时取证。

---

## Phase 3: Implement Calibration Mode

**What to implement**

实现 `calibrate` 模式，把后续流程需要的最小人工校准固定下来：

- 输出当前设备分辨率和窗口尺寸。
- 保存截图和 UI dump。
- 支持记录以下可选坐标：
  - 排行榜入口兜底坐标
  - 第一条卡片兜底坐标
  - 下载按钮兜底坐标
  - 返回按钮兜底坐标
- 将校准结果写回 `scripts/hongguo_downloader_config.json`。

**Documentation references**

- `uiautomator2` README:
  - `d.window_size()`
  - `d.click(x, y)`
  - `d.dump_hierarchy(...)`
- [docs/superpowers/specs/2026-04-21-hongguo-mumu-downloader-design.md](F:/local_code/aiplaylet/docs/superpowers/specs/2026-04-21-hongguo-mumu-downloader-design.md) 的“校准模式”章节

**Verification checklist**

- [ ] `calibrate` 模式能保存当前截图和 XML。
- [ ] 能在不覆盖未改字段的前提下更新配置文件。
- [ ] 坐标字段为空时主流程仍可运行选择器优先逻辑。

**Anti-pattern guards**

- 不要把校准写成强制依赖，每次运行都要求人工点击。
- 不要在校准阶段引入红果排行榜完整遍历；它只负责记录环境和兜底参数。

---

## Phase 4: Implement App Launch and Rank Navigation

**What to implement**

现在再接入红果业务导航：

- 启动红果 App。
- 检查前台包名是否正确。
- 进入排行榜页面。
- 识别排行榜前 10 条条目。
- 打开详情页并读取剧名。
- 返回排行榜后继续下一个条目。

实现顺序建议：

1. 先只打通 App 启动和“进入排行榜页”。
2. 再支持读取第一条剧名。
3. 最后扩展到前 10 条遍历和去重。

**Documentation references**

- `uiautomator2` README:
  - `d.app_start(package)`
  - `d.app_start(package, activity)`
  - `d.wait_activity(...)`
  - selectors: `text`, `description`, `resourceId`
  - `.click()`, `.click_exists(timeout=...)`, `.get_text()`
- Design spec 中的 `rank_navigator` 和错误处理章节

**Verification checklist**

- [ ] 能从冷启动进入红果 App。
- [ ] 能判断当前是否在红果前台。
- [ ] 能进入排行榜页，或在失败时保存截图/XML。
- [ ] 能稳定打开第 1 条详情页并读取剧名。
- [ ] 在单次运行中不会重复处理同一“排名 + 剧名”。

**Anti-pattern guards**

- 不要在还没确认排行榜页稳定前就开始遍历前 10 条。
- 不要只按坐标点列表项；优先用控件文本和结构。
- 不要依赖固定滚动次数定位前 10 条，要根据已见条目集合和排名进度推进。

---

## Phase 5: Implement Download Trigger and Shared Folder Watching

**What to implement**

把详情页下载动作和宿主机文件检测接起来：

- 在详情页识别 `下载`、`缓存`、`离线看` 等入口。
- 处理常见确认弹窗。
- 触发下载前后记录共享目录快照。
- 轮询新增文件，直到文件稳定。
- 将稳定文件整理到 `output/hongguo_videos\<剧名>\`。
- 把条目标记为 `success`、`download_triggered`、`failed` 或 `skipped`。

建议先实现“目录快照 + 稳定文件检测”纯本地逻辑，再把它接到真下载动作上。

**Documentation references**

- `uiautomator2` README:
  - selector click patterns
  - `click_exists(timeout=...)`
  - `dump_hierarchy(...)`
- Design spec 中的 `download_controller`、`shared_folder_watcher`、断点续跑和风险边界章节

**Verification checklist**

- [ ] 触发下载前后会分别记录共享目录快照。
- [ ] 新文件在大小或修改时间稳定后才归档。
- [ ] 目标目录为 `output/hongguo_videos\<剧名>\`。
- [ ] 未检测到新增文件时，不会误报成功。
- [ ] 失败时保存截图、XML 和错误原因。

**Anti-pattern guards**

- 不要把“点击了下载按钮”直接等同于“文件已成功落盘”。
- 不要 move 正在写入的临时文件；必须等稳定窗口结束。
- 不要尝试扫描红果私有目录或媒体数据库来替代共享目录策略。

---

## Phase 6: Wire Resume Logic and Result Reporting

**What to implement**

完善批处理稳定性：

- 状态机支持：
  - `pending`
  - `running`
  - `download_triggered`
  - `success`
  - `failed`
  - `skipped`
- 启动时加载旧状态并跳过已成功项。
- 本次运行结束后写入 `output/hongguo_download_run.json`。
- 输出摘要日志，列出成功、失败、跳过数量及原因。

**Documentation references**

- 参考 [launcher.py](F:/local_code/aiplaylet/launcher.py) 的 JSON 状态读写和防御式清理思路。
- 参考 design spec 的“断点续跑”和“验收标准”章节。

**Verification checklist**

- [ ] 脚本中断后再次运行能跳过已成功项。
- [ ] 已处于 `download_triggered` 的项会先检查目标目录和共享目录，再决定是否重下。
- [ ] `hongguo_download_run.json` 结构稳定，便于后续人工排查。

**Anti-pattern guards**

- 不要把全部运行结果只留在 stdout。
- 不要在状态写入上采用“最后统一落盘”；每处理一项就要持久化。

---

## Phase 7: Verification and Smoke Runs

**What to implement**

补上纯 Python 测试和手工冒烟命令，确保实现不是一次性脚本：

- 为配置解析、状态迁移、共享目录稳定检测添加测试。
- 运行 `check` 模式做环境确认。
- 运行 `run --limit 1` 做单条冒烟。
- 最后运行默认前 10 条批量流程。

**Documentation references**

- 仓库测试约定见 [AGENTS.md](F:/local_code/aiplaylet/AGENTS.md)
- design spec 的“测试方案”与“验收标准”

**Verification checklist**

- [ ] `python -m unittest tests.test_hongguo_downloader -v` 通过。
- [ ] `python scripts/mumu_hongguo_downloader.py check` 可运行。
- [ ] `python scripts/mumu_hongguo_downloader.py run --limit 1` 能完成单条验证或给出完整失败证据。
- [ ] 批量跑前 10 条时，单条失败不阻塞整体。

**Anti-pattern guards**

- 不要把需要真实设备的集成流程塞进自动化单元测试。
- 不要在没有 `check` 和 `--limit 1` 冒烟通过前直接跑前 10 条。

---

## Suggested Execution Order

1. Phase 1: 配置、状态和 CLI 壳子
2. Phase 2: 设备连接、截图、UI dump
3. Phase 3: 校准模式
4. Phase 4: App 启动和排行榜导航
5. Phase 5: 下载与共享目录检测
6. Phase 6: 断点续跑与结果汇总
7. Phase 7: 测试与冒烟验证

## Known Risks to Re-check During Implementation

- MuMu 共享目录是否真的能承接红果官方下载落盘；如果不能，需要在最终结果中明确“自动点击下载成功，但宿主机不可见”。
- 红果 App 是否存在登录、广告、权限弹窗；如果存在，流程里要加显式检测和失败证据保存。
- `uiautomator2` 是否已在当前 Python 环境安装；若未安装，实施时需要先补依赖。
