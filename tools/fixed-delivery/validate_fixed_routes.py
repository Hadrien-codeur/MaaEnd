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
    routes = json.loads(args.routes.read_text(encoding="utf-8"))["routes"]
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    maps = {entry["map_id"]: entry for entry in snapshot["maps"]}
    for route in routes:
        marks = [
            mark
            for mark in maps[route["map_id"]]["marks"]
            if mark["level_id"] == route["level_id"] and mark["template_id"] == route["template_id"]
        ]
        used: set[int] = set()
        for node in route["nodes"]:
            candidates = sorted(
                (
                    math.dist((node[axis] for axis in "xyz"), (mark[axis] for axis in "xyz")),
                    index,
                    mark,
                )
                for index, mark in enumerate(marks)
                if index not in used
            )
            distance, index, mark = candidates[0]
            if distance > 0:
                raise SystemExit(f"{route['id']} node {node['index']} mismatch: {distance:.3f}m")
            used.add(index)
            print(f"{route['id']} #{node['index']}: matched ({mark['x']}, {mark['y']}, {mark['z']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
