import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {depots, destinations, readFixedZiplineRoute} from "./model.mjs";
import rows, {buildRows} from "./routes-data.mjs";
import {buildSyncedRouteConfig} from "./sync-routes.mjs";

test("苏白易固定路线重新生成后保留，普通和站位修正入口不改变", () => {
    const destination = destinations.find((item) => item.id === "deliver_target_map02_lv002_01");
    const fixed = rows.find((row) => row.Node === destination.fixedRouteNode);
    assert.equal(fixed.ActionParam.value.fixed_zipline_route, "wuling_city_subaiyi");
    const depot = depots.find((item) => item.id === "domain_2_lv002_depot_1");
    const fixedDepot = rows.find((row) => row.Node === depot.fixedRouteNode);
    assert.equal(fixedDepot.ActionParam.value.fixed_zipline_route, "wuling_city_pickup");
    const fixedNodes = new Set(
        [
            ...depots,
            ...destinations,
        ]
            .map((item) => item.fixedRouteNode)
            .filter(Boolean),
    );
    for (const row of rows.filter((item) => !fixedNodes.has(item.Node))) {
        assert.equal(row.ActionParam.value.fixed_zipline_route, undefined);
        assert.equal(row.ActionParam.value.fixed_approach_path, undefined);
        assert.equal(row.ActionParam.value.fixed_departure_path, undefined);
    }
    const source = JSON.parse(readFileSync(new URL("./routes.json", import.meta.url)));
    const catalog = JSON.parse(readFileSync(new URL("../data/delivery_destinations.json", import.meta.url)));
    const synced = buildSyncedRouteConfig(catalog, source);
    assert.equal(
        synced.destinations.find((item) => item.source_id === destination.id).fixed_zipline_route,
        "wuling_city_subaiyi",
    );
    assert.equal(synced.depots.find((item) => item.source_id === depot.id).fixed_zipline_route, "wuling_city_pickup");
});

test("武陵三条新路线保留独立录制地面段与终点朝向，重同步不丢失", () => {
    const source = JSON.parse(readFileSync(new URL("./routes.json", import.meta.url)));
    const catalog = JSON.parse(readFileSync(new URL("../data/delivery_destinations.json", import.meta.url)));
    const synced = buildSyncedRouteConfig(catalog, source);
    for (const [
        suffix,
        routeId,
        stance,
        facing,
    ] of [
        [
            "02",
            "wuling_city_lind",
            [
                462.78,
                1712.92,
            ],
            [
                462.06,
                1712.79,
            ],
        ],
        [
            "03",
            "wuling_city_yushi",
            [
                894.71,
                1409.1,
            ],
            [
                894.97,
                1407.6,
            ],
        ],
        [
            "recycle_01",
            "wuling_city_recycle",
            [
                514.06,
                1651.68,
            ],
            [
                513.39,
                1650.67,
            ],
        ],
    ]) {
        const id = `deliver_target_map02_lv002_${suffix}`;
        const destination = destinations.find((item) => item.id === id);
        const fixed = rows.find((row) => row.Node === destination.fixedRouteNode).ActionParam.value;
        assert.equal(fixed.fixed_zipline_route, routeId);
        assert.equal(fixed.fixed_approach_path.length, 8);
        assert.deepEqual(
            fixed.fixed_approach_path.at(-1),
            [
                961.28,
                1831.17,
            ],
        );
        assert.deepEqual(fixed.fixed_departure_path.at(-2), {action: "RUN", target: stance, strict_arrival: true});
        assert.deepEqual(fixed.fixed_departure_path.at(-1), {action: "HEADING", target: facing});
        const saved = synced.destinations.find((item) => item.source_id === id);
        assert.deepEqual(saved.fixed_approach_path, fixed.fixed_approach_path);
        assert.deepEqual(saved.fixed_departure_path, fixed.fixed_departure_path);
    }
});

test("自动滑索与固定滑索节点独立，固定节点保留相同地面路径", () => {
    for (const item of [
        ...depots,
        ...destinations,
    ].filter((item) => item.fixedRouteNode)) {
        const automatic = rows.find((row) => row.Node === item.zipRouteNode).ActionParam.value;
        const fixed = rows.find((row) => row.Node === item.fixedRouteNode).ActionParam.value;
        assert.equal(automatic.zip, true);
        assert.equal(automatic.fixed_zipline_route, undefined);
        assert.deepEqual(fixed.path, automatic.path);
        assert.equal(fixed.fixed_zipline_route, item.fixedZiplineRoute);
    }
});

test("固定配置拒绝未知 ID、空 ID 和 walk_only 冲突", () => {
    for (const id of [
        "unknown",
        "",
        "  ",
        42,
    ]) {
        assert.throws(() => readFixedZiplineRoute(id, false, "test"));
    }
    assert.throws(() => readFixedZiplineRoute("wuling_city_subaiyi", true, "test"));
    assert.equal(readFixedZiplineRoute(undefined, false, "test"), undefined);
});

test("关闭滑索的生成节点不会携带固定架序", () => {
    const result = buildRows("test", "test", "test", [], "walk", "zip", true, "wuling_city_subaiyi");
    for (const row of result) {
        assert.equal(row.ActionParam.value.zip, false);
        assert.equal(row.ActionParam.value.fixed_zipline_route, undefined);
    }
});
