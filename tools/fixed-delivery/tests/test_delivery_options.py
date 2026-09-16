"""Check actual MaaFramework attach merging for both delivery task option trees."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/MapNavigator"))
from runtime import load_maa_runtime, MAAFW_BIN_DIR


class DeliveryOptionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = load_maa_runtime()
        cls.runtime.Library.open(MAAFW_BIN_DIR)

    def test_both_task_options_preserve_zip_and_can_disable_fixed(self):
        nodes = ["AutoDeliveryNavigateDepot", "AutoDeliveryNavigateDestination"]
        for filename, zip_name, fixed_name in [
            ("SeizeDeliveryJobs", "SeizeDeliveryJobsPostDeparturePreferZipline", "SeizeDeliveryJobsFixedZipline"),
            ("DeliveryJobs", "DeliveryJobsAutoDeliveryPreferZipline", "DeliveryJobsAutoDeliveryFixedZipline"),
        ]:
            task = json.loads((ROOT / "assets/tasks" / f"{filename}.json").read_text(encoding="utf-8"))
            options = task["option"]
            zip_cases = {case["name"]: case for case in options[zip_name]["cases"]}
            fixed_cases = {case["name"]: case for case in options[fixed_name]["cases"]}
            self.assertEqual(options[fixed_name]["default_case"], "No")
            self.assertIn(fixed_name, zip_cases["Yes"]["option"])
            with self.subTest(task=filename), tempfile.TemporaryDirectory() as directory:
                bundle = Path(directory)
                (bundle / "pipeline").mkdir()
                (bundle / "pipeline/options.json").write_text(json.dumps({
                    node: {"attach": {"zip": False}} for node in nodes
                }), encoding="utf-8")
                resource = self.runtime.Resource()
                try:
                    self.assertTrue(resource.post_bundle(bundle).wait().succeeded)
                    self.assertTrue(resource.override_pipeline(zip_cases["Yes"]["pipeline_override"]))
                    for enabled in [True, False, True]:
                        case = fixed_cases["Yes" if enabled else "No"]
                        self.assertTrue(resource.override_pipeline(case["pipeline_override"]))
                        for node in nodes:
                            self.assertEqual(resource.get_node_data(node)["attach"], {
                                "zip": True, "fixed_zipline": enabled,
                            })
                    self.assertTrue(resource.override_pipeline(zip_cases["No"]["pipeline_override"]))
                    for node in nodes:
                        self.assertFalse(resource.get_node_data(node)["attach"]["zip"])
                finally:
                    resource = None


if __name__ == "__main__":
    unittest.main()
