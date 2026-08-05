# CLAUDE.md — MaaEnd 开发记录

> 当前分支：`feature/zipline-fast`
> 功能目标：在 `SeizeDeliveryJobs` 取货段，把「步行到取货点」替换为「步行到滑索 → 乘索 → 步行到取货点」，减少地面出怪及好友设施干扰

---

## 0. 交互规则（Claude 每次会话必读必守，优先级最高）

1. **称呼**：每次回复都称呼用户为【博士】（例如开头"博士，……"）。这是硬性要求，不要遗漏。
2. **上下文提醒**：留意本会话的上下文用量，当估计接近 **500k tokens** 时，主动提醒博士"当前上下文已接近 500k，注意及时整理/开新会话或压缩"。
    - ✅ 已配置自动 hook（见 `.claude/settings.json`）：`UserPromptSubmit` 事件触发 `.claude/hooks/context_reminder.py`，越过 500k/700k/900k 档位时各提醒一次。
    - ⚠️ hook 用字符数 ÷ 3 估算 token，是粗略估算；Claude 自己也应"尽量记得"作为兜底。

---

## 1. 项目背景

- **项目**：MaaEnd — 基于 MaaFramework 的《明日方舟：终末地》自动化工具
- **本地路径**：家里电脑 `d:\Github project\Maaend`；公司电脑 `e:\TestBase2\MaaEnd`
- **本次目标**：在官方 `SeizeDeliveryJobs`（抢委托送货）任务中，把写死的 `ZiplinePolicy = Lazy` 改为用户可配置，支持 `Lazy / Active / Aggressive` 三档。

---

## 2. 开发约定

### 模型策略

- **Plan Mode（规划阶段）**：使用 Sonnet 节省成本
- **正式开发阶段**：切换到 Opus 保证代码质量
- 用户会通过 `/model <name>` 命令手动切换

### 协作原则

- 用户是编程新手，需要先解释概念再动手
- 所有方案先进 Plan Mode 写计划文件，用户审批后再实施
- 不会未经用户同意执行 git commit / push 等危险操作
- 每完成一个阶段都要给出详细的测试和调试指南

---

## 3. Git 工作流与多电脑协作

### 3.1 远程仓库（remote）配置

| Remote 名 | 地址                                           | 用途                             |
| --------- | ---------------------------------------------- | -------------------------------- |
| `origin`  | `https://github.com/MaaEnd/MaaEnd.git`         | 官方仓库，**只读**，拉上游更新用 |
| `myfork`  | `https://github.com/Hadrien-codeur/MaaEnd.git` | 用户的 fork，可读写，跨电脑同步  |

### 3.2 分支策略

| 分支                         | 用途                                            |
| ---------------------------- | ----------------------------------------------- |
| `v2`                         | 跟踪官方 `origin/v2`，定期 `git pull origin v2` |
| `feature/zipline-fast`       | 本次开发分支（当前）                            |
| `feature/self-deliver-route` | 旧方案存档，保留不动                            |

### 3.3 常用操作

**拉上游更新并合并到开发分支**：

```bash
git checkout v2
git pull origin v2
git submodule update --init --recursive
git push myfork v2

git checkout feature/zipline-fast
git merge v2
git push myfork feature/zipline-fast
```

**两台电脑之间同步改动**：

```bash
# 电脑 A：提交并推
git add <具体文件> && git commit -m "feat: ..." && git push myfork feature/zipline-fast

# 电脑 B：拉
git checkout feature/zipline-fast
git pull myfork feature/zipline-fast
```

### 3.4 子模块注意事项

- `agent/cpp-algo/MaaUtils`、`assets/resource/model`、`tests/MaaEndTestset` 为子模块
- 切换分支后出现子模块"有改动"是指针差异，**不要 commit**
- 拉主分支后执行 `git submodule update --init --recursive` 同步

### 3.5 Commit 规范（Conventional Commits）

| 前缀     | 用途                 |
| -------- | -------------------- |
| `feat:`  | 新增功能             |
| `fix:`   | 修复 Bug             |
| `docs:`  | 仅文档更改           |
| `style:` | 格式调整，不影响逻辑 |
| `chore:` | 构建/工具变动        |

示例：`feat(SeizeDeliveryJobs): 新增滑索策略用户选项`

---

## 4. 项目架构（四层）

```
assets/interface.json              # 项目入口、任务导入列表
assets/tasks/**/*.json             # 任务 UI 展示、入口节点、选项
assets/resource/pipeline/**/*.json # 识别/操作/跳转（日常最常改）
agent/go-service/**                # 复杂逻辑（复杂识别、计算、特殊交互）
```

**判断该改哪里：**

| 改动类型                     | 文件位置                                           |
| ---------------------------- | -------------------------------------------------- |
| 界面文案、任务名、选项文案   | `assets/locales/interface/zh_cn.json` (+其余4语言) |
| 任务选项、入口节点           | `assets/tasks/**/*.json`                           |
| 识别、点击、跳转流程         | `assets/resource/pipeline/**/*.json`               |
| 复杂逻辑（算法、遍历、计算） | `agent/go-service/**`                              |

**大原则：Pipeline 管流程，Go 管难点。** 禁止在 Go 中编写大量流程代码。

---

## 5. Pipeline 编码规范

### 命名

节点名使用 PascalCase，以任务名为前缀。例如：`SeizeDeliveryJobsRunDeparture`。

### 禁止硬延迟

- 尽量少用 `pre_delay`、`post_delay`、`timeout`、`on_error`、`max_hit`
- 只在必须等待画面静止时使用 `pre_wait_freezes` / `post_wait_freezes`
- 通过增加中间识别节点替代延迟

### 识别 → 操作 → 再识别

每一步操作都基于识别。

**推荐**：识别 A → 点击 A → 识别 B（确认跳转）→ 点击 B

**禁止**：整体识别一次 → 连点 A → B → C

### `next` 第一轮即命中

扩充 `next` 列表覆盖所有可能画面，一次截图命中目标。项目拒绝重试机制。

### 处理弹窗和加载

在 `next` 里挂：

- `[JumpBack]SceneDialogConfirm`
- `[JumpBack]SceneWaitLoadingExit`
- `[JumpBack]SceneAnyEnterWorld`

### OCR 写完整文本

`expected` 写完整文本，不写片段。需要片段或手写正则时在 `expected` 数组内加 `// @i18n-skip`。

### 先复用，再新增

写新节点前先查[组件指南文档](docs/zh_cn/developers/components-guide.md)确认是否已有现成能力。

### 任务选项（switch/select）格式

```json
"OptionName": {
    "type": "select",
    "label": "$task.Xxx.OptionName.label",
    "description": "$task.Xxx.OptionName.description",
    "cases": [
        { "name": "Lazy", "pipeline_override": { ... } },
        { "name": "Active", "pipeline_override": { ... } },
        { "name": "Aggressive", "pipeline_override": { ... } }
    ],
    "default_case": "Lazy"
}
```

---

## 6. 可复用节点速查

### 通用按钮（`assets/resource/pipeline/Common/Button/`）

| 节点名                     | 适用场景                           |
| -------------------------- | ---------------------------------- |
| `WhiteConfirmButtonType1`  | 白色底 + 圆环图标确认              |
| `WhiteConfirmButtonType2`  | 白色底 + 对号图标确认              |
| `YellowConfirmButtonType1` | 黄色底 + 圆环图标确认              |
| `YellowConfirmButtonType2` | 黄色底 + 对号图标确认              |
| `CancelButton`             | 白色底 + X 图标取消                |
| `CloseButtonType1`         | 右上角 X 关界面（不兼容 ESC 菜单） |
| `CloseButtonType2`         | 右上角 X 关界面（兼容 ESC 菜单）   |
| `TeleportButton`           | 右下角传送按钮（固定 ROI）         |

### SceneManager（万能跳转）

只使用 `assets/resource/pipeline/Interface/` 下各 `SceneXXX.json` 中定义的接口节点。**禁止**直接引用 `__ScenePrivate*` 节点。

常用接口：

| 接口名                                     | 说明                 |
| ------------------------------------------ | -------------------- |
| `SceneAnyEnterWorld`                       | 从任意界面进入大世界 |
| `SceneDialogConfirm` / `SceneDialogCancel` | 点击对话框确认/取消  |
| `SceneWaitLoadingExit`                     | 等待加载消失         |
| `SceneEnterMenuRegionalDevelopment`        | 进入地区建设菜单     |

### Custom Action/Recognition 速查

| 场景                | 用什么                  |
| ------------------- | ----------------------- |
| 按顺序跑一组子任务  | `SubTask`               |
| 清零某节点命中计数  | `ClearHitCount`         |
| 强制让 Action 失败  | `FalseAction`           |
| 主动停止当前任务    | `PostStop`              |
| 运行时改节点参数    | `PipelineOverride`      |
| 计算 OCR 数值表达式 | `ExpressionRecognition` |
| Alt + 点击          | `AutoAltClickAction`    |

---

## 7. Go Service 规范

- 只用于 Pipeline 难以实现的复杂图像算法或特殊交互逻辑
- 整体流程仍由 Pipeline 串联，禁止在 Go 中编写大量流程代码
- 新增 Custom 组件需要：
    1. 在对应子包 `register.go` 注册
    2. 在 `agent/go-service/register.go` 的 `registerAll()` 中接入
    3. 重新执行 `python tools/build_and_install.py`

---

## 8. MapTracker（官方自动送货使用）

官方 `SeizeDeliveryJobs` 送货用 `MapTrackerGoal` 实现 NavMesh 寻路。

### MapTrackerGoal 关键参数

```json
{
    "custom_action": "MapTrackerGoal",
    "custom_action_param": {
        "map_name": "map02_lv005",
        "target": [
            670.0,
            350.8
        ],
        "zipline_policy": "Lazy"
    }
}
```

**`zipline_policy` 四档**：

| 策略         | 起用滑索距离 | 官方描述                                   |
| ------------ | ------------ | ------------------------------------------ |
| `Never`      | 永不         | 始终不使用滑索（`MapTrackerGoal` 默认）    |
| `Lazy`       | >180m        | 仅在极端情况（当前 `departure.go` 写死值） |
| `Active`     | >45m         | 像人类玩家一样主动使用                     |
| `Aggressive` | >15m         | 非常积极，一般不推荐                       |

### MapTrackerAssertLocation

判断玩家当前位置是否在预期区域（Recognition 节点）：

```json
{
    "recognition": "Custom",
    "custom_recognition": "MapTrackerAssertLocation",
    "custom_recognition_param": {
        "expected": [{"map_name": "map02_lv002", "target": [
                    670,
                    350,
                    20,
                    20
                ]}]
    },
    "action": "DoNothing"
}
```

### 工具：`tools/map_tracker/map_tracker_master.py`

录路径、框 AssertLocation 区域。**必须从仓库根目录运行**，否则 WORK_DIR/ASSET_DIR 相对 CWD 解析出错报 503：

```bash
python tools/map_tracker/map_tracker_master.py   # → http://127.0.0.1:8060/web/
```

> 旧名 `map_tracker_editor.py` 已不存在（上游 v2 合并改名）。需装 `maafw` pip 包（import 名是 `maa`）。

---

## 9. MapNavigator（路径导航，采集路线使用）

使用 `MapNavigateAction`，路径通过 `tools/MapNavigator/main.py` 录制。

常用 path 节点动作：`RUN` / `SPRINT` / `JUMP` / `INTERACT` / `PORTAL` / `TRANSFER` / `COLLECT` / `DIG` / `HEADING`

`NAVMESH` 语义寻路节点（只需填目标坐标，运行时自动 A\* 规划）：

```json
{"action": "NAVMESH", "target": [
        720,
        630
    ]}
```

---

## 10. 资源规范

- **分辨率基准：1280×720**，所有 roi / target / 模板图以此为准
- MaaFramework 运行时自动缩放到用户设备
- 推荐用 **Maa Pipeline Support**（VS Code 插件）截图取 ROI，也可用 MaaDebugger
- **截图时禁止开 HDR、夜间模式、Nvidia 滤镜**，否则颜色偏差影响识别
- `install/resource` 等目录是软链接，改 `assets/` 立即生效；`interface.json` 是复制文件，改后需运行 `build_and_install.py` 或手动同步

---

## 11. 国际化（i18n）

- 5 个语言文件必须同步：`zh_cn` / `zh_tw` / `en_us` / `ja_jp` / `ko_kr`（均在 `assets/locales/interface/`）
- 仅修改中文，`tools/i18n` 会自动处理多语言 OCR；`expected` 写完整文本
- 英文 `expected` 自动生成忽略大小写的正则，单词间用 `\\s*`
- 手写正则/片段时加 `// @i18n-skip`

---

## 12. 提交前检查

```bash
pnpm format        # JSON/YAML 格式化
pnpm format:go     # Go 代码格式化（改了 Go 才需要）
pnpm check         # 资源和 schema 检查
pnpm test          # 节点测试
```

**改了 Go 代码后必须**：

```bash
python tools/build_and_install.py
```

**改了 Pipeline JSON 后必须完整重启 MaaEnd.exe 才生效**（软链接保证文件最新，但已运行进程的内存不会自动重载）。

---

## 13. 配套文件检查清单

新增或修改功能时，通常需要同步以下文件：

- `assets/tasks/*.json` — 任务选项定义
- `assets/resource/pipeline/**/*.json` — Pipeline 节点
- `assets/locales/interface/zh_cn.json`（+其余 4 语言）— i18n 文案
- `assets/interface.json` — 任务导入（通过 `include "tasks/Xxx.json"` 引用，新任务才需要加）；改了要手动同步 `install/interface.json`（复制文件，非软链接）
- `tests/**/*.json` — 节点测试（识别节点写好后补测试用例）

**录送货滑索路线**（本分支的核心工作）请先读专门文档：[docs/zh_cn/developers/tasks/seize-delivery-jobs-route-recording.md](docs/zh_cn/developers/tasks/seize-delivery-jobs-route-recording.md)

---

## 14. 节点测试规范

测试文件放 `tests/` 下，文件名必须匹配 `test_*.json`，截图放 `tests/MaaEndTestset/`。

```jsonc
{
    "configs": {
        "name": "(Win32-官服)SeizeDeliveryJobs",
        "resource": ["官服"],
        "controller": ["Win32"],
    },
    "cases": [
        {
            "image": "武陵_抢委托_地图弹窗.png",
            "hits": ["InDestinationMap"],
        },
    ],
}
```

- 正例（应命中）和负例（不应命中，`hits: []`）都要有
- 截图分辨率 1280×720，用 Maa Pipeline Support 截取

---

## 15. 调试工具速查

| 工具                 | 用途                                    | 启动方式                                      |
| -------------------- | --------------------------------------- | --------------------------------------------- |
| Maa Pipeline Support | VS Code 插件，截图/ROI/取色/Launch 调试 | VS Code 安装插件后在 Pipeline 节点上点 Launch |
| MaaDebugger          | 独立调试器，连接游戏窗口实时截图取坐标  | `python -m MaaDebugger`                       |
| MaaPipelineEditor    | 可视化构建 Pipeline                     | https://mpe.codax.site                        |
| MaaLogAnalyzer       | 可视化分析日志                          | 见项目 GitHub                                 |

**MaaDebugger 连接步骤**：WIN32 标签页填窗口名 `Endfield` → SCAN → CONNECT → 填 Resource Directory → LOAD → 点图取坐标（终端打印 `on_click_image: x, y`，即 1280×720 游戏坐标，零换算）

---

## 16. 二进制版本管理

- `install/agent/cpp-algo.exe` / `go-service.exe` 来自官方 Release，**不在 git 中**
- 游戏更新或功能需要新 Go 代码时，需更新对应 exe
- 当前已安装版本：**v2.15.0**（2026-06-12，含 PR #3531 自动送货）
- 备份在 `install/_backup_pre_v2.15/`
- 查最新版本：`curl -sL "https://api.github.com/repos/MaaEnd/MaaEnd/releases/latest" | python -c "import sys,json;d=json.load(sys.stdin);print(d['tag_name'])"`
- 主程序：`install/MaaEnd.exe`（旧版叫 `mxu.exe`）

更新时只覆盖 `install/agent/` 三件套 + `deps/bin/` maafw dll，**不覆盖** `resource/tasks/locales/data`（软链接）。

---

## 17. 接力快速上手

新开会话时，把下面这段发给 Claude：

```
继续 MaaEnd feature/zipline-fast 分支的开发。
请先阅读 e:\TestBase2\MaaEnd\CLAUDE.md 了解上下文。

当前阶段：[Plan / 开发 / 测试 / 已完成]
我刚做了：[一句话描述]
```

### 17.1 「回家」收尾流程（博士说"我要回家了"即执行）

博士本人要求保存此流程：当博士说「我回家了 / 要走了」之类的话，Claude 执行以下收尾：

1. 把今天的进度、已确认的决策、下一步，更新到第 18 节「当前进度存档」。
2. 提交改动并推送到 `myfork`（博士的个人 fork）：
    ```bash
    git add <具体文件>
    git commit -m "docs/feat/fix: ..."   # 按 Conventional Commits
    git push myfork feature/zipline-fast
    ```
3. 告知博士已推送，路上注意安全。

> 注：commit 信息须如实反映改动；推送目标仅限博士本人的 fork（`myfork`），不涉及官方仓库。若某次 commit/push 被安全机制拦截，照常请博士手动确认即可。

### 17.2 「接力」开场流程（博士说"继续自动送货开发"即执行）

1. Claude 先把第 18 节内容完整发出来给博士确认（**至少发 18.0，那是最新状态**）。
2. 博士确认无误后，删除第 18 节，继续开发。

---

## 18. 当前进度存档（接力时先读此节，确认后删除）

### 18.0 最新状态（2026-08-06 家里电脑）

**本轮做完三件。前两件已实测通过；第三件（试验园区四条路线）代码已完成，⚠️ 尚未实机测试。**

#### 18.0.1 ⚠️ 试验园区四条路线（代码已完成，**待实机测试**）

博士 2026-08-06 交了全部坐标，四条路线已写完、环境已就绪，**下次开工第一件事就是实机跑这四条**。

| 路线                            | 滑索             | `chain_max_press` | departure.go 终点 |
| ------------------------------- | ---------------- | ----------------- | ----------------- |
| 取货（锚点→仓储节点）           | 单段，跨度 38.11 m | —                 | —                 |
| `No1TypeCAnchorArea` 一号辅桩   | 6 架连滑         | 5                 | `{126.7, 114.2}`  |
| `No3TypeCAnchorArea` 三号辅桩   | 6 架连滑         | 5                 | `{415.9, 193.8}`  |
| `JingweiFieldArea` 经纬田       | 4 架连滑         | 3                 | `{429.7, 294.7}`  |

- **取货段已替换掉上游的 `MapTrackerGoal`**，改走滑索路线（`SeizeDeliveryJobsWalkToDepotNodeTestArea` 现为 SubTask 五段结构）
- 传送锚点用 `SceneEnterWorldWulingTestArea1`（综合科研区，MT `[336.3,420.1]`）
- 三条送货路线**共用起点段** `SeizeDeliveryJobsDeliverTestAreaWalkToZipline`；该起点滑索架与取货段下索点是同一架
- 经纬田是三号辅桩滑索链的**前 4 架前缀**，在第 4 架提前下索
- 三个终点相互距离 102 / 300 / 353 m，远超误匹配半径 30 ✅
- 4 个独立测试入口已建（UI 在「地区建设」分组），跑完即停不做取货/提交

**⚠️ 三处已知风险（实机时重点看）**：

1. **三个 HEADING 距站位仅 1.0~1.2 m**（取货上索 1.20 / 送货上索 1.06 / 一号辅桩 NPC 1.20），低于规范 §3.2 建议的 2 m。但**已测通的武陵城材料研究所路线也是 1.0 m 且稳定**（Owl 那次崩是 0.57 m），故先按现值跑。三处都在 JSON 里注了距离和角度，不稳直接改那一行 target 为同方向更远的点。
2. **三号辅桩 + 经纬田没有 HEADING**：博士给的 NPC 朝向点与送货点位坐标完全相同（相距 0 m），算不出角度。按博士决定先不加，与武陵城取货段做法一致。若交互按钮不出，补录 NPC 本体坐标后按 JSON 里的 TODO 追加。
3. **三号辅桩链第 4→5 架仅 15.26 m**，其余各段 63~81 m。若落错架，先核对架数是否真为 6。

**坐标处理上替博士做的两个判断**（实机若不对先查这里）：

- 取货段最后一个点标的是「取货点位（Heading调整朝向）」，但 `[297.2,413.3]` 与上游 `MapTrackerGoal` 走到的取货点现值 `[297.5,413.3]` 只差 0.30 m → **按站位（NAVMESH）处理，未做 HEADING**
- 三条送货路线前三个点完全相同且等于取货段下索点 → **合并为共用起点段**

#### 18.0.2 ✅ 转交委托「自动送货」（已实测通过，并已扩到试验园区）

「🚚转交委托」任务新增 `DeliveryJobsAutoDeliver` 开关（默认关）。开启后不把委托转交给他人，而是自己走固定滑索路线送达并提交。**现支持武陵城区 + 试验园区**（试验园区部分随 18.0.1 一起待测），四号谷地会停止任务并提示。

| 文件                                                                 | 改动                                                       |
| -------------------------------------------------------------------- | ---------------------------------------------------------- |
| `assets/resource/pipeline/DeliveryJobs/AutoDeliver.json`（新建）     | 9 个接线节点，全默认关闭，**无新识别节点**                 |
| `assets/tasks/DeliveryJobs.json`                                     | 新增 `DeliveryJobsAutoDeliver` switch                      |
| `assets/locales/interface/*.json` ×5                                 | 各 3 个键（label / description / unsupportedRegion）       |
| `docs/zh_cn/developers/tasks/seize-delivery-jobs-route-recording.md` | 新增 §10「复用到其他任务」，同步 §7 的 Go 表结构           |

**关键实现思路**：`SeizeDeliveryJobsPostProcessingEntry` 本身就是自包含的「拿着单 → 取货 → 送货 → 提交」子流程，不依赖抢单；`CheckCarryingGoods` 已同时处理「已带货 / 未带货」两分支。所以**零新流程**，只做接线。

⚠️ **踩到的坑（已解决，写进文档 §10.2）**：**自己装箱产生的委托不会出现在「运送委托列表」里**，官方 `SeizeDeliveryJobsEnterDestinationMap` 走不通、流程卡死。改从「本地仓储节点 →「查看任务」→ 任务界面 → 点定位按钮」进地图，即 `DeliveryJobsAutoDeliverEnterDestinationMap` 那组节点（武陵城区/试验园区各一个 ViewJob 节点，认同页两张卡）。
→ 该节点在整条链里**被调用三次**（传送前、取消蓝点前、送货前），所以覆写它的 `next` 一次性全改道；替代节点**不能加 `max_hit`**。

✅ **全程走 `pipeline_override` 叠加，没改任何上游节点文件**——这正是长期路线图方案 B 的做法，冲突面比取货段现有的「整节点替换」小得多。

⚠️ 选项带 `"controller": ["Win32-Front", "Wlroots"]`：MapTracker/MapNavigator 只在这两个控制器可用，而 `DeliveryJobs` 任务本身支持 ADB/MacOS/PlayCover，故需选项级限制。

#### 18.0.3 ✅ `departure.go` 多地图改造（已完成）

endpoints 从平铺切片改成 `map[地图名][]seizeDeliveryJobsEndpoint`；删掉写死的 `if mapName != "map02_lv002"` 守卫，改为按地图查表。武陵城 4 个点坐标与匹配半径 30 一字未动；`map02_lv005` 三个终点已填。

#### 18.0.4 环境状态

| 项               | 状态                                                              |
| ---------------- | ----------------------------------------------------------------- |
| `cpp-algo.exe`   | ✅ 官方 v2.23.0-beta.4（与合并后源码零 diff）                     |
| `go-service.exe` | ✅ 2026-08-06 01:29 自编，17826816 B，含 lv005 三个终点坐标       |
| 备份             | `install/_backup_pre_v2.23_20260805/`                             |
| 静态检查         | ✅ `pnpm format` / `check`（7 控制器全绿）/ `test` 全通过          |
| 接线完整性       | ✅ 已逐项核对（节点引用、chain 参数、任务注册、i18n 5×8 键）       |
| 取货段抖动       | ✅ 已复测通过（上游 #4572 + beta.4 的 #4576 治住了）              |
| git 代理         | ✅ 已删除 `~/.gitconfig` 里失效的 `127.0.0.1:7897`，改走直连      |

### 18.1 下一步

1. **【下次先做】实机测试试验园区四条路线**（见 18.0.1 的三处已知风险）。

    **完整重启 `MaaEnd.exe`**（pipeline JSON 不热重载），在「地区建设」分组依次跑：

    | 顺序 | 任务                                       |
    | ---- | ------------------------------------------ |
    | 1    | `🧪取货段测试(试验园区)`                   |
    | 2    | `🧪送货路线测试·一号丙型辅桩区(试验园区)`  |
    | 3    | `🧪送货路线测试·三号丙型辅桩区(试验园区)`  |
    | 4    | `🧪送货路线测试·经纬田区(试验园区)`        |

    每个跑完即停，只核对路线与落点。出问题看 `install/debug/cpp-algo/debug/maafw.log`（NAVMESH/HEADING）和 `install/debug/go-service.log`（滑索）。排查表见录制规范 §11。

2. **四条路线测通后**：跑一遍完整「抢委托送货 → 全自动送货 + 萧然Q滑索送货」，验证 Go 分流能把试验园区的 3 种蓝标正确匹配到路线（`map_name_regex` 已含 lv005，终点表已填，但端到端没跑过）。再跑一遍「转交委托 → 自动送货」的试验园区分支。

3. **长期：与上游的更新关系**（未定案）。取货段目前仍是**整节点替换**上游 `MapTrackerGoal`（武陵城和试验园区都是），上游每次改那节点都会冲突。三种走法：
    - **A. 保持私有分支定期合并**（现状）
    - **B. 改成 `pipeline_override` 叠加**——本轮自动送货已验证这条路可行且更干净，建议照此重构现有路线接线
    - **C. 向上游提 PR**——准入门槛是「取货段硬替换要先改成受选项控制」，即先做 B
    - 💡 建议：**等试验园区路线测稳后做 B**，否则边改路线边改架构两头乱。

4. **本机不装 C++ 工具链**（2026-07-30 博士决定）。无 Visual Studio，自编 C++ 需 CMake + VS BuildTools(~5-7GB)。目前改动都在 pipeline JSON + Go，靠官方 Release exe 即可。`python tools/build_and_install.py` 默认跳过 C++。

### 18.2 ⚠️ 换电脑接力提醒（务必先确认二进制）

二进制**不随 git 同步**（`.gitignore` 忽略整个 `install/`）。

**家里电脑（`d:\Github project\Maaend`）：✅ 全部就绪**，见 18.0.4。

**换到公司电脑（`e:\TestBase2\MaaEnd`）时要做**：

- ⚠️ 公司那台是 **v2.22.0** 的 `cpp-algo.exe`，**落后于当前源码**（缺 Recast 大改 + #4576）。要换成 **v2.23.0-beta.4**：覆盖 `install/agent/cpp-algo.exe` + `WebView2Loader.dll` + `install/maafw/*`（**不覆盖** resource/tasks/locales/data 软链接，也**不必**换 `MaaEnd.exe`）。
- `go-service.exe` 不在 git，**必须自己 `python tools/build_and_install.py` 重编**（含 lv005 终点坐标）。
- 覆盖前**先关掉 MaaEnd.exe 及所有 agent 子进程**，否则 dll 被锁。用 `tasklist | grep -i "MaaEnd\|cpp-algo\|go-service"` 确认清空。
    - ⚠️ MapTracker 工具（`map_tracker_master.py`）会 spawn `go-service.exe`，关浏览器页面**不够**，要在终端 Ctrl+C 结束 python 进程。
- 覆盖后**逐字节核对** sha256，别只看时间戳。
- ⚠️ 下 zip 时 GitHub 直连/镜像可能只有 5~10KB/s，193MB 基本下不动。**博士用浏览器手动下更快。**
- 改完**完整重启 MaaEnd.exe**（pipeline JSON 不热重载）。

### 18.3 文件速查

| 内容                     | 位置                                                                                                                                                                                                                                                                |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **录制规范（先读这个）** | [docs/zh_cn/developers/tasks/seize-delivery-jobs-route-recording.md](docs/zh_cn/developers/tasks/seize-delivery-jobs-route-recording.md)（§10 讲跨任务复用，§11 排查表）                                                                                            |
| **试验园区录制清单**     | [docs/zh_cn/developers/tasks/seize-delivery-jobs-testarea-recording-checklist.md](docs/zh_cn/developers/tasks/seize-delivery-jobs-testarea-recording-checklist.md)                                                                                                  |
| 转交委托-自动送货接线    | `assets/resource/pipeline/DeliveryJobs/AutoDeliver.json` + `assets/tasks/DeliveryJobs.json` 的 `DeliveryJobsAutoDeliver`                                                                                                                                            |
| 取货路线（两张图）       | `assets/resource/pipeline/SeizeDeliveryJobs/SeizeDeliveryJobsPost.json`（测试入口 `SeizeDeliveryJobsTestPickupEntry` / `SeizeDeliveryJobsTestPickupTestAreaEntry`）                                                                                                 |
| 送货路线（7 条）         | `assets/resource/pipeline/SeizeDeliveryJobs/SeizeDeliveryJobsDeliverRoutes.json`（武陵城 4 条 + 试验园区 3 条，各带 `SeizeDeliveryJobsTestDeliver*Entry` 测试入口，UI 在「地区建设」分组）                                                                          |
| 抢委托送货 UI 选项       | `assets/tasks/SeizeDeliveryJobs.json` 的 `SeizeDeliveryJobsCustomDelivery`（「萧然Q滑索送货」）                                                                                                                                                                     |
| Go 分流（按地图分组）    | `agent/go-service/seizedeliveryjobs/departure.go` 的 `seizeDeliveryJobsEndpoints`                                                                                                                                                                                   |
| 滑索实现                 | `agent/go-service/maptracker/default/zipline.go`（`chain_max_press` + 1s 发射延迟）                                                                                                                                                                                 |
| 索上转向                 | `agent/go-service/maptracker/default/toward.go`（⚠️ 会位移，见规范 §4.4）                                                                                                                                                                                           |
| 坐标换算参数             | `assets/resource/image/MapLocator/maptracker_coordinate_transforms.json`（lv005：offset `(960.0, 1344.0)`，scale `(0.985337243402, 0.984615384615)`，zone `Wuling_Base`）                                                                                            |
| MapTracker 工具          | `python tools/map_tracker/map_tracker_master.py` → http://127.0.0.1:8060/web/ （**从仓库根目录启动**）                                                                                                                                                              |
