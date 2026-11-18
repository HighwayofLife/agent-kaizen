"""Offline runtime-envelope and real backup-helper tests for the dormant broker."""
import base64
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import kaizen_friction_apply as apply
sys.path.pop(0)


class MutationEvidenceTests(unittest.TestCase):
    def test_schedule_off_freezes_zero_before_reenable(self):
        runner = runpy.run_path(str(SCRIPTS / "kaizen-scheduled"))
        backup = runpy.run_path(str(SCRIPTS / "kaizen-backup"))
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
                os.environ, CLAUDE_CONFIG_DIR=str(Path(temporary).resolve())):
            project = Path(temporary).resolve() / "project"
            (project / "docs/kaizen").mkdir(parents=True)
            config = runner["global_config_path"]()
            config.write_text(json.dumps(dict(scheduledAutonomy="auto", schedule="off")))
            before = runner["freeze_mutation_config"](project, backup)
            config.write_text(json.dumps(dict(scheduledAutonomy="auto", schedule="always")))
            after = runner["freeze_mutation_config"](project, backup)
        self.assertEqual(before[0], 0)
        self.assertGreater(after[0], 0)
        self.assertNotEqual(before, after)

    def test_oversized_stream_is_drained_to_normal_exit(self):
        backup = runpy.run_path(str(SCRIPTS / "kaizen-backup"))

        def launch(argv, stdout):
            return subprocess.run([argv[0], "-c", "import sys; sys.stdout.buffer.write(b'x' * (1 << 20))"],
                                  stdout=stdout, stderr=subprocess.DEVNULL, timeout=5)

        with patch.object(apply, "VERIFIED_STREAM_VERSIONS", {"fixture"}), patch.object(apply, "STREAM_LIMIT", 64):
            result, _, calls = apply.observe_review(launch, [sys.executable], "fixture", backup=backup,
                                                     scope={}, project=Path("."))
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(calls)

    def test_runner_stream_budget_and_shared_ledger_fixture(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/ledger_attestation_v1.json").read_text())
        valid = fixture["valid"]
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve() / "project"
            root = project.with_name("backup")
            (project / "docs/kaizen").mkdir(parents=True)
            root.mkdir()
            ledger, target = project / valid["ledger_relpath"], project / "tracked"
            ledger.write_bytes(base64.b64decode(valid["before_b64"]))
            target.write_text("before")
            for args in (("init", "-q"), ("add", "."), ("-c", "user.name=Fixture", "-c",
                         "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null",
                         "commit", "--no-gpg-sign", "-qm", "fixture")):
                subprocess.run(["git", "-C", str(project), *args], check=True)
            env = dict(os.environ, KAIZEN_BACKUP_DIR=str(root), KAIZEN_RUN_ID=valid["run_id"],
                       KAIZEN_SESSION_ID=valid["session_id"])
            with patch.dict(os.environ, env):
                backup = runpy.run_path(str(SCRIPTS / "kaizen-backup"))
            scope = dict(run_id=valid["run_id"], session_id=valid["session_id"], before=(set(), set()),
                         started=datetime.now(timezone.utc), root_identity=backup["backup_root_identity"](root))
            baseline = backup["capture_git_baseline"](project)
            self.assertIsNotNone(baseline)
            ledger_before = apply.snapshot_ledger(backup, project)
            notes_script = SCRIPTS / "notes-ledger"
            notes = runpy.run_path(str(notes_script))
            csv = project.with_name("notes.csv")
            csv.write_text(",".join(notes["HEADER"]) + "\n")
            notes_before = apply.snapshot_notes(backup, {"csv": csv})
            records = [dict(type="system", subtype="init", claude_code_version="fixture", cwd=str(project))]
            result = dict(type="result", subtype="success", is_error=False, result="review text")

            def dispatch(name, **args):
                ident = str(len(records))
                for kind, block in (("assistant", dict(type="tool_use", id=ident, name=name, input=args)),
                                    ("user", dict(type="tool_result", tool_use_id=ident))):
                    records.append(dict(type=kind, parent_tool_use_id=None,
                                        message=dict(role=kind, content=[block])))

            def evidence(quota=3, transform=lambda raw: raw, config_after=None):
                raw = b"".join((json.dumps(dict(record, session_id=scope["session_id"], uuid=str(i))) + "\n")
                               .encode() for i, record in enumerate([*records, result]))

                def launch(argv, stdout):
                    self.assertEqual(argv[-3:], ["--output-format", "stream-json", "--verbose"])
                    os.write(stdout, transform(raw))
                    return SimpleNamespace(returncode=0)

                with patch.object(apply, "VERIFIED_STREAM_VERSIONS", {"fixture"}):
                    _, rendered, calls = apply.observe_review(launch, [sys.executable], "fixture", backup=backup,
                                                              scope=scope, project=project)
                if calls is not None:
                    self.assertEqual(rendered, "review text")
                return apply.prove_budget(
                    calls, backup=backup, root=root, scope=scope, project=project, baseline=baseline,
                    ledger_before=ledger_before, config_before=(quota,), config_after=config_after or (quota,),
                    backup_script=script, notes_script=notes_script, python=sys.executable,
                    notes_add=notes["add"], notes_before=notes_before)

            script = SCRIPTS / "kaizen-backup"

            def helper(*args):
                argv = [sys.executable, str(script), *args]
                dispatch("Bash", command=shlex.join(argv))
                return subprocess.check_output(argv, env=env, cwd=project, text=True).strip()

            dispatch("Read", file_path=str(target))
            fake = json.dumps(dict(type="assistant", message=dict(content=[dict(type="tool_use", name="Write")])))
            records[-1]["message"]["content"][0]["content"] = fake
            self.assertEqual(evidence(), (3, None))
            result["permission_denials"] = [dict(tool_use_id="unobserved", tool_name="Write",
                                                  tool_input=dict(file_path=str(target)))]
            self.assertEqual(evidence(), (None, None))

            del result["permission_denials"]
            self.assertEqual(evidence(config_after=(0,)), (None, None))
            self.assertEqual(evidence(transform=lambda raw: raw.rstrip(b"\n")), (None, None))
            self.assertEqual(evidence(transform=lambda raw: b"\n".join(raw.split(b"\n")[:2]
                                                                      + raw.split(b"\n")[3:])), (None, None))
            self.assertEqual(evidence(transform=lambda raw: raw.replace(b'"uuid": "0"', b'"uuid": "0", "uuid": "0"')),
                             (None, None))
            dispatch("Write", file_path=str(target))
            target.write_text("unbacked")
            target.write_text("before")
            self.assertEqual(evidence(), (None, None))
            del records[-2:]

            folder = helper("begin", "--skill", "trim", "--ledger", "Fixture", str(target))
            target.write_text("after")
            dispatch("Edit", file_path=str(target))
            helper("finish", folder)
            self.assertEqual(evidence(), (2, None))
            self.assertEqual(evidence(1), (0, None))
            records[-2]["message"]["content"][0]["input"]["run_in_background"] = True
            self.assertEqual(evidence(), (None, None))
            del records[-2]["message"]["content"][0]["input"]["run_in_background"]
            target.write_text("after finish")
            self.assertEqual(evidence(), (None, None))
            target.write_text("after")
            dispatch("Edit", file_path=str(ledger))
            ledger.write_text(fixture["after_utf8"])
            self.assertEqual(evidence(), (2, valid))
            for override in fixture["invalid_overrides"].values():
                with self.assertRaises(ValueError):
                    backup["ledger_append"](dict(valid, **override), scope, project)
            config = project.with_name("agent-kaizen.json")
            config.write_text(json.dumps({"notesLedger": {"csv": str(csv)}}))
            argv = [sys.executable, str(notes_script), "add", "--date", "2026-11-18", "--category", "test",
                    "--change", "Fixture", "--why", "verification", "--measure", "test", "--source", "offline"]
            subprocess.check_output(argv, env=dict(env, CLAUDE_CONFIG_DIR=str(config.parent)), cwd=project)
            dispatch("Bash", command=shlex.join(argv))
            self.assertEqual(evidence(), (2, valid))
            alias = csv.with_name("alias.csv")
            os.link(csv, alias)
            self.assertEqual(evidence(), (None, None))
            alias.unlink()
            ledger.write_text(fixture["after_utf8"].replace("Fixture", ""))
            self.assertEqual(evidence(), (None, None))


class BrokerLedgerTests(unittest.TestCase):
    def test_copied_install_undo_and_bookkeeping_recovery(self):
        from test_schedule import CRONTAB

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cache = root / "plugins/cache/agent-kaizen/version"
            scripts = cache / "scripts"
            shutil.copytree(SCRIPTS, scripts)
            config = root / "config"
            cron = root / "crontab"
            cron.write_text(CRONTAB)
            cron.chmod(0o700)
            env = dict(os.environ, HOME=str(root), CLAUDE_CONFIG_DIR=str(config),
                       PATH=str(root) + os.pathsep + os.environ["PATH"], CRON_FILE=str(root / "cron-state"),
                       KAIZEN_HOST="claude", KAIZEN_BACKUP_DIR=str(config / "backups"))
            for name in ("KAIZEN_RUN_ID", "KAIZEN_SESSION_ID", "CLAUDE_PLUGIN_ROOT"):
                env.pop(name, None)

            def command(path, *args, code=0, **extra_env):
                result = subprocess.run([sys.executable, str(path), *map(str, args)], env=dict(env, **extra_env),
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, code, result.stderr)

            command(scripts / "install-schedule", "--apply", "--scheduler", "cron")
            installed = config / "bin"
            shutil.rmtree(cache)
            runtime = installed / "kaizen_friction_apply.py"
            self.assertFalse(runtime.is_symlink())
            broker = runpy.run_path(str(runtime))["BrokerLedger"]
            host = runpy.run_path(str(installed / "kaizen_friction_actions.py"))
            runner = installed / "kaizen-scheduled"
            installed_runner = runpy.run_path(str(runner))
            store = host["HostActions"](config / "audits", config / "backups",
                                        installed_runner["action_project"], installed_runner["key"])
            store._secret(create=True)
            # Flip only the disposable native helper's live gate to exercise its real transaction and inverse.
            helper = installed / "kaizen-allow-rule"
            helper.write_text(helper.read_text().replace("WRITES_ENABLED = False", "WRITES_ENABLED = True", 1))
            tool = runpy.run_path(str(helper))["transact"]
            legacy = "| 2026-11-18 | Ordinary backup | Audit | Less text | pending | pending |\n"
            six = apply.row_line(apply.HEADER[:6], "\n") + apply.row_line(["---"] * 6, "\n") + legacy
            for enabled, literal in ((True, "ls"), (False, "ls -a")):
                project = root / ("enabled" if enabled else "disabled")
                ledger = project / apply.LEDGER
                ledger.parent.mkdir(parents=True)
                ledger.write_text(six)
                target = project / ".claude/settings.local.json"
                selector = json.dumps([literal, str(project)], separators=(",", ":"))
                ident = store.record(project, "allow-rule", selector, "fixture", allowed=[selector])
                undo = ("actions", "undo", ident, "--for", project)
                with broker.locked(host, store, project) as journal:
                    ledger.write_text("```md\n" + six + "```\n")
                    with self.assertRaises(ValueError):
                        journal.preflight(ident, "allow-rule")
                    ledger.write_text(six)
                    journal.preflight(ident, "allow-rule")
                    with patch.dict(os.environ, env, clear=True), patch.dict(
                            tool.__globals__, evidence=lambda *args: (10, ["fixture"])):
                        result = tool(project, literal, action_id=ident)
                    self.assertEqual(result, dict(status="applied", record=ident))
                    ledger.unlink()
                    with self.assertRaises(FileNotFoundError):
                        journal.record_verified(ident, "allow-rule", ident, "a" * 64, "fixture", 10)
                    ledger.write_text(six)
                    with patch.object(journal, "save", side_effect=OSError("after row")), self.assertRaises(OSError):
                        journal.reconcile(ident)
                    if enabled:
                        self.assertEqual(journal.reconcile(ident), "recorded")
                    self.assertEqual(ledger.read_text().count(ident), 1)
                    self.assertIn(legacy, ledger.read_text())
                    self.assertNotIn(str(project), ledger.read_text())

                    (config / "agent-kaizen.json").write_text(json.dumps(dict(enabled=enabled)))
                    if not enabled:

                        def interrupted(operation, record):
                            self.assertEqual(operation, "allow-rule")
                            command(helper, "undo", record, "--project", project)
                            raise OSError("after native undo")

                        with self.assertRaises(OSError):
                            journal.undo(ident, interrupted)
                        self.assertFalse(target.exists())
                        self.assertNotIn("reverted", ledger.read_text())
                normal = ledger.read_text()
                if enabled:
                    nested = project / "nested"
                    nested.mkdir()
                    subprocess.run(["git", "init", "-q", str(nested)], check=True, env=env)
                    command(runner, *undo[:-1], nested, code=2)
                    forged = "fa1_" + "0" * 64
                    action_row = next(line for line in normal.splitlines(keepends=True) if ident in line)
                    ledger.write_text(normal + action_row.replace(ident, forged))
                    command(runner, "actions", "undo", forged, "--for", project, code=2)
                    for bad in (normal + action_row, normal.replace("Fewer permission prompts", "Spoofed"),
                                normal + "\n" + "x" * (apply.LEDGER_LIMIT - len(normal.encode()) - 1)):
                        ledger.write_text(bad)
                        command(runner, *undo, code=2)
                    self.assertTrue(target.is_file())
                    ledger.write_text(normal.replace(" | Fewer permission prompts | pending | pending |",
                                                     " | Fewer permission prompts | pending | " + "k" * 10000 + " |"))
                    moved = target.parent.rename(project / "moved")
                    target.parent.mkdir()
                    target.write_text("replacement")
                    command(runner, *undo, code=2)
                    self.assertEqual(target.read_text(), "replacement")
                    shutil.rmtree(target.parent)
                    moved.rename(target.parent)
                command(runner, *undo, code=2, KAIZEN_RUN_ID="scheduled")
                command(runner, *undo)
                self.assertFalse(target.exists())
                self.assertIn(f"reverted ({date.today()})", ledger.read_text())
                store.mark(project, ident, "done")
                command(runner, "actions", "reopen", ident, "--for", project)
                self.assertEqual(store.scoped(project)[0]["status"], "open")
                with broker.locked(host, store, project) as journal:
                    self.assertEqual(journal.reconcile(ident), "reverted")
                    with self.assertRaises(ValueError):
                        journal.preflight(ident, "allow-rule")
