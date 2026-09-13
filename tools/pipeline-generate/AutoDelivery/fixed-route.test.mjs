import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {destinations, readFixedZiplineRoute} from "./model.mjs";
import rows, {buildRows} from "./routes-data.mjs";
import {buildSyncedRouteConfig} from "./sync-routes.mjs";

test("苏白易固定路线重新生成后保留，普通和站位修正入口不改变", () => {
    const destination = destinations.find((item) => item.id === "deliver_target_map02_lv002_01");
    const fixed = rows.find((row) => row.Node === destination.zipRouteNode);
    assert.equal(fixed.ActionParam.value.fixed_zipline_route, "wuling_city_subaiyi");
    for (const row of rows.filter((item) => item.Node !== destination.zipRouteNode)) {
        assert.equal(row.ActionParam.value.fixed_zipline_route, undefined);
    }
    const source = JSON.parse(readFileSync(new URL("./routes.json", import.meta.url)));
    const catalog = JSON.parse(readFileSync(new URL("../data/delivery_destinations.json", import.meta.url)));
    const synced = buildSyncedRouteConfig(catalog, source);
    assert.equal(
        synced.destinations.find((item) => item.source_id === destination.id).fixed_zipline_route,
        "wuling_city_subaiyi",
    );
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
