from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/MapNavigator"))
from json_import import discover_path_routes, load_project_import_node

spec = importlib.util.spec_from_file_location("fixed_validator", ROOT / "tools/fixed-delivery/validate_fixed_routes.py")
validator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator_module)


class FixedRouteToolsTest(unittest.TestCase):
    def test_continuous_route_schema(self):
        schema = json.loads((ROOT / "tools/schema/components/fixed_zipline.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema | {"$ref": "#/$defs/RouteFile"})
        data = json.loads((ROOT / "assets/data/MapNavigator/fixed_zipline_routes.json").read_text(encoding="utf-8"))
        validator.validate(data)
        self.assertEqual(data["routes"][0]["continuous_segments"], [{"first": 0, "last": 15}])
        for segment in [{"first": -1, "last": 15}, {"first": 0, "last": "15"}, {"first": 0}]:
            invalid = copy.deepcopy(data)
            invalid["routes"][0]["continuous_segments"] = [segment]
            self.assertFalse(validator.is_valid(invalid))
    def test_schema_boundary(self):
        schema = json.loads((ROOT / "tools/schema/components/fixed_zipline.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema["$defs"]["NavigateParam"])
        valid = {"fixed_zipline_route": "wuling_city_subaiyi", "zip": True, "path": [[1, 2]]}
        self.assertTrue(validator.is_valid(valid))
        self.assertTrue(validator.is_valid({"path": [[1, 2]], "zip": False}))
        for changed in [{"fixed_zipline_route": " "}, {"zip": False}, {"path": []}, {"fixed_zipline_route": 42}]:
            self.assertFalse(validator.is_valid(valid | changed))
        for key in ["path", "zip"]:
            incomplete = valid.copy()
            del incomplete[key]
            self.assertFalse(validator.is_valid(incomplete))

    def test_editor_refuses_lossy_import(self):
        pipeline = json.loads((ROOT / "assets/resource/pipeline/MapNavigator/FixedSubaiyiTest.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "固定架序"):
            discover_path_routes(pipeline)
        with self.assertRaisesRegex(ValueError, "固定架序"):
            load_project_import_node("path", "assets/resource/pipeline/MapNavigator/FixedSubaiyiTest.json", "MapNavigatorFixedSubaiyiTest")

    def test_generator_source_schema(self):
        schema = json.loads((ROOT / "tools/schema/auto_delivery_routes.schema.json").read_text(encoding="utf-8"))
        source = json.loads((ROOT / "tools/pipeline-generate/AutoDelivery/routes.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(source)
        invalid = copy.deepcopy(source)
        target = next(item for item in invalid["destinations"] if "fixed_zipline_route" in item)
        target["walk_only"] = True
        self.assertFalse(Draft202012Validator(schema).is_valid(invalid))

    def test_plain_preview_import(self):
        preview = json.loads((ROOT / "docs/zh_cn/dev-notes/苏白易架序.preview.json").read_text(encoding="utf-8"))
        self.assertEqual(len(discover_path_routes(preview)[0]), 16)

    def test_snapshot_validator_rejects_missing_and_duplicate(self):
        route = {"id": "test", "map_id": "map", "level_id": "level", "template_id": "tower", "nodes": [
            {"index": 0, "x": 0, "y": 1, "z": 0}, {"index": 1, "x": 10, "y": 1, "z": 0},
        ]}
        marks = [{"level_id": "level", "template_id": "tower", **point} for point in route["nodes"]]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "routes.json"
            snapshot = Path(directory) / "snapshot.json"
            config.write_text(json.dumps({"version": 1, "routes": [route]}), encoding="utf-8")
            def run(items):
                snapshot.write_text(json.dumps({"maps": [{"map_id": "map", "marks": items}]}), encoding="utf-8")
                with patch.object(sys, "argv", ["validate", "--routes", str(config), "--snapshot", str(snapshot)]), contextlib.redirect_stdout(io.StringIO()):
                    return validator_module.main()
            self.assertEqual(run(marks), 0)
            for invalid in [[], marks[:1], marks + [copy.deepcopy(marks[0])]]:
                with self.assertRaises(SystemExit):
                    run(invalid)
            for segments in [[{"first": 0, "last": 2}], [{"first": 1, "last": 0}], [{"first": 0, "last": 1}] * 2]:
                invalid_route = route | {"continuous_segments": segments}
                config.write_text(json.dumps({"version": 1, "routes": [invalid_route]}), encoding="utf-8")
                with self.assertRaises(SystemExit):
                    run(marks)


if __name__ == "__main__":
    unittest.main()
