# 固定滑索更新与验证

已验收基线为 `de4b06eb`；本轮更新目标锁定 `ae43a184`。完整计划与实测边界见 [接力记录](../../docs/zh_cn/dev-notes/新版固定滑索送货接力记录.md) 和 [更新方案](../../docs/zh_cn/dev-notes/新版固定滑索版本兼容与自动接入方案.md)。

## 冻结与更新

先用 `freeze_install.py --source <安装目录> --output <源仓库/.cache/新快照目录> --repo <源仓库> --upstream <基线SHA>` 复制可用安装，再用 `--verify <快照目录>` 验证。资源联接、硬链接转为独立文件；debug/record 中的设施与账号盐保留，原始日志、缓存、WebView2 临时数据不纳入。配置可能包含账号信息，因此快照及完整清单只留本机，不提交。

从干净的已验收适配源码工作树运行：

```powershell
. .\tools\fixed-delivery\Enter-Dev.ps1
python tools/fixed-delivery/stage_update.py --target <已审阅的上游完整SHA>
```

脚本显式 fetch `origin/v2`，验证目标属于此次获取的分支，再在共享仓库 `.cache` 下新建命名候选，将上游合入但不提交。失败停止，冲突现场保留，报告位于候选 `.cache/upstream-update.json`；不会自动删除工作树、构建或切换安装。Git 网络参数沿用当前终端/仓库配置；本机若依赖系统代理，可只在当前终端设置 `HTTPS_PROXY`，不更改全局 Git 设置。

## 验证入口

```powershell
python -m unittest discover -s tools/fixed-delivery/tests -p "test_*.py"
python tools/fixed-delivery/check_compatibility.py --json
go -C agent/go-service test ./autodelivery
ctest --test-dir .cache/cpp-build-utf8 --output-on-failure
```

兼容检查覆盖仓储取货与七终点的配置、实际生成节点、独立地面路径及普通/站位修正节点隔离。它不替代 Go/C++ 行为测试或实机验收。原生目标通过 `-DMAAEND_BUILD_ZIPLINE_TESTS=ON` 开启；首次构建和依赖设置参考项目开发文档。

MSVC 先调用 `vcvars64.bat`，再 `chcp 65001` 配置构建，并检查 Ninja 头文件依赖不为空。不可复用历史依赖失效的构建缓存。

资源、Schema、生成器与节点检查按更新方案执行：`pnpm format`、`pnpm format:go`、`pnpm check`、`pnpm test`。只格式化本次涉及文件；记录缺图跳过，不把测试退出成功当成七路线实机通过。

## 完整候选门槛

在独立候选构建并安装两个 Agent 后，提交源码，再运行 `.venv/Scripts/python.exe tools/fixed-delivery/validate_update.py --upstream <完整SHA> --native`。它依次执行工具/生成器/Go/C++/Schema/资源/节点及生产 Agent 离线回放检查，任何失败均停止。报告在 `.cache/fixed-delivery-validation/report.json`，通过状态仅为 `ready_for_gameplay`，不会自动切换安装。

单独跑资源与节点检查使用 `pnpm check tools/fixed-delivery/maatools.config.mts`、`pnpm test tools/fixed-delivery/maatools.config.mts`。固定版本为本次生产依赖 MaaFramework 5.13.0；不在候选验收时跟随 latest 漂移。

`replay_routes.py` 依赖候选安装自己的设施快照及导航数据，不应放进无账号数据的公共 CI。它读取 `install/debug/record`，所有日志保存在候选本机 `.cache`，禁止提交。正式业务测试及回滚顺序见 [本次验收表](../../docs/zh_cn/dev-notes/固定滑索20260927更新验收.md)。
