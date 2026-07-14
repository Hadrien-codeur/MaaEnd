# 送货步行段：MapTrackerMove → NAVMESH 迁移方案

> 分支：`feature/zipline-fast`
> 目标：把送货流程里的手录折线步行段（`MapTrackerMove`）换成只填终点、运行时自动 A\* 的 `NAVMESH`（MapNavigator），解决逐点直走导致的「蛇形 / 割角 / 过冲 / 路径偏长」。滑索段原样保留 MapTracker。
> 状态：**方案已定，待实机打样**。本文档为回头实测时的执行手册。

---

## 0. 一句话结论

- 送货步行段改用 `custom_action: "MapNavigateAction"`（**C++ cpp-algo 实现**），`path` 里写 `{"action":"NAVMESH","target":[bx,by]}`。
- `target` 坐标空间 = **BaseNav base px**（A\* 编辑器原生空间），**不是** MapTracker 的游戏坐标。
- 把现有 `MapTrackerMove` 的**终点**用转换公式换成 base px 即可，中间折线点全部丢弃（NAVMESH 只要终点）。
- **前提**：本机二进制 cpp-algo.exe 必须够新（含 `MapNavigateAction`）；当前 CLAUDE.md 记录仍 v2.15.0，需更新到含该能力的版本，否则节点直接不识别。

---

## 1. 关键技术事实（已代码坐实）

### 1.1 两个「MapNavigate」不是一回事 —— 别踩坑

| custom_action | 实现 | 处理 NAVMESH | 用途 |
|---|---|---|---|
| `MapNavigateAction` | **C++** `agent/cpp-algo/source/main.cpp:61` → `mapnavigator::MapNavigateActionRun` | ✅ 真 A\* 语义寻路 | **本方案要用的** |
| `MapTrackerMoveCompatible` | **Go** `agent/go-service/maptracker/register.go:22` | ❌ **直接丢弃**（`move_compatible.go:232-234` `log.Warn "ignores unsupported NAVMESH waypoint"`） | 旧 MapTracker 路线兼容垫片，**绝不能用** |

> 送货步行段现在是 `custom_action: "MapTrackerMove"`（纯 MapTracker）。改成 NAVMESH 必须写 `MapNavigateAction`，写错成 Compatible 会静默丢点、原地不动。

### 1.2 NAVMESH 节点格式（照抄武陵现成范例）

现成同图（map02 武陵）范例：
- `AutoEcoFarm/RegionNodes/AutoEcoFarmInitWulin.json` → `target: [725.74, 193.06]`
- `AutoCollect/AutoCollectRoute4.json` → `target: [728.68, 366.75]`

标准节点：

```json
"NodeName": {
    "action": "Custom",
    "custom_action": "MapNavigateAction",
    "custom_action_param": {
        "path": [
            { "action": "NAVMESH", "target": [942.65, 721.96] }
        ]
    }
}
```

- `target` = **base px**（见 §1.3）。
- **不需要**填 `zone_id` / `navmesh_zone` / `map_name`：`.nav` 区域运行时按当前定位自动推断（README §A\*）。
- 可选：`"arrival_timeout": 45000`（AutoEcoFarm 用了，长段建议加）。
- 多段路点写成数组：`"path": [ {NAVMESH,t1}, {NAVMESH,t2}, ... ]`。

### 1.3 坐标转换：MapTracker → base px

编辑器 A\* 导出的 target 是 `basePt`（`web/static/js/main.js:1907-1910`），即 base px 空间。

转换公式（`agent/go-service/maptracker/compatible/convert.go` 同源，`maptracker_compat.py:119`）：

```
base_x = offset_x + maptracker_x * scale_x
base_y = offset_y + maptracker_y * scale_y
```

武陵 `map02_lv002` 参数（`assets/resource/image/MapLocator/maptracker_coordinate_transforms.json`）：

| 参数 | 值 |
|---|---|
| offset_x | 288.0 |
| offset_y | 0.0 |
| scale_x | 0.985176738883 |
| scale_y | 0.985074626866 |

> 其它层级（lv001/lv003/lv004、各 tier）offset/scale 不同，转换时**按节点实际 map_name 取对应行**。

**已验证**（A\* 接口 POST `/api/route`, zone_id=2）：
- 直接喂 MapTracker 坐标 `(664.5,734.2)` → A\* 吸附到 `(684,719)`，**偏 28**（错误，证明不能直接用）。
- 转换后 base `(942.65,723.24)` → A\* 精确吸附 `(942.65,723.24)`，干净直线（正确）。

### 1.4 改 pipeline 即可，无需改 Go

送货分流 `departure.go`：
- `nearestEndpoint` 匹配终点（半径 30）→ `runDeliverRoute(endpoint)` → `ctx.RunTask("SeizeDeliveryJobsDeliverRoute"+endpoint)`（`departure.go:448-462`），直接跑同名 pipeline SubTask 节点。
- 未命中终点 → `runGoal`（NavMesh MapTrackerGoal 回退）。

**结论**：步行段是 pipeline 节点，改 JSON 里的 `custom_action` + `path` 就生效，Go 不用动。（改完仍需完整重启 MaaEnd.exe。）

---

## 2. 送货流程步行段清单（9 个 MapTrackerMove）

### 2.1 取货段 `SeizeDeliveryJobsPost.json`

| 节点 | 行 | map | 点数 | 终点(MapTracker) | 终点→base px |
|---|---|---|---|---|---|
| `SeizeDeliveryJobsWulingCityWalkToZipline` | 224 | lv002 | 3 | (673.2,732.9) | **(951.22,721.96)** |
| `SeizeDeliveryJobsWulingCityWalkFromZipline` | 266 | lv002 | 5 | (674.9,789.2) | (952.90,777.51) |
| `SeizeDeliveryJobsWalkToDepotNodeWulingCityBackward` | 300 | lv002 | 2 | (674.9,789.2)（回退用，谨慎改） | — |
| `SeizeDeliveryJobsWalkToDepotNodeTestAreaBackward` | 394 | **lv005** | 2 | (297.5,414.3)（测试区回退，非武陵） | 按 lv005 参数另算 |

### 2.2 送货段 `SeizeDeliveryJobsDeliverRoutes.json`

三明治结构：`DeliverWalkToZipline → GetOnZipline → Zipline(Chain) → GetOffZipline → WalkToNpc`。

| 节点 | map | 点数 | 状态 |
|---|---|---|---|
| `SeizeDeliveryJobsDeliverWalkToZipline`（各路线共用起步） | lv002 | 5 | 起点(675.7,788.1)→终点(684.5,785.5) |
| `SeizeDeliveryJobsDeliverRouteObservatoryWalkToNpc` | lv002 | 2 | (619.5,358.0)→(617.1,358.0) ✅已实测 |
| `SeizeDeliveryJobsDeliverRouteOwlWalkToNpc` | lv002 | **0** | 待录 |
| `SeizeDeliveryJobsDeliverRouteMaterialResearchInstituteWalkToNpc` | lv002 | **0** | 待录 |
| `SeizeDeliveryJobsDeliverRouteTechProductionOfficeWalkToNpc` | lv002 | **0** | 待录 |

> ⚠️ 取货段和 Observatory 送货段的步行**本身就很短**（2~5 点、直线几个单位），换 NAVMESH 收益有限。**NAVMESH 的价值在长/绕的段**（未录的 3 终点 WalkToNpc、以及各 Zipline 之间若有长步行）。打样建议挑一条**明显偏长**的段，而不是最短的取货段。

---

## 3. 打样执行步骤（回头实机做）

### 3.1 起工具
```bash
cd tools/MapNavigator
python -m venv .venv && .venv\Scripts\activate   # 首次
pip install -r requirements.txt                   # 首次（本机已装：fastapi/uvicorn/numpy/pynput/pyperclip）
python main.py                                     # 起服务，自动开浏览器 http://127.0.0.1:8770
```
> maafw 未装 → 录制/实时定位不可用，但 **A\* 离线模式不受影响**（本方案用 A\*）。要用录制/定位再 `pip install maafw`。

### 3.2 A\* 导出 NAVMESH target
1. 浏览器进 **A\* 寻路** 页签（默认页），BaseNav 后台自动加载 `base.nav.gz`。
2. 点 **选择底图与层级** → 选 **Wuling / map02base**（zone 2）。
3. 地图上点起点、终点（多段 A\* 可连续加途经点）。
4. 点 **复制 JSON 配置** → 得到 `{"action":"NAVMESH","target":[bx,by]}`（已是 base px，直接用）。

### 3.3 改 pipeline
把目标节点从：
```json
"custom_action": "MapTrackerMove",
"custom_action_param": { "map_name": "map02_lv002", "path": [ [x1,y1],[x2,y2],... ] }
```
改成：
```json
"custom_action": "MapNavigateAction",
"custom_action_param": { "path": [ {"action":"NAVMESH","target":[bx,by]} ] }
```
> `map_name` 可省（运行时自推断 zone）。多个途经点就多个 NAVMESH 对象。

### 3.4 实测三查
1. **路径质量**：NAVMESH 是否明显比原折线顺/短（尤其转弯处不再蛇形/割角）。
2. **坐标交接**（最高风险，存档 18.2 标注）：**下索落点 → 下一段 NAVMESH 起点定位** 是否正确衔接。因为 NAVMESH 起点靠运行时 `MapLocateRecognition` 实时定位（`MapNavigatorCompatible.cpp:687`），落点定位偏了会导致 A\* 从错误起点规划。
3. **滑索前后**：上索前 WalkToZipline 用 NAVMESH 走到滑索架，能否精确到位触发 `GetOnZipline`。

### 3.5 打样 OK 后推广
- 全部 9 段步行按 §2 清单逐个替换。
- 顺带补录 Owl / MaterialResearchInstitute / TechProductionOffice 三终点（当前 WalkToNpc 空 + `departure.go:39-44` 坐标 `{0,0}` 占位；NAVMESH 只需终点，正好省去录折线）。

---

## 4. 风险与回退

| 风险 | 应对 |
|---|---|
| 二进制太旧无 `MapNavigateAction` | 更新 `install/agent/cpp-algo.exe` 到含该能力版本（v2.19+），或本机 `python tools/build_and_install.py` |
| 误用 `MapTrackerMoveCompatible` | 节点名必须写 `MapNavigateAction`（C++），核对无误 |
| 下索落点定位不准致 A\* 起点错 | 保留原 MapTrackerMove 版本备份；交接段可先加 `MapLocateAssertLocation` 判定站位 |
| tier/层级坐标 | 非 lv002 段按对应 map_name 取转换参数；tier 段编辑器导出已含 `target_tier` |
| 短段收益低 | 只对长/绕段迁移；短段可保留 MapTracker |

**回退**：每段改动独立，出问题单独把该节点 `custom_action` 改回 `MapTrackerMove` + 原 `path` 即可。

---

## 5. 附：坐标转换速查脚本

```python
# map02_lv002 MapTracker -> base px
ox, oy, sx, sy = 288.0, 0.0, 0.985176738883, 0.985074626866
def to_base(x, y):
    return round(ox + x * sx, 2), round(oy + y * sy, 2)
# 示例: to_base(673.2, 732.9) -> (951.22, 721.96)
```

其它层级参数见 `assets/resource/image/MapLocator/maptracker_coordinate_transforms.json`（按 `map_name` 匹配 `offset_x/offset_y/scale_x/scale_y`）。
