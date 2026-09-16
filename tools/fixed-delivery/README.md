# 固定滑索开发与验证

2026-09-14 最新保存点：**苏白易整段连滑实机通过**。16 架 / 15 跳，首跳左键后 14 次 E，末架确认、自动下索和到终点步行全部完成，任务耗时约 107.2 秒，见 [连滑实机验收记录](../../docs/zh_cn/dev-notes/苏白易连滑实机验收记录.md)。前一轮多等第 15 次提示的问题已修复并验证；保留 [首轮诊断](../../docs/zh_cn/dev-notes/苏白易连滑首轮日志分析.md) 供追溯。

固定逐跳的 [实机记录](../../docs/zh_cn/dev-notes/苏白易固定逐跳实机验收记录.md) 同样保留。2026-09-16 博士已确认苏白易取货送货实测通过，当前进入 [双入口与恢复验收](../../docs/zh_cn/dev-notes/苏白易双入口与恢复验收.md)；装箱自送、持货恢复和其他路线尚未全部验收。

## 配置与执行边界

- 架序数据：`assets/data/MapNavigator/fixed_zipline_routes.json`，保存地图、Level、模板及逐架世界坐标，索引从 0 连续排列。
- 测试任务：`FixedZiplineTest` → `MapNavigatorFixedSubaiyiTest`，Win32-Front，仓储附近开始，走到苏白易终点即停，不取货或交付。
- `MapNavigateAction` 同时需要非空 `fixed_zipline_route`、`zip: true` 和终点 `path`。当前仅支持单段 NAVMESH/RUN 移动提示，可保留经区域核验的首个 ZONE 声明，不接受中途必经动作或跨图；完整架序来自数据文件。
- 匹配以地图、Level、模板及三维坐标为准，容差 0.01 米。所有架子唯一匹配并可用后才规划首架至末架；不按成本截取子链。
- 这是严格固定入口：全局 Never 禁滑、错误配置、缺架、歧义、供电或连接不可用时拒绝移动。固定段失败停止，不直接下索换路或重跑整条路线。普通自动滑索仍使用上游恢复逻辑。以后业务模式的可选降级在业务接入阶段另行实现。
- 生成源在 `tools/pipeline-generate/AutoDelivery/routes.json`；固定 ID 只传给 WithZipline 主路线，不进入普通步行或站位修正节点。当前包含武陵城固定取货与苏白易送货。
- 编辑器尚未支持完整固定参数往返，导入含该参数的文件会明确拒绝，避免静默丢失。地图查看使用 `docs/zh_cn/dev-notes/苏白易架序.preview.json`；实际试跑使用独立任务。

## 连滑区间

`fixed_zipline_routes.json` 的每条路线可配置 `continuous_segments`，元素为含首尾的架子索引，例如 `{"first": 0, "last": 15}`。区间必须顺序排列、不重叠，可共享段末/段首；不配置或空数组时保持普通逐跳。

- 预算 = `last - first - 1`，即区间架数减二；首跳由左键完成。当前苏白易 #0～#15 为左键后 14 次 E，#0～#3 为左键后 2 次 E；两架单跳只需左键，不按 E。区间覆盖的滑索跳数仍为 `last - first`，与 E 预算分开。
- 每段只瞄准首跳并左键发射；途中只调用已有 E 模板的识别/按键节点，不调用位置识别，不重新瞄准下一架。
- 同一提示只消费一次，观察到消失后才允许下一次。按键动作成功才记账，动作失败或停止任务时不继续按键。
- 完成预算并观察最后提示消失后才定位末架。确认末架后跳过本段剩余逐跳航点，再接下一段或下索步行；预算用尽不等同于到达成功。
- 等待新提示、提示消失或末架定位超时均停止并记录阶段。超时沿用原滑索 30 秒诊断边界；每次真实提示消费重置等待计时，不通过定时连按推进。

## 已执行验证（含前序未受影响的检查）

| 检查 | 结果 |
| --- | --- |
| 当前账号快照校验 | 16 架唯一匹配；脚本不证明游戏连线和供电 |
| C++ 生产 Agent | 发现头文件依赖漏编后 clean 完整重建，编译安装成功 |
| C++ 固定配置与计数测试 | 通过：匹配异常、区间越界/重叠、4 架 2 次、16 架 14 次、两架零次 E 与零跳防下溢、持续提示去重、预算用尽、实际运行状态重启清空 |
| 原生 Agent 离线规划 | 8 项通过：独立入口完整 15 跳及每跳落点、段首 E 预算 14、生成业务节点完整链、未知 ID 拒绝、禁滑参数拒绝、必经动作拒绝、错起始区域拒绝、普通步行、普通自动滑索 |
| 配置与导入工具 | 6 项通过（含连滑 Schema）；地图导入原有 17 项为上轮结果 |
| 连滑 Pipeline 合成截图 | 前序 2 项通过（本次未改提示节点）：真实模板有/无提示、只按一次、观察不按键、停止在识别前不发按键 |
| AutoDelivery 生成器 | 前序 20 项通过；本次仅修正 C++ E 预算，生成源未变 |
| `pnpm check` | 通过，6 组资源 |
| Pipeline/Task Schema | 通过 |
| `pnpm test` | 通过，1279 项节点用例 |
| 实机 | 苏白易固定逐跳与整段连滑正常空跑均通过，末架自动下索及终点到达有日志证据；全局禁滑、取消重启、异常输入和真实交付不包含在结论内 |

2026-09-13 节点测试曾首次启动无诊断退出，顺序运行后完成 1279 项；本轮再次顺序运行通过，未修改测试断言。DeliveryJobs 的两项上游历史失败未在此轮修改，不把 AutoDelivery 的 20 项通过说成全部送货生成器通过。

本机安装的 C++ Agent SHA256：`C6A7C8956D9A9F1D4362CF8CE27D920D4AA67E11023D46A5B68934ADAA9FEB44`。二进制、原始快照及 `.cache/fixed-delivery-*.log` 仅保留本机。

## 本机构建注意事项

本机 CMake/Ninja 把 MSVC 中文 `/showIncludes` 前缀探测成乱码，导致修改头文件时相关对象未重编。直接增量编译曾生成混合新旧结构体布局的程序，原生规划回归因此失败；clean 全部对象后完整构建恢复。不要把仅有少量 cpp 重编的成功退出当作结构体修改已生效。头文件变更后先运行下方 clean 命令，再正常构建。该问题仍是本机增量构建限制，未通过修改全局环境或安装语言包处理。

## 复现命令

在新版仓库根目录运行。家里本轮没有可调用的 uv，使用已经安装依赖的虚拟环境；这不等同于重新同步依赖锁文件。公司若有 uv，可以使用对应 `uv run --frozen` 入口。

```powershell
. .\tools\fixed-delivery\Enter-Dev.ps1
cmake --build agent/cpp-algo/build --config RelWithDebInfo --target clean
& .venv/Scripts/python.exe -m tools.setup.build_and_install --cpp-algo
& .venv/Scripts/python.exe tools/fixed-delivery/validate_fixed_routes.py

cmake -S tools/fixed-delivery/tests -B .cache/fixed-delivery-tests -G "Visual Studio 17 2022" -A x64
cmake --build .cache/fixed-delivery-tests --config Release
ctest --test-dir .cache/fixed-delivery-tests -C Release --output-on-failure
& .venv/Scripts/python.exe tools/fixed-delivery/tests/test_fixed_route_tools.py
& .venv/Scripts/python.exe tools/fixed-delivery/tests/test_native_route.py
& .venv/Scripts/python.exe tools/fixed-delivery/tests/test_relay_pipeline.py

node --test tools/pipeline-generate/AutoDelivery/*.test.mjs
# 使用已锁定的本地数据生成，不在验收过程中顺带拉取游戏数据更新。
node tools/pipeline-generate/run-all.mjs AutoDelivery
pnpm check
pnpm test
& .venv/Scripts/python.exe tools/validate_schema.py --resource-dirs assets/resource --exclude-dirs assets/resource/gamedata assets/resource/image assets/resource/model --task-dirs assets/tasks
```

原生规划测试使用空控制器，不连接游戏、不发送输入；需要已安装的新 Agent、导航网格和当前账号快照。它验证规划和失败返回，不能替代 E 提示、上索、取消输入与真实落点的游戏测试。

常用格式化命令仍为 `pnpm format`、`pnpm format:go`；本轮只格式化涉及文件，未改 Go 代码。
