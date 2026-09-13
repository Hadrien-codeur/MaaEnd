#pragma once

#include <cstddef>
#include <optional>

#include "semantic_nodes.h"

namespace mapnavigator
{

namespace semantic_nodes
{

// 链上的一跳：不在架子上就先认提示站上去，再把镜头对准落点，按左键起滑。
// 起滑之后这一跳就交给 WaitZipline 相位了。
Result StartZiplineHop(
    const Context& ctx,
    const Waypoint& waypoint,
    double actual_distance,
    const std::optional<size_t>& arrived_absolute_node_idx);

// 连滑段途中只识别 E 提示，预算完成后确认段末；普通单跳仍逐架确认后重新瞄准。
Result TickZiplineRide(const Context& ctx);

// 滑索走不成时的退路：还站在架子上就先下来，再丢掉这条链剩下的每一跳。状态机随后等待稳定
// 定位，从剩余路线中第一个实际可达的点重新接入；接不回去就明确失败，不沿用从预期落点生成的旧路线。
Result AbandonZipline(const Context& ctx, const char* reason, const char* detail);

} // namespace semantic_nodes

} // namespace mapnavigator
