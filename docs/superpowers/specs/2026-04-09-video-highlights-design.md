# 视频高光识别设计

**目标**

在现有剧本工作台中新增“爆点 / 高燃 / 高潮”自动识别能力。系统在 `generate` 成功后自动触发独立的 `highlight` 任务，基于原视频、对白、分段草稿和最终剧本，输出结构化高光结果并在前端展示。

**范围**

- 新增独立任务类型 `highlight`
- 新增高光结果文件 `highlights.json`
- 在 `/api/results/{video_id}` 暴露高光结果
- 前端结果面板新增 `高光` tab
- 左侧任务/队列补充 `highlight` 状态文案

**非目标**

- 不做手动触发入口
- 不做视频剪辑导出
- 不做时间轴可视化编辑器
- 不依赖评分结果

## 处理链路

1. `generate` 任务成功后，队列自动插入两个后续任务：`highlight` 和 `score`
2. `highlight` 任务分两阶段执行：
   - 阶段一：逐段判定。复用现有 `segments.json` 时间窗，对每个片段结合代理视频、片段对白、片段草稿和完整剧本识别是否命中 `爆点 / 高燃 / 高潮候选`
   - 阶段二：全局汇总。对候选片段做去重、合并、排序，输出最终 `3-5` 个高光片段，并选出 `1` 个最佳高潮点
3. 结果持久化到 `output/<video_name>/highlights.json`
4. 前端轮询现有 `/api/results` 接口即可读取结果

## 数据结构

`highlights.json`

```json
{
  "version": 1,
  "video_id": "xxx",
  "video_name": "01",
  "task_id": "highlight-task-id",
  "parent_task_id": "generate-task-id",
  "generated_at": "2026-04-09T00:00:00Z",
  "model": {
    "base_url": "http://example/v1",
    "model_name": "demo-model"
  },
  "summary": "该视频的情绪峰值主要集中在中后段。",
  "highlights": [
    {
      "start": 12.3,
      "end": 18.8,
      "label": "爆点",
      "reason": "关键反转首次揭示，信息密度骤升。"
    }
  ],
  "best_climax": {
    "start": 52.0,
    "end": 60.0,
    "title": "终极高潮",
    "reason": "情绪、冲突和人物决策在这一段同时到峰值。"
  }
}
```

## 校验规则

- `highlights` 数量必须在 `3-5`
- `label` 只能是 `爆点`、`高燃`、`高潮`
- `start < end`
- `summary`、`reason`、`title` 必须为非空字符串
- `best_climax` 必须与至少一个高光时间段有重叠
- 候选汇总时允许合并重叠或高度相邻片段，但不能输出无序时间段

## 失败策略

- `highlight` 任务失败不影响 `generate` 成功状态
- `highlight` 失败不阻断 `score`
- 模型输出非法时自动重试一次
- 两次失败后标记 `highlight` 任务失败，并在前端展示失败信息

## 前端展示

- 结果面板新增 `高光` tab
- 顶部展示 `最佳高潮点` 卡片：时间范围、标题、理由
- 下方展示高光列表：标签、时间范围、理由
- 无结果时显示空状态，失败时显示任务错误

## 测试策略

- 队列：`generate` 成功后自动插入 `highlight` 和 `score`
- 结果接口：返回 `highlights`
- 后端校验：合法结果通过，非法结果失败
- 前端：`高光` tab 渲染最佳高潮点和列表
- 前端：`highlight` 失败时显示错误占位
