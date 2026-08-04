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

### 18.-2 最新状态（2026-08-05 家里电脑，读这节就够）

**本轮做完：合并上游 82 commit + 离线解算试验园区坐标换算 + 二进制更新到 beta.4。三项都已完成，剩下就是实机录路线。**

已 push 到 `myfork/feature/zipline-fast`（`96d5f4d7`）。

#### 18.-2.1 ✅ 环境已就绪，可以直接开录

| 项                       | 状态                                                                                         |
| ------------------------ | -------------------------------------------------------------------------------------------- |
| 上游合并                 | ✅ `v2` 拉到 `ca33e2d4`（82 commit），merge `f5f16b57` **零冲突**，`pnpm check` 7 控制器全绿 |
| `cpp-algo.exe`           | ✅ 官方 **v2.23.0-beta.4**，4362752 B，28 个文件逐字节核对一致                               |
| maafw dll ×17 + WebView2 | ✅ 同 beta.4                                                                                 |
| `go-service.exe`         | ✅ 2026-08-05 01:13 用合并后代码自编，17820160 B                                             |
| 备份                     | `install/_backup_pre_v2.23_20260805/`（3 agent + 17 maafw）                                  |
| 软链接                   | ✅ 9 个完好，`resource`/`tasks`/`locales`/`data` 未被触碰                                    |

> **关键确认**：`v2.23.0-beta.4` 的 **C++ 源码与我们合并后的代码零 diff**（`git diff v2.23.0-beta.4 origin/v2 -- agent/cpp-algo/` 为空），含全部 Recast 新算法 + #4576 箭头修复。**所以二进制与源码已完全同步，NAVMESH 实机结论可信。**
>
> ⚠️ `install/MaaEnd.exe` 有意**未**覆盖（仍是 6-30 版）。它是 GUI 外壳，与 NAVMESH/滑索算法无关，换它可能带来配置兼容问题。zip 里的新版是 28408832 B，需要时再换。
>
> ⚠️ 下载 zip 时 GitHub 直连和两个镜像都只有 5~10KB/s，193MB 下不动，最后是博士手动下的（放在 `d:\Github project\`，仓库上一级）。以后换二进制预留时间。

#### 18.-2.2 ✅ 试验园区坐标换算已解算（无需实机标定）

`map02_lv005` 参数已写进 `maptracker_coordinate_transforms.json`（commit `b22d2ad0`）：

```
zone_id=Wuling_Base   offset=(960.0, 1344.0)   scale=(0.985337243402, 0.984615384615)
```

原计划要博士实机站 3 个点读两套坐标，改用**离线图像匹配**算出来了。方法、验证过程、精确有理数依据全部写在清单 §2，以后加新图照抄。

顺带定掉两件此前悬着的事：

- **`zone_id` = `Wuling_Base`**（和武陵城同 zone）
- **base.nav 完整覆盖试验园区** —— 解压 `base.nav.gz` 查 zone 列表，有 `Wuling_L5_314/316/318/319/321/322/324/326`。原清单 §7「读不出位置可能要换方案」的风险**不存在**。

#### 18.-2.3 ⚠️ 两个已知坑（录制前必读，都已写进清单）

**坑 1：lv005 的 tier（高架层）换算算不出来。**
我把 base 层那套离线方法套到 8 张 tier 图上，**不成立**——tier 映射目标是各自独立的小图而非 Base.png 裁剪。拿已知 lv002/lv003 tier 条目验证时，拟合虽自洽（残差 0.1px）但与真值差很远（`tier_298` 拟合 `scale_y=0.984` vs 真值 `1.072`，offset 差 40px），另有 2 个条目特征点不足直接失败。**没有硬凑数写进表**。
→ 录制时博士**标一下哪些点在高架/桥面上**，届时人工确定 `parent_map_name` + `source_bbox`。已知 `SceneEnterWorldWulingTestArea2` 锚点 `[391.6, 362.5]` 就在 tier 322 上。**地面点不受影响，放心录。**

**坑 2：`departure.go` 只认武陵城，不是「加 3 行坐标」就完事。**
`nearestEndpoint` 首行 `if mapName != "map02_lv002" { return "" }`（[:228](agent/go-service/seizedeliveryjobs/departure.go#L228)），试验园区路线录好了**也匹配不上**。三处要改：单地图常量 `seizeDeliveryJobsWulingCityMap`（[:22](agent/go-service/seizedeliveryjobs/departure.go#L22)）、该守卫、平铺的 endpoints 表改成按地图分组。
→ 好消息：`map_name_regex` 已是 `^(map02_lv002|map02_lv005)$`，**pipeline 侧不用动**。
→ ⚠️ `runDeliverRoute` 用 `前缀+名字` 拼节点名，所以**试验园区 3 条路线的英文名不能和武陵城的 `Owl`/`MaterialResearchInstitute`/`Observatory`/`TechProductionOffice` 重复**，否则串线。

#### 18.-2.4 本轮值得注意的上游改动

| commit                                              | 内容                             | 对我们的影响                                                                                                                                                                               |
| --------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [#4760](https://github.com/MaaEnd/MaaEnd/pull/4760) | 调整试验园区仓储节点寻路终点     | 取货点 `[297.5,414.3]` → **`[297.5,413.3]`**，正是我们要录的图，清单已更正                                                                                                                 |
| [#4719](https://github.com/MaaEnd/MaaEnd/pull/4719) | 修大地图缩放后送货定位标点击错位 | 动了 `bigmap/find_image.go`（我们 Go 分流依赖），缩放后重新截图；另加了「自定义标记面板」恢复分支挂在 `SeizeDeliveryJobsClickTracking.next` 首位，**与我们的分流不冲突**（分流发生在其后） |

#### 18.0 家里电脑更早一轮状态（2026-07-30，历史记录）

**本轮做完：合并上游 25 个 commit + 定位取货步行段抖动根因 + 出试验园区录制清单。**

#### 18.0.-2 ⚠️ 开工先做的三件（前两件已完成）

1. ~~**更新 `cpp-algo.exe`**~~ ✅ 2026-08-05 已换 beta.4，见 18.-2.1。
2. **完整重启 MaaEnd.exe**，跑完整「全自动送货」档位复测取货段（**不要**用取货段独立测试入口，见下）。← **仍待做**
3. **实机确认试验园区地图**（博士说要再看一下），然后按清单录坐标。← **仍待做**

#### 18.0.-1 取货步行段抖动：根因已定位（2026-07-30）

博士反馈「下滑索到取货点的步行段左右甩视角、龟速、agent 卡死」。**已查明，不是我们路线坐标的问题。**

**根因**：小地图上的**蓝色任务追踪光环把人物箭头盖住了**，导致 `MapLocator` 算出的朝向是白噪声。

实测那两张 on_error 截图的小地图像素（ROI `49,51,118,120`，采样中心 `(59,60)`，半径 12px）：

|                     | 22:05 截图 | 22:15 截图 |
| ------------------- | ---------- | ---------- |
| 12px 圈内白色像素   | 26         | 12         |
| 最大白色连通块      | 20px       | 7px        |
| 12px 圈内蓝青色像素 | **79**     | **74**     |
| 最近蓝像素到正中心  | 2.2px      | **1.0px**  |
| 正中心 5×5 内蓝像素 | 3/25       | **11/25**  |

白色像素太少，凑不出完整箭头三角形 → `minEnclosingTriangle` 拿 7~20px 碎片拟合 → 角度随机。

**传导链**（三个症状同一个因）：

- 甩视角 → `heading_error` 每帧翻符号，`SendRelativeMoveNative` 交替发 `dx=±476` 满舵反打
- 龟速 → 冲刺闸门 `heading_aligned_for_sprint` 要求误差 <25°，噪声下永远 false，全程只能走不能跑
- 卡死 → `SteeringController` 对角速度 >60°/s 的帧直接丢（[steering_controller.cpp:31](agent/cpp-algo/source/MapNavigator/steering_controller.cpp#L31)），**27 帧丢 24 帧**，闭环瘫痪 → 撑满 `kDynamicRecoveryTotalTimeoutMs=30000` 后 `dynamic_recovery_timeout` 硬失败。失败那次 `WalkFromZipline` 跑了 **46 秒**（22:04:42→22:05:28），成功那次只要 **5.9 秒**。期间日志暴涨到 **113MB**（11.3 万行 AgentClient TRC），这就是「agent 过载」的来源。

> 📌 我一开始误判成「好友玩家白点粘连」，博士看截图指出是蓝色任务标记——**博士判断正确**，像素统计证实了。

**解法**：上游 #4572「取货前取消任务追踪蓝点」正好治这个，**已合入**，纯 pipeline JSON，重启即生效。#4576（箭头最尖顶点判据）是保险，治的是三角形变形，本场景帮助有限（我们连完整箭头都没有）。

⚠️ **复测必须走完整「全自动送货」档位** —— `SeizeDeliveryJobsPrepareFetchGoods` 只在 `TeleWalkFetchDeliver` 档位下 `enabled: true`（[SeizeDeliveryJobs.json:307](assets/tasks/SeizeDeliveryJobs.json#L307)）。用取货段独立测试入口跑**不会**取消蓝点，测不出效果。

**复测判据**：跑完看 `install/debug/cpp-algo/debug/maafw.log` 里 `glitch-suppressed` 占比。昨天 **24/27**，掉到个位数 = 治住了。若仍抖，下一步上「朝向多帧取中位数」滤波（噪声是单帧随机跳、真实转向是连续的，中位数对这种噪声几乎免费）。

#### 18.0.0 上游合并（2026-07-30，commit `022f321e`）

`v2` 已拉到 `0c7221a1`，合入本分支。**只冲突 1 处**：`components-guide.md`（上游接入 markdownlint 重排表格），已取上游格式 + 保留我们的文档行。`SeizeDeliveryJobsPost.json` 自动合并**语义正确**，两侧改动都在。`pnpm check` 通过。

本轮关键上游改动：

| commit                                              | 内容                                | 对我们的影响                                                                                       |
| --------------------------------------------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------- |
| [#4572](https://github.com/MaaEnd/MaaEnd/pull/4572) | 取货前取消任务追踪蓝点              | ✅ **治我们的抖动根因**，纯 JSON 即生效                                                            |
| [#4576](https://github.com/MaaEnd/MaaEnd/pull/4576) | MapLocator 箭头尖端最小内角判据     | 源码已在树，**需新 exe 才生效**                                                                    |
| [#4577](https://github.com/MaaEnd/MaaEnd/pull/4577) | 精细进近改为脉冲移动                | 重写 `MapTrackerMove` 终点收敛 + **调了走跑速度参数**，会影响我们的 Backward 重试节点和 NAVMESH 段 |
| [#4565](https://github.com/MaaEnd/MaaEnd/pull/4565) | 补齐 tick 时延与转向残差埋点        | 复测时方便看残差                                                                                   |
| [#4521](https://github.com/MaaEnd/MaaEnd/pull/4521) | 调 `map02_lv005` 的 MTNM（+72/−25） | 试验园区寻路网格在动，录制时留意                                                                   |

**🎉 武陵城 4 条送货路线 + 取货路线全部实测通过，功能已合并进抢委托送货主流程。**

本阶段目标（把送货段替换成固定滑索路线）**已达成**。技术细节已沉淀成正式文档，不再堆在这里：

> **[docs/zh_cn/developers/tasks/seize-delivery-jobs-route-recording.md](docs/zh_cn/developers/tasks/seize-delivery-jobs-route-recording.md)**
> ——录制规范全文（三明治结构、需要博士提供哪些坐标、HEADING 两条硬规矩、坐标换算、排查指南、术语对照）。
> 新增其他地图路线时**先读它**，本节只留状态和待办。

#### 18.0.1 UI 入口（2026-07-29 定稿）

**抢单结束后的操作 → 全自动送货 → 「萧然Q滑索送货」**（switch，默认关）。

- 就是原来那个「自定义送货」开关改名而来（选项 key 仍是 `SeizeDeliveryJobsCustomDelivery`，博士当时忘了自己开过这个功能，名字太含糊）。
- **没有**在下拉框加第 5 项——博士明确要求替换旧开关，不新增下拉项。
- 开启后 `custom_delivery: true` → Go 侧 `nearestEndpoint` 按 big-map 蓝标匹配预录路线；匹配不到**直接失败，不回退寻路**（[departure.go:151-167](agent/go-service/seizedeliveryjobs/departure.go#L151-L167)）。

#### 18.0.2 已测通的路线一览

| 路线                                      | 滑索段 target（MapTracker）               | chain_max_press | 状态 |
| ----------------------------------------- | ----------------------------------------- | --------------- | ---- |
| 取货（锚点→仓储节点）                     | `[682.9, 785.25]`                         | 0（单段）       | ✅   |
| Owl（猫头鹰，右下）                       | 段A `[663.7,807.3]` + 段B `[241.3,653.8]` | 8 + 1           | ✅   |
| MaterialResearchInstitute（材研所，左下） | `[663.7, 807.3]`                          | 9               | ✅   |
| Observatory（观测站，右上）               | —                                         | —               | ✅   |
| TechProductionOffice（技术办，左上）      | `[673.6, 732.4]`                          | 14              | ✅   |

**Owl 最后是怎么修好的**（唯一一条卡过的）：原 HEADING target 距站位只有 **0.57m**，角度被 MapLocator 的 ~0.7m 单帧抖动完全主导（±51°），转向纯随机。重录 NPC 点拉到 **2.07m** 后即稳。索上转向 `MapTrackerToward` 由 90° 调成 **100°**。

⚠️ **取货段是无条件走固定滑索路线的**（[SeizeDeliveryJobsPost.json:235-248](assets/resource/pipeline/SeizeDeliveryJobs/SeizeDeliveryJobsPost.json#L235-L248) 硬替换了上游的 `MapTrackerGoal`），不受选项控制。这是博士 2026-07-29 明确决定保留的现状，不是遗漏。

#### 18.0.3 departure.go 终点坐标（当前值，无需改动）

[departure.go:39-44](agent/go-service/seizedeliveryjobs/departure.go#L39-L44)，**MapTracker 游戏坐标**（与蓝标同系，不是 base px），匹配半径 30：

Owl `{229.1, 604.6}`、MaterialResearchInstitute `{178.4, 666.5}`、Observatory `{617.1, 358.0}`、TechProductionOffice `{255.2, 197.4}`

Owl 的 NAVMESH 末点 2026-07-29 挪了 1.3m，远在半径 30 内，故**未回填、未重编 go-service**。

### 18.1 下一步

1. **复测取货段抖动**（二进制已就绪，见 18.-2.1）——跑完整「全自动送货」档位，验证上游 #4572 取消蓝点 + beta.4 的 #4576 箭头修复是否治住了抖动。顺便验证 Go 分流把 4 种蓝标都正确匹配到路线（端到端分流还没专门跑过）。
    - **判据**：看 `install/debug/cpp-algo/debug/maafw.log` 里 `glitch-suppressed` 占比。7-29 是 **24/27**，掉到个位数 = 治住了。
    - ⚠️ **必须走完整档位**，不能用取货段独立测试入口（后者不会取消蓝点，测不出效果）。
2. **录试验园区（`map02_lv005`）路线**——已知 **1 个取货点 + 3 条送货路线**。**先读清单**：

    > **[docs/zh_cn/developers/tasks/seize-delivery-jobs-testarea-recording-checklist.md](docs/zh_cn/developers/tasks/seize-delivery-jobs-testarea-recording-checklist.md)**

    ✅ **坐标换算已解算完毕，不用实机标定**（见 18.-2.2）。**坐标全部用 MapTracker 读即可**，base px 我这边换。
    ⚠️ 但要注意两个坑：**高架层点要标注**、**路线名不能和武陵城重复**（见 18.-2.3）。

    工具：MapTracker（`python tools/map_tracker/map_tracker_master.py` :8060）。**必须从仓库根目录启动。**

    试验园区现成传送锚点：`SceneEnterWorldWulingTestArea1`（综合科研区下，MT `[336.3,420.1]`）、`...2`（测试区，MT `[391.6,362.5]`，⚠️ 在 tier 322 高架层上）。取货点上游现值 **`[297.5,413.3]`**（#4760 改过）。

3. **长期：与上游的更新关系**（2026-07-30 讨论，未定案）。现状硬伤：我们把上游 `MapTrackerGoal` **整节点替换**掉了，上游每次改那个节点都会冲突。三种走法：
    - **A. 保持私有分支定期合并**（现状）——最省事，但路线越多人工判断成本越高
    - **B. 改成 `pipeline_override` 叠加而非替换**——上游改动自动跟随，冲突面缩到近零，代价是重构现有 5 条路线接线
    - **C. 向上游提 PR**——最彻底，但准入门槛是「取货段硬替换要先改成受选项控制」
    - 💡 我的建议：**B 和 C 同方向，先做 B**（B 要做的重构正好是 C 的准入门槛）。但**等所有路线录完、行为稳定后再做**，否则边改路线边改架构两头乱。

4. **本机不装 C++ 工具链**（2026-07-30 博士决定）。本机**完全没有 Visual Studio**，`CMakePresets.json` 在 Windows 上只有 MSVC 预设（[build_and_install.py:400](tools/build_and_install.py#L400)），要自编 C++ 需装 CMake(~100MB) + VS BuildTools(**~5-7GB**)。目前所有改动都在 pipeline JSON + Go，不需要 C++，靠官方 Release exe 即可。
    - ⚠️ `python tools/build_and_install.py` **默认跳过 C++**，要加 `--cpp-algo`（加了本机也会因缺 CMake 失败，属预期）

### 18.2 ⚠️ 换电脑接力提醒（务必先确认二进制）

二进制**不随 git 同步**（`.gitignore` 忽略整个 `install/`）。

**家里电脑（`d:\Github project\Maaend`）当前状态：✅ 全部就绪**，见 18.-2.1 的表。

**换到公司电脑（`e:\TestBase2\MaaEnd`）时要做**：

- ⚠️ 公司那台是 **v2.22.0** 的 `cpp-algo.exe`（8-04 换的），**落后于当前源码**（缺 Recast 大改 + #4576）。要换成 **v2.23.0-beta.4**，覆盖 `install/agent/cpp-algo.exe` + `install/agent/WebView2Loader.dll` + `install/maafw/*`（**不覆盖** resource/tasks/locales/data 软链接，也**不必**换 `MaaEnd.exe`）。
- `go-service.exe` 含 departure.go 终点坐标，编好的 exe 不在 git，**必须自己 `python tools/build_and_install.py` 重编**。
- 覆盖前**先关掉 MaaEnd.exe**（含 agent 子进程），否则 dll 被锁、覆盖会失败或只成功一半。用 `tasklist | grep -i "MaaEnd\|cpp-algo\|go-service"` 确认清空。
- 覆盖后**逐字节核对**（拿 zip 里的文件算 sha256 比一遍），别只看时间戳。
- ⚠️ 下 zip 时 GitHub 直连/镜像可能只有 5~10KB/s，193MB 基本下不动。**博士用浏览器手动下更快**。
- 改完**完整重启 MaaEnd.exe**（pipeline JSON 改动不会热重载）。

### 18.3 文件速查

| 内容                     | 位置                                                                                                                                                                                                                    |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **录制规范（先读这个）** | [docs/zh_cn/developers/tasks/seize-delivery-jobs-route-recording.md](docs/zh_cn/developers/tasks/seize-delivery-jobs-route-recording.md)                                                                                |
| **试验园区录制清单**     | [docs/zh_cn/developers/tasks/seize-delivery-jobs-testarea-recording-checklist.md](docs/zh_cn/developers/tasks/seize-delivery-jobs-testarea-recording-checklist.md)                                                      |
| MapNavigator 工具        | `python tools/MapNavigator/main.py` → http://127.0.0.1:8770/ （出 **base px**，`G` 复制坐标，**从仓库根目录启动**）                                                                                                     |
| 取货路线                 | `assets/resource/pipeline/SeizeDeliveryJobs/SeizeDeliveryJobsPost.json`（测试入口 `SeizeDeliveryJobsTestPickupEntry`）                                                                                                  |
| 送货 4 条路线            | `assets/resource/pipeline/SeizeDeliveryJobs/SeizeDeliveryJobsDeliverRoutes.json`（测试入口 `SeizeDeliveryJobsTestDeliver{Observatory,Owl,MaterialResearchInstitute,TechProductionOffice}Entry`，UI 在「地区建设」分组） |
| UI 选项                  | `assets/tasks/SeizeDeliveryJobs.json` 的 `SeizeDeliveryJobsCustomDelivery`                                                                                                                                              |
| Go 分流                  | `agent/go-service/seizedeliveryjobs/departure.go`                                                                                                                                                                       |
| 滑索实现                 | `agent/go-service/maptracker/default/zipline.go`（`chain_max_press` + 1s 发射延迟，博士的修复）                                                                                                                         |
| 索上转向                 | `agent/go-service/maptracker/default/toward.go`（⚠️ 会位移，见规范 §4.4）                                                                                                                                               |
| 坐标换算参数             | `assets/resource/image/MapLocator/maptracker_coordinate_transforms.json`                                                                                                                                                |
| MapTracker 工具          | `python tools/map_tracker/map_tracker_master.py` → http://127.0.0.1:8060/web/ （**从仓库根目录启动**）                                                                                                                  |
