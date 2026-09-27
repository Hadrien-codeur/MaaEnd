import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {depots, destinations, runtimeCatalog} from "./model.mjs";
import rows from "./routes-data.mjs";
import {buildSyncedRouteConfig} from "./sync-routes.mjs";

const read = (relative) => JSON.parse(readFileSync(new URL(relative, import.meta.url), "utf8"));
const contract = read("../../fixed-delivery/compatibility.json");
const source = read("./routes.json");
const fixedRoutes = read("../../../assets/data/MapNavigator/fixed_zipline_routes.json");

test("pickup and seven destinations retain authored fixed paths while ordinary routes stay independent", () => {
    const expected = {...contract.delivery_routes.depots, ...contract.delivery_routes.destinations};
    assert.equal(Object.keys(expected).length, 8);
    for (const [
        id,
        route,
    ] of Object.entries(expected)) {
        const item = [
            ...depots,
            ...destinations,
        ].find((item) => item.id === id);
        const original = [
            ...source.depots,
            ...source.destinations,
        ].find((item) => item.source_id === id);
        assert.equal(item.fixedRouteNode, route.fixed_route_node);
        const fixed = rows.find((row) => row.Node === item.fixedRouteNode).ActionParam.value;
        assert.equal(fixed.fixed_zipline_route, route.fixed_zipline_route);
        assert.equal(fixed.zip, true);
        assert.deepEqual(fixed.fixed_approach_path, original.fixed_approach_path);
        assert.deepEqual(fixed.fixed_departure_path, original.fixed_departure_path);
        for (const name of [
            item.routeNode,
            item.zipRouteNode,
            item.retryRouteNode,
        ].filter(Boolean)) {
            const params = rows.find((row) => row.Node === name).ActionParam.value;
            assert.ok(Object.keys(params).every((key) => !key.startsWith("fixed_")));
        }
    }
    assert.deepEqual(read("../../../assets/data/AutoDelivery/catalog.json"), runtimeCatalog);
});

test("upstream zipline-only restriction survives the fixed overlay and generation", () => {
    const pei = destinations.find((item) => item.id === "deliver_target_map02_lv005_02");
    assert.equal(pei.ziplineOnly, true);
    assert.equal(pei.fixedZiplineRoute, "test_area_pei");
    assert.equal(runtimeCatalog.destinations.find((item) => item.id === pei.id).zipline_only, true);
    for (const name of [
        pei.routeNode,
        pei.zipRouteNode,
        pei.fixedRouteNode,
    ]) {
        assert.equal(rows.find((row) => row.Node === name).ActionParam.value.zip, true);
    }
});

test("syncing upstream catalog preserves fixed-only overlay fields", () => {
    const gameData = read("../data/delivery_destinations.json");
    const synced = buildSyncedRouteConfig(gameData, source);
    for (const section of [
        "depots",
        "destinations",
    ]) {
        for (const original of source[section].filter((item) => item.fixed_zipline_route)) {
            const saved = synced[section].find((item) => item.source_id === original.source_id);
            for (const key of [
                "fixed_zipline_route",
                "fixed_approach_path",
                "fixed_departure_path",
                "zipline_only",
            ]) {
                assert.deepEqual(saved[key], original[key], `${original.source_id}.${key}`);
            }
        }
    }
});

test("confirmed relay budgets and final headings survive updates", () => {
    const expected = {
        wuling_city_subaiyi: {presses: [14]},
        wuling_city_recycle: {
            presses: [
                8,
                1,
            ],
            heading: 101,
        },
        wuling_city_lind: {presses: [9], heading: 294},
        test_area_pei: {presses: [4], heading: 323},
        test_area_ahe: {presses: [4], heading: 343},
        test_area_zhaozhao: {presses: [2], heading: 108},
    };
    for (const [
        id,
        expectedRoute,
    ] of Object.entries(expected)) {
        const route = fixedRoutes.routes.find((route) => route.id === id);
        assert.deepEqual(
            route.continuous_segments.map(({first, last}) => last - first - 1),
            expectedRoute.presses,
        );
        assert.equal(route.dismount_heading, expectedRoute.heading);
    }
});

test("both generated task option chains expose fixed mode only under zipline preference", () => {
    for (const [
        task,
        parent,
        child,
    ] of [
        [
            "SeizeDeliveryJobs",
            "SeizeDeliveryJobsPostDeparturePreferZipline",
            "SeizeDeliveryJobsFixedZipline",
        ],
        [
            "DeliveryJobs",
            "DeliveryJobsAutoDeliveryPreferZipline",
            "DeliveryJobsAutoDeliveryFixedZipline",
        ],
    ]) {
        const options = read(`../../../assets/tasks/${task}.json`).option;
        assert.ok(options[parent].cases.find((item) => item.name === "Yes").option.includes(child));
        assert.equal(options[child].default_case, "No");
        assert.deepEqual(options[child].controller, ["Win32-Front"]);
        for (const choice of options[child].cases) {
            for (const node of [
                "AutoDeliveryNavigateDepot",
                "AutoDeliveryNavigateDestination",
            ]) {
                assert.equal(choice.pipeline_override[node].attach.fixed_zipline, choice.name === "Yes");
            }
        }
    }
});
