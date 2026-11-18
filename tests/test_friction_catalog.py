import hashlib
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


# SHA-256 of canonical parsed wt/p02 values. The archive's apply and
# undo_apply operations are deliberately omitted: this catalogue is data-only.
ARCHIVE_HASHES = {
    "v": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "source": "5966308d4cdeb3d1609dab396bbfe4bf2d09366691c1cc7fbebdda4d77fbc897",
    "output_dir_names": "ed98eb0cb87fe0605dc5328ce413d74e8dab212e48a3bfe5a39abe6b7e3431ab",
    "cloud_sync_names": "6841305d27a9c35165f5cad5a07a35c0c1af802f4a89ea382e9123d86960b270",
    "processes": "1672429302d11bb0fefc1482262ce8f69d6188948acc1699bef616aef26d5099",
    "actions": "80ccc1581c7a5f7a5e4ac023ae31b8268d61adf9371c3935c12cd7120ca01b94",
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key: " + key)
        result[key] = value
    return result


def validate_version(value):
    if type(value) is not int or value != 1:
        raise ValueError("unknown catalogue version")


def validate_template(value):
    # Angle brackets are reserved for the single supported substitution.
    if "<" in value.replace("<path>", "") or ">" in value.replace("<path>", ""):
        raise ValueError("invalid template")


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = CATALOG.read_text(encoding="utf-8")
        with CATALOG.open(encoding="utf-8") as file:
            cls.catalog = json.load(file, object_pairs_hook=unique_object)

    def assert_os(self, values):
        self.assertIsInstance(values, list)
        self.assertTrue(values)
        self.assertTrue(set(values) <= OS)

    def assert_placeholders(self, value):
        validate_template(value)

    def test_archive_values(self):
        self.assertEqual(set(self.catalog), set(ARCHIVE_HASHES))
        for key, expected in ARCHIVE_HASHES.items():
            with self.subTest(field=key):
                encoded = json.dumps(self.catalog[key], sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode("utf-8")
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), expected)

    def test_invalid_inputs(self):
        for raw in ('{"v": 1, "v": 1}', '{"nested": {"x": 1, "x": 2}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                json.loads(raw, object_pairs_hook=unique_object)
        for version in (0, 2, "1", True, None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                validate_version(version)
        for template in ("<other>", "<path", "path>", "<<path>>", "<>"):
            with self.subTest(template=template), self.assertRaises(ValueError):
                validate_template(template)
        validate_template("<path>/.nomedia")

    def test_top_level(self):
        c = self.catalog
        validate_version(c["v"])
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
