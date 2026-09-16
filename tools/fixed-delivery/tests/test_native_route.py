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
