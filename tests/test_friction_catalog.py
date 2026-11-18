import json
import re
import unittest
from pathlib import Path


CATALOG = Path(__file__).resolve().parents[1] / "scripts" / "friction-catalog.json"
IDS = [
    "spotlight-output", "timemachine-output", "tm-local-snapshots", "defender-repo",
    "windows-search", "linux-localsearch", "linux-baloo", "linux-updatedb",
    "inotify-limit", "edr-agent", "cloud-sync-repo", "wsl-cross-fs",
    "worktree-prune", "worktree-stale", "low-disk",
]
OS = {"macos", "linux", "windows", "any"}
KEYS = {"free_disk_bytes", "free_disk_pct", "cloud_roots", "prunable_worktrees",
        "stale_worktrees", "inotify_max_user_watches", "wsl_cross_fs"}


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = CATALOG.read_text(encoding="utf-8")
        with CATALOG.open(encoding="utf-8") as file:
            cls.catalog = json.load(file)

    def assert_os(self, values):
        self.assertIsInstance(values, list)
        self.assertTrue(values)
        self.assertTrue(set(values) <= OS)

    def assert_placeholders(self, value):
        for placeholder in re.findall(r"<[^<>]+>", value):
            self.assertEqual(placeholder, "<path>")

    def test_top_level(self):
        c = self.catalog
        self.assertEqual(c["v"], 1)
        self.assertIsInstance(c["v"], int)
        self.assertIsInstance(c["source"], dict)
        self.assertRegex(c["source"]["checked"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsInstance(c["source"]["note"], str)
        for key, typ in (("output_dir_names", list), ("cloud_sync_names", list),
                         ("processes", dict), ("actions", list)):
            self.assertIsInstance(c[key], typ)

    def test_actions_and_verification(self):
        actions = self.catalog["actions"]
        self.assertEqual([a["id"] for a in actions], IDS)
        self.assertEqual(len({a["id"] for a in actions}), len(actions))
        required = {"id", "os", "problem", "detect", "steps", "verify", "undo",
                    "automatable", "flap_steps", "metric", "sources", "needs_research"}
        for a in actions:
            with self.subTest(action=a["id"]):
                self.assertTrue(required <= a.keys())
                self.assert_os(a["os"])
                for key in ("id", "problem", "undo"):
                    self.assertIsInstance(a[key], str)
                for key in ("steps", "flap_steps", "sources"):
                    self.assertIsInstance(a[key], list)
                    self.assertTrue(all(isinstance(x, str) for x in a[key]))
                self.assertIsInstance(a["needs_research"], bool)
                self.assertIn(a["automatable"], {"no", "marker", "script"})
                v = a["verify"]
                self.assertIn(v["kind"], {"command", "exists", "manual"})
                if "note" in v:
                    self.assertIsInstance(v["note"], str)
                if "expect" in v:
                    self.assertIsInstance(v["expect"], str)
                if v["kind"] == "command":
                    self.assertIsInstance(v["argv"], list)
                    self.assertTrue(v["argv"])
                    for arg in v["argv"]:
                        self.assertIsInstance(arg, str)
                        self.assertNotIn(arg, {"sudo", "add", "remove", "set", "rm", "-p"})
                        self.assert_placeholders(arg)
                if v["kind"] == "exists":
                    self.assertIsInstance(v["path"], str)
                    self.assert_placeholders(v["path"])

    def test_actions_are_data_only(self):
        for action in self.catalog["actions"]:
            with self.subTest(action=action["id"]):
                self.assertNotIn("apply", action)
                self.assertNotIn("undo_apply", action)

    def test_research_steps(self):
        for a in self.catalog["actions"]:
            with self.subTest(action=a["id"]):
                self.assertEqual(bool(a["steps"]), not a["needs_research"])

    def test_metrics_and_detection(self):
        processes = self.catalog["processes"]
        for a in self.catalog["actions"]:
            with self.subTest(action=a["id"]):
                detect = a["detect"]
                self.assertIsInstance(detect["text"], str)
                self.assertIsInstance(detect["categories"], list)
                self.assertTrue(set(detect["categories"]) <= processes.keys())
                self.assertIn(detect["finding"], {None, "low-disk", "sprawl", "cloud-paths", "indexed-output", "inotify"})
                metric = a["metric"]
                if metric is None:
                    continue
                self.assertIsInstance(metric, dict)
                if metric["kind"] == "process_hits":
                    self.assertEqual(set(metric), {"kind", "category"})
                    self.assertIn(metric["category"], processes)
                else:
                    self.assertEqual(metric["kind"], "probe")
                    self.assertEqual(set(metric), {"kind", "key"})
                    self.assertIn(metric["key"], {"facts." + k for k in KEYS})

    def test_directory_names(self):
        names = self.catalog["output_dir_names"]
        self.assertEqual(names, ["out", "build", "dist", "target", "coverage", ".gradle", "obj"])
        self.assertFalse({"Library", "node_modules", ".git"} & set(names))
        self.assertTrue(all(isinstance(x, str) and x for x in self.catalog["cloud_sync_names"]))

    def test_sources_and_privacy(self):
        for a in self.catalog["actions"]:
            for source in a["sources"]:
                self.assertTrue(source.startswith("https://"))
        self.assertNotRegex(self.raw, r"/Users/|/home/")

    def test_processes(self):
        processes = self.catalog["processes"]
        self.assertEqual(set(processes), {"spotlight", "timemachine", "defender", "windows-search", "localsearch", "baloo", "updatedb", "edr"})
        for name, process in processes.items():
            with self.subTest(process=name):
                self.assert_os(process["os"])
                self.assertIsInstance(process["names"], list)
                self.assertTrue(process["names"])
                self.assertTrue(all(isinstance(x, str) and x for x in process["names"]))
                self.assertIsInstance(process["informational"], bool)
                self.assertEqual(process["informational"], name in {"defender", "windows-search"})
        self.assertTrue(processes["edr"]["needs_research"])
        self.assertTrue(processes["edr"]["note"])


if __name__ == "__main__":
    unittest.main()
