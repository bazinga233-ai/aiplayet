# 剧本自动评分设计说明

- 日期：2026-04-09
- 项目：`F:\local_code\novalai`
- 状态：设计已确认，待进入实现计划

## 1. 目标

为现有短剧工作台新增“剧本自动评分”能力，满足以下目标：

- 在剧本生成完成后自动触发评分
- 评分使用当前剧本生成链路所使用的同一套远端大模型服务
- 评分时同时参考原视频、`dialogues.json`、`segments.json` 和 `script.txt`
- 评分结果落盘保存，后端重启和页面刷新后仍可读取
- 评分结果在前端结果面板中展示
- 评分失败不影响剧本结果查看

## 2. 非目标

第一版明确不包含以下能力：

- 人工修改评分结果
- 多模型并行评分
- 评分版本历史管理
- 人工复核流、审核流、评论流
- 评分驱动的任务重排、优先级调度
- 独立的评分管理页面

## 3. 总体方案

采用“独立评分任务”的方式实现自动评分，而不是把评分内嵌进 `video2script.py` 主流程。

核心原则如下：

- `generate` 任务负责生成剧本产物
- `score` 任务负责读取已生成产物并调用远端模型评分
- `generate` 成功后自动派生一个 `score` 任务
- `score` 与 `generate` 共用同一条串行任务队列，但在模型层面是独立任务

这样设计的原因：

- 自动评分可以成立
- 前端可以明确展示“评分中 / 评分失败 / 评分完成”
- 后续支持“重新评分”“换模型评分”“多版本评分”时不需要推翻任务结构

## 4. 评分维度与 100 分权重

评分采用固定 13 维度与固定权重，由后端写死，模型不得自行更改权重。

| 维度 | key | 权重 |
| --- | --- | ---: |
| 与原视频一致性 | `video_faithfulness` | 18 |
| 信息完整性 | `information_completeness` | 12 |
| 情节/因果 | `plot_causality` | 10 |
| 结构 | `structure` | 10 |
| 人物 | `character` | 8 |
| 冲突 | `conflict` | 8 |
| 对白 | `dialogue` | 8 |
| 节奏 | `pacing` | 6 |
| 逻辑/自洽 | `logic` | 6 |
| 概念/立意 | `premise_theme` | 5 |
| 风格/语气/主题 | `style_tone_theme` | 4 |
| 结尾/整体效果 | `ending_overall_effect` | 3 |
| 工艺/格式 | `craft_format` | 2 |

合计 `100` 分。

### 4.1 核心解释

- `与原视频一致性`：检查人物、事件、顺序、情绪、细节是否编错
- `信息完整性`：检查关键情节、转折、关系、结尾是否遗漏

这两个维度是本项目评分体系的核心，合计占 `30` 分，因为当前业务目标是“评估模型对原视频的正确还原能力”，而不是“评选原创编剧作品”。

## 5. 任务模型设计

### 5.1 新增任务类型

任务新增字段：

- `task_type`: `generate | score`
- `parent_task_id`: `string | null`

约束如下：

- 用户手动创建的任务类型固定为 `generate`
- 系统自动派生的评分任务类型固定为 `score`
- `score.parent_task_id` 指向对应的 `generate.task_id`

### 5.2 任务状态

现有任务状态沿用：

- `queued`
- `running`
- `completed`
- `failed`

现有 `stage` 基础上新增：

- `scoring`

约束如下：

- `generate` 任务继续使用现有阶段：`queued / asr / segmenting / multimodal / merging / done / failed`
- `score` 任务使用：`queued / scoring / done / failed`

### 5.3 自动派生规则

当 `generate` 任务成功完成后：

1. 将 `generate` 任务标记为 `completed`
2. 自动创建一个新的 `score` 任务
3. 新任务继承同一个 `video_id`、`video_name`、`video_path`、`source_type`
4. 新任务的 `parent_task_id` 指向刚完成的 `generate` 任务
5. 新任务自动入队并按现有队列规则执行

失败规则：

- `generate` 失败时，不创建 `score`
- `score` 失败时，不回滚 `generate` 结果

## 6. 产物与落盘格式

评分结果与剧本结果放在同一输出目录下：

```text
output/<video_name>/
├─ dialogues.json
├─ segments.json
├─ script.txt
└─ score.json
```

### 6.1 `score.json` 结构

第一版采用单文件覆盖策略，不保存历史版本。

建议结构：

```json
{
  "version": 1,
  "video_id": "2f0a0f1e2c3d",
  "video_name": "01",
  "task_id": "score-task-id",
  "parent_task_id": "generate-task-id",
  "generated_at": "2026-04-09T08:00:00Z",
  "model": {
    "base_url": "http://127.0.0.1:8000/v1",
    "model_name": "qwen-vl"
  },
  "total_score": 82,
  "summary": "整体结构完整，人物与冲突成立，但对白辨识度一般。",
  "dimensions": [
    {
      "key": "video_faithfulness",
      "label": "与原视频一致性",
      "score": 15,
      "max_score": 18,
      "reason": "主线事件和情绪基本一致，但部分细节描述偏离画面。"
    }
  ]
}
```

### 6.2 文件写入规则

- 仅在评分成功且结构校验通过后写入 `score.json`
- 写入采用原子策略：先写临时文件，再替换正式文件
- 若评分失败，不创建残缺 `score.json`
- 若已有旧 `score.json`，新评分成功后覆盖旧文件

## 7. 后端架构设计

### 7.1 模块拆分

建议新增独立评分模块，避免把评分逻辑继续堆进 `video2script.py`：

- `backend/scoring.py`
  - 构造评分提示词
  - 调用远端模型
  - 校验评分 JSON
  - 写入 `score.json`

- `backend/llm_client.py`
  - 抽取当前远端模型调用公共逻辑
  - 复用 `video2script.py` 当前使用的 OpenAI-compatible 请求方式

说明：

- `video2script.py` 不改其业务职责，仍专注于“对白/分段/剧本生成”
- 新的评分任务直接复用共享的 LLM 客户端能力

### 7.2 任务执行分发

当前 `TaskQueue` 只接受单一 `runner`。第一版改为“按任务类型分发”：

- `generate` -> 现有 `run_video2script`
- `score` -> 新增 `run_score_task`

建议方式：

- 保留 `TaskQueue` 结构
- 把 `runner(task, on_line)` 从单一实现升级为统一调度入口
- 该入口根据 `task.task_type` 调用对应执行器

### 7.3 评分任务输入

评分任务必须同时读取：

- 原视频文件
- `output/<video_name>/dialogues.json`
- `output/<video_name>/segments.json`
- `output/<video_name>/script.txt`

任何一个关键文件缺失都应直接失败，并写入明确错误信息。

## 8. 远端模型调用与评分提示词

### 8.1 模型接入

评分复用当前剧本生成链路的同一套远端模型配置：

- `LLM_BASE_URL`
- `LLM_CHAT_COMPLETIONS_URL`
- `LLM_API_KEY`
- `LLM_MODEL_NAME`

并继续使用 OpenAI-compatible `chat/completions` 接口。

### 8.2 输入组织

评分请求内容采用：

- `video_url`
- `text`

其中 `text` 部分包含：

- 评分任务说明
- 固定 13 维度及其权重
- `dialogues.json` 的精简文本化内容
- `segments.json` 的精简文本化内容
- `script.txt` 原文
- 严格 JSON 输出约束

### 8.3 输出格式约束

模型必须输出合法 JSON，不得输出解释性前缀、Markdown、代码围栏。

目标结构：

```json
{
  "total_score": 82,
  "summary": "整体结构完整，但个别细节与画面不一致。",
  "dimensions": [
    {
      "key": "character",
      "label": "人物",
      "score": 7,
      "max_score": 8,
      "reason": "人物动机较清楚，但配角区分度一般。"
    }
  ]
}
```

### 8.4 输出校验

后端必须校验：

- JSON 可解析
- `total_score` 为数值
- `dimensions` 数量恰好为 13
- 所有 `key` 必须属于固定维度集
- 每个维度必须包含 `score`、`max_score`、`reason`
- `max_score` 必须等于后端固定权重
- `score` 必须在 `0..max_score` 范围内
- `total_score` 必须等于 13 项得分之和

## 9. 错误处理与重试策略

### 9.1 评分模型输出异常

若模型输出不合法：

1. 首次失败后自动重试一次
2. 第二次提示词显式指出“上次输出不是合法 JSON，请仅输出合法 JSON”
3. 若第二次仍失败，则将评分任务标记为 `failed`

### 9.2 文件异常

以下情况应直接失败：

- `dialogues.json` 缺失
- `segments.json` 缺失
- `script.txt` 缺失
- 文件不可解码
- JSON 文件损坏

### 9.3 前端可见性

评分失败不阻塞其他结果：

- 视频和剧本仍可查看
- 评分区显示“评分失败”
- 失败原因从最近一个 `score` 任务读取

## 10. API 设计变更

### 10.1 `GET /api/tasks`

任务返回体新增字段：

- `task_type`
- `parent_task_id`

### 10.2 `GET /api/tasks/{task_id}`

单任务详情同样新增：

- `task_type`
- `parent_task_id`

### 10.3 `GET /api/results/{video_id}`

返回体新增：

```json
{
  "score": {
    "version": 1,
    "total_score": 82,
    "summary": "...",
    "dimensions": []
  }
}
```

规则：

- 若 `score.json` 不存在，返回 `score: null`
- 若 `score.json` 存在但损坏，返回 `409`
- 剧本未生成完成时仍沿用现有 `409`

## 11. 前端设计

### 11.1 类型定义

前端类型新增：

- `ScoreDimension`
- `ScorePayload`

并扩展：

- `TaskItem.task_type`
- `TaskItem.parent_task_id`
- `ResultPayload.score`

### 11.2 结果面板

`ResultPanel` 新增一个 Tab：

- `评分`

显示内容：

- 总分
- 总评摘要
- 13 个维度的得分、满分、理由

### 11.3 空状态与运行态

当 `result.score` 为空时，前端按以下顺序判断：

1. 若当前或最近存在运行中的 `score` 任务，显示“评分中”
2. 若最近一个 `score` 任务失败，显示失败信息
3. 否则显示“暂无评分”

### 11.4 布局原则

评分仍然属于结果区，不新增独立页面。

这样可以保持当前工作台结构：

- 左侧：调度与任务
- 右侧：视频与结果

## 12. 数据流

完整数据流如下：

1. 用户创建 `generate` 任务
2. 队列执行 `generate`
3. `video2script.py` 生成 `dialogues.json`、`segments.json`、`script.txt`
4. `generate` 标记完成
5. 系统自动派生 `score` 任务
6. 队列执行 `score`
7. 评分模块读取视频和产物
8. 评分模块调用远端模型
9. 评分结果通过校验后写入 `score.json`
10. 前端轮询任务与结果接口
11. 前端在“评分”Tab 展示结果

## 13. 测试策略

### 13.1 后端测试

新增测试覆盖：

- `score.json` 存在时，`/api/results/{video_id}` 返回评分
- `score.json` 缺失时，`score` 为 `null`
- `generate` 成功后自动派生 `score` 任务
- `generate` 失败时不派生评分任务
- `score` 失败不影响已生成剧本结果读取
- 评分 JSON 结构校验失败时任务标记失败

### 13.2 前端测试

新增测试覆盖：

- 结果面板出现“评分”Tab
- 存在评分时正确展示总分和维度列表
- 评分中状态展示正常
- 评分失败状态展示正常

## 14. 实现注意事项

- 不要把评分逻辑继续塞进 `video2script.py` 主流程
- 远端模型公共配置应抽到共享位置，避免两套配置漂移
- `score.json` 的结构必须有版本号，为后续升级保留空间
- 第一版不做评分历史版本管理，只做单文件覆盖

## 15. 待进入实现计划的问题

以下问题在本设计内已固定，不再在实现阶段重新讨论：

- 采用独立评分任务，而不是内嵌评分
- 评分自动触发
- 评分结果落盘保存
- 评分同时参考原视频、对白、分段、剧本
- 权重采用固定 100 分表
- 评分展示位于现有结果面板中
