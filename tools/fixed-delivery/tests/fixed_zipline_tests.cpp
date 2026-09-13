#include <algorithm>
#include <iostream>
#include <stdexcept>

#include "Common/JsoncFile.h"
#include "MapNavigator/fixed_zipline_route.h"

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
        std::cout << "Fixed route parsing and matching checks passed\n";
        return 0;
    }
    catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
