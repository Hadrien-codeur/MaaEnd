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

## 11. Git 工作流与多电脑协作

### 11.1 远程仓库（remote）配置

| Remote 名 | 地址 | 用途 |
|-----------|------|------|
| `origin` | `https://github.com/MaaEnd/MaaEnd.git` | 官方仓库，**只读**，拉上游更新用 |
| `myfork` | `https://github.com/Hadrien-codeur/MaaEnd.git` | 用户的 fork，可读写，跨电脑同步用 |

### 11.2 分支策略

| 分支 | 用途 |
|------|------|
| `v2` | 跟踪官方 `origin/v2`，定期 `git pull origin v2` 拉更新 |
| `feature/self-deliver-route` | 用户的开发分支，包含本次「自己送货」全部改动 + CLAUDE.md |

### 11.3 常用操作

**拉上游更新并合并到开发分支**：
```bash
git checkout v2
git pull origin v2
git submodule update --init --recursive
git push myfork v2

git checkout feature/self-deliver-route
git merge v2
git push myfork feature/self-deliver-route
```

**新电脑首次拉取**：
```bash
git clone https://github.com/Hadrien-codeur/MaaEnd.git
cd MaaEnd
git checkout feature/self-deliver-route
git remote rename origin myfork
git remote add origin https://github.com/MaaEnd/MaaEnd.git
git submodule update --init --recursive
pnpm install
git config user.name "Hadrien-codeur"
git config user.email "1648022241@qq.com"
git config credential.helper manager   # Windows 凭据管理器
```

**两台电脑之间同步改动**：
```bash
# 电脑 A：提交并推
git add . && git commit -m "..." && git push myfork feature/self-deliver-route

# 电脑 B：拉
git checkout feature/self-deliver-route
git pull myfork feature/self-deliver-route
```

### 11.4 认证方式
- 使用 Personal Access Token（GitHub Settings → Developer settings → Tokens）
- 首次 push 时 Windows 凭据管理器会弹窗，输入用户名 + token 后永久缓存
- 推送时**不要**把 token 直接写在 remote URL 里（避免泄露）

### 11.5 子模块
项目包含 3 个 git 子模块，本地切换分支时可能显示子模块"有改动"，这是子模块指针差异，不是真改动：
- `agent/cpp-algo/MaaUtils`
- `assets/resource/model`
- `tests/MaaEndTestset`

**不要 commit 这些子模块的变化**，除非有明确意图。同步上游时用 `git submodule update --init --recursive` 让子模块跟着上游一起更新。

---

## 12. 开发时间线（按会话顺序）

| 阶段 | 操作 | 关键产物 |
|------|------|---------|
| 会话 1（Plan）| 用 Sonnet 4.6 规划，探索 AutoCollect/DeliveryJobs 现有结构 | Plan 文件 |
| 会话 1（开发）| 切 Opus 4.7 实施 | 9 个文件改动 + 2 个新文件 |
| 会话 1（文档）| 写 CLAUDE.md 留底 | 本文件 |
| 会话 1（启动）| 找到客户端 `install/mxu.exe`，确认 install 是 assets 的软链接，改动立即生效 | — |
| 会话 1（同步上游）| `git fetch origin v2` 拉 25+ 条新提交，feature 分支零冲突合并 | `MapNavigator HEADING target` 等更新到位 |
| 会话 1（推送）| Fork 仓库 → 加 myfork remote → push feature 分支 | https://github.com/Hadrien-codeur/MaaEnd |
| 会话 2（v2 重设计）| 把 OCR 钩入点前移到调度申请界面，重写 SelfDeliver.json 框架 | 第 13、14 节 |
| 会话 3（阶段 1.A）| 启动 mxu.exe，验证「🚶自己送货」开关 i18n 渲染正常 | 截图（图A）通过 |
| 会话 3（同步 push）| `.agents/` 加 ignore，提交 v2 框架 + CLAUDE.md，push 到 myfork 准备多电脑接力 | 见第 16 节 |
| 会话 4（阶段 1.B）| 阶段 1.B 跑通：pipeline_override 三处改写在 maafw.log 中确认生效，零道具消耗 | install/debug/2026-05-28-1.log |
| 会话 4（v2.1 重构）| 用户决定改"OCR 买方名"为"点查看位置 + 地图模板匹配"，重写 SelfDeliver.json | 见第 13bis 节 |

---

> 后续会话开始时，请先阅读本 CLAUDE.md，了解上下文后再继续工作。
> 新电脑接力开发时，参考第 11 节的"新电脑首次拉取"步骤。

---

## 13. v2 方案修订（2026/05/26 会话 2）

> 第 3 节描述的是 v1 方案（钩在「装货完回大世界 → 重进仓储 UI 点查看任务」）。
> v2 把 OCR 钩入点**前移**到「调度申请界面（接任务环节）」，本节为最新设计，实现以此节为准。

### 13.1 关键变更
- **OCR 钩入位置前移**：从「装货后回仓储 UI 点查看任务」改为「调度申请界面（图2）直接 OCR 买方信息列」
- **流程更顺**：调度申请界面 OCR → 设 anchor → 点开始运送 → 装完回大世界后直接进入送货流程
- **「自动送货」隐含「仅接取任务」**：开启自动送货时不需要再开 AcceptJobOnly 开关
- **不再需要 ExitUi 节点**：流程不会回仓储 UI

### 13.2 新钩入点
| 节点 | pipeline_override 改写 | 作用 |
|------|----------------------|------|
| `DeliveryJobsInCargoRedistributionBid` | `next` 数组前面插入买方识别节点 + 兜底节点 | 调度申请界面 OCR 决定路线 |
| `DeliveryJobsBackToDepot` | `next` 改为 `[DeliveryJobsSelfDeliverPickupStart]` | 装完回大世界后跳自动送货 |
| `DeliveryJobsClickTransferJob` | `enabled: false` | 禁止转交（同 AcceptJobOnly 语义） |

### 13.3 OCR 识别策略
- 在调度申请界面（图2）OCR 买方信息列文本（如「采购-疏散区物资模组」）
- 每个买方对应一个 `DeliveryJobsSelfDeliverDispatchToBuyerX` 节点（OCR 识别 + anchor 设置）
- 通过 anchor 机制把路线起点绑定到 `DeliveryJobsSelfDeliverPickupEntrance` 占位符
- 必要时用「查看位置」按钮辅助人工确定买方→路线映射（开发期），程序运行时只 OCR 名称即可

### 13.4 默认买方选择
游戏在调度申请界面默认选中报价最高的买方。MVP 不主动切换买方，依赖此默认行为。

### 13.5 MVP 行为
- 框架阶段所有 BuyerX 节点 OCR 都是 TODO，必然走 `DeliveryJobsSelfDeliverNoBuyerMatch` 兜底
- 任务停在调度申请界面，**不会**点击「开始运送」，货物滞留，零道具消耗
- 用户验证 UI 开关 + Pipeline 结构无误后再补充买方配置

### 13.6 v2 文件变更清单
**新建（2 个）**：
- `assets/resource/pipeline/DeliveryJobs/SelfDeliver.json`（分发节点 + 兜底 + End）
- `assets/resource/pipeline/DeliveryJobs/SelfDeliver/OriginiumSciencePark.json`（路线模板，全 TODO）

**修改（6 个）**：
- `assets/tasks/DeliveryJobs.json`（option 末尾加 `DeliveryJobsSelfDeliverMode` switch）
- 5 个 i18n 文件，新增 4 个 key：`label` / `description` / `NoBuyerMatch` / `NoRoute`

### 13.7 v2 计划文件位置
`C:\Users\hongjiawei\.claude\plans\generic-sleeping-riddle.md`

---

## 13bis. v2.1 方案再修订（2026/05/28 会话 4）

> 第 13 节是 v2 OCR 买方名方案，**已废弃**。会话 4 改为"点击查看位置 + 地图模板匹配"方案，更稳健。

### 13bis.1 关键变更
- **路线分发依据**：从 OCR 买方信息列文本 → 改为**点「查看位置」按钮打开地图 + TemplateMatch 取送货点连线**
- **优势**：不受多语言/买方改名/同物资多买方影响；取货点+送货点对在地图上唯一；地图视角每次自动对准（用户确认）
- **MVP 安全前提**：路线模板 PNG 留 TODO 占位 → TemplateMatch 必失败 → 走 `NoRouteMatch` → ESC 关地图 → StopTask，**不会**点击「开始运送」

### 13bis.2 新流程
```
DeliveryJobsInCargoRedistributionBid（识别调度申请界面）
  ↓
DeliveryJobsSelfDeliverClickViewLocation（OCR「查看位置」→ Click）
  ↓ 打开大地图弹窗
DeliveryJobsSelfDeliverMapDispatch（DirectHit 路由）
  ├─ MatchRouteOriginiumScienceParkA（TemplateMatch 路线 A 模板图 → 设 anchor）
  │     ↓ 命中
  │   CloseMapAndStartDelivery（ESC 关地图）
  │     ↓
  │   DeliveryJobsRedistributionBidNextStep（点开始运送，原节点）
  │     ↓ 装货 → BackToDepot → SelfDeliverPickupStart
  │     ↓ Anchor 解析跳到路线 A 起点
  │   ...路线 A 取货+送货流程...
  └─ NoRouteMatch（兜底）→ ESC 关地图 → StopTask
```

### 13bis.3 v2.1 文件变更（在 v2 基础上的增量）
**修改**：
- `assets/resource/pipeline/DeliveryJobs/SelfDeliver.json`：完全重写
  - 删：`DispatchToBuyerA` / `NoBuyerMatch`
  - 增：`ClickViewLocation` / `MapDispatch` / `MatchRouteOriginiumScienceParkA` / `CloseMapAndStartDelivery` / `NoRouteMatch` / `StopForNoRouteMatch`
  - 保留：`PickupStart` / `NoRoute` / `End`（anchor 占位机制不变）
- `assets/tasks/DeliveryJobs.json`：`InCargoRedistributionBid.next` 改为跳 `ClickViewLocation`
- 5 个 i18n 文件：`NoBuyerMatch` key 改名为 `NoRouteMatch`，description 文案对齐新流程

**未改动**：
- `SelfDeliver/OriginiumSciencePark.json`（路线 A 内部流程不变，anchor 仍由模板匹配节点设置）
- `BackToDepot.next` 改写（依然指向 `SelfDeliverPickupStart`）
- `ClickTransferJob.enabled = false`（互斥转交逻辑不变）

### 13bis.4 v2.1 TODO 占位清单

> ⚠️ **本表中的 `MatchRouteOriginiumScienceParkA`（TemplateMatch + PNG 模板图）已在会话 6 废弃**，
> 改为 OCR「送货点」坐标落点方案。最新 TODO 占位清单见 **第 18.3 节**。

| 文件 | 字段 | 当前值 | 由哪个阶段填写 |
|------|------|--------|--------------|
| `SelfDeliver.json` | `ClickViewLocation.roi` | `[0, 0, 1280, 720]` | 阶段 2 |
| ~~`SelfDeliver.json`~~ | ~~`MatchRouteOriginiumScienceParkA.roi`~~ | ~~`[0, 0, 1280, 720]`~~ | ❌ 废弃，见 18.3 |
| ~~`SelfDeliver.json`~~ | ~~`MatchRouteOriginiumScienceParkA.template`~~ | ~~`OriginiumSciencePark_RouteA_Map.png`~~ | ❌ 废弃，不再需要 PNG |
| `SelfDeliver/OriginiumSciencePark.json` | 全部 TODO | 同 14.2 节 | 阶段 4-5 |

---

## 14. v2 MVP 开发完成状态（2026/05/27 会话 2 收尾）

### 14.1 已完成 ✅
所有 v2 MVP 框架代码已落盘，prettier 通过。9 个文件状态：

| 文件 | 状态 | 关键内容 |
|------|------|---------|
| `assets/resource/pipeline/DeliveryJobs/SelfDeliver.json` | ✅ 新建 | 5 节点：DispatchToBuyerA / NoBuyerMatch / PickupStart / NoRoute / End |
| `assets/resource/pipeline/DeliveryJobs/SelfDeliver/OriginiumSciencePark.json` | ✅ 新建 | 6 节点路线A 模板（全 TODO 占位） |
| `assets/tasks/DeliveryJobs.json` | ✅ 改写 | v2 switch + pipeline_override 三处钩入 |
| `assets/resource/pipeline/DeliveryJobs/ValleyIV.json` | ✅ 清理 | 移除 v1 残留 `DeliveryJobsDeliverRouteEntrance` anchor |
| 5 个 i18n 文件 | ✅ 更新 | label / description / NoBuyerMatch（新） / NoRoute |

v1 残留文件（`DeliverRoute.json` 与 `DeliverRoute/OriginiumSciencePark.json`）在会话 2 开始时已删除。

### 14.2 当前 TODO 占位清单（按文件 + 阶段）

| 文件 | 字段 | 当前值 | 由哪个阶段填写 |
|------|------|--------|--------------|
| `SelfDeliver.json` | `DispatchToBuyerA.roi` | `[0, 0, 1280, 720]` | 阶段 2 |
| `SelfDeliver.json` | `DispatchToBuyerA.expected` | `["TODO_BUYER_A_NAME"]` | 阶段 2 |
| `SelfDeliver/OriginiumSciencePark.json` | `RouteAAssertLocation.zone_id` / `target` | `TODO_FILL_ZONE_ID` / `[0,0,20,20]` | 阶段 3.1 |
| `SelfDeliver/OriginiumSciencePark.json` | `RouteAGotoPickup.path` | 只有 ZONE 声明 | 阶段 3.2 |
| `SelfDeliver/OriginiumSciencePark.json` | `RouteAPickupAction` 识别+动作 | `DirectHit` + `DoNothing` | 阶段 4 |
| `SelfDeliver/OriginiumSciencePark.json` | `RouteAGotoDestination.path` | 只有 ZONE 声明 | 阶段 3.3 |
| `SelfDeliver/OriginiumSciencePark.json` | `RouteASubmitAction` 识别+动作 | `DirectHit` + `DoNothing` | 阶段 4 |

### 14.3 测试阶段进度

- [x] **阶段 1.A**：UI 框架验证（i18n 开关展示）✅ 会话 3 通过
- [x] **阶段 1.B**：跑一次任务，确认 pipeline_override 生效（maafw.log 已确认 `found in override [node_name=DeliveryJobsInCargoRedistributionBid]`）✅ 会话 4 通过
- [x] **方案 v2.1 重构**：改 OCR 买方名 → 点「查看位置」+ 识别地图标签 ✅ 会话 4 完成
- [x] **识别策略确定**：会话 5 对比两条路线截图，确定用 OCR「送货点」标签坐标落点判区间（见第 17 节）✅
- [x] **阶段 2（代码部分）**：会话 6 重写 `SelfDeliver.json` 的 MapDispatch 逻辑（TemplateMatch → OCR 落点），5 个 i18n 文案同步去掉"模板图"措辞 ✅（见第 18 节）
- [ ] **阶段 2（量参数）**：录制「查看位置」按钮 roi（填 `ClickViewLocation.roi`）→ 等图D
- [ ] **阶段 3**：为每条路线确定「送货点」标签坐标区间（填 `CheckRouteX.roi`）→ 等图E 系列
- [ ] **阶段 4**：MapNavigator 录路径（zone_id/target/取货段/送货段）
- [ ] **阶段 5**：取货/交货动作识别（等用户提交 UI 截图）
- [ ] **阶段 6**：端到端测试

### 14.4 阶段 2 用户需要提交的物料（识别策略更新后）
- 📸 图D：调度申请界面**完整截图**（1280×720，能看清买方下方的「查看位置」按钮位置）→ 用来填 `ClickViewLocation.roi`
- 📸 图E：点「查看位置」后，**源石研究园每条路线的地图弹窗截图**（至少两张不同送货目的地）→ 量「送货点」标签 Y 坐标区间阈值

### 14.5 安全前提（已落地，无需用户额外操作）
- MVP 开启自己送货开关后，送货点 OCR 不命中 → 走 `NoRouteMatch` → ESC 关地图 → StopTask
- 任务**不会**点击「开始运送」，**不会**真接单消耗道具
- 所有路线节点都有 `timeout` + `on_error: [DeliveryJobsSelfDeliverNoRoute]` 兜底
- 不开启开关时原转交流程完全不受影响

### 14.6 git 状态
- 当前分支：`feature/self-deliver-route`
- 会话 3 已把 v2 MVP 框架代码 + CLAUDE.md 更新提交并 push 到 `myfork/feature/self-deliver-route`
- `.agents/`（外部工具产生的 skill 镜像目录）已加入 `.gitignore`，**不入仓**
- 同步的具体 commit 见第 12 节时间线

---

## 15. 下次会话快速接力指南（重要）

新开窗口时，把下面这段贴给 Claude，能在 1 分钟内恢复完整上下文：

```
继续 MaaEnd「自己送货」v2 MVP 的开发。
请先阅读 e:\TestBase2\MaaEnd\CLAUDE.md，重点看第 13、14 节。
v2 MVP 框架代码已全部落盘并 prettier 通过，git 未提交。
当前推进到阶段 1：等我提交 UI 截图 + 调度申请界面截图 + maa.log 尾巴。

我现在的进度是：[在此填写一句你的当前状态，例如]
- "已跑通阶段 1，提交图 A/B/C"，或
- "阶段 1 没跑，需要你先教我怎么启动 MaaEnd"，或
- "我直接跳到阶段 3 录了 zone_id：xxx，target：xxx"
```

> **沟通要点**：每次接力先报当前阶段（1/2/3/4/5）和你刚做了什么，Claude 就能直接从对应阶段继续，不需要重复解释方案。如果有截图或日志，直接拖到对话框里。

---

## 16. 多电脑接力速查表（2026/05/27 起）

### 16.1 离开当前电脑前（旧电脑 push checklist）

```bash
# 在 e:\TestBase2\MaaEnd 目录下
git status                                # 看一眼有没有遗漏
git add -A                                # 一键加（.agents/ 等已被 ignore，不会误进）
git commit -m "<本次进度的一句话总结>"     # 描述清楚做到哪了
git push myfork feature/self-deliver-route
```

> 已确认 `.agents/` 被 ignore 后，`git add -A` 是安全的；子模块状态不要单独提交。

### 16.2 到新电脑后（新电脑接力 checklist）

**情况 A：新电脑从来没拉过这个仓库**
按第 11.3 节"新电脑首次拉取"那段命令走一遍即可。

**情况 B：新电脑之前已经 clone 过（最常见）**
```bash
cd <新电脑上的 MaaEnd 仓库路径>
git fetch myfork
git checkout feature/self-deliver-route
git pull myfork feature/self-deliver-route
git submodule update --init --recursive
pnpm install                              # 只在 package.json 变过时需要
```

### 16.3 新电脑上跟 Claude 接力的对话咒语

打开新电脑的 Claude Code，在 MaaEnd 仓库根目录下开一个新会话，**第一条消息**贴下面这段（按需修改最后一行）：

```
继续 MaaEnd「自己送货」v2 MVP 的开发。
请先阅读 e:\TestBase2\MaaEnd\CLAUDE.md，重点看第 13、14、15、16 节。
最新状态见第 14.3 节进度表和第 14.6 节 git 状态。

当前阶段：[阶段 1.B / 阶段 2 / 阶段 3 / 阶段 4 / 阶段 5 中的一个]
我刚做了：[一句话描述，例如：
  - "我换了台电脑，已经 git pull 过最新代码，准备跑阶段 1.B 看日志"
  - "我已经跑完阶段 1.B，日志命中预期序列，要进阶段 2"
  - "我跳到阶段 3 录好了 zone_id=XXX、target=[...]"]
```

> 路径换行：如果新电脑的仓库路径不是 `e:\TestBase2\MaaEnd`，记得替换。
> 不需要把整个 CLAUDE.md 内容粘贴给 Claude，让它自己读文件比手动贴更可靠。

### 16.4 同步注意事项

| 事项 | 说明 |
|------|------|
| 子模块变动 | 切分支后 `git status` 显示子模块"有改动"是指针差异，**不要 commit**，用 `git submodule update --init --recursive` 同步即可 |
| 凭据 | 第一次 push 弹 Windows 凭据管理器，用 PAT 而不是密码 |
| install 软链接 | 各电脑独立，新电脑不一定有 install/ 软链接；如果运行 mxu.exe 找不到 resource，要先把仓库根目录的 assets 软链/复制到 install/resource |
| pnpm install | `package.json` 没变就不用跑，省时间 |
| 不要同时两台电脑都改 | 推荐"一台开发，另一台 pull 之后再继续"，避免分叉后手动合并 |


---

## 17. 识别策略最终决定（2026/06/01 会话 5）

### 17.1 从截图观察到的地图行为

用户提供了供能高地两条不同路线的地图弹窗截图（适用所有地区）：

| 属性 | 结论 |
|------|------|
| 地图缩放比例 | **固定不变**（两张背景完全像素一致） |
| 取货点位置 | **同地区固定**（同一地区取货点永远在同一屏幕位置） |
| 送货点位置 | **随路线变化**，且可能超出屏幕边缘 |
| 取货点/送货点标识 | 橙色文字标签「取货点」/「送货点」+ 箭头图标 |

### 17.2 为什么放弃 TemplateMatch 整图方案

- 同地区地图背景完全相同 → 无法区分路线
- 能区分路线的送货点标签位置 → 可能跑出屏幕，TemplateMatch 会匹配失败
- 整图模板匹配需要裁 PNG → 维护成本高，且取货/送货点距离太远时框太大失去意义

### 17.3 最终采用策略：OCR「送货点」标签坐标落点判区间

**核心思路**：
1. 地图弹窗打开后，OCR 识别「送货点」标签文字，获取其在屏幕上的 **Y 坐标**
2. 不同路线的「送货点」Y 坐标落在不同区间 → 判断对应哪条路线
3. OCR 找不到「送货点」（超出屏幕）→ 直接走 `NoRouteMatch` → 安全兜底

**优势**：
- OCR 认字，对画面轻微变化容忍度高
- 取货点固定不用识别，只需识别送货点一个元素
- 送货点跑出屏幕 → 自然兜底，不会误接单
- 不需要裁 PNG，维护成本低

### 17.4 v2.2 SelfDeliver.json 节点设计（待会话 6 实施）

替换 `MatchRouteOriginiumScienceParkA`（TemplateMatch）为基于坐标落点的分发逻辑：

```
DeliveryJobsSelfDeliverClickViewLocation
  ↓ 地图弹窗打开
DeliveryJobsSelfDeliverOCRDeliveryPointLabel   ← OCR「送货点」标签，获取坐标
  ├─ 命中且 Y < 阈值A → DeliveryJobsSelfDeliverRouteDispatchByCoord（按坐标判路线）
  └─ 不命中 → DeliveryJobsSelfDeliverNoRouteMatch（ESC + StopTask）

DeliveryJobsSelfDeliverRouteDispatchByCoord（DirectHit 路由节点）
  ├─ CheckRouteA（OCR roi 限定在「送货点」坐标区间A 内）→ anchor RouteA → CloseMap
  ├─ CheckRouteB（OCR roi 限定在区间B 内）→ anchor RouteB → CloseMap
  └─ NoRouteMatch（兜底）
```

**具体阈值**：需要用户提供源石研究园各路线的地图弹窗截图，Claude 量出各送货点 Y 坐标后确定分界线。

### 17.5 待用户提供的物料（阶段 2 接力点）

1. 📸 **图D**：调度申请界面完整截图（1280×720）→ 量「查看位置」按钮 roi
2. 📸 **图E 系列**：源石研究园**每条路线**的地图弹窗截图 → 量各「送货点」标签 Y 坐标
   - 每张截图游戏内截图，1280×720，不加水印
   - 需要：有几条路线就截几张（每次「查看位置」对应不同买方）
3. 告知每张图对应的买方/目的地名称（例如"这张对应矿区营地"）

### 17.6 时间线更新

| 阶段 | 操作 | 关键产物 |
|------|------|---------|
| 会话 1-4 | v2.1 框架搭建完成，阶段 1.A/1.B 通过 | 见第 12 节 |
| 会话 5 | 对比供能高地两条路线截图，确定 OCR 落点识别策略，放弃 TemplateMatch 方案 | 本节 |
| 会话 6 | 落地 v2.2：重写 SelfDeliver.json 的 MapDispatch（TemplateMatch → OCR 落点），5 个 i18n 去模板图措辞，prettier 通过，push 到 myfork | 见第 18 节 |
| 会话 7 | 确认 roi 用「紧框」（默认选顶部最高报价买方）；收到源石研究园路线 A 地图截图，量出送货点坐标；等路线 B 截图才能定死不重叠区间 | 见第 19 节 |

---

## 18. v2.2 落地（2026/06/01 会话 6）

> 第 17 节是识别策略决定，本节是**实际落地的代码**。实现比 17.4 草图更简：
> 不另写"先 OCR 取坐标再按坐标路由"两段，而是**每条路线一个 OCR 节点，把该路线「送货点」的坐标区间直接写进它自己的 `roi`**——
> 标签落在哪个区间，哪个节点的 OCR 就命中，自然分流。无需自定义识别器算 Y 坐标。

### 18.1 SelfDeliver.json 最终节点结构

```
DeliveryJobsSelfDeliverClickViewLocation（OCR「查看位置」→ Click 打开地图）
  ↓
DeliveryJobsSelfDeliverMapDispatch（DirectHit 路由）
  ├─ DeliveryJobsSelfDeliverCheckRouteOriginiumScienceParkA
  │     （OCR「送货点」，roi 限定在路线 A 坐标区间 → 命中即设 anchor RouteA）
  │        ↓ 命中
  │   DeliveryJobsSelfDeliverCloseMapAndStartDelivery（ESC 关地图）
  │        ↓
  │   DeliveryJobsRedistributionBidNextStep（原节点，点开始运送）
  └─ DeliveryJobsSelfDeliverNoRouteMatch（兜底 → ESC → StopForNoRouteMatch）
```

未改动：`PickupStart` / `NoRoute` / `End`（anchor 占位机制不变），`OriginiumSciencePark.json` 路线内部流程，`BackToDepot.next`，`ClickTransferJob.enabled=false`。

### 18.2 增删节点对照（相对 v2.1）

| 操作 | 节点 |
|------|------|
| 删 | `DeliveryJobsSelfDeliverMatchRouteOriginiumScienceParkA`（TemplateMatch + PNG） |
| 增 | `DeliveryJobsSelfDeliverCheckRouteOriginiumScienceParkA`（OCR「送货点」+ roi 区间） |
| 改 | `MapDispatch.next` → `[CheckRouteOriginiumScienceParkA, NoRouteMatch]` |

新增路线时：复制一个 `CheckRouteXxx` 节点，填它自己的 `roi` 区间 + anchor，插进 `MapDispatch.next`（兜底节点排最后）。

### 18.3 v2.2 TODO 占位清单（最新，取代 13bis.4 / 14.2 的模板图行）

| 文件 | 字段 | 当前值 | 安全性 | 由哪个阶段填 |
|------|------|--------|--------|------------|
| `SelfDeliver.json` | `ClickViewLocation.roi` | `[0, 0, 1280, 720]` | 全屏找「查看位置」，能用但偏慢 | 阶段 2（图D） |
| `SelfDeliver.json` | `CheckRouteOriginiumScienceParkA.roi` | `[0, 0, 1, 1]` | **1px → OCR 必失败 → 走兜底，零道具** | 阶段 3（图E） |
| `SelfDeliver/OriginiumSciencePark.json` | 全部 TODO | 同 14.2 节 | path 空 → on_error 兜底 | 阶段 4-5 |

### 18.4 i18n 文案变更
5 个语言文件的 `SelfDeliverMode.description` 与 `NoRouteMatch`：
- 「地图模板匹配」/「map template matching」→「识别『送货点』标签位置」
- 「请补充路线模板图」/「add a route template image」→「请补充路线坐标区间」

### 18.5 安全前提（v2.2 仍成立）
`CheckRouteOriginiumScienceParkA.roi = [0,0,1,1]` → OCR 必然不命中 → `MapDispatch` 走 `NoRouteMatch` → ESC 关地图 → `StopForNoRouteMatch`（StopTask）。**绝不点「开始运送」，零道具消耗。** 填入真实区间前可放心反复跑。

### 18.6 阶段 2/3 接力：等用户提供的物料
1. 📸 **图D**：调度申请界面完整截图（1280×720）→ 量「查看位置」按钮 roi → 填 `ClickViewLocation.roi`
2. 📸 **图E 系列**：源石研究园**每条路线**的地图弹窗截图（送货点标签可见）→ 量各路线「送货点」标签 `[x, y, w, h]` → 填 `CheckRouteXxx.roi`
   - 多条路线就多截几张，并告知每张对应的买方/目的地名称

---

## 19. 阶段 3 进行中（2026/06/04 会话 7）

### 19.1 本会话两个决定

1. **roi 用「紧框」**：用户确认调度申请界面**永远默认选中列表最顶部（报价最高）的买方**。
   所以 `ClickViewLocation.roi` 只圈顶部那一颗「查看位置」按钮即可，不放宽到整列四个按钮（放宽反而有选中非顶部买方的风险）。
2. **路线 B 之后再补**：用户先给 1 条路线（A）的图，后续路线再追加。

### 19.2 截图换算系数（本会话新确认，重要）

用户的游戏截图是 **2K（2560×1440）**，但通过对话发图时被压到 **2000 宽显示**。
MaaFW pipeline 跑在 **1280×720**。所以从「我在显示图上量到的坐标」换算到「游戏 roi 坐标」：

```
显示图(2000 宽)  ──×0.64──►  游戏坐标(1280 宽)     （0.64 = 1280 ÷ 2000）
```

> ⚠️ 注意：这个 ×0.64 是「2000 宽显示图 → 1280 游戏」。若以后用户改用别的发图方式（不压到 2000 宽），换算系数要重算 = 1280 ÷ 实际显示宽。量参数前先跟用户核对显示宽度。

### 19.3 路线 A 测量结果（源石研究园 / 四号谷地）

图：地图标题「// 四号谷地 / 源石研究园」，含两个橙色标签「取货点」「送货点」。

| 标签 | 显示图(2000×1125)上位置 | ×0.64 → 游戏(1280×720) | 用途 |
|------|------------------------|------------------------|------|
| 取货点 | 中心约 (745, 545) | 中心约 (477, 349) | 固定锚点，**不识别** |
| **送货点（路线A）** | 橙框约 x[1075,1190] y[560,600]，中心(1130,580) | **中心约 (725, 371)**，框约 x[688,762] y[358,384] | 路线 A 要 OCR 的目标 |

> 路线 A 送货点在屏幕**右中部 (725, 371)**。取货点在中部偏左 (477, 349)，两点都在屏幕中央、距离不算远。

### 19.4 当前卡点（下次会话从这里继续）

- ⏳ **等路线 B 的地图截图**才能定死两条路线的 roi。原因：必须保证 A、B 两个「送货点」Y/X 区间**不重叠**（中间留缓冲带），单看 A 无法确认分界线。
- ⚠️ **潜在隐患**：路线 A 送货点离取货点不远、都在屏幕中部。第 17 节原假设「送货点可能跑出屏幕→自然兜底」。若源石研究园几条路线送货点都挤在中部、彼此很近，只看 Y 区间可能分不开 → 那时改用 **X+Y 联合定位**（roi 框得更准）。等图 B 量完间距才能判定。
- 📌 路线 A 的数 (725, 371) 已落盘本节，会话压缩也不丢。

### 19.5 下次接力第一步
用户发**路线 B 地图截图**（2K 直接发，标注对应买方/目的地）+ 确认显示宽度仍是 2000 → Claude 量 B → 确认不重叠 → 一次性把 A/B 两个 `CheckRouteXxx.roi` 写进 `SelfDeliver.json`。
（注：`ClickViewLocation.roi` 已在会话 6 阶段 2 填好 = `[1040,150,140,50]`，见 SelfDeliver.json 第 14 行；图D 不再缺。）

---

## 19bis. 会话 8（2026/06/05）：识别方式改 OCR → ColorMatch + 边缘识别讨论

### 19bis.1 本会话决定（重要，下次别退回 OCR）
1. **识别方式从 OCR「送货点」文字 → 改为 ColorMatch 橙色标记**。
   - 起因：用户问「取货点/送货点标签处于地图边缘时会显示不全或边缘变暗，能否仍识别」。
   - 结论：**边缘变暗/文字被裁断** → ColorMatch 比 OCR 稳得多（橙色在灰绿地图上独特，露几个像素即可命中；变暗只需放宽橙色亮度下限）。送货点图标下还有一个橙色小图标 → 多一块橙色证据。
   - **标签真跑出屏幕外**（不在视野）→ 任何截图识别都救不了，仍走 NoRouteMatch 兜底（不写地图拖动，不进 MVP）。
2. ⚠️ **ColorMatch 解决「变暗」但解决不了「重叠」**：两条路线送货点挤在屏幕同一块 → 坐标区间重叠问题，需换区分维度（如 OCR 送货点旁的**地区名**灰字标签：研究所/生态种植区/崖边山道…）。变暗与重叠是两件事，要一起定。

### 19bis.2 ColorMatch 写法参考（仓库现成范例）
- `assets/resource/pipeline/SceneManager/SceneMap.json` 第 287 行、第 352 行：
  - 第 352 行匹配**黄橙色**：`lower:[245,229,0]` `upper:[255,249,10]` + `connected:true` + `count:10` —— 与「送货点」橙色同类，可直接借鉴。
- 字段：`lower`/`upper`（RGB 上下界）、`connected`（连通域）、`count`（最小连通像素数，防误判）。
- **橙色精确 RGB 范围 + count 阈值要对着真实截图像素调**，故未写死，等路线 B 图一起定。

### 19bis.3 待落地的节点改动（等路线 B 图后一次性做）
把 `DeliveryJobsSelfDeliverCheckRouteOriginiumScienceParkA` 由 OCR 改 ColorMatch：
- `recognition: "OCR"` + `expected:["送货点"]` → `recognition:"ColorMatch"` + `lower/upper/connected/count`
- `roi` 仍是该路线送货点所在的坐标区间（落点判区间逻辑不变，只是把"认字"换成"认橙色"）
- 安全占位：当前 `roi:[0,0,1,1]` 改 ColorMatch 后 1px 内不可能有 count 个橙色像素 → 仍必然不命中 → 走兜底，零道具消耗（安全前提 18.5 不变）。
- i18n 第 18.4 节的「识别『送货点』标签位置」措辞仍贴切，无需再改。

### 19bis.4 本会话收到的图
用户发的「源石研究园」地图截图，量出送货点游戏坐标约 (728,371)，与会话 7 路线 A (725,371) **重合** → 经确认是**路线 A 重发**，非新数据。手头仍只有 1 条路线，卡点不变：**等真·路线 B（目的地明显不同）截图**。
