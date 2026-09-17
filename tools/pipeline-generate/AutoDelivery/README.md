# AutoDelivery 路线生成器

私人固定路线扩展：`routes.json` 可声明 `fixed_zipline_route`，对应 `assets/data/MapNavigator/fixed_zipline_routes.json` 中唯一的 ID。生成器额外生成独立 `WithFixedZipline` 主路线，并在运行时目录中写入 `fixed_route_node`。普通 `WithZipline`、步行与站位修正节点不携带固定 ID；未知 ID、空 ID 和 `walk_only: true` 冲突会报错。抢单与装箱自送通过 `attach.fixed_zipline` 显式选择固定路线，默认关闭，未配置终点保持原自动规划。当前覆盖武陵城取货、苏白易、材料研究所、观测站和猫头鹰送货。三条新终点可在源配置中声明 `fixed_approach_path` / `fixed_departure_path`，仅传入独立固定节点，逐点保留录制地面段和离索后的最终 HEADING；固定数据中的 `dismount_heading` 在末架确认后、下索前生效。苏白易既有取货送货结果保持通过；博士对本次新路线实测反馈滑索段正常、交付步行段有问题，留待下次修复。测试目的地覆盖未逐条说明，完整交付闭环尚未验收。详见 [固定路线验证](../../fixed-delivery/README.md)。

`tools/pipeline-generate/data/delivery_destinations.json` 是 zmdmap 数据 CI 生成并由 `fetch:zmdmap` 下载的仓储/终点目录；本目录的 `routes.json` 参考 EnvironmentMonitoring 的 metadata-only 维护方式，自动同步全部仓储和终点的检索元数据，并仅在需要覆盖自动 `NAVMESH` 目标时保存实测路线。`tools/schema/auto_delivery_routes.schema.json` 为其提供 IDE 校验。两者共同生成：

- `assets/resource/pipeline/AutoDelivery/Routes/{RouteFileId}.json`：按仓储节点分组保存可直接试跑的 `AutoDeliveryRoute...` 节点，并为主路线生成允许滑索的变体；文件名取自仓储英文名（如 `OriginLodespring.json`），终点路线的 `desc` 会注明起点仓储节点；
- `assets/resource/pipeline/AutoDelivery/RecycleBinAreas.json`：按区域生成资源回收站任务的二次判定入口；`AutoDeliveryRecognizeDestination` 发现同一地图的同一区域存在多个回收站后开始追踪或打开任务地图，并依次检查该区域的全部候选节点；
- `assets/resource/pipeline/AutoDelivery/RecycleBinCandidates.json`：为每个资源回收站单独生成 `MapFind` 候选节点，使用数据源中的 `u/v` 坐标检查 `RecycleBin` 图标，并把命中的精确终点交给既有路线分发节点；
- `assets/data/AutoDelivery/catalog.json`：Go Service 运行时 OCR 匹配目录，只包含文本、归属关系与对应的生成节点名，不再包含坐标或路径。

运行：

```powershell
pnpm generate:AutoDelivery
```

完整送货业务调用方仍只进入 `AutoDelivery`。生成的 `AutoDeliveryRoute...` 节点是公开的单路线测试入口，可在节点测试工具中单独运行；正常流程由 Go Service 识别当前仓储/终点后，通过固定 `SubTask` 分发节点动态调用。

运行生成命令时，`sync-routes.mjs` 会按 `source_id` 刷新仓储的 `name` 以及终点的 `name` / `depot_id`，为游戏数据中的新增项补充 metadata-only 条目，并保留已有的人工字段。仓储和终点都支持 `description` / `path` / `retry_path` / `walk_only`；`departure_path` 仅用于仓储，并会拼接到该仓储所有终点主路线之前。所有仓储和送货目标默认还会用自动两点接近路线生成 retry 节点，显式 `retry_path` 可覆盖其站位修正路径。

需要完整保留录制路径、禁止全局滑索规划跳过作者路点时，在对应仓储或终点条目上设置 `"walk_only": true`。生成器仍会保留普通节点和 `WithZipline` 节点名，但两个节点都会使用 `"zip": false`；因此用户全局启用滑索时，该条路线仍严格按作者路径步行执行。`required: true` 只用于标记启用滑索规划时的必经点，不等价于整条路线仅步行。

修改 `routes.json` 时只使用 MapNavigator 工具实测得到的路径。普通可达目标仅保留同步出的元数据：仓储节点和资源回收站会在终点的 yaw 正方向 8 米处生成一个 `required: true` 的 `NAVMESH` 必经点，再前往原始坐标，保证从交互正面接近；普通收货 NPC 仍只生成原始坐标的单个 `NAVMESH` 点。跨层、断网格、交互或需要站位修正的路线才填写对应的路径覆盖，人工 `path` 不会自动插入接近点。不要为了补齐字段而复制默认坐标。
