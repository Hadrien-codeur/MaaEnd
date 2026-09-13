"""Validate fixed zipline routes against an imported Ziplines snapshot."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes", type=Path, default=Path("assets/data/MapNavigator/fixed_zipline_routes.json"))
    parser.add_argument("--snapshot", type=Path, default=Path("install/debug/record/Ziplines.json"))
    args = parser.parse_args()
    config = json.loads(args.routes.read_text(encoding="utf-8"))
    if config.get("version") != 1 or not isinstance(config.get("routes"), list):
        raise SystemExit("Expected fixed route version 1 and routes array")
    routes = config["routes"]
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    maps = {entry["map_id"]: entry for entry in snapshot["maps"]}
    if len(maps) != len(snapshot["maps"]):
        raise SystemExit("Duplicate map IDs in snapshot")
    route_ids: set[str] = set()
    for route in routes:
        if not route.get("id") or route["id"] in route_ids:
            raise SystemExit("Empty or duplicate fixed route ID")
        route_ids.add(route["id"])
        if route["map_id"] not in maps or len(route["nodes"]) < 2:
            raise SystemExit(f"{route['id']}: map missing or fewer than two towers")
        segments = route.get("continuous_segments", [])
        if not isinstance(segments, list):
            raise SystemExit(f"{route['id']}: continuous_segments must be an array")
        previous_end = 0
        for segment in segments:
            first, last = segment.get("first"), segment.get("last")
            if type(first) is not int or type(last) is not int or not previous_end <= first < last < len(route["nodes"]):
                raise SystemExit(f"{route['id']}: invalid or overlapping continuous segment")
            previous_end = last
            print(f"{route['id']}: continuous #{first} -> #{last}, {last - first} E presses after mouse launch")
        marks = [
            mark
            for mark in maps[route["map_id"]]["marks"]
            if mark["level_id"] == route["level_id"] and mark["template_id"] == route["template_id"]
        ]
        used: set[int] = set()
        for expected_index, node in enumerate(route["nodes"]):
            if node["index"] != expected_index or not all(math.isfinite(node[axis]) for axis in "xyz"):
                raise SystemExit(f"{route['id']}: invalid index or coordinates at #{expected_index}")
            candidates = [
                (index, mark)
                for index, mark in enumerate(marks)
                if math.dist((node[axis] for axis in "xyz"), (mark[axis] for axis in "xyz")) <= 0.01
            ]
            if len(candidates) != 1:
                raise SystemExit(f"{route['id']} #{node['index']}: expected one match, got {len(candidates)}")
            index, mark = candidates[0]
            if index in used:
                raise SystemExit(f"{route['id']} #{node['index']}: repeated tower")
            used.add(index)
            print(f"{route['id']} #{node['index']}: matched ({mark['x']}, {mark['y']}, {mark['z']})")
        print(f"{route['id']}: {len(used)} towers, {len(used) - 1} hops; power and live connectivity not checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
