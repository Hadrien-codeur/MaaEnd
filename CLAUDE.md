# CLAUDE.md — MaaEnd 自己送货功能开发记录

> 本文件用于记录"DeliveryJobs 自己送货"功能的开发过程、方案设计、待办事项，方便后续会话继续接力。
> 用户身份：编程新手，使用 Claude Code 配合 MaaEnd 项目做二次开发。

---

## 1. 项目背景

- **项目**：MaaEnd — 基于 MaaFramework 的《明日方舟：终末地》自动化工具
- **本地路径**：`e:\TestBase2\MaaEnd`
- **现有功能**：拜访好友、自动收礼、自动种田、自动领取送货任务（含接取 + 装货 + 转交他人）
- **本次目标**：在现有 DeliveryJobs 任务基础上，新增「自己送货」模式 —— 装货完成后，由角色亲自按预设路线送达，而非转交给他人

---

## 2. 开发约定

### 模型策略
- **Plan Mode（规划阶段）**：使用 Sonnet（`claude-sonnet-4-6`）节省成本
- **正式开发阶段**：切换到 Opus（`claude-opus-4-7`）保证代码质量
- 用户会通过 `/model <name>` 命令手动切换，切换前会通知 Claude

### 协作原则
- 用户是新手，需要先解释概念再动手
- 所有方案先进 Plan Mode 写计划文件，用户审批后再实施
- **不会**未经用户同意执行 git commit / push 等危险操作
- 每完成一个阶段都要给出**详细的测试和调试指南**

---

## 3. 本次开发已完成的方案（MVP：仅源石研究园）

### 3.1 整体钩入点设计

```
原有装货流程
  → DeliveryJobsDeliverQuickly（点击"请尽快送达"屏幕）
  → DeliveryJobsBackToDepot（识别 InWorld → 跳回仓储）
         ↑
   [自己送货模式钩入点]
   通过 pipeline_override 改写 DeliveryJobsBackToDepot.next
         ↓
  → DeliveryJobsDeliverRouteDispatch（新增：分发节点）
  → [Anchor]DeliveryJobsDeliverRouteEntrance（按仓储节点跳路线）
  → 路线移动 + 送货交互
  → DeliveryJobsDeliverRouteEnd
  → [Anchor]DeliveryJobsGoToDepot（回到仓储节点，继续主循环）
```

### 3.2 路线分发机制（关键设计）

- **入口分发**通过 `[Anchor]DeliveryJobsDeliverRouteEntrance` 实现
- 每个仓储节点的 `EnterXxxCargo` 节点的 `anchor` 字段中追加一个映射：
  ```json
  "anchor": {
      "DeliveryJobsSelectItemToFill": "DeliveryJobsSelectItemToFillValleyIV",
      "DeliveryJobsDeliverRouteEntrance": "DeliveryJobsDeliverRouteOriginiumScienceParkStart"
  }
  ```
- MaaFramework 会在装货流程中把 Anchor 解析到对应路线的 Start 节点
- 优点：未来加新地区时，只需新增路线文件 + 在对应 EnterCargo 节点追加 anchor 即可

### 3.3 互斥与兜底机制

| 风险场景 | 处理方式 |
|---------|---------|
| 启用自己送货 + 启用转交（冲突） | `pipeline_override` 中 `DeliveryJobsClickTransferJob.enabled = false`，互斥禁用转交 |
| 路线数据为空（path: []） | `Goto` 节点 `next` 包含 `DeliveryJobsDeliverRouteEnd` 兜底，跳过该节点不卡死 |
| 当前仓储节点无路线（Anchor 找不到对应节点） | `DeliveryJobsDeliverRouteDispatch.next` 兜底走 `DeliveryJobsDeliverRouteNoRoute`，打日志并跳过 |
| 导航超时（角色卡墙、识别错误） | `Goto` 节点 `timeout: 600000` + `on_error: [DeliveryJobsDeliverRouteEnd]` |
| 位置断言失败 | `AssertLocation` 节点 `timeout: 20000` + `on_error` 跳到 End |
| 交付识别失败 | `Deliver` 节点 `timeout: 30000` + `on_error` 跳到 End |
| 死循环 | `Goto` 节点 `max_hit: 1`，只执行一次 |

> **道具保护**：所有节点都有 `timeout` + `on_error` 双重保险，最坏情况是停任务，不会因死循环误扣道具。

---

## 4. 文件变更清单

### 新建（2 个）
| 文件 | 作用 |
|------|------|
| `assets/resource/pipeline/DeliveryJobs/DeliverRoute.json` | 分发节点 + 结束节点 + 兜底节点 |
| `assets/resource/pipeline/DeliveryJobs/DeliverRoute/OriginiumSciencePark.json` | 源石研究园路线（含 4 个 TODO 占位节点） |

### 修改（7 个）
| 文件 | 改动内容 |
|------|---------|
| `assets/resource/pipeline/DeliveryJobs/ValleyIV.json` | `DeliveryJobsEnterOriginiumScienceParkCargo.anchor` 追加 `DeliveryJobsDeliverRouteEntrance` 映射 |
| `assets/tasks/DeliveryJobs.json` | `task[0].option` 数组末尾追加 `"DeliveryJobsSelfDeliverMode"`，`option` 对象中新增 `DeliveryJobsSelfDeliverMode` switch 定义 |
| `assets/locales/interface/zh_cn.json` | 追加 3 个 i18n 条目 |
| `assets/locales/interface/zh_tw.json` | 追加 3 个 i18n 条目 |
| `assets/locales/interface/en_us.json` | 追加 3 个 i18n 条目 |
| `assets/locales/interface/ja_jp.json` | 追加 3 个 i18n 条目 |
| `assets/locales/interface/ko_kr.json` | 追加 3 个 i18n 条目 |

### i18n 新增的 key
- `task.DeliveryJobs.SelfDeliverMode.label`
- `task.DeliveryJobs.SelfDeliverMode.description`
- `task.DeliveryJobs.SelfDeliverMode.NoRoute`

---

## 5. 当前路线文件的 TODO 占位（待用户录制数据后填写）

`assets/resource/pipeline/DeliveryJobs/DeliverRoute/OriginiumSciencePark.json` 中：

| TODO 位置 | 当前值 | 待填内容 | 获取方式 |
|----------|-------|---------|---------|
| `AssertLocation.custom_recognition_param.zone_id` | `"TODO_FILL_ZONE_ID"` | 源石研究园对应的 zone_id（如 `ValleyIV_OriginiumSciencePark`） | MapNavigator Assert 模式导出 |
| `AssertLocation.custom_recognition_param.target` | `[0, 0, 20, 20]` | 角色起点的小地图坐标矩形 | MapNavigator Assert 模式导出 |
| `Goto.action.param.custom_action_param.path` | `[]`（空数组） | 完整移动路径数组，含滑索点位 `"INTERACT"` 标记 | MapNavigator 录制模式导出 |
| `Deliver.action` | `"DoNothing"` | 真实的识别 + Click 动作（OCR 识别交付按钮 / TemplateMatch 匹配按钮图） | 用户提供目的地 UI 截图，Claude 协助编写 |

---

## 6. 项目核心约定（Claude 必读）

### 6.1 MaaEnd Pipeline 协议要点
- **节点命名**：使用 PascalCase，按"任务前缀 + 阶段 + 动作"组合
  例：`DeliveryJobsDeliverRouteOriginiumScienceParkStart`
- **识别方式**：`OCR`（文字）、`TemplateMatch`（图片）、`And`（组合）、`Custom`（自定义识别器）
- **动作方式**：`Click`、`Swipe`、`DoNothing`、`StopTask`、`Custom`（自定义动作）
- **路线节点必须使用** `MapLocateAssertLocation`（不是 `MapTrackerAssertLocation` 老式）
- **地图导航必须使用** `MapNavigateAction`（不是 `MapTrackerMove` 老式）
- 参考已有路线：`assets/resource/pipeline/AutoCollect/AutoCollectRoute6.json`（单段 MapNavigateAction 路线模板）

### 6.2 国际化（i18n）
- 5 个语言文件必须同步增删：`zh_cn.json` / `zh_tw.json` / `en_us.json` / `ja_jp.json` / `ko_kr.json`
- 任务 UI 文本通过 `$task.XxxTask.YyyKey.label` 引用 i18n key

### 6.3 任务选项（switch）模式
```json
"OptionName": {
    "type": "switch",
    "label": "$task.Xxx.label",
    "description": "$task.Xxx.description",
    "cases": [
        { "name": "Yes", "pipeline_override": { ... } },
        { "name": "No" }
    ],
    "default_case": "No"
}
```
通过 `pipeline_override` 启用时动态改写 Pipeline 节点。

### 6.4 格式化
- **每次改完 JSON 必须运行**：
  ```bash
  pnpm prettier --write <file1> <file2> ...
  ```
- Prettier 可能会调整字段顺序（如把 `next` 放在 `focus` 之前），这是项目规范，**不要回滚**。

### 6.5 可用的 Skill
项目中已为常见场景准备了专门的 skill（在 .claude 配置中）：
- `autocollect-add-route` — 新建采集路线
- `pipeline-guide` — Pipeline JSON 编写规范
- `maaend-issue-log-analysis` — 分析上游 issue 日志包
- `cpp-algo-style` / `go-service-guide` — C++ / Go 编码规范
- `environment-monitoring-add-route` — 环境监测观察点新增

---

## 7. 用户调试指引（已发给用户）

### 阶段 1：框架验证（路线数据为空，零道具消耗）
1. 启动 MaaEnd
2. 在「🚚转交委托」任务选项中，看是否出现新开关「🚶自己送货」
3. 仅打开自己送货开关，运行任务
4. 装货后日志应出现 `DeliveryJobsDeliverRouteDispatch` → `DeliveryJobsDeliverRouteNoRoute`
5. 任务正常结束、不卡死

### 阶段 2：数据采集（MapNavigator 工具）
- 工具位置：`tools/MapNavigator/main.py`
- Assert 模式 → 采 zone_id + target
- 录制模式 → 采 path 数组（含滑索 `"INTERACT"` 标记）

### 阶段 3：交付节点编写
- 用户提供目的地 UI 截图
- Claude 协助选择 OCR / TemplateMatch 并编写节点

### 阶段 4：分阶段端到端测试
- A：只测断言（path 空）
- B：测短路径（5米左右）
- C：测完整路径但不交付（Deliver 保持 DoNothing）
- D：完整流程（含交付）

### 日志位置
```
debug/maa.log       # 主日志
debug/maa.bak.log   # 备份
```

---

## 8. 后续可扩展方向（用户已知，但未开始）

待源石研究园 MVP 跑通后，可按相同模式扩展到：
- 矿脉源区（`OriginLodespring`）
- 供能高地（`PowerPlateau`）
- 武陵城区（`WulingCity`）

**扩展步骤**：
1. 新建 `DeliverRoute/[Region].json`（复制源石研究园模板，改节点名 + TODO 占位）
2. 修改对应的 `ValleyIV.json` 或 `Wuling.json`，在 `EnterXxxCargo.anchor` 中追加路线入口映射
3. 跑 prettier
4. 录制路线数据填入

---

## 9. 已知的潜在风险点（待验证）

| 风险 | 验证方式 |
|------|---------|
| `MapLocateAssertLocation` 在源石研究园是否有对应 `zone_id` | MapNavigator 实际框选时如果导出失败，需检查 `assets/resource/map_navigator/` 下是否有源石研究园的地图数据 |
| `MapNavigateAction` 是否支持滑索 `INTERACT` 动作 | 查阅 `agent/cpp-algo/` 或 `agent/go-service/` 中 MapNavigateAction 的实现源码 |
| Anchor 在 `pipeline_override` + 多层 anchor 嵌套场景下的解析行为 | 跑阶段 1 测试时观察日志 |
| `on_error` 触发后能否正确跳到 `next` 中的兜底节点 | 阶段 B 测试（路径错误时观察） |

---

## 10. Plan 文件留档

完整的实施计划保存在：`C:\Users\hongjiawei\.claude\plans\partitioned-growing-pie.md`

---

> 后续会话开始时，请先阅读本 CLAUDE.md，了解上下文后再继续工作。
