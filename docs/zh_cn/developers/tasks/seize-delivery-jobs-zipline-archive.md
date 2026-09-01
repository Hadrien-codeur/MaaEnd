# 固定滑索送货方案 — 存档、避坑指南与移植参考

> **状态：已归档（2026-09-01）**，分支 `feature/zipline-fast`。
> 本方案**不再继续开发**，作为兜底保留。后续在上游最新 NavMesh 进度基础上重新移植。
>
> 阅读顺序建议：先读 §1（结论）→ §5（避坑指南，最有价值）→ §6（移植建议）。
> 录制操作细节见配套文档 [seize-delivery-jobs-route-recording.md](./seize-delivery-jobs-route-recording.md)。

---

## 1. 归档结论（先看这个）

### 1.1 为什么归档

不是因为方案跑不通，而是**上游变了**：

1. 上游完成了 MapTracker → MapNavigator/NavMesh 的迁移，官方送货链路本身变得更完善；
2. 我们这套方案建立在 `go-service/maptracker` 包之上（`MapTrackerZipline` / `MapTrackerToward` / `MapTrackerInfer`），而该包正是上游计划删除的目标；
3. 在旧基线上继续打补丁，迁移成本只会越滚越大。

**决策**：以上游最新进度为基线重新移植我们的需求，本方案冻结为兜底。

### 1.2 冻结时的实际可用范围

| 地图 | 取货段 | 送货路线 | 状态 |
| --- | --- | --- | --- |
| 武陵城 `map02_lv002` | ✅ 已测通 | 4 条：`Owl` / `MaterialResearchInstitute` / `Observatory` / `TechProductionOffice` | ✅ **相对稳定，兜底可用** |
| 试验园区 `map02_lv005` | ✅ 已测通 | 3 条：`No1TypeCAnchorArea` / `No3TypeCAnchorArea` / `JingweiFieldArea` | ✅ 可用 |
| 源石研究园（四号谷地）`map01_lv005` | ❌ 卡死 | 5 条：`HighwayFive` / `CommandCenter` / `RefiningCompoundFactory` / `ResearchInstitute` / `ResearchInstituteLower` | ❌ **已放弃，见 §7** |

> ⚠️ **四号谷地的代码仍在仓库里且仍会被 `departure.go` 匹配执行**（本次决定不动代码）。
> 若要把兜底方案实际用在四号谷地，**必须先修 §7.1 的坐标 Bug**，否则必然卡死。

---

## 2. 整体实现思路

### 2.1 核心想法

官方送货用 `MapTrackerGoal` 做 NavMesh 寻路，全程走地面 → 会遇到出怪、好友设施干扰、卡地形。
我们的思路：**把地面长途替换成「预录的固定滑索路线」**——空中不掉血、不遇怪、耗时可预测。

### 2.2 三明治模型

无论取货段还是送货段，一条路线都是同一个结构：

```
步行到起点滑索架 → 上索 → 滑行（可连滑） → 下索 → 步行到目标 NPC
 MapNavigateAction  现成节点   MapTrackerZipline   现成节点   MapNavigateAction
   (base px)                  (MapTracker 坐标)              (base px)
```

用 `SubTask` 把 5 段串起来，一条路线 = 一个 `SeizeDeliveryJobsDeliverRoute<Endpoint>` 节点。

### 2.3 数据流：蓝标 → 路线分流

送货段最关键的一环，是**怎么知道该跑哪条路线**：

```
big-map 上的蓝色任务标记
  ↓ MapTrackerBigMapFindImage（模板匹配 BlueTaskLocation.png）
  ↓ 得到 (map_name, MapTracker 世界坐标)
  ↓ departure.go: nearestEndpoint(mapName, target)
  ↓ 在 seizeDeliveryJobsEndpoints[mapName] 里找半径 30 内最近的预录终点
  ├─ 命中 → RunTask("SeizeDeliveryJobsDeliverRoute" + Name)   ← 跑我们的滑索路线
  └─ 未命中 → MapTrackerGoal (NavMesh)                        ← 回退官方寻路
```

**这个「命中走固定路线、未命中回退官方」的设计是整套方案最值得保留的部分**，它让我们的改动是**增量叠加**而非替换：新地图没录路线时自动退回官方行为，不会把上游功能改坏。

`custom_delivery: true` 可强制只走固定路线（不回退），用于测试入口。

### 2.4 复用：不改上游节点

`DeliveryJobs`（转交委托）的「自动送货」选项复用了整套能力，**没有新写任何流程节点**——
所有接线都写在 `assets/tasks/DeliveryJobs.json` 的 `pipeline_override` 里，
`assets/resource/pipeline/` 下只**新增**了 `DeliveryJobs/AutoDeliver.json`。

> ✅ **这是本项目最成功的一个决策，务必在新方案里延续。**
> 上游更新这些节点时不会产生冲突。相比之下，取货段当年用的是「整节点替换」，
> 每次上游动一下就要人工合并，痛苦得多。

---

## 3. 文件清单（存档索引）

### 3.1 Pipeline

| 文件 | 行数 | 内容 | 归属 |
| --- | --- | --- | --- |
| `SeizeDeliveryJobs/SeizeDeliveryJobsDeliverRoutes.json` | 1489 | **送货路线主体**：12 条路线 + 测试入口 | 我们新增 |
| `SeizeDeliveryJobs/SeizeDeliveryJobsPost.json` | 803 | 取货段（3 张图）+ 传送 + 地区判定 + 接货 | 上游 + 我们大改 |
| `SeizeDeliveryJobs/SeizeDeliveryJobsPostDeparture.json` | 270 | 送货出发段 | 上游 |
| `SeizeDeliveryJobs/SeizeDeliveryJobsEndpointFilter.json` | 252 | 终点名定义（须与 `departure.go` 严格一致） | 上游 |
| `SeizeDeliveryJobs/SeizeDeliveryJobsCommon.json` | 307 | 公共节点（`EnterDestinationMap` 等） | 上游 |
| `DeliveryJobs/AutoDeliver.json` | 262 | 转交委托复用送货的桥接节点 | 我们新增 |

### 3.2 Go Service

| 文件 | 行数 | 内容 |
| --- | --- | --- |
| `agent/go-service/seizedeliveryjobs/departure.go` | 502 | **分流核心**：蓝标识别 → 终点匹配 → 跑路线 / 回退 NavMesh |
| `agent/go-service/seizedeliveryjobs/find_target.go` | 212 | 蓝标查找 |
| `agent/go-service/seizedeliveryjobs/scan_target.go` | 175 | 目标扫描 |

依赖的 maptracker 组件（**上游计划删除**）：
`MapTrackerZipline`（滑索，×12 处）、`MapTrackerToward`（索上转向，×1 处）、
`MapTrackerOpenWorld_GetOnZipline` / `_GetOffZipline`、`MapTrackerBigMapFindImage`、
`MapTrackerAssertLocation`、`MapTrackerGoal`。

### 3.3 终点表（`departure.go`）

```go
var seizeDeliveryJobsEndpoints = map[string][]seizeDeliveryJobsEndpoint{
    "map02_lv002": { // 武陵城
        {Name: "Owl",                       Target: [2]float64{229.1, 604.6}},
        {Name: "MaterialResearchInstitute", Target: [2]float64{178.4, 666.5}},
        {Name: "Observatory",               Target: [2]float64{617.1, 358.0}},
        {Name: "TechProductionOffice",      Target: [2]float64{255.2, 197.4}},
    },
    "map02_lv005": { // 试验园区
        {Name: "No1TypeCAnchorArea", Target: [2]float64{126.7, 114.2}},
        {Name: "No3TypeCAnchorArea", Target: [2]float64{415.9, 193.8}},
        {Name: "JingweiFieldArea",   Target: [2]float64{429.7, 294.7}},
    },
    "map01_lv005": { // 源石研究园 —— ⚠️ 已放弃，坐标存疑，见 §7.1
        {Name: "HighwayFive",             Target: [2]float64{172.2, 307.6}},
        {Name: "CommandCenter",           Target: [2]float64{104.3, 242.3}},
        {Name: "RefiningCompoundFactory", Target: [2]float64{349.2, 389.8}},
        {Name: "ResearchInstitute",       Target: [2]float64{404.1, 300.0}},
        {Name: "ResearchInstituteLower",  Target: [2]float64{364.8, 303.6}},
    },
}
```

- 匹配半径 `seizeDeliveryJobsEndpointMatchRadius = 30`
- 节点名前缀 `seizeDeliveryJobsDeliverRoutePrefix = "SeizeDeliveryJobsDeliverRoute"`
- ⚠️ **终点名必须全局唯一（跨地图也不能重名）**——节点名是「前缀 + 名字」拼出来的，重名会跑到另一张图的路线上

### 3.4 测试入口

12 个 `SeizeDeliveryJobsTestDeliver*.json` + 3 个 `SeizeDeliveryJobsTestPickup*.json`，
均已在 `assets/interface.json:196-210` 注册。跑完即停，只核对路线和落点。

---

## 4. 两个坐标系（最容易出事的地方）

**整套方案里有两个坐标系，混用是最高频的故障源。**

| 坐标系 | 谁吃它 | 怎么得到 |
| --- | --- | --- |
| **MapTracker 游戏坐标** | `MapTrackerZipline.target`、`MapTrackerAssertLocation`、`departure.go` 终点表、big-map 蓝标 | MapTracker 工具直接读 |
| **base px** | `MapNavigateAction` 的 `NAVMESH` / `HEADING` 点 | MapTracker 坐标**换算**，或 MapNavigator 工具直接读 |

### 换算公式

```
base_x = offset_x + mt_x × scale_x
base_y = offset_y + mt_y × scale_y
```

参数只在 [`assets/resource/image/MapLocator/maptracker_coordinate_transforms.json`](../../../../assets/resource/image/MapLocator/maptracker_coordinate_transforms.json)，按 `map_name` 取行：

| map_name | zone_id | offset_x | offset_y | scale_x | scale_y |
| --- | --- | --- | --- | --- | --- |
| `map02_lv002`（武陵城） | `Wuling_Base` | 288.0 | **1056.0** | 0.985176738883 | 0.985074626866 |
| `map02_lv005`（试验园区） | `Wuling_Base` | 960.0 | **1344.0** | 0.985337243402 | 0.984615384615 |
| `map01_lv005`（源石研究园） | `ValleyIV_Base` | **810.0** | **540.0** | 0.923753665689 | 0.923076923077 |

> ⚠️ **最常见的错误：把 `offset` 当 0。** 换算后如果某点比预期少了一大截，先怀疑漏了 offset。
>
> **自检技巧**：`offset` 就是该地图在大图里的裁剪原点，所以**换算结果必然 ≥ offset**。
> 例如源石研究园的任何 base px 点，`y` 都应 ≥ 540；若算出 y=288，一定错了（§7.1 就栽在这）。

---

## 5. 避坑指南（本方案最有价值的部分）

以下每一条都是实机踩出来的，**新方案移植时逐条对照**。

### 5.1 ⚠️ HEADING 的 target ≠ NAVMESH 的 target

- `NAVMESH.target` = **人要站的位置**
- `HEADING.target` = **要面朝的对象**（NPC 本体 / 滑索架本体）

录成同一个点则算不出角度。录 HEADING 时人站在落点不动，把准星点在 **NPC 身上**，不是脚下。

### 5.2 ⚠️ HEADING target 距站位必须 ≥ 2m

MapLocator 单帧定位抖动约 **0.7m**，目标太近时角度完全被噪声主导：

| 站位→目标距离 | 角度不确定度 | 结论 |
| --- | --- | --- |
| 0.57m | ±**51°** | ❌ 不可用（Owl 初版栽在这，转向完全随机） |
| 1.0m | ±35° | ⚠️ 勉强（靠 40° 容差兜住，不稳） |
| **≥ 2.0m** | ±20° 以内 | ✅ 可用 |

C++ 侧容差 `kHeadingAcceptToleranceDeg = 40.0`。**低于 2m 就重录一个更远的目标点。**

### 5.3 ⚠️ 滑索 `target` 是「下一架」，不是脚下这架

`MapTrackerZipline.target` **只用来算方位角**（`result.Loc.AngleTo(target)`），必须是远处的下一架。

| 参数 | 指向 | 距站位 |
| --- | --- | --- |
| 起点段 `HEADING.target` | 脚下这架（正对以便上索） | 1~2 m |
| `MapTrackerZipline.target` | **第一跳飞向的下一架** | 通常 30~80 m |

**别把起点段 HEADING 的坐标抄过来**。已测通路线实际值：武陵城 31~54m，试验园区 38m。
**算出 < 5m 基本就是抄错了。**

> **实战案例（2026-08-08）**：试验园区三条路线全部卡在上索后不发射。
> 日志 `distance=0.57` + `similarity=0.9999917` + 1.8 秒就返回 false（timeout 是 60s，不是超时）。
> 根因就是 `target` 抄成了起点架 → 方位角是噪声（只转了 3°）→ 没锁到索 → 按 E 空点。
> **`distance` 那行日志是最快的判据。**

### 5.4 ⚠️ `chain_max_press` 只认「跳数」，不认「架数」

```
起点架 ──跳1──> 架2 ──跳2──> 架3 ──跳3──> 终点架
（脚下）                                （落这里）

含起点架 4 架 = 3 跳 → chain_max_press = 3 − 1 = 2
```

| 表述 | 公式 |
| --- | --- |
| **跳数（推荐）** | `chain_max_press = 跳数 − 1` |
| 含起点架的架数 | `chain_max_press = 架数 − 2` |
| 不含起点架的架数 | `chain_max_press = 架数 − 1` |

最后一跳的提示故意不按，人物就落在终点架。

> **写注释必须标明基准**（「共 6 架（含起点）= 5 跳」）。
> 武陵城旧注释**不含**起点架，试验园区新注释**含**起点架，套同一个公式必然差 1。
> 数错的表现是「落错滑索架」。

### 5.5 ⚠️ `MapTrackerToward` 会把人推偏

索上转向用的 `MapTrackerToward`，实现是「转镜头 → 后退 250ms → 前进 75ms」，
**净位移往后**，而且**循环执行到角度收敛**（容差 12°，超时 5s）。
实测 Owl 跑了 4 轮，把索上挂点推偏 **3.6m**，下索落点跟着错。

**能用的前提**：后面紧跟 NAVMESH 步行段（会从实际位置重新 A\*，自己走回来）。
**后面没有 NAVMESH 兜底就不要用。**

### 5.6 ⚠️ 走位一律用 NAVMESH，不要用 `MapTrackerMove`

| | `NAVMESH`（C++ `MapNavigateAction`） | `MapTrackerMove`（Go） |
| --- | --- | --- |
| 寻路 | 读 `.nav` 文件真 A\* | 无，直线推算 |
| 控制 | 闭环，`strict_arrival = true` | **开环**：截图定位 → 转镜头 → 按方向键 |
| 远距离 | 稳 | 拉 sprint 时截图延迟直接变过冲距离 |

试过「MapTrackerMove 多断点调朝向」，实测坐标不准、常冲出去一段，已废弃。**别再走回头路。**

另外：`MapTrackerMoveCompatible` 是 Go 垫片，**会静默丢 NAVMESH 点，绝不能用**。

### 5.7 ⚠️ 同一个公共节点被调用多次，每次所处界面不同

**这是本分支耗时最长的一个坑（08-21 ~ 08-23）。**

`SeizeDeliveryJobsEnterDestinationMap` 在整条送货链被调用 **3 次**：

| 调用点 | 角色所处界面 |
| --- | --- |
| `PostProcessingEntry`（传送前） | **仓储界面** |
| `PrepareFetchGoods`（取消追踪前） | **大世界** |
| `PostDepartureRun`（送货前） | 大世界 / 仓储 |

我们当初用 `pipeline_override` 把它的 `next` **无条件全量改道**到「仓储界面查看任务 → 打开地图」，
而这条路**只在仓储界面有效** → 第 2、3 次调用时 8 个识别全 miss → 空转 20 秒卡死。

**教训**：
1. **override 一个公共节点前，先数清楚它被调用几次、每次在什么界面**；
2. 改道时要让 `next` 覆盖**所有**调用场景（我们最终的解法是在 `next` 里补 `SceneEnterMapAny` 覆盖大世界场景）；
3. 替代节点**不能加 `max_hit`**，否则第二次进不去。

### 5.8 ⚠️ 锚点（Anchor）必须覆盖所有入口路径

同一个 anchor 有多条入口路径时，**每条都要赋值**。

我们的 `DeliveryJobsAutoDeliverBackToDepot` 最初只在**装箱路径**（`EnterXXXCargo`）里赋值，
**「已有单」路径**（`EnterXXXDeliveryJob`）没赋 → 走到兜底时报
`get_pipeline_data failed, node not exist` → 卡死。

**症状识别**：日志里出现 `node not exist` 且节点名是个 anchor 占位符 → 就是漏赋值。

### 5.9 ⚠️ `SceneEnterMapAny` 不能当「中间步骤」用

曾尝试给改道节点补 `SceneEnterMapAny`（官方大世界打开地图），**第一次实测失败并回退**：
该节点打开地图后 `next` 没有 JumpBack 回调用者，**控制权漂移到主循环**，后续流程接不上。

它是「打开地图并结束」的**独立节点**。要在它之后继续流程，必须用 `[JumpBack]` 语义把控制权拿回来。

### 5.10 ⚠️ 自己装箱产生的委托不在「运送委托列表」里

官方 `EnterDestinationMap` 走的是「仓储管理 → 运送委托列表 → 查看当前任务 → 点定位」。
**这条路只适用于抢来的委托。**

实测（2026-08-06）：自己装箱产生的委托**不出现在运送委托列表**，
`__SeizeDeliveryJobsRecoViewCurrentJob` 识别不到，流程直接卡死。

正确路径是走**本地仓储节点页签的「查看任务」**。

### 5.11 ⚠️ 依赖 MapTracker/MapNavigator 的选项必须限制控制器

只有 `Win32-Front` 和 `Wlroots` 支持。

`SeizeDeliveryJobs` 整个任务只声明这两个，但 `DeliveryJobs` 任务本身支持 ADB / MacOS / PlayCover，
所以要在**选项级**加 `"controller": ["Win32-Front", "Wlroots"]`。

### 5.12 其他工程约束

- **改 pipeline JSON 后必须完整重启 `MaaEnd.exe`**（软链接保证文件最新，但已运行进程的内存不重载）
- **改 Go 后必须** `pnpm format:go` + `python tools/build_and_install.py`
- `install/interface.json` 是**复制文件不是软链接**，改了 `assets/interface.json` 要手动同步
- 录制工具**必须从仓库根目录启动**，否则相对路径解析出错报 503

---

## 6. 移植到新方案的建议

### 6.1 先做的三件事

1. **确认上游 MapNavigator 是否已具备滑索能力。**
   截至 2026-08 调研，MapNavigator 的 12 种 action（`RUN` / `SPRINT` / `JUMP` / `FIGHT` / `INTERACT` /
   `TRANSFER` / `PORTAL` / `HEADING` / `NAVMESH` / `ZONE` / `COLLECT` / `DIG`）**没有任何一种能替代乘索/连滑/索上转向**。
   → **这是整个移植的前置判断题**：
   - 若上游已加滑索 action → 直接用官方能力重写，本方案只留路线坐标；
   - 若仍无 → 要么保留 maptracker 滑索子集，要么放弃滑索改纯 NavMesh（见 6.2）。

2. **评估上游新方案的成功率是否已经够用。**
   若官方纯 NavMesh 送货已经稳定，我们「加滑索」的收益可能不再值得这套维护成本——
   **先测官方基线，再决定要不要做**。

3. **重新测量坐标换算参数**，不要直接复制本文档的表（地图更新会变）。

### 6.2 保留哪些、丢弃哪些

| 保留 ✅ | 丢弃 ❌ |
| --- | --- |
| **§2.3 蓝标 → 终点匹配 → 分流 + 回退**的架构 | 「整节点替换」的接线方式（取货段旧做法） |
| **§2.4 全部走 `pipeline_override`、不改上游节点** | 对 `go-service/maptracker` 的深度耦合 |
| §5 全部避坑条目 | 四号谷地的全部坐标（§7.1） |
| 武陵城/试验园区的**滑索架位置与连滑跳数**（实机信息，重录成本高） | 已换算的 base px 值（换算参数会变，留 MapTracker 原值即可） |
| 测试入口「跑完即停」的三段结构 | |

> 💡 **强烈建议**：新方案里把每个路线点的 **MapTracker 原始坐标写进注释**（我们做到了，非常救命）。
> 换算参数一变，只要有原值就能批量重算，不用回游戏重录。

### 6.3 兼容性备选（若上游仍无滑索能力）

| 方案 | 成本 | 评价 |
| --- | --- | --- |
| ① 保留 maptracker 滑索子集 | 最小 | 违背上游方向，长期要还债 |
| ② 移植进 C++ MapNavigator | 中 | **本机无 C++ 工具链，编不了** |
| ③ 抽独立 Go 包 | 名义 500 行，实际连带 1500~2000 行 | 深度耦合：`Infer` 被所有段共享拆不开，`goal.go` 反向调 `zipline` 成循环依赖 |

---

## 7. 四号谷地（源石研究园）：已放弃 + 遗留缺陷

**决定：放弃开发，流程不成熟。** 代码保留在仓库中未删除，但**不要直接复用**。

### 7.1 🔴 坐标 Bug：ValleyIV 全部步行点的 base px 换算错误

> **这是分析仓库数据得出的结论，未经实机验证**（本次决定不动代码），
> 但算术证据很强，且能完整解释 08-23 的卡点。**移植时务必先验证这一条。**

**现象**：`map01_lv005` 的所有 `NAVMESH` / `HEADING` 点，`y` 值都在 222~390 之间。

**为什么这不可能**：换算公式 `base_y = 540.0 + mt_y × 0.923077`，而 `mt_y ≥ 0`，
所以源石研究园的任何 base px 点**必然 `y ≥ 540`**。实际值全部 < 540 → 结构性错误。

**反推出错在哪**（用 3 个点交叉验证）：

以 `SeizeDeliveryJobsDeliverRouteCommandCenterWalkToNpc` 的最后一个 NAVMESH 点 `[817.29, 224.12]` 为例，
若用**错误的** offset `(720, 0)` 反推：

```
mt_x = (817.29 − 720) / 0.923754 = 105.3
mt_y = (224.12 − 0)   / 0.923077 = 242.8
```

得到 `[105.3, 242.8]`，与 `departure.go` 里 `CommandCenter` 的终点 `[104.3, 242.3]` **吻合到 1 个单位内**。
用 `RefiningCompoundFactory` 的 HEADING 点 `[1042.34, 359.82]` 同法反推得 `[348.9, 389.8]`，
与终点表 `[349.2, 389.8]` **几乎完全一致**。

**结论**：当初换算 ValleyIV 坐标时用的是 offset `(720, 0)`，而正确值是 `(810, 540)`。

**修复方法（纯平移，scale 无误）**：

```
正确 base px = 现有值 + (90, 540)
```

需要修正的节点（`SeizeDeliveryJobsDeliverRoutes.json` + `SeizeDeliveryJobsPost.json`）：
`SeizeDeliveryJobsDeliverValleyIVWalkToZipline`、5 条路线的 `...WalkToNpc`、
以及取货段的 `SeizeDeliveryJobsOriginiumScienceParkWalkToZipline` / `...WalkFromZipline`。

**这很可能就是 08-23 卡点的根因**：CLAUDE.md §18 记录卡在
`SeizeDeliveryJobsOriginiumScienceParkWalkToZipline`，该节点首个 NAVMESH 点是 `[876.18, 290.49]`，
`y=290` 落在 NavMesh 可行域之外 → A\* 无解 / 永不到达 → 无限等待。
**与「取消追踪/锚点」无关，是坐标问题。**

> 对照组：武陵城与试验园区的坐标**换算正确**，可反推验证——
> 试验园区注释「MapTracker `[297.2,413.3]`」→ `960 + 297.2×0.985337 = 1252.84`、
> `1344 + 413.3×0.984615 = 1750.94`，与文件中的 `[1252.84, 1750.94]` 完全一致 ✅。

### 7.2 🟡 `chain_max_press` 与注释不一致

| 节点 | 注释说 | 实际值 | 按公式应为 |
| --- | --- | --- | --- |
| `...HighwayFiveZiplineA` | 3 架含起点，按 1 次 E | **缺失（默认 0）** | 1 |
| `...CommandCenterZiplineA` | 3 架含起点，按 1 次 E | **缺失（默认 0）** | 1 |
| `...RefiningCompoundFactoryZiplineA` | 6 架含起点，按 **4** 次 E | **2** | 4 |
| `...ResearchInstituteZipline` | 4 架含起点，按 2 次 E | 2 ✅ | 2 |
| `...ResearchInstituteLowerZipline` | 4 架含起点，按 2 次 E | 2 ✅ | 2 |

`chain_max_press` 缺失时默认 0（不连滑，落在第一架），会导致**落错滑索架**（§5.4）。

### 7.3 🟡 注释提到「索上转向」但 SubTask 里没有对应节点

`...HighwayFiveZiplineB` / `...CommandCenterZiplineB` / `...RefiningCompoundFactoryZiplineB/C`
的 `desc` 都写着「索上转向后发射朝 …」，但对应路线的 `SubTask.sub` 列表里**没有 `MapTrackerToward` 节点**
（对比武陵城 Owl 有独立的 `...ZiplineFaceBeforeGetOff`）。
注释与实现不符，说明这几条路线**从未跑通过**。

### 7.4 若将来要恢复四号谷地

按顺序做：
1. 修 §7.1 坐标（全部 `+ (90, 540)`），并重新反推校验 `departure.go` 终点表；
2. 修 §7.2 的 `chain_max_press`；
3. 澄清 §7.3 的转向节点到底要不要；
4. 用 5 个已有测试入口逐条实机验证。

---

## 8. 排查速查表

| 现象 | 先查什么 |
| --- | --- |
| 上索失败 / 没上去 | 起点步行段 HEADING 是否正对滑索架（§5.1/5.2） |
| 滑索没发射 | `target` 是否是**下一架**、距站位 ≥ 15m（§5.3）；日志搜 `Zipline fast travel did not start`，看 `distance` |
| 落错滑索架 | `chain_max_press` 数错（§5.4） |
| 下索落点偏 | 是否用了 `MapTrackerToward`（§5.5） |
| 走到 NPC 但交互按钮不出 | HEADING target 距站位是否 ≥ 2m（§5.2）；是否从 NPC 背后绕行 |
| **步行段一直不动 / 无限等待** | **坐标是否在合法范围（§4 自检、§7.1）** |
| Go 分流匹配不到路线 | 终点是否用了 MapTracker 坐标系；是否在半径 30 内 |
| 空转 20 秒后卡死 | 公共节点多次调用场景没覆盖（§5.7）；anchor 漏赋值（§5.8，日志搜 `node not exist`） |

**日志位置**：

| 文件 | 看什么 |
| --- | --- |
| `install/debug/cpp-algo/debug/maafw.log` | NAVMESH / HEADING（搜 `Heading-only node completed`、`NAVMESH generated path`、`position.x=`） |
| `install/debug/go-service.log` | 滑索、`MapTrackerToward`（搜 `Adjusting orientation`、`Zipline chain relay`、`Zipline fast travel`） |

---

## 9. 术语对照

| 别混 | 区别 |
| --- | --- |
| `MapNavigateAction` vs `MapTrackerMoveCompatible` | 前者 = C++ 真 A\*（步行段用）；后者 = Go 垫片，**会静默丢点，绝不能用** |
| `MapLocateAssertLocation` vs `MapTrackerAssertLocation` | 前者 C++ 用 base px；后者 Go 用 MapTracker 坐标 |
| `MapTrackerGoal` vs 固定滑索路线 | 前者官方 NavMesh 寻路（`zipline_policy` 四档）；后者本项目预录路线 |
| HEADING vs `MapTrackerToward` | 前者是 `MapNavigateAction` 的 path 节点，闭环无位移；后者是独立 action，**会位移** |
| base px vs MapTracker 坐标 | 步行段吃 base px；滑索段、`departure.go` 终点、big-map 蓝标吃 MapTracker 坐标 |
