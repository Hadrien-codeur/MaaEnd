#pragma once

#include <cmath>
#include <optional>
#include <string>
#include <vector>

#include <meojson/json.hpp>

#include "../Zipline/ZiplineFrames.h"

namespace mapnavigator
{

// 森空岛坐标以米计；沿用已试跑配置的 1 cm 匹配容差，只容忍序列化舍入。
constexpr double kFixedZiplineMatchMeters = 0.01;

struct FixedZiplinePoint
{
    size_t index = 0;
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;

    MEO_JSONIZATION(index, x, y, z)
};

struct FixedZiplineRoute
{
    std::string id;
    std::string map_id;
    std::string level_id;
    std::string template_id;
    std::vector<FixedZiplinePoint> nodes;

    struct ContinuousSegment
    {
        size_t first = 0;
        size_t last = 0;

        MEO_JSONIZATION(first, last)
    };

    std::vector<ContinuousSegment> continuous_segments;

    MEO_JSONIZATION(id, map_id, level_id, template_id, nodes, MEO_OPT continuous_segments)
};

inline std::optional<FixedZiplineRoute> ParseFixedZiplineRoute(const json::value& value, const std::string& id, std::string& error)
{
    error.clear();
    const auto version = value.find<int>("version");
    const auto routes = value.find<json::array>("routes");
    if (!version || *version != 1 || !routes) {
        error = "invalid fixed route file: expected version 1 and routes array";
        return std::nullopt;
    }
    std::optional<FixedZiplineRoute> selected;
    for (const auto& entry : *routes) {
        if (entry.get("id", std::string {}) != id) {
            continue;
        }
        FixedZiplineRoute route;
        if (selected || !route.from_json(entry) || route.id.empty() || route.map_id.empty() || route.level_id.empty()
            || route.template_id.empty() || route.nodes.size() < 2) {
            error = "invalid or duplicate fixed route definition";
            return std::nullopt;
        }
        for (size_t i = 0; i < route.nodes.size(); ++i) {
            const auto& point = route.nodes[i];
            if (point.index != i || !std::isfinite(point.x) || !std::isfinite(point.y) || !std::isfinite(point.z)) {
                error = "invalid coordinate or nonsequential fixed route index";
                return std::nullopt;
            }
            for (size_t j = 0; j < i; ++j) {
                const auto& previous = route.nodes[j];
                if (std::hypot(point.x - previous.x, point.y - previous.y, point.z - previous.z) <= kFixedZiplineMatchMeters) {
                    error = "fixed route repeats a tower";
                    return std::nullopt;
                }
            }
        }
        size_t previous_end = 0;
        for (const auto& segment : route.continuous_segments) {
            if (segment.first < previous_end || segment.first >= segment.last || segment.last >= route.nodes.size()) {
                error = "continuous segments must be ordered, nonoverlapping tower intervals";
                return std::nullopt;
            }
            previous_end = segment.last;
        }
        selected = std::move(route);
    }
    if (!selected) {
        error = "fixed route id not found";
    }
    return selected;
}

// candidates 已经过地图与供电筛选；每架必须唯一匹配，且不能复用同一设施。
inline std::optional<std::vector<zipline::ZiplineNode>>
    MatchFixedZiplineRoute(const FixedZiplineRoute& route, const std::vector<zipline::ZiplineNode>& candidates, std::string& error)
{
    error.clear();
    std::vector<zipline::ZiplineNode> ordered;
    std::vector<bool> used(candidates.size(), false);
    for (const auto& point : route.nodes) {
        size_t count = 0;
        size_t matched = 0;
        for (size_t i = 0; i < candidates.size(); ++i) {
            const auto& node = candidates[i];
            if (node.level_id == route.level_id && node.template_id == route.template_id
                && std::hypot(node.world_x - point.x, node.world_y - point.y, node.world_z - point.z) <= kFixedZiplineMatchMeters) {
                ++count;
                matched = i;
            }
        }
        if (count != 1 || used[matched]) {
            error = "fixed tower #" + std::to_string(point.index) + (count == 0 ? " missing or unpowered" : " ambiguous or reused");
            return std::nullopt;
        }
        used[matched] = true;
        ordered.push_back(candidates[matched]);
    }
    return ordered;
}

} // namespace mapnavigator
