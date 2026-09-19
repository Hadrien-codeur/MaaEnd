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
    const recordedDeparture = [
        [
            537.86,
            1269.57,
        ],
        [
            537.95,
            1268.94,
        ],
        [
            538.37,
            1267.02,
        ],
        [
            538.79,
            1265.18,
        ],
        [
            539.15,
            1263.33,
        ],
        [
            539.55,
            1261.4,
        ],
        [
            540.01,
            1259.53,
        ],
        [
            540.42,
            1257.67,
        ],
        [
            540.76,
            1255.76,
        ],
        [
            541.19,
            1253.86,
        ],
        [
            541.53,
            1251.68,
        ],
        [
            541.58,
            1251.15,
        ],
        [
            540.56,
            1250.9,
        ],
    ];
    const fixedDeparture = fixed.ActionParam.value.fixed_departure_path;
    assert.deepEqual(fixedDeparture, [
        {action: "ZONE", zone_id: "Wuling_Base"},
        ...recordedDeparture,
        {
            action: "RUN",
            target: [
                538.75,
                1250.66,
            ],
            strict_arrival: true,
        },
    ]);
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
    assert.deepEqual(
        synced.destinations.find((item) => item.source_id === destination.id).fixed_departure_path,
        fixedDeparture,
    );
    assert.equal(synced.depots.find((item) => item.source_id === depot.id).fixed_zipline_route, "wuling_city_pickup");
});

test("武陵城接单实测入口复用四终点固定路线且保留正式任务选项", () => {
    const entry = JSON.parse(
        readFileSync(new URL("../../../assets/tasks/FixedWulingSubaiyiDeliveryTest.json", import.meta.url)),
    ).task[0];
    const formal = JSON.parse(readFileSync(new URL("../../../assets/tasks/SeizeDeliveryJobs.json", import.meta.url)))
        .task[0];
    assert.equal(entry.entry, formal.entry);
    assert.deepEqual(entry.option, formal.option);
    for (const id of [
        "deliver_target_map02_lv002_01",
        "deliver_target_map02_lv002_02",
        "deliver_target_map02_lv002_03",
        "deliver_target_map02_lv002_recycle_01",
    ]) {
        const destination = destinations.find((item) => item.id === id);
        assert.ok(destination?.fixedRouteNode);
        assert.equal(
            rows.find((row) => row.Node === destination.fixedRouteNode).ActionParam.value.fixed_zipline_route,
            destination.fixedZiplineRoute,
        );
    }
});

test("武陵三条新路线保留独立录制地面段与已配置的终点朝向，重同步不丢失", () => {
    const source = JSON.parse(readFileSync(new URL("./routes.json", import.meta.url)));
    const catalog = JSON.parse(readFileSync(new URL("../data/delivery_destinations.json", import.meta.url)));
    const synced = buildSyncedRouteConfig(catalog, source);
    for (const [
        suffix,
        routeId,
        firstGroundPoint,
        stance,
        facing,
        departureLength,
    ] of [
        [
            "02",
            "wuling_city_lind",
            [
                473.58,
                1718.96,
            ],
            [
                462.71,
                1713.21,
            ],
            [
                461.93,
                1713.43,
            ],
            10,
        ],
        [
            "03",
            "wuling_city_yushi",
            [
                898.4,
                1407.4,
            ],
            [
                894.71,
                1409.1,
            ],
            [
                894.97,
                1407.6,
            ],
            15,
        ],
        [
            "recycle_01",
            "wuling_city_recycle",
            [
                510.94,
                1652.51,
            ],
            [
                513.33,
                1652.14,
            ],
            null,
            7,
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
        assert.equal(fixed.fixed_departure_path.length, departureLength);
        assert.deepEqual(fixed.fixed_departure_path[1], firstGroundPoint);
        assert.deepEqual(fixed.fixed_departure_path.at(facing ? -2 : -1), {
            action: "RUN",
            target: stance,
            strict_arrival: true,
        });
        if (facing) {
            assert.deepEqual(fixed.fixed_departure_path.at(-1), {action: "HEADING", target: facing});
        }
        const saved = synced.destinations.find((item) => item.source_id === id);
        assert.deepEqual(saved.fixed_approach_path, fixed.fixed_approach_path);
        assert.deepEqual(saved.fixed_departure_path, fixed.fixed_departure_path);
    }
});

test("材料研究所末架下索前朝向保持为 294 度", () => {
    const routes = JSON.parse(
        readFileSync(new URL("../../../assets/data/MapNavigator/fixed_zipline_routes.json", import.meta.url)),
    );
    assert.equal(routes.routes.find((route) => route.id === "wuling_city_lind").dismount_heading, 294);
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
