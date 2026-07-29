# 试验园区（map02_lv005）送货路线录制清单

给博士实机照着走的操作清单。录制规范全文见 [seize-delivery-jobs-route-recording.md](./seize-delivery-jobs-route-recording.md)，本文只列**这次要录什么、怎么读数**。

已知目标：**1 个取货点 + 3 条送货路线**。

---

## 0. 开工前必读的两条硬规矩

这两条踩过坑，违反了路线一定不稳（规范 §3）。

### 规矩 1：HEADING 的点 ≠ NAVMESH 的点

- `NAVMESH.target` = **人要站的位置**
- `HEADING.target` = **要面朝的对象**（NPC 本体 / 滑索架本体）

录 HEADING 时：人站在落点不动，把**准星/鼠标点在 NPC 或滑索架身上**，不是点自己脚下。录成同一个点则算不出角度。

### 规矩 2：HEADING 目标距站位必须 ≥ 2m

MapLocator 单帧定位抖动约 0.7m，目标太近时角度被噪声主导：

| 站位→目标距离 | 角度不确定度 | 能否用 |
| ------------- | ------------ | ------ |
| 0.57m | ±51° | ❌ Owl 初版栽在这，转向纯随机 |
| 1.0m | ±35° | ⚠️ 勉强 |
| **≥ 2.0m** | ±20° 以内 | ✅ |

**距离低于 2m 就重录一个更远的目标点。**

---

## 1. 工具准备

两个工具都**必须从仓库根目录启动**，否则相对路径解析出错报 503。

| 工具 | 启动命令 | 网址 | 读出来是什么坐标 |
| ---- | -------- | ---- | ---------------- |
| MapTracker | `python tools/map_tracker/map_tracker_master.py` | http://127.0.0.1:8060/web/ | **MapTracker 游戏坐标**（与 big-map 蓝标同系） |
| MapNavigator | `python tools/MapNavigator/main.py` | http://127.0.0.1:8770/ | **base px**（NAVMESH 用的坐标系） |

需要 `maafw` pip 包（import 名是 `maa`）。

**MapNavigator 快捷键**（[recording_service.py:207-228](../../../../tools/MapNavigator/recording_service.py#L207)）：

- 按 **`G`** = 复制当前位置坐标到剪贴板，格式 `[x, y]`，同时显示 `zone`
- 按 **`X`** = 在当前位置打一个严格到达点

> ⚠️ **`zone` 值要一起记下来**。武陵城是 `Wuling_Base`，试验园区的 zone 需要实测确认（`map02_lv005` 属于哪个 zone 表里没写）。

---

## 2. ⚠️ 第一步：标定坐标换算参数（必须先做）

### 为什么必须先做

`map02_lv005` **不在** [maptracker_coordinate_transforms.json](../../../../assets/resource/image/MapLocator/maptracker_coordinate_transforms.json) 里 —— 表里只有 `map02_lv001/002/003/004`。

没有 `offset_x/offset_y/scale_x/scale_y`，MapTracker 坐标就换不成 base px，**所有步行段的 NAVMESH 都写不出来**。

滑索段、`departure.go` 终点、`MapTrackerBigMapPick` 直接吃 MapTracker 坐标，不受影响。

### 怎么标定

**同时开着两个工具**，站在同一个位置分别读两个数。

找 **3 个位置**，要求：

- 两两之间**尽量远**（越远越准，建议横跨大半张图）
- 站得稳、地面平整、周围没有会挤过来的 NPC/玩家
- 前 2 个用来解方程，第 3 个用来交叉验证

| 点 | MapTracker 坐标 | base px 坐标 | zone |
| --- | --------------- | ------------ | ---- |
| C1 | `[    ,     ]` | `[    ,     ]` | |
| C2 | `[    ,     ]` | `[    ,     ]` | |
| C3（验证用） | `[    ,     ]` | `[    ,     ]` | |

**操作**：站定 → 在 MapTracker 网页读坐标记下 → 切到 MapNavigator 按 `G` 复制 → 记下。**人不要动**，两个数必须是同一位置。

换算公式（规范 §6）：

```
base_x = offset_x + mt_x × scale_x
base_y = offset_y + mt_y × scale_y
```

两点两组解出 offset/scale，第 3 点验证。**误差 1px 内算通过。**

> 如果 MapNavigator 在试验园区读不出位置（定位失败/zone 不认），**先告诉我，不要硬录** —— 说明这张图 base.nav 可能不覆盖，方案要换。

---

## 3. 取货路线（1 条）

### 3.1 先定传送锚点

试验园区有两个现成锚点（[SceneWuling.json:456-477](../../../../assets/resource/pipeline/Interface/SceneWuling.json#L456)）：

| 节点名 | 位置 | MapTracker 坐标 |
| ------ | ---- | --------------- |
| `SceneEnterWorldWulingTestArea1` | 综合科研区下 | `[336.3, 420.1]` |
| `SceneEnterWorldWulingTestArea2` | 测试区 | `[391.6, 362.5]` |

**要定的**：哪个锚点离起点滑索架更近 → 选它。

已知取货点在 `[297.5, 414.3]`（上游现值），看着 TestArea1 更近，但**要实机确认滑索架在哪**才能定。

**填**：选用锚点 = `SceneEnterWorldWulingTestArea____`

### 3.2 要录的坐标

全部用 **MapTracker** 录。

| # | 录什么 | 用途 | 值 |
| --- | ------ | ---- | --- |
| P1 | 传送落点 | NAVMESH 首点 | `[    ,     ]` |
| P2 | 落点→滑索架途经点 1 | NAVMESH 走位 | `[    ,     ]` |
| P3 | 落点→滑索架途经点 2（可选） | NAVMESH 走位 | `[    ,     ]` |
| P4 | **起点滑索架本体** ⚠️规矩1 | HEADING 正对滑索架 | `[    ,     ]` |
| P5 | 发射要瞄准的**下一架**滑索架 | `MapTrackerZipline.target` | `[    ,     ]` |
| P6 | 途经滑索架**总数** | `chain_max_press` = 总数 − 1 | ____ 架 |
| P7 | 中途是否落地过？ | 落地要拆 ChainA/ChainB | 是 / 否 |
| P8 | 下索落点 | NAVMESH 首点 | `[    ,     ]` |
| P9 | 下索后途经点 1 | NAVMESH 走位 | `[    ,     ]` |
| P10 | 下索后途经点 2（可选） | NAVMESH 走位 | `[    ,     ]` |
| P11 | **仓储节点 NPC 本体** ⚠️规矩1+2 | HEADING 正对 NPC | `[    ,     ]` |

---

## 4. 送货路线（3 条）

### 4.1 起点段（3 条路线共用，只录一次）

武陵城就是这么做的（`SeizeDeliveryJobsDeliverWalkToZipline` 4 条路线共享）。

| # | 录什么 | 用途 | 值 |
| --- | ------ | ---- | --- |
| D0-1 | 取货点→滑索架途经点 1 | NAVMESH 走位 | `[    ,     ]` |
| D0-2 | 取货点→滑索架途经点 2 | NAVMESH 走位 | `[    ,     ]` |
| D0-3 | 取货点→滑索架途经点 3（可选） | NAVMESH 走位 | `[    ,     ]` |
| D0-4 | **起点滑索架本体** ⚠️规矩1 | HEADING 正对滑索架 | `[    ,     ]` |

> 送货起点滑索架**可能和取货的 P4 是同一架**（武陵城就是）。是同一架就不用重录，标一下即可。

### 4.2 每条路线各录一组（×3）

**先给 3 条路线起英文名**（PascalCase，按地标起）。武陵城用的是 `Owl` / `MaterialResearchInstitute` / `Observatory` / `TechProductionOffice`。这个名字会用在节点名、`departure.go`、i18n 三处，**必须严格一致**。

| 路线 | 英文名 | 大致方位 |
| ---- | ------ | -------- |
| 路线 1 | `____________` | |
| 路线 2 | `____________` | |
| 路线 3 | `____________` | |

**每条路线填一份下表**：

#### 路线 ___（名字：____________）

| # | 录什么 | 用途 | 值 |
| --- | ------ | ---- | --- |
| D1 | 发射瞄准的**下一架**滑索架 | `MapTrackerZipline.target` | `[    ,     ]` |
| D2 | 途经滑索架**总数** | `chain_max_press` = 总数 − 1 | ____ 架 |
| D3 | 中途是否落地过？ | 落地要拆 ChainA/ChainB | 是 / 否 |
| D4 | 下索落点 | NAVMESH 首点 | `[    ,     ]` |
| D5 | 下索后途经点 1 | NAVMESH 走位 | `[    ,     ]` |
| D6 | 下索后途经点 2（可选） | NAVMESH 走位 | `[    ,     ]` |
| D7 | **送货 NPC 本体** ⚠️规矩1+2 | HEADING 正对 NPC | `[    ,     ]` |

> D5/D6 的**最后一个走位点**同时会填进 `departure.go` 的 endpoints 表当终点坐标（用 MapTracker 坐标，匹配半径 30）。

---

## 5. 汇总：一共要交多少

| 组 | 内容 | 数量 |
| --- | ---- | ---- |
| 标定 | 3 个点 × (MapTracker + base px + zone) | 3 组 |
| 取货 | P1–P11 | 1 套 |
| 送货共用起点 | D0-1 ~ D0-4 | 1 套 |
| 送货各路线 | D1–D7 + 路线名 | ×3 |

约 **25–30 个坐标 + 4 个滑索架计数 + 3 个路线名 + 1 个锚点选择**。

---

## 6. 交给我之后我做什么

不用博士操心，列出来只为让您知道进度怎么算：

1. 解算 lv005 的 offset/scale，写进 `maptracker_coordinate_transforms.json`
2. 换算所有步行段坐标 → base px
3. 写 pipeline 节点 → `SeizeDeliveryJobsDeliverRoutes.json`（送货）+ `SeizeDeliveryJobsPost.json`（取货）
4. 加 3 个终点坐标 → [departure.go](../../../../agent/go-service/seizedeliveryjobs/departure.go) 的 endpoints 表
5. 建 4 个测试入口（3 送货 + 1 取货）
6. 5 语言 i18n + `interface.json` 注册 + 同步 `install/interface.json`
7. `pnpm format && pnpm check` + `python tools/build_and_install.py`（改了 Go）
8. 交回给博士实机测

---

## 7. 录不动时怎么办

| 现象 | 怎么处理 |
| ---- | -------- |
| MapNavigator 在试验园区读不出位置 | **停下告诉我**，说明 base.nav 可能不覆盖这张图，方案要换 |
| 两个工具读出的 zone 不一致 | 记下两个值都告诉我 |
| HEADING 目标找不到 ≥2m 的点 | 往后退两步再录，或换个更远的地标当朝向目标 |
| 滑索架数不清 | 宁可多跑一次数准，`chain_max_press` 数错是最常见的失败原因 |
| 中途落地了 | 记下在第几架落的，要拆成 ChainA/ChainB |

排查表见规范 §10，日志位置：

- `install/debug/cpp-algo/debug/maafw.log` — NAVMESH / HEADING
- `install/debug/go-service.log` — 滑索、`MapTrackerToward`
