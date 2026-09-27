"""Exercise update and rollback failures against disposable repositories and installations."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


stage_update = module("stage_update")
freeze_install = module("freeze_install")


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "upstream"
        self.repo = self.root / "adapter"
        self.remote.mkdir()
        self.git(self.remote, "init", "-b", "v2")
        self.identity(self.remote)
        (self.remote / "shared.txt").write_text("base\n")
        self.commit(self.remote, "base")
        self.base = self.git(self.remote, "rev-parse", "HEAD")
        self.git(self.root, "clone", str(self.remote), str(self.repo))
        self.identity(self.repo)
        self.git(self.repo, "switch", "-c", "codex/adapter")
        (self.repo / ".gitignore").write_text(".cache/\n")
        (self.repo / "fixed.txt").write_text("fixed\n")
        self.commit(self.repo, "adapter")
        self.accepted = self.git(self.repo, "rev-parse", "HEAD")

    def git(self, root, *args):
        return stage_update.value(root, *args)

    def identity(self, root):
        self.git(root, "config", "user.name", "Update Test")
        self.git(root, "config", "user.email", "update-test@example.invalid")

    def commit(self, root, message):
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", message)

    def upstream(self, filename="upstream.txt"):
        (self.remote / filename).write_text("upstream change\n")
        self.commit(self.remote, "upstream change")
        return self.git(self.remote, "rev-parse", "HEAD")

    def test_explicit_fetch_and_merge_preserves_baseline(self):
        target = self.upstream()
        self.git(self.repo, "config", "--unset-all", "remote.origin.fetch")
        report = stage_update.stage(self.repo, target, "origin", "v2")
        candidate = Path(report["candidate"])
        self.assertEqual(report["status"], "merged_needs_validation")
        self.assertEqual(self.git(candidate, "rev-parse", "MERGE_HEAD"), target)
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), self.accepted)
        self.assertFalse((self.repo / "upstream.txt").exists())
        self.assertTrue((candidate / "fixed.txt").exists())
        self.assertEqual(report["upstream_changes"], ["upstream.txt"])

    def test_fetch_failure_does_not_use_stale_ref(self):
        self.git(self.repo, "remote", "set-url", "origin", str(self.root / "missing"))
        with self.assertRaises(subprocess.CalledProcessError):
            stage_update.stage(self.repo, self.base, "origin", "v2")
        self.assertFalse((self.repo / ".cache").exists())
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), self.accepted)

    def test_conflict_retains_both_sides_and_report(self):
        target = self.upstream("shared.txt")
        (self.repo / "shared.txt").write_text("adapter change\n")
        self.commit(self.repo, "custom change")
        report = stage_update.stage(self.repo, target, "origin", "v2")
        self.assertEqual(report["status"], "merge_failed")
        self.assertEqual(report["conflicts"], ["shared.txt"])
        self.assertEqual(report["overlap"], ["shared.txt"])
        self.assertTrue((Path(report["candidate"]) / ".cache/upstream-update.json").is_file())
        self.assertEqual((self.repo / "shared.txt").read_text(), "adapter change\n")

    def test_refuses_dirty_source_and_existing_candidate(self):
        target = self.upstream()
        (self.repo / "uncommitted.txt").write_text("user work")
        with self.assertRaises(ValueError):
            stage_update.stage(self.repo, target, "origin", "v2")
        (self.repo / "uncommitted.txt").unlink()
        with self.assertRaises(ValueError):
            stage_update.stage(self.repo, target, "origin", "v2", self.repo)

    def test_snapshot_materializes_hardlinks_and_detects_changes(self):
        source = self.repo / ".cache/install"
        required = ("agent/cpp-algo.exe", "agent/go-service.exe", "interface.json",
                    "data/MapNavigator/fixed_zipline_routes.json", "data/AutoDelivery/catalog.json")
        for name in required:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test fixture")
        (source / "version.json").write_text('{}')
        os.link(source / "interface.json", source / "hardlink.json")
        (source / "Cache").mkdir()
        (source / "Cache/volatile").write_text("ignored")
        output = self.repo / ".cache/frozen"
        report = freeze_install.freeze(source, output, self.repo, self.base)
        freeze_install.verify(output)
        self.assertNotIn("Cache/volatile", report["files"])
        self.assertFalse(os.path.samefile(source / "hardlink.json", output / "hardlink.json"))
        (source / "interface.json").write_text("source changed")
        freeze_install.verify(output)
        (output / "agent/cpp-algo.exe").write_text("corrupted")
        with self.assertRaises(ValueError):
            freeze_install.verify(output)
        with self.assertRaises(ValueError):
            freeze_install.freeze(source, output, self.repo, self.base)


if __name__ == "__main__":
    unittest.main()
