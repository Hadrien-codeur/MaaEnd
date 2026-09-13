"""Exercise production relay nodes against synthetic frames and an input-counting null controller."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/MapNavigator"))
from json_import import load_jsonc
from navmesh_backend import _make_null_controller
from runtime import load_maa_runtime, MAAFW_BIN_DIR


class RelayPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime = load_maa_runtime()
        runtime.Library.open(MAAFW_BIN_DIR)

        class CountingController(type(_make_null_controller())):
            def __init__(self):
                super().__init__()
                self.keys = []
                self._frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                self.block_capture = False
                self.capture_started = threading.Event()
                self.capture_release = threading.Event()

            def screencap(self):
                if self.block_capture:
                    self.capture_started.set()
                    if not self.capture_release.wait(5):
                        return None
                return self._frame

            def click_key(self, keycode):
                self.keys.append(keycode)
                return True

            def key_down(self, keycode):
                self.keys.append(keycode)
                return True

        cls.temp = tempfile.TemporaryDirectory()
        bundle = Path(cls.temp.name)
        (bundle / "pipeline").mkdir()
        (bundle / "image/RealTimeTask").mkdir(parents=True)
        template_path = ROOT / "assets/resource/image/RealTimeTask/Zipline.png"
        shutil.copyfile(template_path, bundle / "image/RealTimeTask/Zipline.png")
        with Image.open(template_path) as template:
            cls.template = np.asarray(template.convert("RGB"))[:, :, ::-1].copy()
        source = load_jsonc(ROOT / "assets/resource/pipeline/MapNavigator/Zipline.json")
        pipeline = {name: node for name, node in source.items() if name.startswith("MapNavigatorZiplineRelay")}
        prompt = load_jsonc(ROOT / "assets/resource/pipeline/RealTimeTask/AutoZipline.json")["RealTimeAutoZipline"]
        # And 引用只读取识别；剔除未被调用的实时辅助后继节点，保持测试资源包独立。
        pipeline["RealTimeAutoZipline"] = {key: value for key, value in prompt.items() if key != "next"}
        (bundle / "pipeline/relay.json").write_text(json.dumps(pipeline), encoding="utf-8")
        cls.resource = runtime.Resource()
        assert cls.resource.post_bundle(bundle).wait().succeeded
        cls.controller = CountingController()
        assert cls.controller.post_connection().wait().succeeded
        cls.tasker = runtime.Tasker()
        assert cls.tasker.bind(cls.resource, cls.controller)

    @classmethod
    def tearDownClass(cls):
        cls.tasker.post_stop().wait()
        cls.tasker = None
        cls.resource = None
        cls.controller = None
        cls.temp.cleanup()

    def run_probe(self, visible, press):
        self.controller._frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        if visible:
            height, width = self.template.shape[:2]
            self.controller._frame[432:432 + height, 1040:1040 + width] = self.template
        name = "MapNavigatorZiplineRelayPress" if press else "MapNavigatorZiplineRelayObserve"
        job = self.tasker.post_task(name + "Start").wait()
        self.assertTrue(job.succeeded)
        detail = self.tasker.get_task_detail(job.job_id)
        return any(node.name == name and node.completed for node in detail.nodes)

    def test_prompt_press_observe_and_absence(self):
        self.controller.keys.clear()
        self.assertFalse(self.run_probe(False, True))
        self.assertEqual(self.controller.keys, [])
        self.assertTrue(self.run_probe(True, True))
        self.assertEqual(self.controller.keys, [69])
        for _ in range(3):
            self.assertTrue(self.run_probe(True, False))
        self.assertEqual(self.controller.keys, [69])
        self.assertFalse(self.run_probe(False, False))
        self.assertTrue(self.run_probe(True, True))
        self.assertEqual(self.controller.keys, [69, 69])

    def test_cancel_before_recognition_does_not_press(self):
        self.controller.keys.clear()
        self.controller._frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        height, width = self.template.shape[:2]
        self.controller._frame[432:432 + height, 1040:1040 + width] = self.template
        self.controller.block_capture = True
        try:
            job = self.tasker.post_task("MapNavigatorZiplineRelayPressStart")
            self.assertTrue(self.controller.capture_started.wait(5))
            stop = self.tasker.post_stop()
            self.controller.capture_release.set()
            stop.wait()
            job.wait()
            self.assertEqual(self.controller.keys, [])
        finally:
            self.controller.block_capture = False
            self.controller.capture_release.set()


if __name__ == "__main__":
    unittest.main()
