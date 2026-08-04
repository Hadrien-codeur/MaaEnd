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

> ⚠️ **`zone` 值要一起记下来**。试验园区和武陵城一样是 **`Wuling_Base`**（见 §2）。

---

## 2. ✅ 坐标换算参数已解算完毕（无需实机标定）

**2026-08-05 更新：这一步已经做完，博士不用管了。** 原计划要实机站 3 个点读两套坐标，现在改用图像匹配离线解算，结论已写进 [maptracker_coordinate_transforms.json](../../../../assets/resource/image/MapLocator/maptracker_coordinate_transforms.json)：

```json
{
    "map_name": "map02_lv005",
    "zone_id": "Wuling_Base",
    "offset_x": 960.0,
    "offset_y": 1344.0,
    "scale_x": 0.985337243402,
    "scale_y": 0.984615384615
}
```

换算公式（规范 §6）：

```
base_x = 960.0  + mt_x × 0.985337243402
base_y = 1344.0 + mt_y × 0.984615384615
```

### 怎么解出来的（复现方法，以后加新图照抄）

这些 transform 本质是「关卡小图 → MapLocator Base 大图」的裁剪+缩放关系，两张图都在仓库里，所以能纯离线算：

1. 把 `assets/resource/image/MapTracker/map/map02_lv005.png`（682×585）缩放后模板匹配到 `assets/resource/image/MapLocator/Wuling/Base.png`（2016×2976），得 offset 粗值。
2. SIFT + RANSAC 拟合仿射，对 x/y 分别一元线性回归求 scale/offset，迭代剔除 2σ 外点。
3. **在已知的 `map02_lv001/002/003/004` 上验证方法**：offset 复现误差 <0.02px，残差 0.05px —— 方法可信。
4. 精确化：发现所有图的 `offset` 和 `span = size × scale` **都是 96 的整数倍**（Base.png 本身就是 2016×2976 = 96×21 × 96×31 的网格切片）。据此把拟合值吸附到精确有理数：
    - lv005 `span_x = 672 = 96×7` → `scale_x = 672/682 = 0.985337243402`
    - lv005 `span_y = 576 = 96×6` → `scale_y = 576/585 = 0.984615384615`
    - `offset = (960, 1344) = (96×10, 96×14)`
5. 反向验证：按参数 warp lv005 叠到 Base.png，重叠区相关系数 **0.979**，±3px 网格搜索最优解就在 (0,0)。

### base.nav 覆盖已确认

清单原来担心「MapNavigator 在试验园区可能读不出位置」——**这个风险不存在**。解压 `assets/resource/model/map/navmesh/base.nav.gz` 查 zone 列表，里面有 `Wuling_Base` 和 `Wuling_L5_314/316/318/319/321/322/324/326`，试验园区被完整覆盖。

### ⚠️ 唯一残留坑：lv005 的 tier（高架层）没进表

lv005 有 8 张 tier 图（314/316/318/319/321/322/324/326），但换算表里**只有 base 层条目、没有 tier 条目**。落在高架层上的点会错用 base 层参数。

已知 **`SceneEnterWorldWulingTestArea2` 锚点 `[391.6, 362.5]` 就落在 tier 322 上**。

**录制时的判断办法**：如果某个 NAVMESH 点在高架/桥面/二层平台上，标一句"这点在高架上"告诉我，我补 tier 条目（需要 `parent_map_name` + `source_bbox`）。地面点不受影响。

---

## 3. 取货路线（1 条）

### 3.1 先定传送锚点

试验园区有两个现成锚点（[SceneWuling.json:456-477](../../../../assets/resource/pipeline/Interface/SceneWuling.json#L456)）：

| 节点名 | 位置 | MapTracker 坐标 |
| ------ | ---- | --------------- |
| `SceneEnterWorldWulingTestArea1` | 综合科研区下 | `[336.3, 420.1]` |
| `SceneEnterWorldWulingTestArea2` | 测试区 | `[391.6, 362.5]`（⚠️ 在 tier 322 高架层上，见 §2） |

**要定的**：哪个锚点离起点滑索架更近 → 选它。

已知取货点在 **`[297.5, 413.3]`**（上游 [#4760](https://github.com/MaaEnd/MaaEnd/pull/4760) 2026-08-04 从 `414.3` 调到 `413.3`，修站位不准导致取不到货），看着 TestArea1 更近，但**要实机确认滑索架在哪**才能定。

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
| ~~标定~~ | ~~3 个点 × (MapTracker + base px + zone)~~ | ✅ **已离线解算，不用录**（§2） |
| 取货 | P1–P11 | 1 套 |
| 送货共用起点 | D0-1 ~ D0-4 | 1 套 |
| 送货各路线 | D1–D7 + 路线名 | ×3 |

约 **22–27 个坐标 + 4 个滑索架计数 + 3 个路线名 + 1 个锚点选择**。

坐标**全部用 MapTracker 读**即可（换算参数已有，我这边换 base px）。顺手标一下哪些点在高架层上。

---

## 6. 交给我之后我做什么

不用博士操心，列出来只为让您知道进度怎么算：

1. ~~解算 lv005 的 offset/scale，写进 `maptracker_coordinate_transforms.json`~~ ✅ 2026-08-05 已完成
2. 换算所有步行段坐标 → base px（必要时补 tier 条目）
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
| MapNavigator 在试验园区读不出位置 | base.nav **已确认覆盖** lv005（§2），若仍读不出是定位/二进制问题，告诉我 |
| 某个点在高架/桥面/二层平台上 | 标注一下，我补 tier 换算条目（§2 末） |
| 两个工具读出的 zone 不一致 | 记下两个值都告诉我 |
| HEADING 目标找不到 ≥2m 的点 | 往后退两步再录，或换个更远的地标当朝向目标 |
| 滑索架数不清 | 宁可多跑一次数准，`chain_max_press` 数错是最常见的失败原因 |
| 中途落地了 | 记下在第几架落的，要拆成 ChainA/ChainB |

排查表见规范 §10，日志位置：

- `install/debug/cpp-algo/debug/maafw.log` — NAVMESH / HEADING
- `install/debug/go-service.log` — 滑索、`MapTrackerToward`
