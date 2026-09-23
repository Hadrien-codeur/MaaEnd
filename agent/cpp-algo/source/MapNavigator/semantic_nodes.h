#pragma once

#include "action_executor.h"
#include "navigation_runtime_state.h"
#include "navigation_session.h"
struct MaaContext;

namespace mapnavigator
{

class ActionWrapper;
class MotionController;
class PositionProvider;

namespace semantic_nodes
{

struct Context
{
    ActionWrapper* action_wrapper = nullptr;
    PositionProvider* position_provider = nullptr;
    NavigationSession* session = nullptr;
    MotionController* motion_controller = nullptr;
    ActionExecutor* action_executor = nullptr;
    NaviPosition* position = nullptr;
    NavigationRuntimeState* runtime_state = nullptr;
    MaaContext* maa_context = nullptr;
    // Immutable fact for the current navigation request. This must come from NaviParam,
    // not from mutable recovery state, because only delivery routes with an authored
    // fixed departure path may rejoin that path after landing.
    bool fixed_departure_path_available = false;
};

struct Result
{
    bool consumed = false;
    bool stay_in_current_tick = false;
    bool request_failure = false;
    bool changed_zone = false;
    const char* failure_reason = "";
    const char* failure_log_message = "";
};

Result TickSemanticFlow(const Context& ctx, NaviPhase phase);
Result ConsumeInlineSemantics(const Context& ctx);
Result HandleArrival(const Context& ctx, const Waypoint& waypoint, double actual_distance);

} // namespace semantic_nodes

} // namespace mapnavigator
