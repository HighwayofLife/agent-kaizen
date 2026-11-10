import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
LINK = ROOT / "scripts" / "kaizen-link"


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.bin = self.home / "bin"
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.home),
                        KAIZEN_BACKUP_DIR=str(self.home / "backups"))

    def run_link(self, *args, root=ROOT):
        return subprocess.run(["python3", str(LINK), "--plugin-root", str(root), *args],
                              env=self.env, text=True, capture_output=True)

    def run_script(self, path, *args):
        return subprocess.run([str(path), *args], env=self.env, text=True, capture_output=True)

    def settings(self, names):
        (self.home / "agent-kaizen.json").write_text(json.dumps({"localScripts": names}))

    def test_stale_installed_cache(self):
        self.env['HOME'] = str(self.home)
        plugin = self.home / 'source'
        shutil.copytree(ROOT, plugin, ignore=shutil.ignore_patterns('.git', 'out'))
        cache = self.home / 'cache'
        shutil.copytree(plugin, cache)
        registry = self.home / 'plugins/installed_plugins.json'
        registry.parent.mkdir()
        name = json.loads((plugin / '.claude-plugin/plugin.json').read_text())['name'] + '@market'
        registry.write_text(json.dumps({'plugins': {name: [{'installPath': str(cache)}]}}))
        self.assertEqual(self.run_link('--check', root=plugin).returncode, 0)
        (cache / 'scripts/kaizen-link').write_text('old')
        result = self.run_link('--check', root=plugin)
        self.assertEqual(result.returncode, 1)
        self.assertIn('STALE-CACHE ' + name, result.stdout)
        self.assertIn('claude plugin uninstall ' + name, result.stdout)
        registry.unlink()
        self.assertEqual(self.run_link('--check', root=plugin).returncode, 0)

    def test_unlink_after_sources_removed(self):
        fake = self.home / 'plugin'
        shutil.copytree(ROOT / 'scripts', fake / 'scripts')
        self.assertEqual(self.run_link('--apply', root=fake).returncode, 0)
        (self.bin / 'token-audit').unlink()
        (self.bin / 'token-audit').write_text('owner file')
        shutil.rmtree(fake)
        result = self.run_link('--unlink', root=fake)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.bin / 'token-audit').read_text(), 'owner file')
        self.assertFalse((self.bin / 'codex-review').is_symlink())

    def test_help_empty_and_plan(self):
        self.assertEqual(self.run_link("--help").returncode, 0)
        result = self.run_link("--check", "--json")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(all(e["status"] == "ABSENT" for e in json.loads(result.stdout)["entries"]))
        self.assertIn("would link token-audit", self.run_link().stdout)
        self.assertFalse(self.bin.exists())

    def test_apply_idempotent_and_installed_help(self):
        self.assertEqual(self.run_link("--apply").returncode, 0)
        target = self.bin / "token-audit"
        self.assertEqual(target.resolve(), (ROOT / "scripts/token-audit").resolve())
        before = target.lstat().st_mtime_ns
        self.assertEqual(self.run_link("--apply").returncode, 0)
        self.assertEqual(before, target.lstat().st_mtime_ns)
        self.assertEqual(self.run_link("--check").returncode, 0)
        for name in ("token-audit", "kaizen-scheduled"):
            result = self.run_script(self.bin / name, "--help")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_drift_replace_broken_and_prefixed(self):
        self.bin.mkdir()
        (self.bin / "token-audit").write_text("old")
        (self.bin / "kaizen-backup").write_text("old backup")
        (self.bin / "codex-review").symlink_to(self.home / "missing")
        check = self.run_link("--check")
        self.assertEqual(check.returncode, 1)
        self.assertIn("DRIFT token-audit", check.stdout)
        self.assertIn("BROKEN codex-review", check.stdout)
        self.run_link("--apply", "--replace-prefixed")
        self.assertEqual((self.bin / "token-audit").read_text(), "old")
        self.assertTrue((self.bin / "kaizen-backup").is_symlink())
        self.run_link("--apply", "--replace")
        self.assertTrue((self.bin / "token-audit").is_symlink())
        self.assertEqual(next(self.bin.glob("token-audit.replaced-*")).read_text(), "old")
        self.assertEqual(self.run_link("--check").returncode, 0)

    def test_local_is_never_mutated(self):
        self.bin.mkdir()
        (self.bin / "codex-review").write_text("private")
        (self.bin / "preambles").mkdir()
        (self.bin / "preambles" / "owner.md").write_text("owner")
        self.settings(["codex-review", "preambles"])
        def digest():
            return [hashlib.sha256(p.read_bytes()).hexdigest() for p in
                    (self.bin / "codex-review", self.bin / "preambles" / "owner.md")]
        before = digest()
        for action in (("--apply", "--replace"), ("--unlink",)):
            result = self.run_link(*action)
            self.assertIn("skip LOCAL codex-review", result.stdout)
            self.assertIn("skip LOCAL preambles", result.stdout)
            self.assertEqual(digest(), before)
        result = self.run_link("--check", "--only", "codex-review,preambles")
        self.assertEqual(result.returncode, 0)
        self.assertIn("2 local", result.stdout)

    def test_copy_auto_dependencies_and_directories(self):
        fake = self.home / "plugins/cache/example/version"
        shutil.copytree(ROOT / "scripts", fake / "scripts")
        result = self.run_link("--apply", root=fake)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.bin / "token-audit").is_symlink())
        for name in ("usage-series", "usage-compare"):
            result = self.run_script(self.bin / name, "--help")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.bin / "pricing.json").is_file())
        folder = self.bin / "preambles"
        (folder / "extra.md").write_text("extra")
        self.assertEqual(self.run_link("--check", "--only", "preambles", root=fake).returncode, 0)
        source_file = next(p for p in (fake / "scripts/preambles").iterdir() if p.is_file())
        (folder / source_file.name).write_text("stale")
        self.assertEqual(self.run_link("--check", "--only", "preambles", root=fake).returncode, 1)
        self.run_link("--apply", "--replace", "--only", "preambles", root=fake)
        self.assertEqual(next(self.bin.glob("preambles.replaced-*/extra.md")).read_text(), "extra")
        self.assertEqual(self.run_link("--check", "--only", "preambles", root=fake).returncode, 0)
        (self.bin / "token-audit").write_text("stale")
        self.assertEqual(self.run_link("--check", "--only", "token-audit", root=fake).returncode, 1)

    def test_copy_rules_lint_finds_bundled_patterns(self):
        self.env["HOME"] = str(self.home)
        result = self.run_link("--apply", "--mode", "copy")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("rules-lint", "rules-lint.patterns"):
            self.assertTrue((self.bin / name).is_file())
            self.assertFalse((self.bin / name).is_symlink())
        repo = self.home / "fixture"
        repo.mkdir()
        fixture = repo / "CLAUDE.md"
        fixture.write_text("Use project-repos.txt to find projects.\n")
        result = self.run_script(self.bin / "rules-lint", "--repo", str(repo), "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["count"], 1)
        self.assertEqual(report["hits"][0]["path"], str(fixture))
        self.assertIn("project-repos.txt", report["hits"][0]["text"])

    def test_unlink_and_restore(self):
        self.bin.mkdir()
        (self.bin / "token-audit").write_text("original")
        self.run_link("--apply", "--replace", "--only", "token-audit,preambles")
        self.assertTrue((self.bin / "preambles").is_symlink())
        foreign = self.bin / "kaizen-backup"
        foreign.symlink_to(self.home / "foreign")
        self.run_link("--unlink", "--restore-replaced")
        self.assertEqual((self.bin / "token-audit").read_text(), "original")
        self.assertFalse((self.bin / "preambles").is_symlink())
        self.assertTrue(foreign.is_symlink())

    def test_root_validation_and_help(self):
        copied = self.home / "copied-link"
        shutil.copy(LINK, copied)
        result = subprocess.run(["python3", str(copied), "--check"], env=self.env,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--plugin-root", result.stderr)
        self.assertIn("--plugin-root DIR", self.run_link("--help").stdout)
        result = subprocess.run(["python3", str(copied), "--plugin-root", str(ROOT), "--check"],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_link("--restore-replaced").returncode, 2)

    def test_mutation_rejects_destinations_inside_root(self):
        fake = self.home / "plugin"
        (fake / "scripts").mkdir(parents=True)
        (fake / "scripts/token-audit").write_text("source")
        alias = self.home / "alias"
        alias.symlink_to(fake, target_is_directory=True)
        for action in ("--apply", "--unlink"):
            for option in ("--bin", "--hooks-dir"):
                result = self.run_link(action, option, str(alias / "nested"), root=fake)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("inside plugin root", result.stderr)
        self.assertFalse((fake / "nested").exists())

    def test_unlink_removed_source_and_regular_file(self):
        fake = self.home / "plugin"
        (fake / "scripts").mkdir(parents=True)
        source = fake / "scripts/token-audit"
        source.write_text("source")
        (fake / "scripts/kaizen-backup").write_text("other source")
        self.assertEqual(self.run_link("--apply", "--only", "token-audit", root=fake).returncode, 0)
        source.unlink()
        self.assertEqual(self.run_link("--unlink", root=fake).returncode, 0)
        self.assertFalse((self.bin / "token-audit").is_symlink())
        (self.bin / "token-audit").write_text("user")
        self.run_link("--unlink", root=fake)
        self.assertEqual((self.bin / "token-audit").read_text(), "user")

    def test_auto_link_directory_and_json_drift(self):
        result = self.run_link("--apply", "--mode", "auto", "--only", "preambles")
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.bin / "preambles"
        self.assertTrue(target.is_symlink())
        self.assertEqual(self.run_link("--check", "--only", "preambles").returncode, 0)
        target.unlink()
        target.mkdir()
        (target / "custom").write_text("old")
        result = self.run_link("--check", "--json", "--only", "preambles")
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {"entries", "drift", "broken", "local"})
        self.assertEqual(data["drift"], 1)
        self.assertEqual(set(data["entries"][0]), {"name", "kind", "status", "detail"})
        self.assertEqual(data["entries"][0]["status"], "DRIFT")
        self.run_link("--apply", "--replace", "--mode", "link", "--only", "preambles")
        self.assertTrue(target.is_symlink())
        self.assertEqual(next(self.bin.glob("preambles.replaced-*/custom")).read_text(), "old")

    def test_rollback_order(self):
        for unlink_first in (False, True):
            with self.subTest(unlink_first=unlink_first):
                fake = self.home / ("safe" if unlink_first else "unsafe")
                (fake / "scripts").mkdir(parents=True)
                source = fake / "scripts/token-audit"
                source.write_text("plugin source")
                installed = self.bin / "token-audit"
                self.bin.mkdir(exist_ok=True)
                if installed.exists() or installed.is_symlink():
                    installed.unlink()
                installed.write_text("original user file")
                before = hashlib.sha256(source.read_bytes()).hexdigest()
                backup = ROOT / "scripts/kaizen-backup"
                result = self.run_script(backup, "begin", "--skill", "test", "--ledger", "test", str(installed))
                self.assertEqual(result.returncode, 0, result.stderr)
                change = result.stdout.strip()
                self.run_link("--apply", "--replace", "--only", "token-audit", root=fake)
                if unlink_first:
                    self.run_link("--unlink", "--only", "token-audit", root=fake)
                result = self.run_script(backup, "undo", change)
                if not unlink_first:
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("symlink", result.stderr)
                    self.assertTrue(installed.is_symlink())
                    self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
                    self.run_link("--unlink", "--only", "token-audit", root=fake)
                    result = self.run_script(backup, "undo", change)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(installed.read_text(), "original user file")
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)


    def test_live_foreign_symlink_is_kept_without_replace_and_saved_with_replace(self):
        self.bin.mkdir()
        mine = self.home / "mine"
        mine.write_text("mine")
        link = self.bin / "token-audit"
        link.symlink_to(mine)
        self.assertIn("DRIFT token-audit", self.run_link("--check", "--only", "token-audit").stdout)
        self.assertIn("would skip token-audit", self.run_link("--only", "token-audit").stdout)
        result = self.run_link("--apply", "--only", "token-audit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRIFT token-audit", result.stdout)
        self.assertIn("--replace", result.stdout)
        self.assertEqual(link.resolve(), mine.resolve())
        self.assertEqual(list(self.bin.glob("token-audit.replaced-*")), [])
        result = self.run_link("--apply", "--replace", "--only", "token-audit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(link.resolve(), (ROOT / "scripts/token-audit").resolve())
        saved = list(self.bin.glob("token-audit.replaced-*"))
        self.assertEqual(len(saved), 1)
        self.assertTrue(saved[0].is_symlink())
        self.assertEqual(saved[0].resolve(), mine.resolve())

    def test_symlinks_into_the_plugin_root_or_older_caches_and_broken_ones_are_fixed_without_replace(self):
        fake = self.home / "plugin"
        (fake / "scripts").mkdir(parents=True)
        (fake / "scripts/token-audit").write_text("source")
        (fake / "scripts/kaizen-backup").write_text("source")
        (fake / "scripts/codex-review").write_text("source")
        (fake / "scripts/other").write_text("other")
        (fake / ".claude-plugin").mkdir()
        (fake / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "agent-kaizen"}))
        old = self.home / "plugins/cache/market/agent-kaizen/0.1.0/scripts"
        old.mkdir(parents=True)
        (old / "kaizen-backup").write_text("old")
        self.bin.mkdir()
        (self.bin / "token-audit").symlink_to(fake / "scripts/other")
        (self.bin / "kaizen-backup").symlink_to(old / "kaizen-backup")
        (self.bin / "codex-review").symlink_to(self.home / "missing")
        result = self.run_link("--apply", root=fake)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("token-audit", "kaizen-backup", "codex-review"):
            self.assertEqual((self.bin / name).resolve(), (fake / "scripts" / name).resolve())
        self.assertEqual(list(self.bin.glob("*.replaced-*")), [])

    def test_symlinks_that_only_look_like_the_plugin_are_foreign(self):
        fake = self.home / "plugin"
        (fake / "scripts").mkdir(parents=True)
        for name in ("token-audit", "kaizen-backup", "codex-review"):
            (fake / "scripts" / name).write_text("source")
        elsewhere = self.home / "elsewhere/scripts"
        cache_other = self.home / "plugins/cache/market/agent-kaizen/0.1.0/scripts"
        for folder in (elsewhere, cache_other):
            folder.mkdir(parents=True)
            (folder / "token-audit").write_text("mine")
        (cache_other / "kaizen-backup").write_text("mine")
        self.bin.mkdir()
        (self.bin / "token-audit").symlink_to(elsewhere / "token-audit")  # right name, not a plugin cache
        (self.bin / "kaizen-backup").symlink_to(cache_other / "token-audit")  # cache, wrong file
        (self.bin / "codex-review").symlink_to(cache_other / "kaizen-backup")  # cache, wrong file
        self.assertEqual(self.run_link("--apply", root=fake).returncode, 0)
        self.assertEqual((self.bin / "token-audit").resolve(), (elsewhere / "token-audit").resolve())
        self.assertEqual((self.bin / "kaizen-backup").resolve(), (cache_other / "token-audit").resolve())
        self.assertEqual((self.bin / "codex-review").resolve(), (cache_other / "kaizen-backup").resolve())

    def test_another_plugins_cache_copy_is_foreign_and_own_cache_and_marketplace_copies_are_replaced(self):
        fake = self.home / "plugin"
        (fake / "scripts").mkdir(parents=True)
        (fake / ".claude-plugin").mkdir()
        (fake / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "agent-kaizen"}))
        names = ("token-audit", "kaizen-backup", "codex-review")
        for name in names:
            (fake / "scripts" / name).write_text("source")
        copies = {"token-audit": "plugins/cache/market/other-plugin/1.0.0/scripts",
                  "kaizen-backup": "plugins/cache/market/agent-kaizen/0.1.0/scripts",
                  "codex-review": "plugins/marketplaces/market/agent-kaizen/scripts"}
        self.bin.mkdir()
        for name, folder in copies.items():
            (self.home / folder).mkdir(parents=True)
            (self.home / folder / name).write_text("old")
            (self.bin / name).symlink_to(self.home / folder / name)
        result = self.run_link("--apply", root=fake)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.bin / "token-audit").resolve(), (self.home / copies["token-audit"] / "token-audit").resolve())
        self.assertIn("DRIFT token-audit", result.stdout)
        for name in ("kaizen-backup", "codex-review"):
            self.assertEqual((self.bin / name).resolve(), (fake / "scripts" / name).resolve())
        self.assertEqual(list(self.bin.glob("*.replaced-*")), [])

    def test_cache_copy_name_falls_back_to_the_plugin_root_folder_name_without_a_manifest(self):
        fake = self.home / "agent-kaizen"
        (fake / "scripts").mkdir(parents=True)
        (fake / "scripts/kaizen-backup").write_text("source")
        old = self.home / "plugins/cache/market/agent-kaizen/0.1.0/scripts"
        old.mkdir(parents=True)
        (old / "kaizen-backup").write_text("old")
        self.bin.mkdir()
        (self.bin / "kaizen-backup").symlink_to(old / "kaizen-backup")
        self.assertEqual(self.run_link("--apply", "--only", "kaizen-backup", root=fake).returncode, 0)
        self.assertEqual((self.bin / "kaizen-backup").resolve(), (fake / "scripts/kaizen-backup").resolve())

    def test_unlink_removes_identical_copies_and_keeps_changed_ones_with_a_reason(self):
        result = self.run_link("--apply", "--mode", "copy", "--only", "token-audit,preambles,kaizen-backup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("copied", result.stdout)
        self.assertNotIn("copyed", result.stdout)
        self.assertFalse((self.bin / "token-audit").is_symlink())
        (self.bin / "kaizen-backup").write_text("edited")
        extra = self.bin / "preambles/extra.md"
        extra.write_text("mine")
        result = self.run_link("--unlink", "--only", "token-audit,preambles,kaizen-backup")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.bin / "token-audit").exists())
        self.assertEqual((self.bin / "kaizen-backup").read_text(), "edited")
        self.assertTrue(extra.is_file())
        for line in result.stdout.splitlines():
            if "kaizen-backup" in line or "preambles" in line:
                self.assertIn("differs", line)
        extra.unlink()
        self.assertEqual(self.run_link("--unlink", "--only", "preambles").returncode, 0)
        self.assertFalse((self.bin / "preambles").exists())

    def test_unlink_still_works_when_settings_are_malformed(self):
        self.assertEqual(self.run_link("--apply", "--only", "token-audit").returncode, 0)
        (self.home / "agent-kaizen.json").write_text("{not json")
        result = self.run_link("--unlink", "--only", "token-audit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning", result.stderr)
        self.assertFalse((self.bin / "token-audit").exists())
        self.assertEqual(self.run_link("--apply", "--only", "token-audit").returncode, 2)

    def test_restore_replaced_picks_the_newest_suffix_not_the_newest_mtime(self):
        self.bin.mkdir()
        names = {"token-audit.replaced-20261104": "oldest day", "token-audit.replaced-20261105": "first of day",
                 "token-audit.replaced-20261105-2": "newest", "token-audit.replaced-20261105-1": "second of day"}
        for index, (name, text) in enumerate(names.items()):
            (self.bin / name).write_text(text)
            os.utime(self.bin / name, (1_000_000 - index * 1000, 1_000_000 - index * 1000))
        os.utime(self.bin / "token-audit.replaced-20261104", (2_000_000, 2_000_000))  # newest mtime
        result = self.run_link("--unlink", "--restore-replaced", "--only", "token-audit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.bin / "token-audit").read_text(), "newest")

    def test_only_strips_whitespace_around_names(self):
        result = self.run_link("--apply", "--only", "token-audit, preambles ,")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.bin / "token-audit").is_symlink())
        self.assertTrue((self.bin / "preambles").is_symlink())
        self.assertFalse((self.bin / "usage-series").exists())


if __name__ == "__main__":
    unittest.main()
