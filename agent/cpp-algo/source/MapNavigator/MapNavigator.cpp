#include "MapNavigator.h"

#include <cstring>

#include <MaaUtils/Logger.h>

#include "navi_controller.h"
#include "navi_param_parser.h"
#include "zipline_preference.h"

namespace mapnavigator
{

namespace
{

constexpr MaaBool kMaaTrue = 1;
constexpr MaaBool kMaaFalse = 0;

} // namespace

MaaBool MAA_CALL MapNavigateActionRun(
    MaaContext* context,
    [[maybe_unused]] MaaTaskId task_id,
    [[maybe_unused]] const char* node_name,
    [[maybe_unused]] const char* custom_action_name,
    const char* custom_action_param,
    [[maybe_unused]] MaaRecoId reco_id,
    [[maybe_unused]] const MaaRect* box,
    [[maybe_unused]] void* trans_arg)
{
    if (custom_action_param == nullptr || std::strlen(custom_action_param) == 0) {
        return kMaaTrue;
    }

    LogInfo << "MapNavigateActionRun param string: " << custom_action_param;

    NaviParam param;
    if (!TryParseNaviParam(custom_action_param, param)) {
        return kMaaFalse;
    }
    LogInfo << "Navigation parameters parsed." << VAR(param.path.size()) << VAR(param.fixed_approach_path.size())
            << VAR(param.fixed_departure_path.size());

    if (param.path.empty()) {
        return kMaaTrue;
    }

    // 文字表指了节点的交互点在这里解析: pipeline 已经问得到, 而且还没开始走。
    ResolveInteractTextNodes(context, param);
    LogInfo << "Navigation interaction text resolved; reading zipline preference.";
    param.zipline_enabled = ResolveZiplineEnabled(context, param.zipline_enabled);
    LogInfo << "Navigation zipline preference resolved." << VAR(param.zipline_enabled);
    if (param.zipline_enabled) {
        LogInfo << "Navigation reading zipline account identity.";
        param.zipline_account_id = ResolveZiplineAccountId(context);
        LogInfo << "Navigation zipline account resolution completed.";
    }

    // Planning runs on the navmesh base mesh, so normalize live fixes onto the navmesh base-pixel
    // frame using the navmesh's own baked tier affine.
    param.normalize_position_via_navmesh = true;

    NaviController controller(context);
    LogInfo << "Navigation entering controller.";
    const bool arrived = controller.Navigate(param);
    NoticeZiplineOutcome(context);
    return arrived ? kMaaTrue : kMaaFalse;
}

} // namespace mapnavigator
