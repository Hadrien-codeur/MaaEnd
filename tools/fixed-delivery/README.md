# 固定滑索开发与验证

2026-09-13：当前苏白易为 **16 架、15 跳**。上一轮独立空跑成功；本轮补强后待博士再空跑一轮，不要求连续三次。连滑段按路线定制，分段待确认；真实交付、双入口及其他路线暂缓。

## 配置与执行边界

- 架序数据：`assets/data/MapNavigator/fixed_zipline_routes.json`，保存地图、Level、模板及逐架世界坐标，索引从 0 连续排列。
- 测试任务：`FixedZiplineTest` → `MapNavigatorFixedSubaiyiTest`，Win32-Front，仓储附近开始，走到苏白易终点即停，不取货或交付。
- `MapNavigateAction` 同时需要非空 `fixed_zipline_route`、`zip: true` 和终点 `path`。当前仅支持单段 NAVMESH/RUN 移动提示，可保留经区域核验的首个 ZONE 声明，不接受中途必经动作或跨图；完整架序来自数据文件。
- 匹配以地图、Level、模板及三维坐标为准，容差 0.01 米。所有架子唯一匹配并可用后才规划首架至末架；不按成本截取子链。
- 这是严格固定入口：全局 Never 禁滑、错误配置、缺架、歧义、供电或连接不可用时拒绝移动。固定段失败停止，不直接下索换路或重跑整条路线。普通自动滑索仍使用上游恢复逻辑。以后业务模式的可选降级在业务接入阶段另行实现。
- 生成源在 `tools/pipeline-generate/AutoDelivery/routes.json`；固定 ID 只传给 WithZipline 主路线，不进入普通步行或站位修正节点。现有苏白易业务接线保留，但不视为真实业务验收。
- 编辑器尚未支持完整固定参数往返，导入含该参数的文件会明确拒绝，避免静默丢失。地图查看使用 `docs/zh_cn/dev-notes/苏白易架序.preview.json`；实际试跑使用独立任务。

## 本轮已执行验证

| 检查 | 结果 |
| --- | --- |
| 当前账号快照校验 | 16 架唯一匹配；脚本不证明游戏连线和供电 |
| C++ 生产 Agent | MSVC 本地编译安装成功 |
| C++ 固定配置局部测试 | 通过：乱序快照、缺中间架、重复/近邻歧义、错层、错类型、高度、坏字段、重复 ID 等 |
| 原生 Agent 离线规划 | 8 项通过：独立入口完整 15 跳及每跳落点、生成业务节点完整链、未知 ID 拒绝、禁滑参数拒绝、必经动作拒绝、错起始区域拒绝、普通步行、普通自动滑索 |
| 配置与导入工具 | 5 项通过；地图导入原有 17 项通过 |
| AutoDelivery 生成器 | 20 项通过，重新生成仍保留固定 ID |
| `pnpm check` | 通过，6 组资源 |
| Pipeline/Task Schema | 通过 |
| `pnpm test` | 通过，1279 项节点用例 |
| 本轮实机 | 待博士再空跑一轮；真实全局禁滑、取消重启和异常输入的实机行为尚未验收 |

节点测试首次启动未进入测试且无诊断输出，顺序重新运行后完成全部 1279 项；未修改测试断言。DeliveryJobs 的两项上游历史失败未在此轮修改，不把 AutoDelivery 的 20 项通过说成全部送货生成器通过。

本机安装的 C++ Agent SHA256：`D29138ECC39095053527374F52300212610F41A5072056158DFD115D7A5B33E9`。二进制、原始快照及 `.cache/fixed-delivery-*.log` 仅保留本机。

## 复现命令

在新版仓库根目录运行。家里本轮没有可调用的 uv，使用已经安装依赖的虚拟环境；这不等同于重新同步依赖锁文件。公司若有 uv，可以使用对应 `uv run --frozen` 入口。

```powershell
. .\tools\fixed-delivery\Enter-Dev.ps1
& .venv/Scripts/python.exe -m tools.setup.build_and_install --cpp-algo
& .venv/Scripts/python.exe tools/fixed-delivery/validate_fixed_routes.py

cmake -S tools/fixed-delivery/tests -B .cache/fixed-delivery-tests -G "Visual Studio 17 2022" -A x64
cmake --build .cache/fixed-delivery-tests --config Release
ctest --test-dir .cache/fixed-delivery-tests -C Release --output-on-failure
& .venv/Scripts/python.exe tools/fixed-delivery/tests/test_fixed_route_tools.py
& .venv/Scripts/python.exe tools/fixed-delivery/tests/test_native_route.py

node --test tools/pipeline-generate/AutoDelivery/*.test.mjs
# 使用已锁定的本地数据生成，不在验收过程中顺带拉取游戏数据更新。
node tools/pipeline-generate/run-all.mjs AutoDelivery
pnpm check
pnpm test
& .venv/Scripts/python.exe tools/validate_schema.py --resource-dirs assets/resource --exclude-dirs assets/resource/gamedata assets/resource/image assets/resource/model --task-dirs assets/tasks
```

原生规划测试使用空控制器，不连接游戏、不发送输入；需要已安装的新 Agent、导航网格和当前账号快照。它验证规划和失败返回，不能替代 E 提示、上索、取消输入与真实落点的游戏测试。

常用格式化命令仍为 `pnpm format`、`pnpm format:go`；本轮只格式化涉及文件，未改 Go 代码。
