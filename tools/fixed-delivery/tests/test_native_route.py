"""Offline planning regression against the installed Agent and local imported snapshot.

Uses MapNavigator's null controller: no game connection or input is performed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/MapNavigator"))
from navmesh_backend import NavmeshBackend


class NativeFixedRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = NavmeshBackend(ROOT / "assets/resource/model/map/navmesh/base.nav.gz")
        pipeline = json.loads((ROOT / "assets/resource/pipeline/MapNavigator/FixedSubaiyiTest.json").read_text(encoding="utf-8"))
        cls.param = pipeline["MapNavigatorFixedSubaiyiTest"]["custom_action_param"]

    @classmethod
    def tearDownClass(cls):
        cls.backend.close()

    def preview(self, param, zone="Wuling_Base", position=None):
        return self.backend.query(
            "route_preview", position=position or [950.498, 1832.767], position_zone=zone,
            custom_action_param=param,
        )

    def assert_tower_chain(self, result, route_id):
        config = json.loads((ROOT / "assets/data/MapNavigator/fixed_zipline_routes.json").read_text(encoding="utf-8"))
        route = next(route for route in config["routes"] if route["id"] == route_id)
        frames = json.loads((ROOT / "assets/data/MapNavigator/zipline_frames.json").read_text(encoding="utf-8"))
        plane = next(frame["plane"] for frame in frames["frames"] if frame["map_id"] == route["map_id"])
        targets = [
            [plane[0] * node["x"] + plane[1] * node["z"] + plane[2],
             plane[3] * node["x"] + plane[4] * node["z"] + plane[5]]
            for node in route["nodes"]
        ]
        hops = result["zipline_segments"]
        self.assertEqual(len(hops), len(targets) - 1)
        for hop, start, end in zip(hops, targets[:-1], targets[1:], strict=True):
            for key, expected in [("from", start), ("to", end)]:
                for actual, value in zip(hop[key], expected, strict=True):
                    self.assertAlmostEqual(actual, value, places=3)

    def test_full_confirmed_chain(self):
        result = self.preview(self.param)
        self.assertTrue(result.get("ok"), result)
        hops = result["zipline_segments"]
        self.assertEqual(len(hops), 15)
        self.assertEqual(hops[0]["relay_presses_after_launch"], 14)
        self.assertTrue(all("relay_presses_after_launch" not in hop for hop in hops[1:]))
        self.assert_tower_chain(result, "wuling_city_subaiyi")
        self.assertEqual(result["points"][-1], self.param["path"][-1]["target"])

    def test_unknown_id_does_not_walk(self):
        param = copy.deepcopy(self.param)
        param["fixed_zipline_route"] = "missing"
        result = self.preview(param)
        self.assertFalse(result.get("ok"), result)
        self.assertNotIn("points", result)

    def test_generated_subaiyi_node_keeps_full_chain(self):
        pipeline = json.loads((ROOT / "assets/resource/pipeline/AutoDelivery/Routes/WulingCity.json").read_text(encoding="utf-8"))
        param = next(node["custom_action_param"] for node in pipeline.values()
                     if node.get("custom_action_param", {}).get("fixed_zipline_route") == "wuling_city_subaiyi")
        result = self.preview(param)
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(len(result["zipline_segments"]), 15)

    def test_generated_pickup_keeps_single_directed_hop(self):
        pipeline = json.loads((ROOT / "assets/resource/pipeline/AutoDelivery/Routes/WulingCity.json").read_text(encoding="utf-8"))
        param = next(node["custom_action_param"] for node in pipeline.values()
                     if node.get("custom_action_param", {}).get("fixed_zipline_route") == "wuling_city_pickup")
        result = self.preview(param, position=[941.78, 1778.6])
        self.assertTrue(result.get("ok"), result)
        self.assert_tower_chain(result, "wuling_city_pickup")
        self.assertTrue(all(hop.get("relay_presses_after_launch", 0) == 0 for hop in result["zipline_segments"]))

    def test_disabled_zipline_rejected(self):
        param = copy.deepcopy(self.param)
        param["zip"] = False
        self.assertFalse(self.preview(param).get("ok"))

    def new_destination_param(self, route_id):
        pipeline = json.loads((ROOT / "assets/resource/pipeline/AutoDelivery/Routes/WulingCity.json").read_text(encoding="utf-8"))
        return next(node["custom_action_param"] for node in pipeline.values()
                    if node.get("custom_action_param", {}).get("fixed_zipline_route") == route_id)

    def test_three_new_routes_preserve_towers_ground_paths_and_headings(self):
        for route_id, relays, stance, facing, heading in [
            ("wuling_city_lind", {0: 9}, [462.78, 1712.92], [462.06, 1712.79], None),
            ("wuling_city_yushi", {0: 4, 5: 2}, [894.71, 1409.1], [894.97, 1407.6], None),
            ("wuling_city_recycle", {0: 8, 9: 1}, [514.06, 1651.68], [513.39, 1650.67], 101),
        ]:
            with self.subTest(route=route_id):
                param = self.new_destination_param(route_id)
                result = self.preview(param)
                self.assertTrue(result.get("ok"), result)
                self.assert_tower_chain(result, route_id)
                self.assertEqual({i: hop["relay_presses_after_launch"] for i, hop in enumerate(result["zipline_segments"])
                                  if "relay_presses_after_launch" in hop}, relays)
                hops = result["zipline_segments"]
                self.assertEqual(hops[-1].get("dismount_heading"), heading)
                self.assertTrue(all("dismount_heading" not in hop for hop in hops[:-1]))
                self.assertEqual(result["points"][-1], stance)
                self.assertEqual(result["headings"], [{"target": facing}])
                for field, walk in [("fixed_approach_path", result["walk_segments"][0]),
                                    ("fixed_departure_path", result["walk_segments"][-1])]:
                    cursor = 0
                    for point in param[field]:
                        if isinstance(point, dict) and point["action"] in ["ZONE", "HEADING"]:
                            continue
                        target = point if isinstance(point, list) else point["target"]
                        # Every recorded bend must survive in order, not just the final destination.
                        cursor = walk.index(target, cursor) + 1

    def test_fixed_ground_paths_reject_invalid_or_cross_zone_input(self):
        for field in ["fixed_approach_path", "fixed_departure_path"]:
            for path in [[], None, [{"action": "ZONE", "zone_id": "Wuling_Base"}],
                         [{"action": "INTERACT", "target": [961, 1831]}],
                         [[961, 1831], {"action": "RUN", "target": [962, 1831], "zone_id": "ValleyIV_Base"}],
                         [{"action": "ZONE", "zone_id": "ValleyIV_Base"}, [961, 1831]]]:
                with self.subTest(field=field, path=path):
                    param = self.new_destination_param("wuling_city_lind")
                    param[field] = path
                    self.assertFalse(self.preview(param).get("ok"))
        param = self.new_destination_param("wuling_city_lind")
        del param["fixed_zipline_route"]
        self.assertFalse(self.preview(param).get("ok"))

    def test_semantic_boundary_rejected(self):
        param = copy.deepcopy(self.param)
        # A ZONE declaration is legal; an intermediate required movement is not.
        param["path"].insert(1, {"action": "NAVMESH", "target": [961.39, 1832.63], "required": True})
        self.assertFalse(self.preview(param).get("ok"))

    def test_wrong_initial_zone_rejected(self):
        param = copy.deepcopy(self.param)
        param["path"].insert(0, {"action": "ZONE", "zone_id": "ValleyIV_Base"})
        result = self.preview(param)
        self.assertFalse(result.get("ok"), result)
        self.assertEqual(result["failure"]["code"], "fixed_zipline_wrong_zone")

    def test_plain_walk_still_works(self):
        param = {"path": [{"action": "NAVMESH", "target": [961.5, 1830.75]}], "zip": False}
        result = self.preview(param)
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["zipline_segments"], [])

    def test_normal_zipline_option_still_works(self):
        param = {"path": [self.param["path"][-1]], "zip": True}
        result = self.preview(param)
        self.assertTrue(result.get("ok"), result)


if __name__ == "__main__":
    unittest.main()
