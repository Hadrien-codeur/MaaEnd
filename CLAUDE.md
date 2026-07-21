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
- **本地路径**：`e:\TestBase2\MaaEnd`
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

### 工具：`tools/map_tracker/map_tracker_editor.py`

录路径、框 AssertLocation 区域。运行：

```bash
python tools/map_tracker/map_tracker_editor.py
```

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
- `assets/interface.json` — 任务导入（通过 `include "tasks/Xxx.json"` 引用，新任务才需要加）
- `tests/**/*.json` — 节点测试（识别节点写好后补测试用例）

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

1. Claude 先把第 18 节内容完整发出来给博士确认。
2. 博士确认无误后，删除第 18 节，继续开发。

---

## 18. 当前进度存档（接力时先读此节，确认后删除）

### 18.1 状态：已同步 v2.20.0 + 本机二进制已更新 + 待「A 方案」复测 NAVMESH 步行段

**本次会话完成（2026-07-21，本机 = 装 cmake 那台之外的另一台，二进制原本更旧）**：

1. **对齐另一台电脑**：`feature/zipline-fast` fast-forward 到 `d8886c7c`（取货段坐标已用 MapNavigator 校准定稿，见 18.3）。
2. **同步上游到 v2.20.0**：本地 `v2` 更新到 `origin/v2`（`f60dcd52`，+114 提交）；merge 进开发分支（merge commit `29157402`）。
    - 解决 2 处冲突：`zh_cn.json`（我们的测试任务文案 + 上游新增「接取价格」文案，两者都留）、`SeizeDeliveryJobsPost.json`（保留我们的取货段测试入口）。
    - **修复合并引入的悬空引用**：上游 PR #4240（快捷选点传送重构）删掉了 `__SeizeDeliveryJobsEnsureInWorld` 定义，而我们两处仍引用它 → 已把该私有守卫节点补回 `SeizeDeliveryJobsPost.json`。`pnpm check` 4 控制器全绿。
    - ⚠️ **上游 PR #4240 大改了送货主流程**（`SeizeDeliveryJobs.json` −308 行、新增 `find_target.go`，用自动传送点选择替代旧自定义点选）。我们的 `departure.go`/`SeizeDeliveryJobsDeliverRoutes.json` 核心逻辑未被波及（diff 为空），但**取货段与上游新流程的运行时衔接尚未实机复验**。
3. **二进制混合更新（本机）**：旧的已备份到 `install/_backup_pre_v2.20_20260721`。
    - `cpp-algo.exe`：**官方 v2.20.0 覆盖**（2.36MB→4.0MB，含 MapNavigator 修复 #3995 自动绕障 / #4055 防卡墙 / #4164 走廊门控 / #4169 折角）。我们没改 C++，安全。
    - `maafw dll ×16`（`deps/bin/`）：**官方 v2.20.0 覆盖**。
    - `go-service.exe`：**本机 go1.26.2 自编译**（`python tools/build_and_install.py`，默认只编 Go 跳过 cpp-algo）。因为它含我们分支独有的送货分流 + 滑索发射延迟修复，官方版没有。ABI 兼容已核实：`go.mod` binding `maa-framework-go/v4 v4.0.0-beta.18` 就是官方 v2.20.0 编译所用版本，同源。
4. **导航工具体系调研**（三路并行，结论见 18.6）：确认「MapNavigator/MapLocator 定位更准、上游主推、但无滑索能力」；坐标与移动方式硬绑定，跨用有损（`MapTrackerMoveCompatible` 静默丢 NAVMESH 点）。

### 18.2 坐标转换（本次核心工具，务必记住）

MapNavigator 编辑器导出的是 **base px**（如 [942,722]）；MapTracker 的 `path`/`target` 用 **MapTracker 游戏坐标**（如 [664,734]）。**两者不同系，不能直接互填**。

- 正向 base = offset + mt×scale；**反向 mt = (base − offset) / scale**
- 武陵 `map02_lv002`：`offset=(288, 0)`，`scale=(0.985176738883, 0.985074626866)`
- 速查脚本：`mt_x=(bx-288)/0.985176738883`，`mt_y=by/0.985074626866`
- 其它层级参数见 `assets/resource/image/MapLocator/maptracker_coordinate_transforms.json`（按 map_name 取行）。
- 实测：MapNavigator 定位很准，转回 MapTracker 后与原手录坐标仅差 0.6~3 单位（双向验证公式正确）。

### 18.3 已定稿改动（取货段，本次已提交）

`SeizeDeliveryJobsPost.json` 取货三明治，仅校准首尾锚点、保留中间过渡点与走法（滑索段的 `MapTrackerZipline` 机制不变）：
- `SeizeDeliveryJobsWulingCityWalkToZipline`：起点 (664.5,734.2)→**(663.87,733.9)**，终点 (673.2,732.9)→**(670.36,731.79)**
- `SeizeDeliveryJobsWulingCityZipline`：target (684.4,785.5)→**(682.9,785.25)**
- `SeizeDeliveryJobsWulingCityWalkFromZipline`：起点 (683.3,785.5)→**(682.25,786.75)**，终点 (674.9,789.2)→**(674.99,788.58)**
- 方案文档：`docs/zh_cn/dev-notes/送货步行段迁移NAVMESH方案.md`（记录了 NAVMESH vs MapTracker、坐标转换、MapNavigateAction ≠ MapTrackerMoveCompatible 的坑）。

### 18.4 下一步（博士回家后先做「A 方案」，再录 3 终点）

#### 🅰️ A 方案：用新二进制复测「步行段改 NAVMESH」是否可行（回家后第一件事）

**动机**：18.1 里 NAVMESH 直替取货段失败的两个根因之一是「旧 cpp-algo（6-30）MapNavigator 定位抖动，缺 #4164/#4169 修复」。本机 cpp-algo 已升到 v2.20.0（含这些修复），值得**重新打样一次**，看定位抖动是否消除、上索贴位容差是否够。

**⚠️⚠️ 另一台电脑二进制备注（务必先确认）**：
- 二进制 **不在 git 里**（`.gitignore`），推送到 myfork 的只有源码/pipeline/文档，**不含更新后的 exe/dll**。
- 因此**另一台电脑（cmake 那台）拉取本次改动后，cpp-algo.exe 仍是它本地的旧版**，若不更新就复测 NAVMESH，结果不可信（会重现旧的定位抖动）。
- **A 方案必须在「已更新 cpp-algo 到 v2.20.0」的机器上做**。本机（2026-07-21 这台）已更新完毕，直接可测。若换回 cmake 那台，需先：`--cpp-algo` 自编译，或按 18.5「二进制」流程用官方 v2.20.0 覆盖 cpp-algo + maafw dll，再 `python tools/build_and_install.py` 编 go-service。
- 每台机器改完 Go/Pipeline/locale 后都要 **完整重启 MaaEnd.exe** 才生效。

**A 方案打样步骤**（挑最短、最易翻车的取货段做 A/B 对照）：
1. 备份现取货段（已定稿的 MapTracker 折线坐标在 18.3，git 里有，随时可回退）。
2. 把取货 `SeizeDeliveryJobsWulingCityWalkToZipline` 从 `MapTrackerMove` 改成 `MapNavigateAction`（**C++ 真 A\***，`custom_action:"MapNavigateAction"`，**绝不要用 Go 的 `MapTrackerMoveCompatible`——它静默丢 NAVMESH 点**），path 用 `NAVMESH` 目标点（base px，用 MapNavigator web 工具 A\* 页取）。
3. 定位断言若也换，配套用 `MapLocateAssertLocation`（C++，base px），不要混 `MapTrackerAssertLocation`。
4. 跑 `SeizeDeliveryJobsTestPickup` 实测：
    - ✅ 若 NAVMESH 能贴到滑索架、`GetOnZipline` 上索按钮识别成功（score 明显 >0.5）→ 说明新二进制解决了问题，可推广到送货步行段。
    - ❌ 若仍停在距架 ~2 单位、上索失败 → 确认「取货段太短 + 贴位容差」是硬伤，NAVMESH 不适合极短贴位段；**回退到已定稿的 MapTracker 折线**，维持「MapNavigator 只当取坐标器」方案，直接进「录 3 终点」。
5. 无论成败，把结论写回 18.1 / 18.6，并更新方案文档 `docs/zh_cn/dev-notes/送货步行段迁移NAVMESH方案.md`。

#### 🅱️ A 方案定论后：录送货 3 终点（Owl / MaterialResearchInstitute / TechProductionOffice）

- **样板 = Observatory 路线**（`SeizeDeliveryJobsDeliverRoutes.json`，已实测通过）。每条 = SubTask 串：`DeliverWalkToZipline(共用,已录) → GetOnZipline → <滑索段> → GetOffZipline → <WalkToNpc>`。
- **已确认：3 条新路线共用起点滑索段 `SeizeDeliveryJobsDeliverWalkToZipline`**（都从同一起点滑索架出发，上索后滑向不同方向）。
- 每条路线博士需用 MapNavigator 提供（**base px，Claude 负责转 MapTracker**）：
  1. 单段滑索 还是 连滑（连滑要 `chain_max_press`=途中按E次数 + 途经架子，需实机滑一遍数）；
  2. 滑索段 `target`（朝哪个滑索架发射）；
  3. 下索落点 → NPC 的 `WalkToNpc` 步行折线点。
- 现有 3 终点节点已在 `SeizeDeliveryJobsDeliverRoutes.json` 建好骨架，`target`/`path` 是 TODO 空占位，填坐标即可。
- `departure.go:39-44` 三终点世界坐标仍 `{0,0}` 占位（`nearestEndpoint` 匹配半径 30），录完 WalkToNpc 后**需同步把终点世界坐标填进去**，否则分流匹配不到。

### 18.5 复用节点 & 文件速查

- **送货路线**：`SeizeDeliveryJobsDeliverRoutes.json`（Observatory 已实测；3 终点骨架已建、坐标待填）。
- **取货路线**：`SeizeDeliveryJobsPost.json`（取货三明治，坐标已定稿）。测试任务 `SeizeDeliveryJobsTestPickup`（入口 `SeizeDeliveryJobsTestPickupEntry`）。
- **送货 Go 分流**：`departure.go`（`nearestEndpoint`→`runDeliverRoute` RunTask 同名节点；改坐标只动 pipeline，Go 不用改）。
- **滑索**：`zipline.go`（`chain_max_press` 连滑 + 1s 发射延迟）；`MapTrackerZipline` target=发射朝向的滑索架。
- **MapNavigator 工具**：`python tools/MapNavigator/main.py` → 8770。A\* 页选 Wuling/map02base(zone 2) 点点取 base px。**两个"MapNavigate"别混**：`MapNavigateAction`=C++真A\*；`MapTrackerMoveCompatible`=Go垫片会丢NAVMESH。
- **二进制（两台机器状态不同，务必区分）**：
  - **本机（2026-07-21 这台，无 cmake）**：cpp-algo.exe = 官方 v2.20.0（含 MapNavigator 修复）；maafw dll ×16 = 官方 v2.20.0；go-service.exe = 本机 go1.26.2 自编译（含送货分流+滑索修复）。备份 `install/_backup_pre_v2.20_20260721/`。**A 方案可直接在此机测**。
  - **另一台电脑（cmake 那台）**：二进制**不随 git 同步**，拉取后 cpp-algo.exe 仍是它本地旧版（6-30，缺 #4164/#4169）。**若在该机复测 A 方案，必须先把 cpp-algo 升到 v2.20.0**（自编译 `--cpp-algo`，或用官方包覆盖 cpp-algo.exe + `deps/bin/` maafw dll），否则重现定位抖动、结论不可信。
  - 更新二进制通用流程：官方包只覆盖 `install/agent/cpp-algo.exe`+`WebView2Loader.dll` 和 `deps/bin/*.dll`（**不覆盖** resource/tasks/locales/data 软链接）；go-service 用 `python tools/build_and_install.py` 本机编（默认跳过 cpp-algo）。改完完整重启 MaaEnd.exe。

### 18.6 导航工具体系调研结论（2026-07-21，供工具选型）

**两套独立系统，坐标系不同，硬绑定各自运行时**：

| | MapTracker（旧） | MapNavigator/MapLocator（新） |
|---|---|---|
| 录制工具 | `tools/map_tracker/map_tracker_editor.py`（OpenCV GUI） | `tools/MapNavigator/`（Web，`main.py`→:8770） |
| 坐标系 | MapTracker 大地图 PNG 像素 | **base 像素**（MapLocator 全局底图） |
| 定位 | `MapTrackerAssertLocation`（Go，模板匹配，有抖动） | `MapLocateAssertLocation`（C++，YOLO+ZNCC+运动预测，**更准**） |
| 移动 | `MapTrackerMove` 折线 / `MapTrackerZipline` 滑索 / `MapTrackerGoal`(.mtnm Dijkstra) | `MapNavigateAction`（录制 path 或 `NAVMESH` A\*） |
| 运行时 | Go | C++ cpp-algo |

**关键事实**：
1. **精度**：MapNavigator/MapLocator 定位更准（实测转回 MapTracker 仅差 0.6~3 单位）。→ 无论最终用哪套移动，**取坐标都优先用 MapNavigator web 工具**。
2. **滑索是 MapTracker 独有**：MapNavigator 无 ZIPLINE 动作。→ 送货三明治的**滑索段只能留 MapTracker**，不能整段迁 MapNavigator。
3. **坐标不能喂错运行时**：MapNavigator 录的含 NAVMESH 的 path 绝不能走 `MapTrackerMoveCompatible`（`move_compatible.go:236` 静默丢弃 NAVMESH 点，不报错）。
4. **上游趋势**：近 4 个月 MapNavigator 72 提交 / MapTracker 63 提交，都活跃。MapNavigator 是寻路算法主战场（绕障/防卡墙/门控/折角，从 Beta 收敛到可靠）；MapTracker 偏玩法（滑索/传送/资源）。官方 skill 明确要求 **AutoCollect 新路线用 MapNavigateAction+MapLocateAssertLocation、禁用 MapTracker**；MapNavigator 指南默认「优先 NAVMESH」。两套是共享底座（#3359 已把 NavMesh 回接进 MapTracker），无淘汰风险。
5. **现状**：SeizeDeliveryJobs（我们）= 纯 MapTracker；TrialOfSwordmancy/AutoSell = 纯 MapNavigator；AutoCollect 正从 MapTracker 向 MapNavigator 过渡。

**对送货的选型定论**：
- 滑索段：MapTracker（不变，唯一有滑索）。
- 步行段：先做 A 方案复测 NAVMESH（新二进制下）；成则简化（只填终点+自动绕障），败则回退「MapNavigator 取坐标 + MapTracker 折线」的已定稿方案。
