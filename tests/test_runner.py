"""Offline tests for the scheduled runner and shared config model."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import shlex
import subprocess
import sys
import time
import unittest
import uuid
from unittest.mock import patch

from test_scripts import StubCase, write, jsonl, executable


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class RunnerTests(StubCase):
    def setUp(self):
        super().setUp()
        self.env.pop("CLAUDE_CONFIG_DIR", None)
        self.env.pop("CODEX_HOME", None)
        self.config_dir = self.root / "custom claude config"
        self.env["CLAUDE_CONFIG_DIR"] = str(self.config_dir)
        environment = patch.dict(os.environ, self.env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.project = self.work
        (self.project / "docs/kaizen").mkdir(parents=True)
        self.global_path = self.config_dir / "agent-kaizen.json"
        self.project_path = self.project / "docs/kaizen/config.json"
        self.runner = runpy.run_path(str(SCRIPTS / "kaizen-scheduled"))

    def config(self, *args, code=0):
        return self.run_script("kaizen-scheduled", "config", *args, code=code)

    def test_defaults_and_global_reports(self):
        result = self.config("show")
        self.assertEqual(json.loads(result.stdout), {
            "enabled": {"value": True, "source": "default"},
            "schedule": {"value": "active", "source": "default"},
            "scheduledAutonomy": {"value": "propose", "source": "default"},
            "retention": {"value": "auto", "source": "default"},
            "retentionOverrides": {"value": {}, "source": "default"},
            "reports": None,
        })
        self.assertEqual(result.stderr, "")
        self.assertFalse(self.config_dir.exists())

    def test_precedence(self):
        cases = [
            ({"enabled": False}, {"schedule": "always"}, "schedule", "off", "global"),
            ({"schedule": "active"}, {"schedule": "off"}, "schedule", "off", "project"),
            ({"schedule": "off"}, {"schedule": "active"}, "schedule", "active", "project"),
            ({"scheduledAutonomy": "propose"}, {"scheduledAutonomy": "auto"},
             "scheduledAutonomy", "auto", "project"),
            ({"schedule": "always"}, {}, "schedule", "always", "global"),
        ]
        for global_cfg, project_cfg, name, value, source in cases:
            with self.subTest(global_cfg=global_cfg, project_cfg=project_cfg):
                write(self.global_path, json.dumps(global_cfg))
                write(self.project_path, json.dumps(project_cfg))
                data = self.runner["effective"](self.project)
                self.assertEqual(data[name], {"value": value, "source": source})
                if global_cfg.get("enabled") is False:
                    self.assertEqual(data["enabled"], {"value": False, "source": "global"})

    def test_config_typed_validators(self):
        valid = self.runner["valid_value"]
        with patch.dict(self.runner["SCHEMA"], {"count": {"kind": "int", "minimum": 5}}):
            self.assertTrue(valid("count", 5))
            for value in (True, "5", 4.0, 4, None):
                with self.subTest(value=value):
                    self.assertFalse(valid("count", value))
        self.assertTrue(valid("retention", "off"))
        for value in ("never", True, [], {}):
            self.assertFalse(valid("retention", value))
        for value in ({}, {"samples": {}}, {"samples": {"days": 30, "hours": 1, "maxMB": 2}}):
            self.assertTrue(valid("retentionOverrides", value))
        for value in ({"samples": {"days": 0}}, {"samples": {"weeks": 1}}, {"samples": 5},
                      {"samples": {"days": True}}, {"samples": {"hours": 1.0}},
                      {"samples": {"maxMB": "5"}}, {1: {"days": 30}}, [], None):
            with self.subTest(value=value):
                self.assertFalse(valid("retentionOverrides", value))

    def test_config_relative_paths_are_syntax_only(self):
        valid = self.runner["valid_relative_paths"]
        self.assertTrue(valid(["out", "build/cache"]))
        self.assertTrue(valid([]))
        for value in (["/abs"], [".."], ["a/../b"], ["."], [""], ["a//b"], ["C:x"],
                      ["a\\b"], ["a\0b"], ["a/./b"], ["a/"], "out", ("out",), [5]):
            with self.subTest(value=value):
                self.assertFalse(valid(value))
        with patch.dict(self.runner["SCHEMA"], {"folders": {"kind": "paths"}}):
            self.assertTrue(self.runner["valid_value"]("folders", ["out"]))
            self.assertFalse(self.runner["valid_value"]("folders", ["../out"]))

    def test_config_set_typed_values(self):
        schema = {"count": {"kind": "int", "minimum": 5, "default": 5},
                  "folders": {"kind": "paths", "default": []}}
        with patch.dict(self.runner["SCHEMA"], schema), \
                patch.dict(self.runner["DEFAULTS"], {name: spec["default"] for name, spec in schema.items()}):
            for assignment in ("count=no", "count=4", "count=4.0", "folders=notjson", 'folders=[".."]'):
                with self.subTest(assignment=assignment), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        self.runner["main"](["config", "set", "retention=off", assignment])
                    self.assertEqual(error.exception.code, 2)
                    self.assertFalse(self.global_path.exists())
            with redirect_stdout(io.StringIO()) as output:
                self.runner["main"](["config", "set", "count=6", 'folders=["build/cache"]'])
            self.assertEqual(json.loads(self.global_path.read_text()), {"count": 6, "folders": ["build/cache"]})
            shown = json.loads(output.getvalue())
            self.assertEqual(shown["count"], {"value": 6, "source": "global"})
            self.assertEqual(shown["folders"], {"value": ["build/cache"], "source": "global"})

    def test_config_retention_set_and_invalid_assignments(self):
        invalid = ("retention=never", "retentionOverrides=notjson", 'retentionOverrides={"samples":{"days":0}}')
        for existing in (False, True):
            for assignment in invalid:
                with self.subTest(existing=existing, assignment=assignment):
                    original = '{"schedule":"active"}\n'
                    if existing:
                        write(self.global_path, original)
                    self.config("set", "schedule=off", assignment, code=2)
                    self.assertEqual(self.global_path.exists(), existing)
                    if existing:
                        self.assertEqual(self.global_path.read_text(), original)
        self.config("set", "retention=off", 'retentionOverrides={"samples":{"days":30}}')
        stored = json.loads(self.global_path.read_text())
        self.assertEqual(stored["retention"], "off")
        self.assertEqual(stored["retentionOverrides"], {"samples": {"days": 30}})

    def test_config_retention_global_only(self):
        for name, value in (("retention", "off"), ("retentionOverrides", "{}")):
            for existing in (False, True):
                with self.subTest(name=name, existing=existing):
                    original = '{"schedule":"active"}\n'
                    if existing:
                        write(self.project_path, original)
                    else:
                        self.project_path.unlink(missing_ok=True)
                    result = self.config("set", "schedule=off", f"{name}={value}", "--for", self.project, code=2)
                    self.assertIn(f"{name} is global-only", result.stderr)
                    self.assertEqual(self.project_path.exists(), existing)
                    if existing:
                        self.assertEqual(self.project_path.read_text(), original)
                    self.assertFalse(self.global_path.exists())
        write(self.global_path, '{"retention":"off","retentionOverrides":{"samples":{"days":30}}}')
        write(self.project_path, '{"retention":"auto","retentionOverrides":{}}')
        result = self.config("show", "--for", self.project)
        self.assertEqual(result.stderr.splitlines(), [
            f"config: {self.project_path}: {name} is global-only, ignored"
            for name in ("retention", "retentionOverrides")])
        shown = json.loads(result.stdout)
        self.assertEqual(shown["retention"], {"value": "off", "source": "global"})
        self.assertEqual(shown["retentionOverrides"], {"value": {"samples": {"days": 30}}, "source": "global"})

    def test_config_retention_invalid_values_warn_and_use_defaults(self):
        for name, value, fallback in (("retention", "never", "auto"),
                                      ("retentionOverrides", {"samples": {"days": 0}}, {}),
                                      ("retentionOverrides", [], {})):
            with self.subTest(name=name, value=value):
                write(self.global_path, json.dumps({name: value}))
                result = self.config("show")
                shown = value if isinstance(value, str) else json.dumps(value)
                self.assertEqual(result.stderr, f"config: {self.global_path}: {name}={shown} invalid, using {fallback}\n")
                self.assertEqual(json.loads(result.stdout)[name], {"value": fallback, "source": "default"})

    def test_interactive_autonomy_is_ignored(self):
        write(self.global_path, '{"autonomy": "auto"}')
        write(self.project_path, '{"autonomy": "auto"}')
        self.assertEqual(self.runner["effective"](self.project)["scheduledAutonomy"],
                         {"value": "propose", "source": "default"})

    def test_set_global_boolean_and_multiple_settings(self):
        result = self.config("set", "enabled=false", "schedule=always", "scheduledAutonomy=auto")
        self.assertEqual(json.loads(self.global_path.read_text()),
                         {"enabled": False, "schedule": "always", "scheduledAutonomy": "auto"})
        data = json.loads(result.stdout)
        self.assertEqual(data["enabled"], {"value": False, "source": "global"})
        self.assertEqual(data["schedule"], {"value": "off", "source": "global"})
        self.assertEqual(data["scheduledAutonomy"], {"value": "auto", "source": "global"})
        self.assertEqual(data, json.loads(self.config("show").stdout))
        self.config("set", "enabled=true")
        self.assertIs(json.loads(self.global_path.read_text())["enabled"], True)
        self.assertFalse((self.home / ".claude").exists())

    def test_project_enabled_is_rejected_without_writes(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                original = '{"autonomy":"safe"}\n'
                if existing:
                    write(self.project_path, original)
                result = self.config("set", "--for", self.project,
                                     "schedule=always", "enabled=false", code=2)
                self.assertIn("enabled is global-only", result.stderr)
                self.assertEqual(self.project_path.read_text() if existing else None,
                                 original if existing else None)
                self.assertEqual(self.project_path.exists(), existing)
                self.assertFalse(self.global_path.exists())

    def test_set_project_preserves_other_keys_order_and_format(self):
        write(self.project_path, '{"maxChangesPerRun":3,"autonomy":"safe",'
              '"scheduledAutonomy":"propose","allowInstalls":false}')
        result = self.config("set", "--for", self.project, "scheduledAutonomy=auto")
        expected = {"maxChangesPerRun": 3, "autonomy": "safe",
                    "scheduledAutonomy": "auto", "allowInstalls": False}
        self.assertEqual(self.project_path.read_text(), json.dumps(expected, indent=2) + "\n")
        self.assertEqual(list(json.loads(self.project_path.read_text())), list(expected))
        self.assertEqual(json.loads(result.stdout)["scheduledAutonomy"],
                         {"value": "auto", "source": "project"})
        self.assertEqual(json.loads(result.stdout),
                         json.loads(self.config("show", "--for", self.project).stdout))
        self.assertEqual(list(self.project_path.parent.iterdir()), [self.project_path])

    def test_set_project_requires_kaizen_directory(self):
        target = self.root / "missing project"
        result = self.config("set", "--for", target, "schedule=active", code=2)
        self.assertIn("must contain docs/kaizen/", result.stderr)
        self.assertFalse(target.exists())
        self.assertFalse(self.global_path.exists())

    def test_invalid_assignments_write_nothing(self):
        invalid = ("colour=red", "schedule=weekly", "scheduledAutonomy=safe",
                   "enabled=0", "enabled=False", "schedule", "=active")
        for project in (False, True):
            path = self.project_path if project else self.global_path
            arguments = ("--for", self.project) if project else ()
            for existing in (False, True):
                for assignment in invalid:
                    with self.subTest(project=project, existing=existing, assignment=assignment):
                        original = '{"autonomy": "auto"}\n'
                        if existing:
                            write(path, original)
                        self.config("set", *arguments, "schedule=off", assignment, code=2)
                        self.assertEqual(path.exists(), existing)
                        if existing:
                            self.assertEqual(path.read_text(), original)
                        self.assertFalse(list(path.parent.glob("config.json.*")))

    def test_malformed_configs_are_read_as_empty_but_never_overwritten(self):
        for project in (False, True):
            path = self.project_path if project else self.global_path
            arguments = ("--for", self.project) if project else ()
            for content in ("{oops", "[]", "null", '"text"', "42"):
                with self.subTest(project=project, content=content):
                    write(path, content)
                    original = path.read_bytes()
                    result = self.config("set", *arguments, "schedule=always", code=2)
                    self.assertEqual(result.stderr,
                                     f"config: {path} is not valid JSON; fix or remove it\n")
                    self.assertEqual(path.read_bytes(), original)
                    errors = io.StringIO()
                    with redirect_stderr(errors):
                        self.assertEqual(self.runner["load_config"](path), {})
                    self.assertEqual(len(errors.getvalue().splitlines()), 1)
                    shown = self.config("show", *arguments)
                    self.assertEqual(json.loads(shown.stdout)["schedule"],
                                     {"value": "active", "source": "default"})
                    self.assertEqual(len(shown.stderr.splitlines()), 1)
            path.unlink()

    def test_invalid_values_fall_through_with_warnings(self):
        write(self.global_path, '{"schedule": "weekly"}')
        result = self.config("show")
        self.assertEqual(result.stderr,
                         f"config: {self.global_path}: schedule=weekly invalid, using active\n")
        self.assertEqual(json.loads(result.stdout)["schedule"],
                         {"value": "active", "source": "default"})
        write(self.global_path, '{"schedule": "always", "scheduledAutonomy": "auto"}')
        write(self.project_path, '{"schedule": "weekly", "scheduledAutonomy": "safe"}')
        result = self.config("show", "--for", self.project)
        self.assertEqual(result.stderr.splitlines(), [
            f"config: {self.project_path}: schedule=weekly invalid, using always",
            f"config: {self.project_path}: scheduledAutonomy=safe invalid, using auto",
        ])
        self.assertEqual(json.loads(result.stdout)["schedule"],
                         {"value": "always", "source": "global"})
        self.assertEqual(json.loads(result.stdout)["scheduledAutonomy"],
                         {"value": "auto", "source": "global"})

    def test_enabled_requires_json_boolean(self):
        for value in (0, 1, "false", None, [], {}):
            with self.subTest(value=value):
                write(self.global_path, json.dumps({"enabled": value}))
                result = self.config("show")
                self.assertEqual(json.loads(result.stdout)["enabled"],
                                 {"value": True, "source": "default"})
                self.assertIn(" invalid, using true\n", result.stderr)
                self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_project_enabled_is_logged_and_ignored(self):
        write(self.project_path, '{"enabled": false}')
        result = self.config("show", "--for", self.project)
        self.assertEqual(result.stderr, f"config: {self.project_path}: enabled is global-only, ignored\n")
        self.assertEqual(json.loads(result.stdout)["enabled"],
                         {"value": True, "source": "default"})

    def test_keys_and_reports_path(self):
        key = self.runner["key"]
        self.assertNotEqual(key(Path("/w/a-b")), key(Path("/w/a/b")))
        for path in (self.project, Path("/"), self.root / ("a" * 80), self.root / "---"):
            with self.subTest(path=path):
                self.assertRegex(key(path), r"^[A-Za-z0-9-]{1,40}-[0-9a-f]{12}$")
                self.assertTrue(key(path).endswith(hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]))
        self.assertEqual(key(self.project / "docs/.."), key(self.project))
        result = self.config("show", "--for", self.project)
        self.assertEqual(json.loads(result.stdout)["reports"],
                         str(self.config_dir / "audits/projects" / key(self.project)) + "/")

    def test_paths_are_resolved_at_call_time(self):
        self.assertEqual(self.runner["claude_home"](), self.config_dir)
        self.assertEqual(self.runner["claude_json"](), self.config_dir / ".claude.json")
        self.assertEqual(self.runner["global_config_path"](), self.global_path)
        self.assertEqual(self.runner["project_config_path"](self.project), self.project_path)
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "~/other", "CODEX_HOME": "~/codex-other"}):
            self.assertEqual(self.runner["audits_dir"](), self.home / "other/audits")
            self.assertEqual(self.runner["codex_home"](), self.home / "codex-other")
        with patch.dict(os.environ):
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
            os.environ.pop("CODEX_HOME", None)
            self.assertEqual(self.runner["claude_home"](), self.home / ".claude")
            self.assertEqual(self.runner["claude_json"](), self.home / ".claude.json")
            self.assertEqual(self.runner["codex_home"](), self.home / ".codex")

    def test_write_config_uses_atomic_replace(self):
        original = '{"autonomy": "safe"}\n'
        write(self.global_path, original)
        replace = os.replace

        def observe_replace(source, destination):
            self.assertEqual(Path(source).parent, self.global_path.parent)
            self.assertEqual(Path(destination), self.global_path)
            self.assertEqual(self.global_path.read_text(), original)
            self.assertEqual(json.loads(Path(source).read_text()),
                             {"autonomy": "safe", "schedule": "off"})
            replace(source, destination)

        with patch.object(os, "replace", side_effect=observe_replace) as mocked:
            self.runner["write_config"](self.global_path, {"schedule": "off"})
        mocked.assert_called_once()
        self.assertEqual(list(self.config_dir.iterdir()), [self.global_path])

    def test_paths_helper_copies_are_identical(self):
        copies = {}
        start = b"# --- paths helper ---"
        end = b"# --- end paths helper ---"
        for path in SCRIPTS.iterdir():
            if not path.is_file():
                continue
            content = path.read_bytes()
            if start in content:
                self.assertEqual(content.count(start), 1, path.name)
                self.assertEqual(content.count(end), 1, path.name)
                copies[path.name] = content.split(start, 1)[1].split(end, 1)[0]
        self.assertIn("kaizen-scheduled", copies)
        self.assertEqual(len(set(copies.values())), 1, list(copies))

    def test_help_commands(self):
        for command in ((), ("config",), ("config", "show"), ("config", "set"), ("audit",), ("review",)):
            with self.subTest(command=command):
                self.run_script("kaizen-scheduled", *command, "--help")
        help_text = self.run_script("kaizen-scheduled", "--help").stdout
        self.assertIn("audit", help_text)
        self.assertIn("review", help_text)
        self.assertFalse(self.record.exists())


class DiscoveryCase(StubCase):
    def setUp(self):
        super().setUp()
        self.cfg = self.root / "cfg"
        self.cx = self.root / "cx"
        self.audits = self.root / "audits"
        self.env.update(CLAUDE_CONFIG_DIR=str(self.cfg), CODEX_HOME=str(self.cx),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid")
        environment = patch.dict(os.environ, self.env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        spec = importlib.util.spec_from_loader("kaizen_scheduled", importlib.machinery.SourceFileLoader(
            "kaizen_scheduled", str(SCRIPTS / "kaizen-scheduled")))
        self.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.runner)

    def project(self, name):
        path = self.root / name
        write(path / "docs/kaizen/config.json", "{}")
        return path

    def claude_session(self, path, name="session", folder="lossy-folder"):
        return jsonl(self.cfg / "projects" / folder / (name + ".jsonl"),
                     [dict(type="user", cwd=str(path))])

    def codex_session(self, path, name="rollout"):
        return jsonl(self.cx / "sessions/2026/10/20" / (name + ".jsonl"),
                     [dict(type="session_meta", payload=dict(cwd=str(path)))])

    def preview(self, *args):
        return self.run_script("kaizen-scheduled", "review", "--dry-run", "--audits", self.audits, *args).stdout

    def discover(self, project_dirs=None):
        return self.runner.discover(self.cfg / "projects", self.cx / "sessions",
                                    self.runner.read_index(self.audits), project_dirs)

    def git(self, path, *args):
        result = subprocess.run(["git", "-C", str(path), *args], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def repo(self, name):
        path = self.project(name)
        self.git(path, "init")
        self.git(path, "add", "docs")
        self.git(path, "commit", "-m", "enroll")
        return path


class DiscoveryTests(DiscoveryCase):
    def test_json_preview_autonomy_sources_without_writes(self):
        one, two = self.project('one'), self.project('two')
        write(one / 'docs/kaizen/config.json', '{"scheduledAutonomy":"auto"}')
        write(self.cfg / 'agent-kaizen.json', '{"enabled":false,"scheduledAutonomy":"propose"}')
        rows = json.loads(self.preview('--json', '--project-dir', str(one), '--project-dir', str(two)))
        self.assertEqual(rows, [dict(path=str(one), scheduledAutonomy='auto', source='project'),
                                dict(path=str(two), scheduledAutonomy='propose', source='global')])
        self.assertFalse(self.audits.exists())
        result = self.run_script('kaizen-scheduled', 'review', '--json', code=2)
        self.assertIn('--json requires --dry-run', result.stderr)

    def test_json_preview_stays_json_with_corrupt_index(self):
        one = self.project('one')
        write(self.audits / 'projects/index.json', '{broken')
        rows = json.loads(self.preview('--json', '--project-dir', str(one)))
        self.assertEqual([row['path'] for row in rows], [str(one)])

    def test_discovery_union_sorted_and_deduplicated(self):
        a, b, c = [self.project(name) for name in ("a", "b", "c")]
        self.claude_session(a)
        self.codex_session(a, "a")
        self.codex_session(b, "b")
        write(self.audits / "projects/index.json", json.dumps({"v": 1, "projects": {str(c): "old"}}))
        output = self.preview()
        self.assertEqual([line for line in output.splitlines() if line.startswith("project:")],
                         [f"project: {path}" for path in (a, b, c)])
        for path in (a, b, c):
            self.assertIn(f"  key: {self.runner.key(path)}", output)

    def test_lossy_folder_names_do_not_merge_projects(self):
        a, b = self.project("w/a-b"), self.project("w/a/b")
        self.claude_session(a, "one", "-w-a-b")
        self.claude_session(b, "two", "-w-a-b")
        output = self.preview()
        keys = [line.removeprefix("  key: ") for line in output.splitlines() if line.startswith("  key:")]
        self.assertEqual(len(set(keys)), 2)
        for value in keys:
            self.assertRegex(value, r"^[A-Za-z0-9-]{1,40}-[0-9a-f]{12}$")

    def test_walk_up_nearest_enrollment_and_resolve(self):
        outer = self.project("outer")
        inner = self.project("outer/inner")
        child = inner / "src"
        child.mkdir()
        self.claude_session(child / "../src")
        alias = self.root / "alias"
        alias.symlink_to(child, target_is_directory=True)
        self.codex_session(alias)
        output = self.preview()
        self.assertEqual(output.count("project: "), 1)
        self.assertIn(f"project: {inner}\n", output)
        self.assertNotIn(f"project: {outer}\n", output)

    def test_not_enrolled_and_deleted_candidates(self):
        missing = self.root / "deleted"
        self.claude_session(missing, "deleted")
        self.claude_session(self.work, "plain")
        output = self.preview()
        self.assertIn(f"not enrolled: {self.work} (no docs/kaizen/ in it or any parent)", output)
        self.assertNotIn(str(missing), output)
        self.assertNotIn("project: ", output)
        self.assertIn("no projects found; enrol a project with /agent-kaizen:start or pass --project-dir", output)

    def test_explicit_directories_replace_discovery_without_walkup(self):
        a, b, c = [self.project(name) for name in ("a", "b", "c")]
        self.claude_session(b)
        write(self.audits / "projects/index.json", json.dumps({"v": 1, "projects": {str(c): "old"}}))
        child = a / "src"
        child.mkdir()
        output = self.preview("--project-dir", a, "--project-dir", child, "--project-dir", self.work)
        self.assertEqual([line for line in output.splitlines() if line.startswith("project:")], [f"project: {a}"])
        self.assertIn(f"not enrolled: {child}", output)
        self.assertIn(f"not enrolled: {self.work}", output)
        self.assertEqual(self.discover([]), ([], []))

    def test_first_cwd_line_limit_and_malformed_rows(self):
        path = write(self.root / "prefix.jsonl", 'bad "cwd"\n[]\n{"payload":{"cwd":"nested"}}\n')
        with path.open("a") as stream:
            stream.write('{"cwd":null}\n{"cwd":"first"}\n{"cwd":"second"}\n')
        self.assertIsNone(self.runner.first_cwd(path, 4))
        self.assertEqual(self.runner.first_cwd(path), "first")
        self.assertIsNone(self.runner.first_cwd(self.root / "absent"))
        jsonl(path, [{}] * 50 + [{"cwd": "late"}])
        self.assertIsNone(self.runner.first_cwd(path))

    def test_only_five_newest_top_level_claude_sessions(self):
        old, current, nested = [self.project(name) for name in ("old", "current", "nested")]
        path = self.claude_session(old, "old")
        os.utime(path, (1, 1))
        for number in range(5):
            self.claude_session(current, str(number))
        self.claude_session(nested, "subagents/nested")
        (self.cfg / "projects" / "encoded-path-only").mkdir()
        self.assertEqual([project.canonical for project in self.discover()[0]], [current])

    def test_codex_recent_first_line_only(self):
        current, old, later = [self.project(name) for name in ("current", "old", "later")]
        self.codex_session(current)
        path = self.codex_session(old, "old")
        expired = time.time() - 31 * 24 * 60 * 60
        os.utime(path, (expired, expired))
        jsonl(path.parent / "later.jsonl", [{}, {"payload": {"cwd": str(later)}}])
        write(path.parent / "bad.jsonl", "invalid\n")
        self.assertEqual([project.canonical for project in self.discover()[0]], [current])

    @unittest.skipUnless(shutil.which("git"), "git required")
    def test_worktrees_group_main_and_separate_repositories(self):
        main = self.repo("z-main")
        worktree = self.root / "a-worktree"
        unmentioned = self.root / "unmentioned"
        self.git(main, "worktree", "add", str(worktree), "-b", "wt")
        self.git(main, "worktree", "add", str(unmentioned), "-b", "other")
        other = self.repo("other")
        nested = self.repo("z-main/nested")
        for number, path in enumerate((main, worktree, other, nested)):
            self.claude_session(path, str(number))
        projects, _ = self.discover()
        self.assertEqual([project.canonical for project in projects], sorted([main, other, nested]))
        project = next(project for project in projects if project.canonical == main)
        self.assertEqual(project.paths, sorted([main, worktree, unmentioned]))
        self.assertEqual(project.folder, self.cfg / "audits/projects" / project.key)
        output = self.preview()
        self.assertEqual(output.count("project: "), 3)
        self.assertIn("  paths: " + ", ".join(map(str, sorted([main, worktree, unmentioned]))), output)
        # A run from one linked worktree uses that enrolled directory as canonical.
        selected = self.discover([worktree])[0][0]
        self.assertEqual(selected.canonical, worktree)
        self.assertEqual(selected.paths, project.paths)
        self.runner.write_index(self.audits, projects)
        index = self.runner.read_index(self.audits)
        for path in project.paths:
            self.assertEqual(index[str(path)], project.key)

    def test_git_fallback_relative_common_dir_and_lexical_canonical(self):
        a, b = self.project("a"), self.project("b")
        replies = ["../shared", "../shared", ""]
        with patch.object(self.runner, "_git", side_effect=replies) as git:
            projects, _ = self.discover([b, a])
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].canonical, a)
        self.assertEqual(projects[0].paths, [a, b])
        self.assertEqual(git.call_args_list[0].args, (a, "rev-parse", "--git-common-dir"))

    def test_missing_git_is_not_fatal(self):
        path = self.project("standalone")
        with patch.object(self.runner.subprocess, "run", side_effect=FileNotFoundError):
            projects, _ = self.discover([path])
        self.assertEqual(projects[0].canonical, path)

    def test_index_atomic_merge_preserves_missing_and_unselected_entries(self):
        a, b = self.project("a"), self.project("b")
        gone = str(self.root / "gone")
        index_path = write(self.audits / "projects/index.json",
                           json.dumps({"v": 1, "projects": {gone: "keep"}}))
        projects = self.discover([a, b])[0]
        replace = os.replace

        def observe(source, target):
            self.assertEqual(Path(source).parent, index_path.parent)
            self.assertEqual(Path(target), index_path)
            self.assertEqual(json.loads(index_path.read_text())["projects"], {gone: "keep"})
            replace(source, target)

        with patch.object(os, "replace", side_effect=observe) as mocked:
            self.runner.write_index(self.audits, projects)
        mocked.assert_called_once()
        expected = {gone: "keep", **{str(p.canonical): p.key for p in projects}}
        self.runner.write_index(self.audits, self.discover([a])[0])
        self.assertEqual(json.loads(index_path.read_text()), {"v": 1, "projects": expected})
        self.assertEqual(list(index_path.parent.iterdir()), [index_path])

    def test_invalid_index_is_logged_and_missing_index_is_silent(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.runner.read_index(self.audits), {})
        self.assertEqual(output.getvalue(), "")
        for content in ("bad", "[]", '{"v":2,"projects":{}}', '{"v":1,"projects":{"x":3}}'):
            write(self.audits / "projects/index.json", content)
            with self.subTest(content=content), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(self.runner.read_index(self.audits), {})
            self.assertIn("invalid or unreadable", output.getvalue())
            self.assertRegex(output.getvalue(), r"^\d{4}-\d\d-\d\dT.*\+00:00 index:")

    def test_preview_has_no_writes_and_matches_index_writer(self):
        path = self.project("enrolled")
        self.claude_session(path)
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        directories = {p for p in self.root.rglob("*") if p.is_dir()}
        output = self.preview("--now", "2026-10-29T00:00:00Z")
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes()
                                  for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(directories, {p for p in self.root.rglob("*") if p.is_dir()})
        self.assertFalse(self.audits.exists())
        prefix = "index.json (not written, dry run): "
        document = json.loads(next(line[len(prefix):] for line in output.splitlines() if line.startswith(prefix)))
        self.runner.write_index(self.audits, self.discover()[0])
        self.assertEqual(document, json.loads((self.audits / "projects/index.json").read_text()))

    def test_preview_config_sources_and_only_git_subprocesses(self):
        path = self.project("enrolled")
        self.claude_session(path)
        write(self.cfg / "agent-kaizen.json", '{"schedule":"off"}')
        write(path / "docs/kaizen/config.json", '{"schedule":"always"}')
        for name in ("curl", "wget", "claude"):
            executable(self.bin / name, '#!/bin/sh\nprintf called >> "$RECORD"\n')
        output = self.preview()
        self.assertIn("config: enabled=true (default); schedule=always (project); scheduledAutonomy=propose (default)", output)
        self.assertIn("gate: due (schedule always)", output)
        self.assertFalse(self.record.exists())
        with patch.object(self.runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")) as run:
            self.discover()
        self.assertTrue(run.called)
        for call in run.call_args_list:
            self.assertEqual(call.args[0][0], "git")
            self.assertEqual(call.kwargs, {"capture_output": True, "text": True})


class GateTests(DiscoveryCase):
    def preview(self, *args):
        return super().preview("--now", "2026-10-29T12:00:00Z", *args)

    def stamp(self, path, when="2026-10-28T12:00:00Z"):
        stamp = self.runner.parse_time(when).timestamp()
        os.utime(path, (stamp, stamp))
        return path

    def state(self, project, **values):
        folder = self.audits / "projects" / self.runner.key(project)
        return write(folder / "state.json", json.dumps(values))

    def decision(self, path, state=None, projects=None, cache=None):
        projects = projects if projects is not None else self.discover([path])[0]
        project = next(project for project in projects if project.canonical == path)
        return self.runner.gate(project, projects, self.runner.effective(path), state or {},
                                self.runner.parse_time("2026-10-29T12:00:00Z"),
                                self.cfg / "projects", self.cx / "sessions", cache)

    def test_own_sessions_and_subagents_are_excluded(self):
        path = self.project("own")
        self.state(path, reviewed_at="2026-10-20T00:00:00Z", ignore_sessions=["own-1"])
        parent = self.stamp(self.claude_session(path, "own-1"))
        child = self.stamp(jsonl(parent.parent / "own-1/subagents/x.jsonl", [{"cwd": str(path)}]))
        output = self.preview("--project-dir", path)
        self.assertIn("gate: skipped: no activity since 2026-10-20\n", output)
        self.assertIn("reviewed_at: 2026-10-20T00:00:00Z\n", output)
        self.assertIn("cutoff: 2026-10-20T00:00:00Z\n", output)
        parent.rename(parent.with_name("other-1.jsonl"))
        self.assertIn("gate: due (activity (claude transcript))", self.preview("--project-dir", path))
        parent.with_name("other-1.jsonl").unlink()
        child.parent.parent.rename(child.parent.parent.with_name("other-1"))
        self.assertIn("gate: due (activity (claude transcript))", self.preview("--project-dir", path))

    def test_default_cutoff_and_strict_mtime(self):
        path = self.project("default")
        session = self.claude_session(path)
        for when, due in (("2026-10-27T12:00:00Z", True), ("2026-10-21T12:00:00Z", False),
                          ("2026-10-22T12:00:00Z", False)):
            with self.subTest(when=when):
                self.stamp(session, when)
                output = self.preview("--project-dir", path)
                self.assertIn("cutoff: 2026-10-22T12:00:00Z\n", output)
                self.assertIn("reviewed_at: never\n", output)
                self.assertIn("gate: due" if due else "gate: skipped: no activity since 2026-10-22\n", output)

    def test_collision_uses_cwd_instead_of_folder(self):
        dash, nested = self.project("w/a-b"), self.project("w/a/b")
        folder = self.runner.re.sub(r"[^a-zA-Z0-9]", "-", str(dash))
        self.stamp(self.claude_session(dash, "old", folder), "2026-10-01T00:00:00Z")
        self.stamp(self.claude_session(nested, "recent", folder))
        output = self.preview("--project-dir", dash, "--project-dir", nested)
        blocks = {block.splitlines()[0]: block for block in output.split("project: ")[1:]}
        self.assertIn("gate: skipped: no activity since 2026-10-22", blocks[str(dash)])
        self.assertIn("gate: due (activity (claude transcript))", blocks[str(nested)])

    def test_no_cwd_fallback_and_cwd_always_overrides_folder(self):
        path = self.project("fallback")
        folder = self.runner.re.sub(r"[^a-zA-Z0-9]", "-", str(path))
        session = self.stamp(write(self.cfg / "projects/other/no-cwd.jsonl", "{}\n"))
        self.assertFalse(self.decision(path)[0])
        encoded = self.cfg / "projects" / folder / session.name
        encoded.parent.mkdir()
        session.rename(encoded)
        self.assertTrue(self.decision(path)[0])
        self.stamp(jsonl(encoded, [{"cwd": str(path) + "-sibling"}]))
        self.assertFalse(self.decision(path)[0])
        self.stamp(write(encoded, "{}\n" * 50 + json.dumps({"cwd": str(path) + "-sibling"}) + "\n"))
        self.assertTrue(self.decision(path)[0])

    def test_subagents_follow_parent_or_use_own_cwd_if_parent_missing(self):
        path = self.project("subagents")
        parent = self.stamp(self.claude_session(self.root / "unrelated", "session.with.dot"),
                            "2026-10-01T00:00:00Z")
        child = self.stamp(jsonl(parent.parent / "session.with.dot/subagents/a.jsonl", [{"cwd": str(path)}]))
        self.assertFalse(self.decision(path)[0])
        self.stamp(jsonl(parent, [{"cwd": str(path)}]), "2026-10-01T00:00:00Z")
        self.stamp(jsonl(child, [{"cwd": str(self.root / "elsewhere")}]))
        self.assertTrue(self.decision(path)[0])
        parent.unlink()
        self.assertFalse(self.decision(path)[0])
        self.stamp(jsonl(child, [{"cwd": str(path)}]))
        self.assertTrue(self.decision(path)[0])

    def test_codex_first_line_cwd_and_no_folder_fallback(self):
        path = self.project("codex")
        session = self.stamp(self.codex_session(path / "pkg"))
        self.assertEqual(self.decision(path), (True, "due: activity (codex session)"))
        for rows in ([{"payload": {"cwd": str(self.root / "other")}}], [{}],
                     [{}, {"payload": {"cwd": str(path)}}], [{"cwd": str(path)}]):
            with self.subTest(rows=rows):
                self.stamp(jsonl(session, rows))
                self.assertFalse(self.decision(path)[0])

    def test_schedule_order_and_sources(self):
        path = self.project("schedule")
        global_path, project_path = self.cfg / "agent-kaizen.json", path / "docs/kaizen/config.json"
        for global_cfg, project_cfg, expected in (
                ({}, {"schedule": "always"}, "gate: due (schedule always)"),
                ({}, {"schedule": "off"}, "gate: skipped: schedule off (project)"),
                ({"schedule": "off"}, {}, "gate: skipped: schedule off (global)"),
                ({"schedule": "off"}, {"schedule": "active"}, "gate: skipped: no activity since 2026-10-22"),
                ({"enabled": False}, {"schedule": "always"}, "skipped: disabled")):
            with self.subTest(global_cfg=global_cfg, project_cfg=project_cfg):
                write(global_path, json.dumps(global_cfg))
                write(project_path, json.dumps(project_cfg))
                self.assertIn(expected + "\n", self.preview("--project-dir", path))
                with patch.object(self.runner.Path, "glob", side_effect=AssertionError("must not scan")):
                    if expected != "gate: skipped: no activity since 2026-10-22":
                        self.decision(path, projects=[self.runner.Project(path, [path])])

    def test_nested_projects_and_per_run_caches(self):
        parent, child = self.project("n"), self.project("n/sub")
        session = self.stamp(self.claude_session(child / "pkg"))
        self.stamp(self.claude_session(parent, "stale"), "2026-10-01T00:00:00Z")
        projects = self.discover([parent, child])[0]
        cache = {}
        with patch.object(self.runner, "first_cwd", wraps=self.runner.first_cwd) as sniff:
            with patch.object(self.runner.os.path, "realpath", wraps=os.path.realpath) as resolve:
                self.assertFalse(self.decision(parent, projects=projects, cache=cache)[0])
                self.assertTrue(self.decision(child, projects=projects, cache=cache)[0])
        sniff.assert_called_once_with(session)
        resolve.assert_called_once_with(str(child / "pkg"))
        output = self.preview("--project-dir", parent, "--project-dir", child)
        self.assertEqual(output.count("gate: due"), 1)
        self.assertEqual(output.count("gate: skipped: no activity since 2026-10-22"), 1)
        session.unlink()
        self.stamp(self.codex_session(child / "pkg"))
        self.assertFalse(self.decision(parent, projects=projects)[0])
        self.assertTrue(self.decision(child, projects=projects)[0])

    def test_symlink_cwd_and_unrelated_sibling(self):
        path = self.project("real")
        link = self.root / "link"
        link.symlink_to(path, target_is_directory=True)
        (path / "sub").mkdir()
        for cwd, due in ((link / "sub", True), (path, True), (self.root / "real-sibling", False)):
            with self.subTest(cwd=cwd):
                session = self.stamp(self.claude_session(cwd))
                self.assertEqual(self.decision(path)[0], due)
        session.unlink()
        self.stamp(self.codex_session(link))
        self.assertEqual(self.decision(path), (True, "due: activity (codex session)"))

    @unittest.skipUnless(shutil.which("git"), "git required")
    def test_git_local_branches_but_not_remote_refs(self):
        self.env.update(GIT_AUTHOR_DATE="2026-10-01T00:00:00Z", GIT_COMMITTER_DATE="2026-10-01T00:00:00Z")
        path = self.repo("git")
        branch = self.git(path, "symbolic-ref", "--short", "HEAD").strip()
        self.assertFalse(self.decision(path)[0])
        self.git(path, "checkout", "-b", "recent")
        self.env.update(GIT_AUTHOR_DATE="2026-10-28T00:00:00Z", GIT_COMMITTER_DATE="2026-10-28T00:00:00Z")
        self.git(path, "commit", "--allow-empty", "-m", "activity")
        recent = self.git(path, "rev-parse", "HEAD").strip()
        self.git(path, "checkout", branch)
        self.assertEqual(self.decision(path), (True, "due: activity (git commit)"))
        self.assertIn("gate: due (activity (git commit))", self.preview("--project-dir", path))
        self.git(path, "update-ref", "refs/remotes/origin/main", recent)
        self.git(path, "branch", "-D", "recent")
        self.assertFalse(self.decision(path)[0])
        # A successful review's own commit predates the recorded exit time.
        self.git(path, "branch", "recent", recent)
        self.assertFalse(self.decision(path, {"reviewed_at": "2026-10-28T00:00:01Z"})[0])
        # A commit in the same second as the recorded exit is the review's own.
        self.assertFalse(self.decision(path, {"reviewed_at": "2026-10-28T00:00:00Z"})[0])

    def test_nul_in_transcript_cwd_is_not_fatal(self):
        path = self.project("nul")
        self.stamp(self.claude_session(Path(str(path) + "\0x")))
        self.stamp(self.codex_session(Path("/tmp/a\0b")))
        self.assertFalse(self.decision(path)[0])
        self.assertIn("project: ", self.preview("--project-dir", path))

    def test_git_failures_and_non_repository_are_not_activity(self):
        path = self.project("not-git")
        self.assertFalse(self.decision(path)[0])
        projects = [self.runner.Project(path, [path])]
        for failure in (FileNotFoundError("git missing"), OSError("git failed")):
            with self.subTest(failure=failure), patch.object(self.runner.subprocess, "run", side_effect=failure):
                self.assertFalse(self.decision(path, projects=projects)[0])

    @unittest.skipUnless(shutil.which("git"), "git required")
    def test_worktree_activity_counts_for_merged_project(self):
        self.env.update(GIT_AUTHOR_DATE="2026-10-01T00:00:00Z", GIT_COMMITTER_DATE="2026-10-01T00:00:00Z")
        main = self.repo("main")
        worktree = self.root / "worktree"
        self.git(main, "worktree", "add", str(worktree), "-b", "work")
        self.stamp(self.claude_session(worktree))
        output = self.preview("--project-dir", main, "--project-dir", worktree)
        self.assertEqual(output.count("project: "), 1)
        self.assertIn("gate: due (activity (claude transcript))", output)

    def test_state_loading_and_invalid_timestamp_fallback(self):
        path = self.project("state")
        project = self.runner.Project(path, [path], self.audits / "projects" / self.runner.key(path))
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.runner.read_state(project), {})
        self.assertEqual(output.getvalue(), "")
        state_path = self.state(path, status="ignored", ignore_sessions=["own"])
        self.assertEqual(self.runner.read_state(project), {"status": "ignored", "ignore_sessions": ["own"]})
        for content in ("{", "[]", "null", "42"):
            write(state_path, content)
            with self.subTest(content=content), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(self.runner.read_state(project), {})
            self.assertEqual(len(output.getvalue().splitlines()), 1)
            self.assertIn("state:", output.getvalue())
        with patch.object(Path, "read_text", side_effect=PermissionError()), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.runner.read_state(project), {})
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        for invalid in (None, 123, "bad", "2026-10-20", "2026-10-20T00:00:00"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(self.runner.parse_time(invalid))
                self.assertEqual(self.decision(path, {"reviewed_at": invalid}),
                                 (False, "skipped: no activity since 2026-10-22"))
        self.assertEqual(self.runner.parse_time("2026-10-29T05:00:00-07:00"),
                         self.runner.parse_time("2026-10-29T12:00:00Z"))

    def test_invalid_now_and_real_clock(self):
        path = self.project("clock")
        result = self.run_script("kaizen-scheduled", "review", "--dry-run", "--now", "bad", code=2)
        self.assertIn("--now must be an ISO timestamp", result.stderr)
        now = self.runner.parse_time("2026-10-29T12:00:00Z")
        with patch.object(self.runner, "datetime") as clock, redirect_stdout(io.StringIO()) as output:
            clock.now.return_value = now
            self.runner.review_dry_run(self.audits, [path])
        self.assertIn("cutoff: " + (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"), output.getvalue())

    def test_gate_preview_has_no_writes_and_only_git_subprocesses(self):
        path = self.project("readonly")
        self.state(path, reviewed_at="2026-10-20T00:00:00Z", ignore_sessions=["own"])
        self.stamp(self.claude_session(path, "own"))
        before = {p: p.read_bytes() if p.is_file() else None for p in self.root.rglob("*")}
        with patch.object(self.runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")) as run:
            with redirect_stdout(io.StringIO()) as output:
                self.runner.review_dry_run(self.audits, [path], self.runner.parse_time("2026-10-29T12:00:00Z"))
        self.assertIn("gate: skipped: no activity since 2026-10-20\n", output.getvalue())
        self.assertEqual(before, {p: p.read_bytes() if p.is_file() else None for p in self.root.rglob("*")})
        self.assertTrue(run.called)
        self.assertTrue(all(call.args[0][0] == "git" for call in run.call_args_list))
        log_call = next(call.args[0] for call in run.call_args_list if "log" in call.args[0])
        self.assertEqual(log_call, ["git", "-C", str(path), "log", "-1", "--branches",
                                   "--since=@1792454401", "--format=%H"])


STUB_CLAUDE = '''#!/usr/bin/env python3
import hashlib, json, os, pathlib, re, signal, sys
args = sys.argv[1:]
cwd = os.getcwd()
session_id = args[args.index('--session-id') + 1]
slug = re.sub('[^a-zA-Z0-9]+', '-', pathlib.Path(cwd).name).strip('-')[:40] or 'root'
key = slug + '-' + hashlib.sha256(cwd.encode()).hexdigest()[:12]
state_path = pathlib.Path(os.environ['STUB_AUDITS']) / 'projects' / key / 'state.json'
state = json.loads(state_path.read_text()) if state_path.exists() else None
with pathlib.Path(os.environ['RECORD']).open('a') as stream:
    stream.write(json.dumps(dict(argv=args, cwd=cwd, state=state,
        env={key: os.environ.get(key) for key in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'KAIZEN_RUN_ID')})) + '\\n')
home = pathlib.Path(os.environ.get('CLAUDE_CONFIG_DIR') or pathlib.Path.home() / '.claude')
folder = home / 'projects' / re.sub('[^a-zA-Z0-9]', '-', cwd)
folder.mkdir(parents=True, exist_ok=True)
(folder / (session_id + '.jsonl')).write_text(json.dumps(dict(type='user', cwd=cwd)) + '\\n')
print('stub cycle output', flush=True)
print('stub cycle stderr', file=sys.stderr, flush=True)
if os.environ.get('STUB_KILL') == '1':
    os.kill(os.getpid(), signal.SIGKILL)
sys.exit(1 if os.environ.get('STUB_FAIL_PROJECT') == pathlib.Path(cwd).name else int(os.environ.get('STUB_EXIT', '0')))
'''

STUB_AUDIT = '''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
out = pathlib.Path(args[args.index('--out') + 1])
out.mkdir(parents=True, exist_ok=True)
report = out / 'token-audit-stub.md'
report.write_text('stub audit report\\n')
print(report)
print('extra audit stdout')
with pathlib.Path(os.environ['AUDIT_RECORD']).open('a') as stream:
    stream.write(json.dumps(args) + '\\n')
sys.exit(int(os.environ.get('STUB_AUDIT_EXIT', '0')))
'''


class ExecutionTests(DiscoveryCase):
    def setUp(self):
        super().setUp()
        self.claude = executable(self.bin / 'stub claude', STUB_CLAUDE)
        self.audit = executable(self.bin / 'stub token-audit', STUB_AUDIT)
        self.pricing = write(self.root / 'pricing.json', '{}')
        self.audit_record = self.root / 'audit-calls.jsonl'
        self.env.update(AUDIT_RECORD=str(self.audit_record), STUB_AUDITS=str(self.audits))
        for name in ('STUB_EXIT', 'STUB_AUDIT_EXIT', 'STUB_KILL', 'STUB_FAIL_PROJECT',
                     'KAIZEN_REVIEW_MODEL', 'KAIZEN_REVIEW_MAX_TURNS'):
            self.env.pop(name, None)

    def review(self, *args, code=0):
        return self.run_script('kaizen-scheduled', 'review', '--audits', self.audits,
                               '--claude', self.claude, '--token-audit', self.audit,
                               '--pricing', self.pricing, *args, code=code)

    def audit_run(self, *args, code=0):
        return self.run_script('kaizen-scheduled', 'audit', '--audits', self.audits,
                               '--token-audit', self.audit, '--pricing', self.pricing, *args, code=code)

    def folder(self, path):
        return self.audits / 'projects' / self.runner.key(path)

    def state(self, path):
        return json.loads((self.folder(path) / 'state.json').read_text())

    def audit_calls(self):
        return [json.loads(line) for line in self.audit_record.read_text().splitlines()]

    def due(self, name):
        path = self.project(name)
        self.claude_session(path, name)
        return path

    @staticmethod
    def values(argv, flag):
        return [argv[index + 1] for index, value in enumerate(argv) if value == flag]

    def expected_config_deny(self, project=None):
        rules = []
        for home in (self.cfg.resolve(), self.cx.resolve()):
            root = '//' + home.as_posix().lstrip('/')
            rules.extend([
                f'Edit({root}/settings*.json)', f'Edit({root}/hooks/**)',
                f'Edit({root}/plugins/**)', f'Edit({root}/skills/**)',
                f'Edit({root}/commands/**)', f'Edit({root}/bin/**)',
                f'Edit({root}/**/*.json)', f'Edit({root}/**/*.toml)',
                f'Edit({root}/**/*.sh)', f'Edit({root}/**/*.py)', f'Edit({root}/**/*.js)',
                f'Edit({root}/.credentials*)', f'Edit({root}/auth.json)',
            ])
        config = (self.cfg / '.claude.json').resolve().as_posix().lstrip('/')
        rules.append(f'Edit(//{config})')
        if project is not None:
            root = project.resolve().as_posix().lstrip('/')
            rules.append(f'Edit(//{root}/.claude/settings*.json)')
        return rules

    def test_two_due_projects_have_independent_commands_outputs_and_state(self):
        b, a = self.due('b project'), self.due('a project')
        before = self.runner.now()
        result = self.review('--model', 'test-model', '--max-turns', '6', '--python', sys.executable)
        after = self.runner.now()
        self.assertEqual([call['cwd'] for call in self.calls()], [str(a), str(b)])
        self.assertTrue((self.audits / 'projects/index.json').is_file())
        for path, call, audit_args in zip((a, b), self.calls(), self.audit_calls()):
            argv = call['argv']
            session_id = self.values(argv, '--session-id')[0]
            self.assertEqual(str(uuid.UUID(session_id)), session_id)
            report = self.folder(path) / 'token-audit-stub.md'
            self.assertEqual(self.values(argv, '-p'), [f'/agent-kaizen:cycle propose-only {report}'])
            self.assertEqual(self.values(argv, '--model'), ['test-model'])
            self.assertEqual(self.values(argv, '--max-turns'), ['6'])
            self.assertIn('--strict-mcp-config', argv)
            self.assertNotIn('--no-session-persistence', argv)
            self.assertEqual(self.values(audit_args, '--cwd'), [str(path)])
            self.assertEqual(self.values(audit_args, '--days'), ['7'])
            self.assertEqual(self.values(audit_args, '--out'), [str(self.folder(path))])
            state = self.state(path)
            self.assertEqual(state['status'], 'ok')
            self.assertEqual(state['report'], str(report))
            self.assertIn(session_id, state['ignore_sessions'])
            reviewed = self.runner.parse_time(state['reviewed_at'])
            self.assertLessEqual(before, reviewed)
            self.assertLessEqual(reviewed, after)
            self.assertEqual(Path(state['proposal']).parent, self.folder(path))
            self.assertEqual(Path(state['proposal']).name, 'cycle-' + reviewed.astimezone().strftime('%Y-%m-%d') + '.md')
            self.assertEqual(Path(state['proposal']).read_text(), 'stub cycle output\n')
            self.assertIn(f'{path}: reviewed (propose-only)', result.stdout)
        self.assertEqual((self.audits / 'run.log').read_text().count('stub cycle stderr'), 2)

    def test_immediate_rerun_ignores_self_activity(self):
        self.due('first')
        self.due('second')
        self.review()
        result = self.review()
        self.assertEqual(result.stdout.count('skipped: no activity since'), 2)
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(len(self.audit_calls()), 2)

    def test_ignore_list_alone_with_old_fixed_clock(self):
        path = self.due('old clock')
        original = self.cfg / 'projects/lossy-folder/old clock.jsonl'
        stamp = self.runner.parse_time('2026-09-30T12:00:00Z').timestamp()
        os.utime(original, (stamp, stamp))
        self.review('--now', '2026-10-01T12:00:00Z')
        state = self.state(path)
        self.assertEqual(state['reviewed_at'], '2026-10-01T12:00:00Z')
        own = next(self.cfg.glob('projects/*/' + state['ignore_sessions'][0] + '.jsonl'))
        self.assertGreater(own.stat().st_mtime, stamp + 86400)
        result = self.review('--now', '2026-10-01T12:00:00Z')
        self.assertIn('skipped: no activity since 2026-10-01', result.stdout)
        self.assertEqual(len(self.calls()), 1)

    def test_claude_failure_retains_review_time_and_retries(self):
        path = self.due('failure')
        self.env['STUB_EXIT'] = '1'
        result = self.review()
        state = self.state(path)
        self.assertNotIn('reviewed_at', state)
        self.assertEqual(state['status'], 'failed')
        self.assertIsNotNone(self.runner.parse_time(state['last_error_at']))
        self.assertIn(self.values(self.calls()[0]['argv'], '--session-id')[0], state['ignore_sessions'])
        self.assertIn(f'{path}: failed (exit 1)', result.stdout)
        self.env['STUB_EXIT'] = '0'
        self.review()
        self.assertEqual(self.state(path)['status'], 'ok')
        previous = self.state(path)
        write(path / 'docs/kaizen/config.json', '{"schedule":"always"}')
        self.env['STUB_EXIT'] = '1'
        self.review()
        state = self.state(path)
        for name in ('reviewed_at', 'report', 'proposal'):
            self.assertEqual(state[name], previous[name])

    def test_audit_failure_does_not_start_claude_and_retries(self):
        path = self.due('audit failure')
        self.env['STUB_AUDIT_EXIT'] = '1'
        result = self.review()
        self.assertFalse(self.record.exists())
        self.assertEqual(self.state(path)['status'], 'audit-failed')
        self.assertNotIn('reviewed_at', self.state(path))
        self.assertNotIn('ignore_sessions', self.state(path))
        self.assertIn('audit failed (exit 1)', result.stdout)
        self.env['STUB_AUDIT_EXIT'] = '0'
        self.review()
        self.assertEqual(self.state(path)['status'], 'ok')

    def test_modes_and_permission_boundaries(self):
        for number, (global_cfg, local_cfg, mode) in enumerate((
                ({}, {}, 'propose-only'), ({}, {'scheduledAutonomy': 'auto'}, 'auto'),
                ({'scheduledAutonomy': 'auto'}, {'scheduledAutonomy': 'propose'}, 'propose-only'))):
            with self.subTest(mode=mode, number=number):
                path = self.due('mode' + str(number))
                write(self.cfg / 'agent-kaizen.json', json.dumps(global_cfg))
                write(path / 'docs/kaizen/config.json', json.dumps(local_cfg))
                self.review('--project-dir', path)
                argv = self.calls()[-1]['argv']
                self.assertIn(f'/agent-kaizen:cycle {mode} ', self.values(argv, '-p')[0])
                auto = mode == 'auto'
                self.assertEqual(self.values(argv, '--permission-mode'), ['acceptEdits' if auto else 'dontAsk'])
                self.assertEqual('--disallowedTools' in argv, auto)
                self.assertEqual(self.values(argv, '--tools'), [self.runner.AUTO_AVAILABLE if auto else self.runner.REVIEW_AVAILABLE])
                self.assertEqual(self.values(argv, '--model'), ['sonnet'])
                self.assertEqual(self.values(argv, '--max-turns'), ['40'])
                allowed = self.values(argv, '--allowedTools')[0]
                for tool in self.runner.READ_ONLY_BASH:
                    self.assertIn(tool, allowed)
                if auto:
                    rules = self.expected_config_deny(path)
                    self.assertEqual(len(rules), 28)
                    self.assertEqual(self.values(argv, '--disallowedTools'),
                                     [','.join([self.runner.HARD_STOP_DENY, *rules])])
                    for rule in rules:
                        self.assertFalse(rule.startswith('Write('))
                        for text in ('.md', 'CLAUDE', 'agents', 'rules'):
                            self.assertNotIn(text, rule)
                    root = '//' + self.cfg.as_posix().lstrip('/')
                    for pattern in ('settings*.json', 'hooks/**', '**/*.json'):
                        self.assertIn(f'Edit({root}/{pattern})', rules)
                    for helper in (self.audit, SCRIPTS / 'kaizen-backup'):
                        self.assertIn(f'Bash(python3 {helper}:*)', allowed)
                        self.assertIn(f'Bash({sys.executable} {helper}:*)', allowed)
                    self.assertIn(f'Bash({SCRIPTS / "kaizen-backup"}:*)', allowed)
                else:
                    self.assertEqual(allowed, self.runner.REVIEW_TOOLS)
                self.assertNotIn('bypassPermissions', argv)

    def test_permission_config_rules_resolve_missing_homes_and_default_user_config(self):
        self.assertFalse(self.cfg.exists())
        self.assertFalse(self.cx.exists())
        self.assertEqual(self.runner.config_home_deny(), self.expected_config_deny())
        self.env.pop('CLAUDE_CONFIG_DIR')
        self.env.pop('CODEX_HOME')
        with patch.dict(os.environ, self.env, clear=True):
            rules = self.runner.config_home_deny()
        root = '//' + self.home.resolve().as_posix().lstrip('/')
        self.assertEqual(rules[0], f'Edit({root}/.claude/settings*.json)')
        self.assertEqual(rules[13], f'Edit({root}/.codex/settings*.json)')
        self.assertEqual(rules[-1], f'Edit({root}/.claude.json)')
        target = self.root / 'actual config'
        target.mkdir()
        self.cfg.symlink_to(target, target_is_directory=True)
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.cfg)}):
            rules = self.runner.config_home_deny()
        root = '//' + target.as_posix().lstrip('/')
        self.assertEqual(rules[0], f'Edit({root}/settings*.json)')
        self.assertEqual(rules[-1], f'Edit({root}/.claude.json)')

    def test_permission_comma_paths_fail_closed_before_claude(self):
        path = self.due('comma home')
        write(path / 'docs/kaizen/config.json', '{"scheduledAutonomy":"auto"}')
        options = self.runner.command_options(type('Args', (), {'dry_run': True})())
        for name in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'project', 'claude_json'):
            comma = self.root / ('bad,' + name)
            environment = {name: str(comma)} if name in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME') else {}
            project = comma if name == 'project' else path
            user_config = comma if name == 'claude_json' else self.cfg / '.claude.json'
            with self.subTest(name=name), patch.dict(os.environ, environment), \
                    patch.object(self.runner, 'claude_json', return_value=user_config):
                with self.assertRaisesRegex(ValueError, "cannot build deny rules: path contains ',':"):
                    self.runner.review_command(options, 'auto', 'report', 'session', project)
                self.assertNotIn('--disallowedTools', self.runner.review_command(
                    options, 'propose-only', 'report', 'session', project))
        self.env['CODEX_HOME'] = str(self.root / 'bad,codex')
        result = self.review('--project-dir', path)
        self.assertIn(f"{path}: failed (cannot build deny rules: path contains ',':", result.stdout)
        self.assertEqual(self.state(path)['status'], 'failed')
        self.assertFalse(self.record.exists())

    def test_permission_rule_metacharacters_fail_closed(self):
        path = self.due('glob home')
        write(path / 'docs/kaizen/config.json', '{"scheduledAutonomy":"auto"}')
        options = self.runner.command_options(type('Args', (), {'dry_run': True})())
        for char in '()*?[]':
            with self.subTest(char=char), patch.dict(os.environ, {'CODEX_HOME': str(self.root / f'bad{char}codex')}):
                with self.assertRaisesRegex(ValueError, 'cannot build deny rules: path contains'):
                    self.runner.review_command(options, 'auto', 'report', 'session', path)
        self.env['CODEX_HOME'] = str(self.root / 'bad*codex')
        result = self.run_script('kaizen-scheduled', 'review', '--dry-run', '--audits', self.audits,
                                 '--project-dir', path)
        self.assertIn("review command: not built (cannot build deny rules: path contains '*':", result.stdout)
        self.assertNotIn('Traceback', result.stderr)

    def test_permission_auto_allows_no_cp_or_touch(self):
        options = self.runner.command_options(type('Args', (), {'dry_run': True})())
        command = self.runner.review_command(options, 'auto', 'report', 'session')
        allowed = command[command.index('--allowedTools') + 1].split(',')
        self.assertNotIn('Bash(cp:*)', allowed)
        self.assertNotIn('Bash(touch:*)', allowed)

    def test_permission_auto_dry_run_has_same_deny_rules(self):
        path = self.due('auto dry project')
        write(path / 'docs/kaizen/config.json', '{"scheduledAutonomy":"auto"}')
        before = {p: p.read_bytes() if p.is_file() else None for p in self.root.rglob('*')}
        output = self.review('--dry-run').stdout
        command = shlex.split(next(line.split('review command: ', 1)[1]
                                   for line in output.splitlines() if 'review command: ' in line))
        expected = ','.join([self.runner.HARD_STOP_DENY, *self.expected_config_deny(path)])
        self.assertEqual(self.values(command, '--disallowedTools'), [expected])
        self.assertEqual(before, {p: p.read_bytes() if p.is_file() else None for p in self.root.rglob('*')})

    def test_disabled_runs_nothing_and_writes_nothing(self):
        self.due('disabled')
        write(self.cfg / 'agent-kaizen.json', '{"enabled":false}')
        before = {p: p.read_bytes() if p.is_file() else None for p in self.root.rglob('*')}
        for command in ('review', 'audit'):
            result = self.run_script('kaizen-scheduled', command, '--audits', self.audits,
                                     '--token-audit', self.root / 'missing')
            self.assertIn('skipped: disabled', result.stdout)
        self.assertIn('skipped: disabled', self.review('--dry-run').stdout)
        with patch.object(self.runner.subprocess, 'run') as run, redirect_stdout(io.StringIO()):
            for args in (['review'], ['review', '--dry-run'], ['audit']):
                self.assertEqual(self.runner.main(args), 0)
        run.assert_not_called()
        self.assertEqual(before, {p: p.read_bytes() if p.is_file() else None for p in self.root.rglob('*')})

    def test_environment_and_only_existing_add_dirs(self):
        path = self.due('environment')
        self.review('--now', '2026-10-01T12:00:00Z')
        call = self.calls()[-1]
        self.assertEqual(call['env']['CLAUDE_CONFIG_DIR'], str(self.cfg))
        self.assertEqual(call['env']['CODEX_HOME'], str(self.cx))
        fixed = self.runner.parse_time('2026-10-01T12:00:00Z')
        self.assertEqual(call['env']['KAIZEN_RUN_ID'], fixed.astimezone().strftime('%Y%m%d-%H%M%S'))
        self.assertEqual(self.values(call['argv'], '--add-dir'), [str(self.cfg)])
        self.cx.mkdir()
        write(path / 'docs/kaizen/config.json', '{"schedule":"always"}')
        self.review()
        self.assertEqual(self.values(self.calls()[-1]['argv'], '--add-dir'), [str(self.cfg), str(self.cx)])

    def test_one_failure_does_not_stop_next_project(self):
        a, b = self.due('a fail'), self.due('b ok')
        self.env['STUB_FAIL_PROJECT'] = a.name
        result = self.review()
        self.assertEqual([call['cwd'] for call in self.calls()], [str(a), str(b)])
        self.assertIn(f'{a}: failed (exit 1)', result.stdout)
        self.assertIn(f'{b}: reviewed (propose-only)', result.stdout)
        self.assertEqual(self.state(b)['status'], 'ok')

    def test_claude_spawn_errors_do_not_stop_next_project(self):
        for error in (FileNotFoundError('missing claude'), PermissionError('not executable')):
            with self.subTest(error=error):
                a, b = self.due('a spawn failure'), self.due('b spawn ok')
                options = self.runner.command_options(type('Args', (), {
                    'claude': str(self.claude), 'token_audit': self.audit, 'pricing': self.pricing})())
                run = subprocess.run

                def spawn(command, **kwargs):
                    if command[0] == str(self.claude) and kwargs.get('cwd') == a:
                        raise error
                    return run(command, **kwargs)

                write(b / 'docs/kaizen/config.json', '{"schedule":"always"}')
                with patch.dict(os.environ, self.env, clear=True), \
                        patch.object(self.runner.subprocess, 'run', side_effect=spawn), \
                        redirect_stdout(io.StringIO()) as output:
                    code = self.runner.run_review(self.audits, [a, b], options, self.runner.now)
                self.assertEqual(code, 0)
                self.assertEqual(self.state(a)['status'], 'failed')
                self.assertIsNotNone(self.runner.parse_time(self.state(a)['last_error_at']))
                self.assertEqual(self.state(b)['status'], 'ok')
                self.assertIn(f'{a}: failed ({error})', output.getvalue())
                self.assertIn(f'{b}: reviewed (propose-only)', output.getvalue())

    def test_audit_exceptions_do_not_stop_next_project(self):
        for failure in ('empty stdout', 'spawn error'):
            with self.subTest(failure=failure):
                a, b = self.due('a audit error'), self.due('b audit ok')
                options = self.runner.command_options(type('Args', (), {
                    'claude': str(self.claude), 'token_audit': self.audit, 'pricing': self.pricing})())
                run = subprocess.run

                def spawn(command, **kwargs):
                    if str(self.audit) in command and str(a) in command:
                        if failure == 'spawn error':
                            raise OSError('audit could not start')
                        return subprocess.CompletedProcess(command, 0, '')
                    return run(command, **kwargs)

                write(b / 'docs/kaizen/config.json', '{"schedule":"always"}')
                with patch.dict(os.environ, self.env, clear=True), \
                        patch.object(self.runner.subprocess, 'run', side_effect=spawn), \
                        redirect_stdout(io.StringIO()) as output:
                    code = self.runner.run_review(self.audits, [a, b], options, self.runner.now)
                self.assertEqual(code, 0)
                self.assertEqual(self.state(a)['status'], 'audit-failed')
                self.assertIsNotNone(self.runner.parse_time(self.state(a)['last_error_at']))
                self.assertNotIn('ignore_sessions', self.state(a))
                self.assertEqual(self.state(b)['status'], 'ok')
                self.assertIn(f'{a}: failed (', output.getvalue())
                self.assertIn(f'{b}: reviewed (propose-only)', output.getvalue())

    def test_same_day_failed_retry_preserves_successful_proposal(self):
        path = self.due('same day retry')
        fixed = '2026-10-01T12:00:00Z'
        self.review('--now', fixed)
        previous = self.state(path)
        proposal = Path(previous['proposal'])
        self.assertEqual(proposal.read_text(), 'stub cycle output\n')
        write(path / 'docs/kaizen/config.json', '{"schedule":"always"}')
        executable(self.claude, STUB_CLAUDE.replace('stub cycle output', 'failed retry output'))
        self.env['STUB_EXIT'] = '1'
        failed = proposal.with_suffix('.failed.md')
        write(failed, 'older failure')
        result = self.review('--now', fixed)
        state = self.state(path)
        self.assertEqual(state['status'], 'failed')
        for name in ('proposal', 'reviewed_at', 'report'):
            self.assertEqual(state[name], previous[name])
        self.assertEqual(proposal.read_text(), 'stub cycle output\n')
        self.assertEqual(failed.read_text(), 'failed retry output\n')
        self.assertIn(f'output: {failed}', result.stdout)
        self.assertEqual(list(self.folder(path).glob(proposal.name + '.*')), [])

    def test_global_audit_empty_stdout_is_normal_failure(self):
        executable(self.audit, '#!/usr/bin/env python3\n')
        result = self.audit_run(code=1)
        self.assertIn('audit: failed (token-audit did not print a report path)', result.stdout)
        self.assertEqual(result.stderr, '')

    def test_global_audit_arguments_and_exit_status(self):
        for exit_code in (0, 3):
            with self.subTest(exit_code=exit_code):
                self.env['STUB_AUDIT_EXIT'] = str(exit_code)
                result = self.audit_run(code=exit_code)
                self.assertEqual(self.audit_calls()[-1], ['--out', str(self.audits), '--pricing', str(self.pricing),
                                                        '--extract-out', str(self.audits / 'extracts')])
                message = f'audit: failed (exit {exit_code})' if exit_code else f'audit: ok {self.audits / "token-audit-stub.md"}'
                self.assertIn(message, result.stdout)
                self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertFalse(self.record.exists())

    def test_review_with_real_token_audit(self):
        path = self.due('real audit')
        self.review('--token-audit', SCRIPTS / 'token-audit', '--pricing', SCRIPTS / 'pricing.json')
        state = self.state(path)
        report = Path(state['report'])
        self.assertTrue(report.is_file())
        self.assertEqual(report.parent, self.folder(path))
        self.assertIn(str(report), self.values(self.calls()[0]['argv'], '-p')[0])
        self.assertFalse(self.audit_record.exists())
        options = self.runner.command_options(type('Args', (), {'dry_run': True})())
        project = self.runner.Project(path, [path], self.folder(path))
        argv = self.runner.audit_command(options, project.folder, project)
        self.assertEqual(argv[2:], ['--cwd', str(path), '--days', '7', '--out', str(project.folder),
                                   '--pricing', str(SCRIPTS / 'pricing.json'),
                                   '--extract-out', str(self.audits / 'extracts')])

    def test_dry_run_commands_are_quoted_and_do_not_write_or_run(self):
        path = self.due('dry project')
        before = {p: p.read_bytes() if p.is_file() else None for p in self.root.rglob('*')}
        output = self.review('--dry-run').stdout
        audit = shlex.split(next(line.split('audit command: ', 1)[1] for line in output.splitlines() if 'audit command: ' in line))
        review = shlex.split(next(line.split('review command: ', 1)[1] for line in output.splitlines() if 'review command: ' in line))
        self.assertEqual(audit, [sys.executable, str(self.audit), '--cwd', str(path),
                                 '--days', '7', '--out', str(self.folder(path)), '--pricing', str(self.pricing),
                                 '--extract-out', str(self.audits / 'extracts')])
        self.assertEqual(review[0], str(self.claude))
        self.assertEqual(self.values(review, '-p'), ['/agent-kaizen:cycle propose-only <report path from audit stdout>'])
        uuid.UUID(self.values(review, '--session-id')[0])
        self.assertEqual(before, {p: p.read_bytes() if p.is_file() else None for p in self.root.rglob('*')})

    def test_session_id_is_saved_before_claude_starts_and_survives_sigkill(self):
        for killed in (False, True):
            with self.subTest(killed=killed):
                path = self.due('killed' if killed else 'normal')
                old = [str(uuid.uuid4()) for _ in range(20)]
                state = dict(ignore_sessions=old, status='previous', report='old report', proposal='old proposal')
                write(self.folder(path) / 'state.json', json.dumps(state))
                self.env['STUB_KILL'] = '1' if killed else '0'
                self.review('--project-dir', path)
                call = self.calls()[-1]
                session_id = self.values(call['argv'], '--session-id')[0]
                self.assertEqual(call['state'], dict(state, ignore_sessions=old[1:] + [session_id]))
                self.assertEqual(self.state(path)['ignore_sessions'], old[1:] + [session_id])
                if killed:
                    self.assertNotIn('reviewed_at', self.state(path))
                    self.assertEqual(self.state(path)['status'], 'failed')
                    self.env['STUB_KILL'] = '0'
                    self.review('--project-dir', path)
                    self.assertEqual(self.state(path)['status'], 'ok')

    @unittest.skipUnless(shutil.which('git'), 'git required')
    def test_worktree_audit_paths_match_preview_without_duplicates(self):
        main = self.repo('main repo')
        worktree = self.root / 'linked tree'
        self.git(main, 'worktree', 'add', '-b', 'linked', str(worktree))
        self.claude_session(worktree, 'worktree')
        argv = []
        for path in (main, worktree):
            argv.extend(['--project-dir', path])
        preview = self.review('--dry-run', *argv).stdout
        preview_audit = shlex.split(next(line.split('audit command: ', 1)[1] for line in preview.splitlines() if 'audit command: ' in line))
        self.review(*argv)
        self.assertEqual(len(self.audit_calls()), 1)
        self.assertEqual(self.audit_calls()[0], preview_audit[2:])
        self.assertEqual(self.values(self.audit_calls()[0], '--cwd'), sorted(map(str, (main, worktree))))

    def test_write_state_is_atomic_and_keeps_format(self):
        path = self.project('atomic')
        project = self.runner.Project(path, [path], self.folder(path))
        state = {'status': 'ok', 'ignore_sessions': ['id']}
        with patch.object(self.runner.os, 'replace', wraps=os.replace) as replace:
            self.runner.write_state(project, state)
        self.assertEqual(replace.call_count, 1)
        temporary, target = replace.call_args.args
        self.assertEqual(temporary.parent, target.parent)
        self.assertEqual(target.read_text(), json.dumps(state, indent=2) + '\n')
        self.assertEqual(list(project.folder.iterdir()), [target])
        with patch.object(self.runner.os, 'replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.runner.write_state(project, {'status': 'failed'})
        self.assertEqual(json.loads(target.read_text()), state)
        self.assertEqual(list(project.folder.iterdir()), [target])

    def test_exit_clock_keeps_fractional_precision_and_same_second_activity_is_old(self):
        path = self.due('subsecond')
        activity = self.runner.parse_time('2026-10-01T12:00:00.250000Z')
        exited = self.runner.parse_time('2026-10-01T12:00:00.750000Z')
        session = self.cfg / 'projects/lossy-folder/subsecond.jsonl'
        os.utime(session, (activity.timestamp(), activity.timestamp()))
        options = self.runner.command_options(type('Args', (), {
            'claude': str(self.claude), 'token_audit': self.audit, 'pricing': self.pricing})())
        times = [activity - timedelta(seconds=1), activity, exited]
        with patch.dict(os.environ, self.env, clear=True), redirect_stdout(io.StringIO()):
            self.runner.run_review(self.audits, [path], options, lambda: times.pop(0))
        self.assertEqual(self.state(path)['reviewed_at'], '2026-10-01T12:00:00.750000Z')
        result = self.review('--now', '2026-10-01T12:00:00.750000Z')
        self.assertIn('skipped: no activity since', result.stdout)
        self.assertEqual(len(self.calls()), 1)

    def test_defaults_installed_siblings_and_errors(self):
        installed = self.root / 'installed'
        installed.mkdir()
        for name in ('kaizen-token-audit', 'token-audit', 'kaizen-pricing.json', 'pricing.json'):
            write(installed / name, '')
        with patch.object(self.runner, 'HERE', installed), patch.dict(os.environ, {
                'KAIZEN_REVIEW_MODEL': 'env-model', 'KAIZEN_REVIEW_MAX_TURNS': '9'}):
            options = self.runner.command_options(type('Args', (), {'dry_run': True})())
        self.assertEqual(options.token_audit, installed / 'kaizen-token-audit')
        self.assertEqual(options.pricing, installed / 'kaizen-pricing.json')
        self.assertEqual((options.model, options.max_turns), ('env-model', '9'))
        (installed / 'kaizen-token-audit').unlink()
        (installed / 'kaizen-pricing.json').unlink()
        with patch.object(self.runner, 'HERE', installed):
            options = self.runner.command_options(type('Args', (), {'dry_run': True})())
            self.assertEqual(options.token_audit, installed / 'token-audit')
            self.assertEqual(options.pricing, installed / 'pricing.json')
        result = self.review('--token-audit', self.root / 'missing', code=2)
        self.assertIn('token-audit not found', result.stderr)
        self.assertFalse(self.audits.exists())
        result = self.review('--max-turns', '0', code=2)
        self.assertIn('--max-turns must be positive', result.stderr)
        write(self.audits, 'not a directory')
        self.due('unwritable')
        self.assertIn('kaizen-scheduled:', self.review(code=2).stderr)
        with patch.object(self.runner.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, 'claude not found; pass --claude or put it on PATH'):
                self.runner.command_options(type('Args', (), {})())
            self.assertEqual(self.runner.command_options(type('Args', (), {'dry_run': True})()).claude, 'claude')
            self.runner.command_options(type('Args', (), {'command': 'audit'})())


if __name__ == "__main__":
    unittest.main()
