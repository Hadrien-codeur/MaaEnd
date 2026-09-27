import {readFileSync, writeFileSync} from "node:fs";
import {resolve} from "node:path";

function option(name, fallback) {
    const index = process.argv.indexOf(name);
    return index >= 0 ? process.argv[index + 1] : fallback;
}

function requiredOption(name) {
    const value = option(name);
    if (!value) {
        throw new Error(`缺少参数 ${name}`);
    }
    return resolve(value);
}

function readJson(path) {
    return JSON.parse(readFileSync(path, "utf8"));
}

const sourcePath = requiredOption("--source");
const targetPath = requiredOption("--target");
const fixedRoutesPath = requiredOption("--fixed-routes");
const checkOnly = process.argv.includes("--check");
const source = readJson(sourcePath);
const target = readJson(targetPath);
const fixedRoutes = readJson(fixedRoutesPath);
const fixedRouteIds = new Set((fixedRoutes.routes ?? []).map((route) => route.id));
const overlayKeys = [
    "fixed_zipline_route",
    "fixed_approach_path",
    "fixed_departure_path",
];

function indexItems(config, section) {
    const result = new Map();
    for (const item of config[section] ?? []) {
        if (!item.source_id || result.has(item.source_id)) {
            throw new Error(`${section}: missing or duplicate source_id ${item.source_id}`);
        }
        result.set(item.source_id, item);
    }
    return result;
}

let applied = 0;
for (const section of [
    "depots",
    "destinations",
]) {
    const sourceItems = indexItems(source, section);
    const targetItems = indexItems(target, section);
    for (const [
        sourceId,
        sourceItem,
    ] of sourceItems) {
        if (!sourceItem.fixed_zipline_route) {
            continue;
        }
        if (!fixedRouteIds.has(sourceItem.fixed_zipline_route)) {
            throw new Error(`${section}.${sourceId} 引用了未知固定路线 ${sourceItem.fixed_zipline_route}`);
        }
        if (sourceItem.walk_only === true) {
            throw new Error(`${section}.${sourceId} 同时声明 walk_only 和固定路线`);
        }
        const targetItem = targetItems.get(sourceId);
        if (!targetItem) {
            throw new Error(`上游路线目录缺少固定路线 source_id：${sourceId}`);
        }
        if (targetItem.walk_only === true) {
            throw new Error(`上游 ${section}.${sourceId} 声明 walk_only，不能覆盖为固定滑索`);
        }
        for (const key of overlayKeys) {
            if (sourceItem[key] !== undefined) {
                targetItem[key] = sourceItem[key];
            }
        }
        applied += 1;
    }
}

if (!checkOnly) {
    writeFileSync(targetPath, `${JSON.stringify(target, null, 4)}\n`, "utf8");
}
console.log(`固定路线 overlay ${checkOnly ? "检查" : "应用"}完成：${applied} 项`);
