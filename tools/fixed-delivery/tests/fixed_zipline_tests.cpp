#include <algorithm>
#include <iostream>
#include <stdexcept>

#include "Common/JsoncFile.h"
#include "MapNavigator/fixed_zipline_route.h"
#include "MapNavigator/navigation_runtime_state.h"
#include "MapNavigator/zipline_relay_state.h"

namespace
{
void require(bool condition, const char* message)
{
    if (!condition) {
        throw std::runtime_error(message);
    }
}
}

int main(int argc, char** argv)
{
    try {
        require(argc == 2, "expected route file");
        auto source = common::OpenJsoncFile(argv[1]);
        require(source.has_value(), "read route file");
        std::string error;
        const auto route = mapnavigator::ParseFixedZiplineRoute(*source, "wuling_city_subaiyi", error);
        require(route.has_value(), "parse confirmed route");
        require(route->nodes.size() == 16, "confirmed route must have 16 towers");
        require(!route->dismount_heading, "existing routes keep default dismount behavior");
        const auto lind = mapnavigator::ParseFixedZiplineRoute(*source, "wuling_city_lind", error);
        require(lind && lind->dismount_heading == 294.0, "Lind route must face northwest before dismount");
        const auto recycle = mapnavigator::ParseFixedZiplineRoute(*source, "wuling_city_recycle", error);
        require(recycle && recycle->dismount_heading == 101.0, "recycle route must turn east before dismount");
        for (const json::value& invalid_heading : { json::value(-1), json::value(360), json::value("101"), json::value(true) }) {
            auto invalid = *source;
            invalid["routes"][0]["dismount_heading"] = invalid_heading;
            require(!mapnavigator::ParseFixedZiplineRoute(invalid, route->id, error), "invalid dismount heading must fail");
        }
        require(
            route->continuous_segments.size() == 1 && route->continuous_segments[0].first == 0 && route->continuous_segments[0].last == 15,
            "confirmed route is one full continuous segment");
        std::vector<zipline::ZiplineNode> nodes;
        for (const auto& point : route->nodes) {
            nodes.push_back({
                .world_x = point.x,
                .world_y = point.y,
                .world_z = point.z,
                .template_id = route->template_id,
                .level_id = route->level_id,
            });
        }
        auto shuffled = nodes;
        std::reverse(shuffled.begin(), shuffled.end());
        const auto ordered = mapnavigator::MatchFixedZiplineRoute(*route, shuffled, error);
        require(
            ordered && ordered->front().world_x == nodes.front().world_x && ordered->back().world_z == nodes.back().world_z,
            "snapshot order must not change route order");
        auto missing = nodes;
        missing.erase(missing.begin() + 8);
        require(!mapnavigator::MatchFixedZiplineRoute(*route, missing, error), "missing middle tower must fail");
        auto duplicate = nodes;
        duplicate.push_back(nodes[8]);
        require(!mapnavigator::MatchFixedZiplineRoute(*route, duplicate, error), "duplicate snapshot tower must fail");
        auto wrong_level = nodes;
        wrong_level[8].level_id = "another_level";
        require(!mapnavigator::MatchFixedZiplineRoute(*route, wrong_level, error), "wrong level must fail");
        auto wrong_type = nodes;
        wrong_type[8].template_id = "power_pole";
        require(!mapnavigator::MatchFixedZiplineRoute(*route, wrong_type, error), "wrong template must fail");
        auto moved = nodes;
        moved[8].world_y += 1.0;
        require(!mapnavigator::MatchFixedZiplineRoute(*route, moved, error), "wrong height must fail");
        moved = nodes;
        moved[8].world_x += 0.005;
        require(mapnavigator::MatchFixedZiplineRoute(*route, moved, error).has_value(), "rounding tolerance should match");
        moved.push_back(nodes[8]);
        require(!mapnavigator::MatchFixedZiplineRoute(*route, moved, error), "nearby candidates must be ambiguous");
        require(!mapnavigator::ParseFixedZiplineRoute(*source, "missing", error), "unknown route must fail");
        auto malformed = *source;
        malformed["routes"] = json::object {};
        require(!mapnavigator::ParseFixedZiplineRoute(malformed, route->id, error), "wrong routes type must fail");
        malformed = *source;
        malformed["version"] = 2;
        require(!mapnavigator::ParseFixedZiplineRoute(malformed, route->id, error), "unknown version must fail");
        malformed = *source;
        malformed["routes"][0]["nodes"][0] = json::object { { "index", 0 } };
        require(!mapnavigator::ParseFixedZiplineRoute(malformed, route->id, error), "missing coordinates must fail");
        malformed = *source;
        malformed["routes"][0]["nodes"][1]["index"] = 8;
        require(!mapnavigator::ParseFixedZiplineRoute(malformed, route->id, error), "bad index must fail");
        malformed = *source;
        malformed["routes"][0]["nodes"][1] = malformed["routes"][0]["nodes"][0];
        malformed["routes"][0]["nodes"][1]["index"] = 1;
        require(!mapnavigator::ParseFixedZiplineRoute(malformed, route->id, error), "repeated route tower must fail");
        malformed = *source;
        malformed["routes"] = json::array { (*source)["routes"][0], (*source)["routes"][0] };
        require(!mapnavigator::ParseFixedZiplineRoute(malformed, route->id, error), "duplicate route id must fail");
        malformed = *source;
        malformed["routes"][0]["continuous_segments"] = json::array {};
        require(
            mapnavigator::ParseFixedZiplineRoute(malformed, route->id, error)->continuous_segments.empty(),
            "empty segments preserve single-hop mode");
        for (const auto& segments : {
                 json::array { json::object { { "first", 0 }, { "last", 16 } } },
                 json::array { json::object { { "first", 3 }, { "last", 3 } } },
                 json::array { json::object { { "first", 5 }, { "last", 2 } } },
                 json::array { json::object { { "first", 0 }, { "last", 4 } }, json::object { { "first", 3 }, { "last", 8 } } },
             }) {
            malformed = *source;
            malformed["routes"][0]["continuous_segments"] = segments;
            require(!mapnavigator::ParseFixedZiplineRoute(malformed, route->id, error), "invalid or overlapping segment must fail");
        }
        malformed = *source;
        malformed["routes"][0]["continuous_segments"] =
            json::array { json::object { { "first", 0 }, { "last", 3 } }, json::object { { "first", 3 }, { "last", 15 } } };
        const auto split_route = mapnavigator::ParseFixedZiplineRoute(malformed, route->id, error);
        require(
            split_route
                && mapnavigator::ZiplineRelayPressCount(
                       split_route->continuous_segments[0].last - split_route->continuous_segments[0].first)
                       == 2,
            "four towers require two E presses after launch");
        require(mapnavigator::ZiplineRelayPressCount(0) == 0, "no relay must not underflow");
        require(mapnavigator::ZiplineRelayPressCount(1) == 0, "two towers only need the initial mouse launch");
        require(mapnavigator::ZiplineRelayPressCount(15) == 14, "sixteen towers require fourteen E presses");
        for (const size_t presses : { mapnavigator::ZiplineRelayPressCount(3), mapnavigator::ZiplineRelayPressCount(15) }) {
            mapnavigator::ZiplineRelayCounter counter { .required = presses };
            require(!counter.readyForLanding(), "left mouse launch does not consume E budget");
            for (size_t index = 0; index < presses; ++index) {
                require(counter.canPress() && counter.commitPress(), "each new prompt permits one E press");
                for (int frame = 0; frame < 20; ++frame) {
                    counter.observe(true);
                    require(!counter.canPress() && !counter.commitPress(), "persistent prompt must not repeat E");
                }
                require(!counter.readyForLanding(), "last prompt must disappear before endpoint verification");
                counter.observe(false);
                require(counter.pressed == index + 1, "only successful press consumes budget");
            }
            require(counter.readyForLanding() && !counter.canPress(), "budget exhaustion disallows extra prompts");
            counter.observe(true);
            require(!counter.commitPress(), "terminal prompt must never issue another E");
        }
        mapnavigator::NavigationRuntimeState runtime;
        runtime.semantic.zipline_relay = { .required = 14, .pressed = 7, .awaiting_clear = true };
        runtime.semantic.zipline_relay_end_index = 19;
        runtime.semantic.zipline_mounted = true;
        runtime.BeginNavigation(std::chrono::steady_clock::now());
        require(
            runtime.semantic.zipline_relay.required == 0 && runtime.semantic.zipline_relay.pressed == 0
                && !runtime.semantic.zipline_relay.awaiting_clear && runtime.semantic.zipline_relay_end_index == 0
                && !runtime.semantic.zipline_mounted,
            "new navigation must not inherit a cancelled relay");
        std::cout << "Fixed route parsing and matching checks passed\n";
        return 0;
    }
    catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
