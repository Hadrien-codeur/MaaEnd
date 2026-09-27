"""Check that an upstream candidate still exposes the fixed-delivery contract.

This is intentionally a fail-closed check. It does not copy files or repair a
candidate: an upstream change must be adapted explicitly before it can replace
the known-good fixed-delivery build.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "tools/fixed-delivery/compatibility.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def git_value(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            check=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def check(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    def indexed(items: list, key: str, label: str) -> dict:
        result = {}
        for item in items:
            identity = item.get(key)
            if not identity or identity in result:
                errors.append(f"{label}: missing or duplicate {key}: {identity!r}")
            result[identity] = item
        return result

    required_files = manifest.get("required_files", [])
    for relative in required_files:
        path = root / relative
        if not path.is_file():
            errors.append(f"缺少固定路线兼容文件：{relative}")

    for relative, markers in manifest.get("required_markers", {}).items():
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(f"{relative} 缺少兼容锚点：{marker}")

    route_config_path = root / manifest["fixed_route_config"]["path"]
    route_config = read_json(route_config_path) if route_config_path.is_file() else {}
    expected_version = manifest["fixed_route_config"]["version"]
    if route_config.get("version") != expected_version:
        errors.append(
            f"固定路线配置版本不匹配：实际 {route_config.get('version')!r}，期望 {expected_version}"
        )
    route_ids = indexed(route_config.get("routes", []), "id", "fixed routes")
    for route_id in manifest["fixed_route_config"]["required_route_ids"]:
        if route_id not in route_ids:
            errors.append(f"固定路线配置缺少已验收路线：{route_id}")

    source_path = root / manifest["delivery_routes"]["path"]
    source = read_json(source_path) if source_path.is_file() else {}
    source_items = [
        *(source.get("depots", []) if isinstance(source, dict) else []),
        *(source.get("destinations", []) if isinstance(source, dict) else []),
    ]
    source_by_id = indexed(source_items, "source_id", "route source")
    expected_routes = {**manifest["delivery_routes"].get("depots", {}),
                       **manifest["delivery_routes"]["destinations"]}
    for source_id, expected in expected_routes.items():
        item = source_by_id.get(source_id)
        if item is None:
            errors.append(f"路线源配置缺少正式终点：{source_id}")
            continue
        if item.get("fixed_zipline_route") != expected["fixed_zipline_route"]:
            errors.append(
                f"{source_id} 固定路线不匹配：{item.get('fixed_zipline_route')!r}"
            )

    catalog_path = root / "assets/data/AutoDelivery/catalog.json"
    catalog = read_json(catalog_path) if catalog_path.is_file() else {}
    catalog_by_id = indexed([*catalog.get("depots", []), *catalog.get("destinations", [])], "id", "catalog")
    nodes = {}
    for path in (root / "assets/resource/pipeline/AutoDelivery/Routes").glob("*.json"):
        for name, node in read_json(path).items():
            if name in nodes:
                errors.append(f"Duplicate generated node: {name}")
            nodes[name] = node
    for source_id, expected in expected_routes.items():
        item = catalog_by_id.get(source_id)
        if item is None:
            errors.append(f"运行时目录缺少正式终点：{source_id}")
            continue
        if item.get("fixed_route_node") != expected["fixed_route_node"]:
            errors.append(
                f"{source_id} fixed_route_node 不匹配：{item.get('fixed_route_node')!r}"
            )
        node = nodes.get(expected["fixed_route_node"], {})
        params = node.get("custom_action_param", {})
        if node.get("custom_action") != "MapNavigateAction" or params.get("zip") is not True:
            errors.append(f"{source_id}: fixed node is missing or is not zip-enabled navigation")
        if params.get("fixed_zipline_route") != expected["fixed_zipline_route"]:
            errors.append(f"{source_id}: generated node lost the fixed route binding")
        source_item = source_by_id.get(source_id, {})
        for key in ("fixed_approach_path", "fixed_departure_path"):
            if params.get(key) != source_item.get(key):
                errors.append(f"{source_id}: generated {key} differs from its authored source")
        if source_item.get("walk_only"):
            errors.append(f"{source_id}: fixed route conflicts with walk_only")
    for item in catalog_by_id.values():
        for key in ("route_node", "zip_route_node", "retry_route_node"):
            name = item.get(key)
            if not name:
                continue
            if name not in nodes:
                errors.append(f"{item['id']}: missing {key}: {name}")
                continue
            if any(key.startswith("fixed_") for key in nodes[name].get("custom_action_param", {})):
                errors.append(f"{name}: ordinary/retry route must not inherit fixed parameters")

    head = git_value(root, "rev-parse", "HEAD")
    branch = git_value(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch is None:
        warnings.append("候选 worktree 处于 detached HEAD；这是迁移候选的正常状态")

    return {
        "ok": not errors,
        "root": str(root),
        "git_head": head,
        "git_branch": branch,
        "errors": errors,
        "warnings": warnings,
        "scope": "static generated-resource contract; does not certify runtime or gameplay",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    root = args.root.resolve()
    manifest = read_json(args.manifest.resolve())
    try:
        report = check(root, manifest)
    except (OSError, ValueError, TypeError, KeyError) as error:
        report = {"ok": False, "root": str(root), "git_head": None,
                  "errors": [f"Invalid compatibility input: {error}"], "warnings": []}
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=4))
    else:
        status = "通过" if report["ok"] else "失败"
        print(f"固定滑索兼容检查：{status}")
        print(f"候选根目录：{report['root']}")
        if report["git_head"]:
            print(f"候选提交：{report['git_head']}")
        for warning in report["warnings"]:
            print(f"警告：{warning}")
        for error in report["errors"]:
            print(f"错误：{error}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
