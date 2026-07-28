# 自动送货路线录制规范

本文档定义 `SeizeDeliveryJobs`（抢委托送货）固定滑索路线的录制与编写规范。已按此规范完成武陵城取货路线 + 4 条送货路线（猫头鹰 / 材料研究所 / 观测站 / 技术生产办公室）。

新增其他地图（如试验园区）的送货路线时，照此流程走即可。

---

## 1. 路线的结构：三明治模型

无论取货段还是送货段，一条固定滑索路线都是同一个「三明治」结构：

```
步行到起点滑索架  →  上索  →  滑行（可连滑）  →  下索  →  步行到目标 NPC
   NAVMESH+HEADING   Pipeline    MapTrackerZipline   Pipeline   NAVMESH+HEADING
```

对应 5 个 SubTask 子节点：

| #   | 段落             | 用什么                                                  | 坐标系                  |
| --- | ---------------- | ------------------------------------------------------- | ----------------------- |
| 1   | 步行到起点滑索架 | `MapNavigateAction`（NAVMESH 走位 + HEADING 朝向）      | **base px**             |
| 2   | 上索             | `MapTrackerOpenWorld_GetOnZipline`（现成节点，无参数）  | —                       |
| 3   | 滑行             | `MapTrackerZipline`                                     | **MapTracker 游戏坐标** |
| 4   | 下索             | `MapTrackerOpenWorld_GetOffZipline`（现成节点，无参数） | —                       |
| 5   | 步行到目标 NPC   | `MapNavigateAction`（NAVMESH 走位 + HEADING 朝向）      | **base px**             |

连滑多段时，第 3 步可以拆成 ChainA / ChainB 多个 `MapTrackerZipline` 节点串联（见 §4.2）。

> ⚠️ **两个坐标系不能混。** 步行段吃 base px，滑索段吃 MapTracker 游戏坐标。换算见 §6。

---

## 2. 录制前需要你提供的坐标清单

下表是录制**一条送货路线**需要博士实机录制并提供的全部输入。全部用 MapTracker 工具录（§5），录的都是 **MapTracker 游戏坐标**，我负责换算成 base px。

### 2.1 起点段（同一地图的多条路线共用，只录一次）

| #   | 录什么                                  | 用途                         | 落到哪个字段                          |
| --- | --------------------------------------- | ---------------------------- | ------------------------------------- |
| A1  | 传送落点 → 起点滑索架前，途中 2-3 个点  | NAVMESH 走位                 | 步行节点 `path` 里的 `NAVMESH.target` |
| A2  | **起点滑索架本体**                      | HEADING 正对滑索架，便于上索 | 步行节点 `path` 末尾 `HEADING.target` |
| A3  | 起点滑索架（同 A2，或发射朝向的那一架） | 滑索发射瞄准                 | `MapTrackerZipline.target`            |

### 2.2 每条路线各自的段

| #   | 录什么                       | 用途                               | 落到哪个字段      |
| --- | ---------------------------- | ---------------------------------- | ----------------- |
| B1  | 途经的每一架滑索架坐标       | 数出 `chain_max_press`（§4.2）     | `chain_max_press` |
| B2  | 下索点位（终点滑索架落地处） | NAVMESH 第一个走位点               | `NAVMESH.target`  |
| B3  | 下索后步行途经点 1-2 个      | NAVMESH 走位                       | `NAVMESH.target`  |
| B4  | **目标 NPC 本体**            | HEADING 正对 NPC，交互按钮才出得来 | `HEADING.target`  |

### 2.3 参数清单（不用录，但要确定）

| 参数              | 怎么定                                                         | 示例                    |
| ----------------- | -------------------------------------------------------------- | ----------------------- |
| `map_name`        | 地图名                                                         | `map02_lv002`（武陵城） |
| `zone_id`         | 从 `maptracker_coordinate_transforms.json` 按 `map_name` 查    | `Wuling_Base`           |
| `chain_max_press` | 连滑架数 − 1（§4.2）                                           | `8`                     |
| `timeout`         | 单段滑索预估耗时 ×1.5，连滑段给足                              | `60000`                 |
| 终点世界坐标      | = B4 前一个点，即最后一个 NAVMESH 走位点的 **MapTracker 坐标** | 填入 `departure.go`     |

---

## 3. ⚠️ 录 HEADING 目标点的两条硬规矩

这两条是踩过坑总结出来的，违反了路线就不稳。

### 3.1 HEADING 的 target 和 NAVMESH 的 target 是两个不同的点

- `NAVMESH.target` = **人要站的位置**
- `HEADING.target` = **要面朝的对象**（NPC 本体 / 滑索架本体）

录成同一个点则算不出角度。录 HEADING 时，人站在下索落点，把准星/鼠标点在 **NPC 身上**，不是点自己脚下。

### 3.2 HEADING target 距站位必须 ≥ 2m

MapLocator 单帧定位抖动约 **0.7m**。目标点离站位太近时，角度完全被噪声主导：

| 站位→目标距离 | 角度不确定度 | 结论                                        |
| ------------- | ------------ | ------------------------------------------- |
| 0.57m         | ±**51°**     | ❌ 不可用（Owl 初版就栽在这，转向完全随机） |
| 1.0m          | ±35°         | ⚠️ 勉强（靠 40° 容差兜住，不稳）            |
| **≥ 2.0m**    | ±20° 以内    | ✅ 可用                                     |

C++ 侧接受容差是 `kHeadingAcceptToleranceDeg = 40.0`（[navi_config.h:72](../../../../agent/cpp-algo/source/MapNavigator/navi_config.h#L72)），所以 ±20° 有余量。**低于 2m 就重录一个更远的目标点。**

---

## 4. 各段的编写细节

### 4.1 步行段：`MapNavigateAction`

```jsonc
{
    "desc": "送货-XXX 下索后步行到送货 NPC【NAVMESH A*(base px) + HEADING 正对 NPC】",
    "pre_delay": 0,
    "action": "Custom",
    "custom_action": "MapNavigateAction",
    "custom_action_param": {
        "map_name": "map02_lv002",
        "path": [
            // 下索点位（MapTracker [228.7,605.8] 换算）
            {"action": "NAVMESH", "target": [513.31, 1652.76], "zone_id": "Wuling_Base"},
            // 步行途经点（MapTracker [229.3,605.9] 换算）
            {"action": "NAVMESH", "target": [513.9, 1652.86], "zone_id": "Wuling_Base"},
            // 正对 NPC（MapTracker [229.4,603.8] 换算，站位→NPC 约 3°/2.07m）
            {"action": "HEADING", "target": [514.0, 1650.79], "zone_id": "Wuling_Base"},
        ],
    },
    "focus": {"Node.Recognition.Succeeded": "送货-XXX 步行到 NPC[NAVMESH]"},
}
```

**注释务必写全**：每个点标注它的 MapTracker 原值，HEADING 额外标注角度和距离。以后微调时不用重新换算。

**为什么走位一律用 NAVMESH，不用 `MapTrackerMove`**：

|        | `NAVMESH`（C++ `MapNavigateAction`） | `MapTrackerMove`（Go）                 |
| ------ | ------------------------------------ | -------------------------------------- |
| 寻路   | 读 `.nav` 文件真 A\*                 | 无，直线推算                           |
| 控制   | 闭环，`strict_arrival = true` 硬编码 | **开环**：截图定位 → 转镜头 → 按方向键 |
| 远距离 | 稳                                   | 拉 sprint 时截图延迟直接变过冲距离     |

试过「MapTrackerMove 多断点调朝向」，实测坐标不准、常冲出去一段，已废弃。**别再走回头路。**

**HEADING 的行为**（[semantic_nodes.cpp:376-427](../../../../agent/cpp-algo/source/MapNavigator/semantic_nodes.cpp#L376-L427)）：转镜头 → 前冲 `kPostHeadingForwardPulseMs = 270` ms 贴合身体 → 重新定位读角度 → 残差超容差再修（最多 3 次）。`has_position = false`，不改变路径位置，但那 270ms 前冲会让人物微移半米内。

两种写法，`target` 优先：

```jsonc
{ "action": "HEADING", "target": [x, y], "zone_id": "Wuling_Base" }  // 朝某坐标，推荐
{ "action": "HEADING", "angle": 90, "zone_id": "Wuling_Base" }       // 绝对角度
```

**角度约定**（[navi_math.cpp:9-18](../../../../agent/cpp-algo/source/MapNavigator/navi_math.cpp#L9-L18)）：`atan2(dx, -dy)`，**0 = 正北（y 减小方向），顺时针**，故 90 = 正东、180 = 正南、270 = 正西。

### 4.2 滑索段：`MapTrackerZipline` 与 `chain_max_press`

```jsonc
{
    "desc": "送货-XXX 连滑（发射朝 [663.7,807.3]，按8次E接力，落 [246.4,705.2]）",
    "pre_delay": 0,
    "action": "Custom",
    "custom_action": "MapTrackerZipline",
    "custom_action_param": {
        "map_name": "map02_lv002",
        "target": [663.7, 807.3], // MapTracker 游戏坐标，不是 base px
        "chain_max_press": 8,
        "timeout": 60000,
    },
}
```

- **`target`** = 发射时要瞄准的**下一架滑索架**（MapTracker 游戏坐标）。Go 会先转镜头对准它，等 1s 让游戏出「已锁定」提示，再点击发射。
- **`chain_max_press`** = 途中按 E 的次数 = **连滑架数 − 1**。最后一架的提示故意不按，人物就落在那里。
    - 例：经过 9 架滑索架 → `chain_max_press: 8`
    - 数错会落错架子，是最常见的错误来源
- **`timeout`** 连滑段给足，武陵城最长的技术生产办公室（15 架）用 60000。

**拆成多段的时机**：中途落地了再重新发射，就要拆成 ChainA / ChainB 两个节点（如 Owl：段A 8 次 E 落地 → 段B 再 1 次 E 到终点架）。同一次连滑不用拆。

### 4.3 上索 / 下索

直接复用现成节点，无参数：

- 上索 `MapTrackerOpenWorld_GetOnZipline` — Alt + 点击滑索交互按钮
- 下索 `MapTrackerOpenWorld_GetOffZipline` — 按一下 Esc

### 4.4 ⚠️ 索上转向：`MapTrackerToward` 会推偏落点

需要在终点滑索架上、下索前转个方向时（避免下索后 NAVMESH 从 NPC 背后绕行），用 Go 侧独立 action `MapTrackerToward`（HEADING 只能当 `MapNavigateAction` 的 path 节点，用不了）：

```jsonc
{
    "action": "Custom",
    "custom_action": "MapTrackerToward",
    "custom_action_param": {"angle": 100},
}
```

**必须知道的副作用**：它的实现是「转镜头 → 后退 250ms → 前进 75ms」贴合身体（[toward.go:155-169](../../../../agent/go-service/maptracker/default/toward.go#L155-L169)），**净位移往后**，而且是**循环**执行到角度收敛（容差 12°，超时 5s）。实测 Owl 跑了 4 轮，把索上挂点推偏了 **3.6m**，下索落点跟着错。

**能接受的前提**：后面紧跟 NAVMESH 步行段。NAVMESH 从实际位置重新 A\*，落点偏了自己会走回来，代价只是多走几米。**如果后面没有 NAVMESH 兜底，不要用这个 action。**

---

## 5. 录制工具

```bash
# 必须从仓库根目录启动，否则 WORK_DIR/ASSET_DIR 相对 CWD 解析出错报 503
python tools/map_tracker/map_tracker_master.py
```

打开 http://127.0.0.1:8060/web/ ，录路径、框 AssertLocation 区域。需要 `maafw` pip 包（import 名是 `maa`）。

录出来的是 **MapTracker 游戏坐标**，和 big-map 蓝标同系。

> 另有 `python tools/MapNavigator/main.py`（:8770）录 base px 路径，但送货路线统一用 MapTracker 录 + 换算，只维护一套坐标来源。

---

## 6. 坐标换算：MapTracker → base px

**公式**：

```
base_x = offset_x + mt_x × scale_x
base_y = offset_y + mt_y × scale_y
```

反向：`mt = (base − offset) / scale`

**参数只在** [`assets/resource/image/MapLocator/maptracker_coordinate_transforms.json`](../../../../assets/resource/image/MapLocator/maptracker_coordinate_transforms.json)，按 `map_name` 取行。

武陵城 `map02_lv002` / `Wuling_Base`：

| 参数       | 值                        |
| ---------- | ------------------------- |
| `offset_x` | 288.0                     |
| `offset_y` | **1056.0** ← 关键，不是 0 |
| `scale_x`  | 0.985176738883            |
| `scale_y`  | 0.985074626866            |

**最常见的错误**：把 `offset_y` 当 0。换算后如果某点 y 比预期少一千多，就是又漏了 `offset_y`。

**交叉验证方法**：拿一个已知的对照点验算。取货段起点北锚点 MapTracker ≈ `[663, 733]`，NAVMESH 首点是 base ≈ `[942, 1779]`；公式算 x = 941、y = 1778，吻合 ✅。

---

## 7. Go 侧分流：`departure.go`

送货时 Go 从 big-map 蓝标读出目标世界坐标，再匹配到最近的预录终点，跑对应路线节点。

**接线约定**：`nearestEndpoint` 匹配到终点名 `X` → RunTask 节点 `SeizeDeliveryJobsDeliverRouteX`。名字必须严格一致，也要和 `SeizeDeliveryJobsEndpointFilter.json` 里的终点名一致。

新增路线要在 [departure.go:39-44](../../../../agent/go-service/seizedeliveryjobs/departure.go#L39-L44) 追加一行：

```go
var seizeDeliveryJobsWulingEndpoints = []seizeDeliveryJobsWulingEndpoint{
    {Name: "Owl", Target: [2]float64{229.1, 604.6}},  // 猫头鹰（右下）
    // ...
}
```

- `Target` 用 **MapTracker 游戏坐标**（跟蓝标同系），不是 base px
- 取值 = 该路线 WalkToNpc 段**最后一个 NAVMESH 走位点**的 MapTracker 坐标
- 匹配半径 `seizeDeliveryJobsEndpointMatchRadius` = 30，所以微调走位点（几米内）**不需要**回填、不需要重编 go-service
- 只有大幅改动最后一个走位点才要同步回填

改了 Go 必须：

```bash
pnpm format:go
python tools/build_and_install.py
```

---

## 8. 新增一条送货路线的完整清单

以下每一步都要做完：

1. **录坐标**（§2）— MapTracker 工具，注意 §3 的两条硬规矩
2. **换算 base px**（§6）— 步行段用，滑索段不用换
3. **写 pipeline 节点** → `assets/resource/pipeline/SeizeDeliveryJobs/SeizeDeliveryJobsDeliverRoutes.json`
    - 一个 `SeizeDeliveryJobsDeliverRoute<Endpoint>` SubTask 串起 5 段
    - 起点步行段同地图多条路线共用一个节点
4. **加终点坐标** → [departure.go](../../../../agent/go-service/seizedeliveryjobs/departure.go) 的 endpoints 表（§7）
5. **建测试入口**（§9）— 单独跑这条路线，不掺杂抢单流程
6. **i18n 5 个语言文件** → `assets/locales/interface/{zh_cn,zh_tw,en_us,ja_jp,ko_kr}.json`
7. **注册任务**（新增测试入口才需要）→ `assets/tasks/*.json` + `assets/interface.json`，然后同步 `install/interface.json`（是复制文件，不是软链接）
8. **格式化 + 校验**：
    ```bash
    pnpm format
    pnpm check
    python tools/build_and_install.py   # 只在改了 Go 时
    ```
9. **完整重启 MaaEnd.exe** — 改 pipeline JSON 后进程内存不会自动重载
10. **实机测试**，按 §10 排查

---

## 9. 测试入口的搭法

给每条新路线建一个独立测试入口，跑完即停，只核对路线和落点，不做取货/提交识别。三段结构：

```
<Prefix>Entry     → 确保回大世界，跳 Teleport
<Prefix>Teleport  → SubTask 传送到锚点
<Prefix>Run       → SubTask：取货路线 → 本条送货路线，跑完停
```

参考 `SeizeDeliveryJobsTestDeliverOwl{Entry,Teleport,Run}`。配套 `assets/tasks/SeizeDeliveryJobsTestDeliverOwl.json` + 5 语言文案 + `interface.json` 注册。

---

## 10. 排查指南

出问题时按现象定位：

| 现象                    | 先查什么                                                                                      |
| ----------------------- | --------------------------------------------------------------------------------------------- |
| 上索失败 / 没上去       | 起点步行段的 HEADING 是否正对滑索架；`GetOnZipline` 的模板匹配 ROI                            |
| 滑索没发射              | `MapTrackerZipline.target` 是否是**下一架**滑索架；日志搜 `Zipline fast travel did not start` |
| 落错滑索架              | `chain_max_press` 数错（= 架数 − 1）                                                          |
| 下索落点偏              | 是否用了 `MapTrackerToward`（§4.4，会推偏数米）                                               |
| 走到 NPC 但交互按钮不出 | HEADING target 距站位是否 ≥ 2m（§3.2）；是否从 NPC 背后绕行                                   |
| Go 分流匹配不到路线     | `departure.go` 终点坐标是否用了 MapTracker 系；是否在半径 30 内                               |

**日志位置**：

| 文件                                     | 看什么                                                                                         |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `install/debug/cpp-algo/debug/maafw.log` | NAVMESH / HEADING（搜 `Heading-only node completed`、`NAVMESH generated path`、`position.x=`） |
| `install/debug/go-service.log`           | 滑索、`MapTrackerToward`（搜 `Adjusting orientation`、`Zipline chain relay`）                  |

排查 HEADING 时，`Heading-only node completed` 那行会打出 `target_heading` / `start_heading` / `achieved_heading`，配合前后的 `position.x=` 就能看出人物到底转到哪、被推到哪。

---

## 11. 术语对照：容易混的几组

| 别混                                                    | 区别                                                                                               |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `MapNavigateAction` vs `MapTrackerMoveCompatible`       | 前者 = C++ 真 A\*（NAVMESH，base px，步行段用）；后者 = Go 垫片，**会静默丢 NAVMESH 点，绝不能用** |
| `MapLocateAssertLocation` vs `MapTrackerAssertLocation` | 前者 C++ 用 base px；后者 Go 用 MapTracker 坐标                                                    |
| `MapTrackerGoal` vs 固定滑索路线                        | 前者官方 NavMesh 寻路（`zipline_policy` 四档）；后者本项目预录路线                                 |
| HEADING vs `MapTrackerToward`                           | 前者是 `MapNavigateAction` 的 path 节点，闭环无位移；后者是独立 action，**会位移**                 |
| base px vs MapTracker 坐标                              | 步行段吃 base px；滑索段、`departure.go` 终点、big-map 蓝标吃 MapTracker 坐标                      |
