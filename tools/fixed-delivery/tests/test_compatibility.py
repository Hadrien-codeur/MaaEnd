import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("compatibility", ROOT / "tools/fixed-delivery/check_compatibility.py")
compatibility = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compatibility)


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = compatibility.read_json(ROOT / "tools/fixed-delivery/compatibility.json")
        paths = set(self.manifest["required_files"] + list(self.manifest["required_markers"]))
        paths.update([self.manifest["fixed_route_config"]["path"], self.manifest["delivery_routes"]["path"]])
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT / "assets/resource/pipeline/AutoDelivery/Routes").glob("*.json"))
        for relative in paths:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    def check(self):
        return compatibility.check(self.root, self.manifest)

    def edit(self, relative, mutate):
        path = self.root / relative
        value = compatibility.read_json(path)
        mutate(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_real_resources_pass(self):
        report = self.check()
        self.assertTrue(report["ok"], report["errors"])

    def test_node_missing_even_when_catalog_marker_survives(self):
        node = self.manifest["delivery_routes"]["depots"]["domain_2_lv002_depot_1"]["fixed_route_node"]
        self.edit("assets/resource/pipeline/AutoDelivery/Routes/WulingCity.json", lambda data: data.pop(node))
        self.assertFalse(self.check()["ok"])

    def test_duplicate_source_cannot_silently_select_last(self):
        self.edit(self.manifest["delivery_routes"]["path"],
                  lambda data: data["destinations"].append(copy.deepcopy(data["destinations"][0])))
        self.assertTrue(any("duplicate" in message for message in self.check()["errors"]))

    def test_generated_departure_cannot_lose_authored_points(self):
        node = self.manifest["delivery_routes"]["destinations"]["deliver_target_map02_lv002_02"]["fixed_route_node"]
        self.edit("assets/resource/pipeline/AutoDelivery/Routes/WulingCity.json",
                  lambda data: data[node]["custom_action_param"].pop("fixed_departure_path"))
        self.assertTrue(any("fixed_departure_path" in message for message in self.check()["errors"]))


if __name__ == "__main__":
    unittest.main()
