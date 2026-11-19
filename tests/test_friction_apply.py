"""Offline runtime-envelope and real backup-helper tests for the dormant broker."""
import base64
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
import errno
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
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
                    notes_add=notes["add"], notes_before=notes_before)[:2]

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
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "project"
        self.ledger = self.project / apply.LEDGER
        self.ledger.parent.mkdir(parents=True)
        self.table = apply.row_line(apply.HEADER, "\n") + apply.row_line(["---"] * 8, "\n")
        self.ledger.write_text(self.table)
        self.runner = runpy.run_path(str(SCRIPTS / "kaizen-scheduled"))
        self.host = runpy.run_path(str(SCRIPTS / "kaizen_friction_actions.py"))
        self.tool = runpy.run_path(str(SCRIPTS / "allow-rule"))
        self.tool["live_writes"].__globals__["WRITES_ENABLED"] = True
        config = self.root / "config"
        environment = dict(os.environ, CLAUDE_CONFIG_DIR=str(config), KAIZEN_HOST="claude",
                           KAIZEN_BACKUP_DIR=str(config / "backups"))
        for name in ("KAIZEN_RUN_ID", "KAIZEN_SESSION_ID"):
            environment.pop(name, None)
        patcher = patch.dict(os.environ, environment, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = self.host["HostActions"](config / "audits", config / "backups",
                                              self.runner["action_project"], self.runner["key"])
        self.secret = self.store._secret(create=True)
        self.extracts = config / "audits/extracts"
        self.extracts.mkdir(mode=0o700, parents=True, exist_ok=True)

    def action(self, literal, roots):
        selector = json.dumps([literal, *map(str, roots)], separators=(",", ":"))
        return self.store.record(self.project, "allow-rule", selector, "fixture", allowed=[selector])

    def signed_extract(self, roots, literals=("ls",)):
        now = datetime.now(timezone.utc)
        rows = [dict(cwd_id=hashlib.sha256(os.fsencode(roots[0])).hexdigest(), literal=literal,
                     accepted=10, denied=0, ambiguous=0) for literal in literals]
        evidence = dict(v=1, since=(now - timedelta(days=1)).isoformat(),
                        scope=dict(v=1, cwd=list(map(str, roots)), project=None, project_dirs=[]),
                        friction=dict(v=1, audited_at=(now - timedelta(seconds=1)).isoformat(),
                                      summary=dict(capped=False), permission_acceptance=rows))
        payload = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("ascii")
        evidence["allow_rule_mac"] = hmac.digest(self.secret, b"allow-rule-extract-v2\0" + payload, "sha256").hex()
        extract = self.extracts / "fixture.extract.json"
        extract.write_text(json.dumps(evidence))
        extract.chmod(0o600)
        return extract

    def locked(self):
        return apply.BrokerLedger.locked(self.host, self.store, self.project)

    def test_caller_tuple_cannot_bind_an_unissued_action(self):
        ident, native_id, generation = "fa1_" + "1" * 64, "fa1_" + "2" * 64, "3" * 64
        with self.locked() as journal:
            with self.assertRaises((TypeError, ValueError)):
                journal.record_verified(ident, "allow-rule", native_id, "4" * 64, generation, 10,
                                        binding=(native_id, generation, 10))
            with self.assertRaisesRegex(ValueError, "invalid verified allow-rule binding"):
                journal.begin_allow_rule(ident)
            self.assertIsNone(journal.load(ident))

    def test_native_receipt_cannot_be_replayed_under_another_action(self):
        self.signed_extract([self.project], ("ls", "ls -a"))
        ident = self.action("ls", [self.project])
        other = self.action("ls -a", [self.project])
        with self.locked() as journal:
            # Use the actual P18d binding and transaction to obtain a real native receipt.
            scope = self.tool["project_scope"](self.project, self.tool["runner_for"]())
            count, (generation, _) = self.tool["evidence"](self.tool["runner_for"](), scope, "ls", self.secret)
            native_id = self.tool["broker_id"](self.secret, scope, "ls", generation)
            self.assertNotEqual(ident, other)
            result = self.tool["transact"](self.project, "ls", action_id=native_id)
            target = self.project / self.tool["TARGET"]
            with self.assertRaises((TypeError, ValueError)):
                journal.record_verified(other, "allow-rule", result["record"],
                                        hashlib.sha256(target.read_bytes()).hexdigest(), generation, count,
                                        binding=(native_id, generation, count))
            self.assertIsNone(journal.load(other))
            self.assertNotEqual(journal.begin_allow_rule(other), native_id)
            with self.assertRaisesRegex(ValueError, "no verified native allow-rule effect"):
                journal.reconcile(other)
            self.assertEqual(journal.load(other)["phase"], "apply-pending")
            self.assertNotIn(other, self.ledger.read_text())

    def test_project_save_after_final_snapshot_is_preserved(self):
        ident = "fa1_" + "1" * 64
        edited = self.table + "\nEditor saved here.\n"
        with self.locked() as journal, journal.table(ident) as (lines, _, _, _, _, write):
            lines.append("\nBroker wrote here.\n")
            snapshot = journal.snapshot

            def edit_after_snapshot(*args, **kwargs):
                before = snapshot(*args, **kwargs)
                if injected.call_count == 1:
                    self.ledger.write_text(edited)
                return before

            with patch.object(journal, "snapshot", side_effect=edit_after_snapshot) as injected:
                with self.assertRaisesRegex(ValueError, "ledger changed"):
                    write()
            self.assertEqual(self.ledger.read_text(), edited)

    def test_project_save_after_publication_stays_live(self):
        ident = "fa1_" + "1" * 64
        updated = self.table + "\nEditor saved here.\n"
        editor = self.ledger.with_name("editor-save")
        editor.write_text(updated)
        with self.locked() as journal, journal.table(ident) as (lines, _, _, _, _, write):
            lines.append("\nBroker wrote here.\n")
            exchange = apply.swap_ledger_entries

            def save_after_exchange(*args, **kwargs):
                exchange(*args, **kwargs)
                if editor.exists():
                    editor.replace(self.ledger)

            with patch.object(apply, "swap_ledger_entries", side_effect=save_after_exchange):
                with self.assertRaisesRegex(ValueError, "ledger changed"):
                    write()
            self.assertEqual(self.ledger.read_text(), updated)

    def test_replaced_backup_directory_cannot_redirect_ledger_exchange(self):
        ident = "fa1_" + "1" * 64
        updated = self.table + "\nBroker wrote here.\n"
        moved = self.root / "moved-backups"
        with self.locked() as journal, journal.table(ident) as (lines, _, _, _, _, write):
            lines.append(updated[len(self.table):])
            exchange = journal.exchange_ledger

            def replace_backup_directory(*args):
                staged, = self.root.rglob(f"{ident}-*.md")
                staged.parent.rename(moved)
                staged.parent.mkdir(mode=0o700)
                staged.write_text("decoy")
                return exchange(*args)

            with patch.object(journal, "exchange_ledger", side_effect=replace_backup_directory), \
                    self.assertRaisesRegex(ValueError, "ledger.*changed"):
                write()
        saved, = moved.iterdir()
        self.assertEqual(self.ledger.read_text(), updated)
        self.assertEqual(saved.read_text(), self.table)
        decoy, = (path for path in self.root.rglob(f"{ident}-*.md") if path != saved)
        self.assertEqual(decoy.read_text(), "decoy")

    def test_ledger_publication_leaves_no_untracked_git_files(self):
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.project), *args], text=True)

        git("init", "-q")
        git("add", str(apply.LEDGER))
        with self.locked() as journal, journal.table("fa1_" + "1" * 64) as (lines, _, _, _, _, write):
            lines.append("\nBroker wrote here.\n")
            write()
        git("add", str(apply.LEDGER))
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--no-gpg-sign",
            "-qm", "ledger")
        self.assertEqual(git("status", "--porcelain", "--untracked-files=all"), "")

    def test_recovery_refuses_replacement_backup_directory(self):
        moved = self.root / "moved-backups"
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            exchange = apply.swap_ledger_entries

            def replace_directory(backups, name, directory, target):
                exchange(backups, name, directory, target)
                path = journal.ledger_backup_path(self.ledger.stat().st_dev)
                path.rename(moved)
                path.mkdir(mode=0o700)
                (path / name).write_text("decoy")

            with patch.object(apply, "swap_ledger_entries", side_effect=replace_directory), \
                    self.assertRaisesRegex(ValueError, "backup directory changed"):
                journal.reconcile(ident)
        with self.locked() as journal:
            with self.assertRaisesRegex(ValueError, "backup directory changed"):
                journal.reconcile(ident)
            record = journal.load(ident)
            self.assertEqual(record["phase"], "effect-verified")
            self.assertFalse(record.get("ledger_backups"))
            path = journal.ledger_backup_path(self.ledger.stat().st_dev)
            shutil.rmtree(path)
            moved.rename(path)
            report = io.StringIO()
            with redirect_stdout(report):
                self.assertEqual(journal.reconcile(ident), "recorded")
            self.assert_ledger_backup(journal, ident, self.table, report)

    def test_failed_final_save_keeps_backup_directory_bound(self):
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            save = journal.save

            def fail_final_save(record, phase):
                if phase == "recorded":
                    raise OSError("before final receipt save")
                return save(record, phase)

            with patch.object(journal, "save", side_effect=fail_final_save), \
                    self.assertRaisesRegex(OSError, "before final receipt save"):
                journal.reconcile(ident)
            path = journal.ledger_backup_path(self.ledger.stat().st_dev)
            backup, = path.iterdir()
            path.rename(self.root / "moved-backups")
            path.mkdir(mode=0o700)
            backup.write_text("decoy")
        with self.locked() as journal:
            with self.assertRaisesRegex(ValueError, "backup directory changed"):
                journal.reconcile(ident)
            self.assertEqual(journal.load(ident)["phase"], "effect-verified")

    def test_directory_replaced_during_final_receipt_save(self):
        moved = self.root / "moved-backups"
        report = io.StringIO()
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            path = journal.ledger_backup_path(self.ledger.stat().st_dev)
            save = journal.save

            def replace_during_save(record, phase):
                if phase == "recorded" and not moved.exists():
                    path.rename(moved)
                    path.mkdir(mode=0o700)
                    backup, = moved.iterdir()
                    (path / backup.name).write_text("decoy")
                    save(record, phase)
                    self.assertEqual(journal.load(ident)["ledger_exchange"], record["ledger_exchange"])
                else:
                    save(record, phase)

            with patch.object(journal, "save", side_effect=replace_during_save), redirect_stdout(report), \
                    self.assertRaisesRegex(ValueError, "backup directory changed"):
                journal.reconcile(ident)
            backup, = moved.iterdir()
            self.assertEqual(backup.read_text(), self.table)
            self.assertIn(str(backup), report.getvalue())
            self.assertEqual((path / backup.name).read_text(), "decoy")
        with self.locked() as journal:
            with self.assertRaisesRegex(ValueError, "backup directory changed"):
                journal.reconcile(ident)
            self.assertEqual(journal.load(ident)["phase"], "effect-verified")
            shutil.rmtree(path)
            moved.rename(path)
            self.assertEqual(journal.reconcile(ident), "recorded")
            self.assertEqual(self.ledger.read_text().count(ident), 1)

    def test_directory_replaced_before_finalization_reports_displaced_copy(self):
        moved = self.root / "moved-backups"
        report = io.StringIO()
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            path = journal.ledger_backup_path(self.ledger.stat().st_dev)
            finish = journal.finish_ledger_exchange

            def replace_before_finish(*args, **kwargs):
                path.rename(moved)
                path.mkdir(mode=0o700)
                backup, = moved.iterdir()
                (path / backup.name).write_text("decoy")
                return finish(*args, **kwargs)

            with patch.object(journal, "finish_ledger_exchange", side_effect=replace_before_finish), \
                    redirect_stdout(report), self.assertRaisesRegex(ValueError, "backup directory changed"):
                journal.reconcile(ident)
            backup, = moved.iterdir()
            self.assertEqual(backup.read_text(), self.table)
            self.assertEqual((path / backup.name).read_text(), "decoy")
            self.assertIn(str(backup), report.getvalue())
            self.assertEqual(journal.load(ident)["phase"], "effect-verified")
            shutil.rmtree(path)
            moved.rename(path)
            self.assertEqual(journal.reconcile(ident), "recorded")

    def test_undo_after_completed_ledger_backup_is_removed(self):
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            self.assertEqual(journal.reconcile(ident), "recorded")
            record = journal.load(ident)
            backup, = record["ledger_backups"]
            Path(backup).unlink()
        target = self.project / self.tool["TARGET"]
        self.assertTrue(target.exists())
        with self.locked() as journal:
            journal.undo(ident, lambda _, record: self.tool["transact"](self.project, record=record))
            record = journal.load(ident)
            self.assertEqual(record["phase"], "reverted")
            self.assertNotIn("ledger_exchange", record)
        self.assertFalse(target.exists())

    def test_undo_recovers_completed_round_one_binding_after_copy_is_removed(self):
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            save = journal.save

            def save_round_one(record, phase):
                if phase != "recorded" or record.get("ledger_exchange"):
                    save(record, phase)

            with patch.object(journal, "save", side_effect=save_round_one):
                self.assertEqual(journal.reconcile(ident), "recorded")
            record = journal.load(ident)
            backup, = record["ledger_backups"]
            self.assertEqual(record["ledger_exchange"][-1], Path(backup).name)
            Path(backup).unlink()
            journal.undo(ident, lambda _, record: self.tool["transact"](self.project, record=record))
            self.assertEqual(journal.load(ident)["phase"], "reverted")
        self.assertFalse((self.project / self.tool["TARGET"]).exists())

    def test_directory_replaced_while_clearing_final_binding_restores_recovery(self):
        moved, report = self.root / "moved-backups", io.StringIO()
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            path = journal.ledger_backup_path(self.ledger.stat().st_dev)
            save = journal.save

            def replace_when_cleared(record, phase):
                save(record, phase)
                if phase == "recorded" and "ledger_exchange" not in record:
                    path.rename(moved)
                    path.mkdir(mode=0o700)

            with patch.object(journal, "save", side_effect=replace_when_cleared), redirect_stdout(report), \
                    self.assertRaisesRegex(ValueError, "backup directory changed"):
                journal.reconcile(ident)
            backup, = moved.iterdir()
            self.assertEqual(backup.read_text(), self.table)
            self.assertIn(str(backup), report.getvalue())
            record = journal.load(ident)
            self.assertEqual(record["phase"], "effect-verified")
            self.assertEqual(record["ledger_exchange"][-1], backup.name)

    def test_git_cross_device_ledger_refuses_local_backup(self):
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        with self.locked() as journal:
            with self.assertRaisesRegex(ValueError, "requires a private backup directory"):
                journal.ledger_backup_path(self.ledger.stat().st_dev + 1)

    def test_non_git_cross_device_ledger_uses_private_local_backup(self):
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            fstat = os.fstat

            def other_state_device(fd):
                info = fstat(fd)
                if fd == journal.state:
                    return SimpleNamespace(st_dev=info.st_dev + 1)
                return info

            with patch.object(os, "fstat", side_effect=other_state_device):
                self.assertEqual(journal.reconcile(ident), "recorded")
                journal.undo(ident, lambda *_: None)
            record = journal.load(ident)
            self.assertEqual(record["phase"], "reverted")
            self.assertEqual({Path(path).parent for path in record["ledger_backups"]},
                             {self.ledger.parent / apply.LEDGER_BACKUPS})

    def test_recovery_moves_legacy_backup_out_of_checkout(self):
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        legacy = self.ledger.parent / apply.LEDGER_BACKUPS
        legacy.mkdir(mode=0o700)
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            displaced = legacy / (ident + "-" + "1" * 32 + ".md")
            displaced.write_text("older ledger copy")
            record = journal.load(ident)
            record["ledger_backups"] = [str(displaced)]
            journal.save(record, record["phase"])
            self.assertEqual(journal.reconcile(ident), "recorded")
            paths = [Path(path) for path in journal.load(ident)["ledger_backups"]]
            self.assertEqual({path.read_text() for path in paths}, {self.table, "older ledger copy"})
            self.assertFalse(any(path.is_relative_to(self.project) for path in paths))
            self.assertEqual(list(legacy.iterdir()), [])

    def test_reconcile_and_undo_keep_read_only_legacy_backup(self):
        legacy = self.ledger.parent / apply.LEDGER_BACKUPS
        legacy.mkdir(mode=0o700)
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            displaced = legacy / (ident + "-" + "1" * 32 + ".md")
            displaced.write_text("older ledger copy")
            with patch.object(os, "rename", side_effect=PermissionError(errno.EACCES, "read-only legacy directory")):
                self.assertEqual(journal.reconcile(ident), "recorded")
                journal.undo(ident, lambda *_: None)
            record = journal.load(ident)
            self.assertEqual(record["phase"], "reverted")
            self.assertIn(str(displaced), record["ledger_backups"])
            self.assertEqual(displaced.read_text(), "older ledger copy")

    def test_reconcile_and_undo_keep_legacy_backup_on_read_only_mount(self):
        legacy = self.ledger.parent / apply.LEDGER_BACKUPS
        legacy.mkdir(mode=0o700)
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            displaced = legacy / (ident + "-" + "1" * 32 + ".md")
            displaced.write_text("older ledger copy")
            displaced.chmod(0o644)
            original = displaced.stat()
            fchmod = os.fchmod

            def chmod_on_mount(fd, mode):
                if os.path.samestat(os.fstat(fd), original):
                    raise OSError(errno.EROFS, "read-only legacy mount")
                return fchmod(fd, mode)

            with patch.object(os, "rename", side_effect=OSError(errno.EROFS, "read-only legacy mount")), \
                    patch.object(os, "fchmod", side_effect=chmod_on_mount):
                self.assertEqual(journal.reconcile(ident), "recorded")
                journal.undo(ident, lambda *_: None)
            record = journal.load(ident)
            self.assertEqual(record["phase"], "reverted")
            self.assertIn(str(displaced), record["ledger_backups"])
            self.assertEqual(displaced.read_text(), "older ledger copy")
            self.assertEqual(displaced.stat().st_mode & 0o777, 0o644)

    def ledger_effect(self, journal):
        self.signed_extract([self.project])
        ident = self.action("ls", [self.project])
        native_id = journal.begin_allow_rule(ident)
        self.tool["transact"](self.project, "ls", action_id=native_id)
        return ident

    def assert_ledger_backup(self, journal, ident, edited, report):
        paths = [Path(path) for path in journal.load(ident).get("ledger_backups", [])]
        self.assertEqual(len(paths), 1)
        path = paths[0]
        self.assertEqual(path.read_text(), edited)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertIn(str(path), report.getvalue())

    def test_editor_descriptor_survives_write_after_verification(self):
        edited = self.table + "\nEditor saved after verification.\n"
        report = io.StringIO()
        with self.locked() as journal, self.ledger.open("r+") as editor:
            ident = self.ledger_effect(journal)
            exchange = journal.exchange_ledger

            def save_after_verification(*args, **kwargs):
                result = exchange(*args, **kwargs)
                editor.seek(0, os.SEEK_END)
                editor.write(edited[len(self.table):])
                editor.close()
                return result

            with patch.object(journal, "exchange_ledger", side_effect=save_after_verification), redirect_stdout(report):
                self.assertEqual(journal.reconcile(ident), "recorded")
            self.assert_ledger_backup(journal, ident, edited, report)
            self.assertEqual(self.ledger.read_text().count(ident), 1)

    def test_crash_after_exchange_recovers_concurrent_save(self):
        edited = self.table + "\nEditor saved before the swap.\n"
        with self.locked() as journal:
            ident = self.ledger_effect(journal)
            exchange = apply.swap_ledger_entries

            def crash_after_exchange(*args, **kwargs):
                self.ledger.write_text(edited)
                exchange(*args, **kwargs)
                raise OSError("after ledger exchange")

            with patch.object(apply, "swap_ledger_entries", side_effect=crash_after_exchange):
                with self.assertRaisesRegex(OSError, "after ledger exchange"):
                    journal.reconcile(ident)
            self.assertEqual(journal.load(ident)["phase"], "effect-verified")
            self.assertEqual(self.ledger.read_text().count(ident), 1)
        report = io.StringIO()
        with self.locked() as journal, redirect_stdout(report):
            self.assertEqual(journal.reconcile(ident), "recorded")
            self.assert_ledger_backup(journal, ident, edited, report)
            self.assertEqual(self.ledger.read_text().count(ident), 1)

    def test_legacy_table_without_outer_pipes_and_malformed_row(self):
        ident = "fa1_" + "1" * 64
        legacy = "\n".join(" | ".join(apply.cells(line)) for line in self.table.splitlines()) + "\n"
        row = "2026-11-18 | Ordinary backup | Audit | Less text | pending | pending"
        with self.locked() as journal:
            self.ledger.write_text(legacy + row + " | malformed\n")
            with self.assertRaisesRegex(ValueError, "invalid broker ledger table row"):
                journal.preflight(ident, "host-fix", evidence_scope=[str(self.project)])
            self.ledger.write_text(legacy + row + "\n")
            tool_record = journal.tool_record(ident, "host-fix")
            self.assertEqual(journal.record_verified(ident, "host-fix", tool_record, "4" * 64, "fixture", 10,
                                                     evidence_scope=[str(self.project)]), "recorded")
            bare = [line.strip().removeprefix("|").removesuffix("|").strip() if ident in line else line
                    for line in self.ledger.read_text().splitlines()]
            self.ledger.write_text("\n".join(bare) + "\n")
            inverse = unittest.mock.Mock()
            journal.undo(ident, inverse)
            inverse.assert_called_once_with("host-fix", tool_record)
            self.assertIn(row + "\n", self.ledger.read_text())
            self.assertIn("reverted", self.ledger.read_text())

    def add_worktree(self, worktree):
        for arguments in (["init", "-q"], ["-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                           "commit", "--allow-empty", "-qm", "initial"],
                          ["worktree", "add", "-q", "--detach", str(worktree)]):
            result = subprocess.run(["git", "-C", str(self.project), *arguments], capture_output=True, text=True,
                                    env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_metric_keeps_both_canonical_worktrees(self):
        worktree = self.root / "worktree with spaces"
        self.add_worktree(worktree)
        roots = sorted([self.project, worktree])
        self.signed_extract(roots)
        ident = self.action("ls", roots)
        with self.locked() as journal:
            with self.assertRaisesRegex(ValueError, "evidence scope is unavailable"):
                journal.preflight(ident, "allow-rule", evidence_scope=[str(self.root / "unknown")])
            expected = dict(id=ident, operation="allow-rule", count=10, date=date.today().isoformat(),
                            evidence_scope=list(map(str, roots)))
            metric = journal.row(expected)[6]
            argv = shlex.split(metric.strip("`"))
            scopes = [(self.project / argv[index + 1]).resolve()
                      for index, arg in enumerate(argv) if arg == "--cwd"]
            self.assertEqual(scopes, roots)
            native_id = journal.begin_allow_rule(ident)
            self.tool["transact"](self.project, "ls", action_id=native_id)
            journal.reconcile(ident)
            self.assertIn(metric, self.ledger.read_text())

    def test_metric_audits_worktree_named_with_literal_tilde(self):
        worktree = self.project / "~x"
        self.add_worktree(worktree)
        with self.locked() as journal:
            record = dict(id="fa1_" + "1" * 64, operation="allow-rule", count=10,
                          date=date.today().isoformat(), evidence_scope=[str(worktree)])
            argv = shlex.split(journal.row(record)[6].strip("`"))
        result = subprocess.run([sys.executable, str(SCRIPTS / "token-audit"), *argv[1:], "--no-write", "--json"],
                                cwd=self.project, env=dict(os.environ, CODEX_HOME=str(self.root / "codex"),
                                                           COPILOT_HOME=str(self.root / "copilot")),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["scope"]["cwd"], [str(worktree)])
        self.assertEqual(argv[2], str(worktree))

    def test_preexisting_relative_metric_row_stays_linked(self):
        with self.locked() as journal, redirect_stdout(io.StringIO()):
            ident = self.ledger_effect(journal)
            journal.reconcile(ident)
            record = journal.load(ident)
            del record["absolute_metric"]
            metric = journal.row(record)[6]
            historical = "`kaizen-token-audit --cwd .`"
            self.ledger.write_text(self.ledger.read_text().replace(metric, historical))
            journal.save(record, "recorded")
            self.assertEqual(journal.reconcile(ident), "recorded")
            journal.undo(ident, lambda _, native: self.tool["transact"](self.project, record=native))
            self.assertEqual(journal.reconcile(ident), "reverted")
            self.assertIn(historical, self.ledger.read_text())

    def test_recovery_after_native_publication_without_extract(self):
        extract = self.signed_extract([self.project])
        ident = self.action("ls", [self.project])
        native_globals = self.tool["write_effect"].__globals__
        rename = native_globals["rename_effect"]

        def crash_after_rename(*args, **kwargs):
            rename(*args, **kwargs)
            raise OSError("after native effect")

        with self.locked() as journal:
            native_id = journal.begin_allow_rule(ident)
            with patch.dict(native_globals, rename_effect=crash_after_rename):
                with self.assertRaisesRegex(OSError, "after native effect"):
                    self.tool["transact"](self.project, "ls", action_id=native_id)
        extract.unlink()
        target = self.project / self.tool["TARGET"]
        self.assertTrue(target.is_file())
        native_journal = self.store.friction / self.tool["STATE"]
        raw = native_journal.read_bytes()
        tampered = dict(json.loads(raw), mac="0" * 64)
        native_journal.write_text(json.dumps(tampered))
        with self.locked() as journal:
            with self.assertRaisesRegex(ValueError, "native allow-rule journal does not authenticate"):
                journal.reconcile(ident)
            self.assertEqual(journal.load(ident)["phase"], "apply-pending")
            native_journal.write_bytes(raw)
            self.assertEqual(journal.reconcile(ident), "recorded")
            journal.undo(ident, lambda _, record: self.tool["transact"](self.project, record=record))
        self.assertFalse(target.exists())
        self.assertEqual(self.ledger.read_text().count(ident), 1)
        self.assertIn("reverted", self.ledger.read_text())

    def test_copied_install_undo_and_bookkeeping_recovery(self):
        self.copied_install_undo_and_bookkeeping_recovery()

    def test_undo_resolves_relative_state_paths(self):
        self.copied_install_undo_and_bookkeeping_recovery(relative_state=True)

    def scheduled_marker_crashes(self, installed, command, env, *, commit_only=False):
        runner, runtime = (installed / name for name in ("kaizen-scheduled", "kaizen_friction_apply.py"))
        fix = installed / "kaizen-host-fix"
        # Exercise the copied transactions with a disposable marker on either Unix test host.
        publication = "os.rename('.fixture-marker', MARKER, src_dir_fd=directory, dst_dir_fd=directory)"
        fix_source = (fix.read_text().replace("LINUX_WRITES = False", "LINUX_WRITES = True")
                       .replace("PLATFORM = sys.platform", "PLATFORM = 'linux'")
                       .replace("os.O_TMPFILE", "os.O_CREAT")
                       .replace("fd = os.open('.'", "fd = os.open('.fixture-marker'")
                       .replace("os.link(f'/proc/self/fd/{fd}', MARKER, dst_dir_fd=directory, follow_symlinks=True)",
                                publication))
        fix.write_text(fix_source)
        runtime_source = runtime.read_text().replace("frozenset()", "frozenset({'99.0.0'})", 1).replace(
            'sys.platform.startswith("linux") and tool["LINUX_WRITES"]', 'tool["LINUX_WRITES"]')
        runtime.write_text(runtime_source)
        probe = installed / "kaizen-host-probe"
        probe.write_text("""import json, pathlib, sys
from datetime import datetime, timezone
project = sys.argv[sys.argv.index('--project') + 1]
out = pathlib.Path(sys.argv[sys.argv.index('--out') + 1])
targets = [str(pathlib.Path(project) / name) for name in ('build', 'dist')
           if (pathlib.Path(project) / name).is_dir()]
(out / 'host-probe-fixture.json').write_text(json.dumps(dict(v=1, project=project,
    generated_at=datetime.now(timezone.utc).isoformat(),
    findings=[dict(id='indexed-output', catalog_id='linux-localsearch',
                   subject=target, evidence=dict(size_bytes=1)) for target in targets],
    regenerable_dirs=[dict(path=target, size_bytes=1) for target in targets])))
""")
        claude = installed / "fixture-claude"
        claude.write_text("#!" + sys.executable + "\n" + r"""import json, os, pathlib, re, shlex, subprocess, sys, time
if sys.argv[1:] == ['--version']:
    print('99.0.0 (Claude Code)')
    sys.exit()
prompt = sys.argv[sys.argv.index('-p') + 1]
inputs = pathlib.Path(json.loads(prompt.splitlines()[0].split(' friction-inputs=', 1)[1]))
actions = [dict(id=row['id'], intent='apply') for row in json.loads(inputs.read_text())['actions']]
session = sys.argv[sys.argv.index('--session-id') + 1]
fault = os.getenv('FIXTURE_FAULT')
if fault == 'timeout':
    time.sleep(3)
if fault == 'invalid':
    (pathlib.Path(os.environ['CLAUDE_CONFIG_DIR']) / 'agent-kaizen.json').write_text('{"maxChangesPerRun":false}')
if fault == 'target':
    pathlib.Path('build').rename('old-build')
    pathlib.Path('build').mkdir()
events = [
    dict(type='system', subtype='init', claude_code_version='99.0.0', cwd=os.getcwd()),
    dict(type='assistant', parent_tool_use_id=None, message=dict(role='assistant',
         content=[dict(type='text', text='Review')])),
]
if fault == 'unbacked':
    events[1]['message']['content'].append(dict(type='tool_use', id='tool', name='Write',
        input=dict(file_path=os.path.join(os.getcwd(), 'unbacked'), content='fixture')))
    events.insert(2, dict(type='user', parent_tool_use_id=None, message=dict(
        role='user', content=[dict(type='tool_result', tool_use_id='tool')])))
case = os.getenv('FIXTURE_COMMIT')
candidate = re.search(r'local commit with action ID (fa1_[0-9a-f]{64})', prompt)
if case and candidate:
    actions.append(dict(id=candidate[1], intent='apply'))
    def dispatch(name, **arguments):
        ident = str(len(events))
        for role, block in [('assistant', dict(type='tool_use', id=ident, name=name, input=arguments)),
                            ('user', dict(type='tool_result', tool_use_id=ident))]:
            events.append(dict(type=role, parent_tool_use_id=None, message=dict(role=role, content=[block])))
    def backup(*args):
        argv = [str(pathlib.Path(sys.argv[0]).with_name('kaizen-backup')), *args]
        output = subprocess.check_output(argv, text=True).strip()
        dispatch('Bash', command=shlex.join(argv))
        return output
    if case != 'empty':
        target = pathlib.Path.cwd() / 'tracked'
        folder = backup('begin', '--skill', 'trim', '--ledger', 'Fixture', str(target))
        target.write_text('after')
        dispatch('Edit', file_path=str(target))
        backup('finish', folder)
        if case == 'valid' or case.startswith('proof-'):
            fixture = json.loads(os.environ['FIXTURE_LEDGER'])
            ledger = pathlib.Path.cwd() / fixture['valid']['ledger_relpath']
            ledger.write_text(fixture['after_utf8'].replace(fixture['valid']['manifest_ids'][0], pathlib.Path(folder).name))
            dispatch('Edit', file_path=str(ledger))
        if case == 'index':
            subprocess.run(['git', 'add', 'tracked'], check=True)
        if case == 'head':
            subprocess.run(['git', 'commit', '--allow-empty', '-qm', 'moved'], check=True)
        if case == 'ambiguous':
            other = target.with_name('other')
            second = backup('begin', '--skill', 'trim', '--ledger', 'Fixture', str(other))
            other.write_text('other edit')
            dispatch('Write', file_path=str(other))
            backup('finish', second)
line = '<!-- kaizen-host-actions ' + json.dumps(dict(v=1, actions=actions)) + ' -->'
if fault == 'malformed':
    line = '<!-- kaizen-host-actions invalid -->'
events.append(dict(type='result', subtype='success', is_error=False, result='Review\n' + line + '\n'))
for index, event in enumerate(events):
    print(json.dumps(dict(event, session_id=session, uuid=str(index))))
""")
        claude.chmod(0o700)
        config = installed.parent
        policy = config / "agent-kaizen.json"
        enabled = '{"scheduledAutonomy":"auto","schedule":"always"}'

        def init_project(name, outputs):
            project = installed.parent.parent / name
            ledger = project / apply.LEDGER
            ledger.parent.mkdir(parents=True)
            ledger.write_text(self.table)
            for output in outputs:
                (project / output).mkdir()
            (project / ".gitignore").write_text("".join(output + "/\n" for output in outputs))
            for args in (("init", "-q"), ("add", "."), ("-c", "user.name=Fixture", "-c",
                         "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null",
                         "commit", "--no-gpg-sign", "-qm", "fixture")):
                subprocess.run(["git", "-C", str(project), *args], check=True, env=env)
            return project, ledger

        if commit_only:
            self.scheduled_local_commits(installed, command, env, runtime_source, init_project)
            return

        for crash in ("timeout", "invalid", "target", "malformed", "unbacked", "takeover", "effect", "row", "policy"):
            policy.write_text(enabled)
            project, ledger = init_project(crash, ("build",))
            marker = project / "build/.nomedia"
            source = runner.read_text()
            if crash == "takeover":
                statement = '                        run_scheduled_broker(audits, project, options, receipt=prepared[1], attempt=attempt)'
                runner.write_text(source.replace(statement, '''                        state_path = root / "friction" / ("prepare-" + project.key + ".json")
                        takeover = json.loads(state_path.read_text())
                        takeover["generation"] += 1
                        state_path.write_text(json.dumps(takeover))
''' + statement))
            if crash == "effect":
                statement = '            record["verification"] = result'
                runtime.write_text(runtime_source.replace(statement, '            os._exit(77)\n' + statement))
            elif crash == "row":
                statement = '                    terminal(ident, applied=phase == "recorded")'
                runner.write_text(source.replace(statement, '                    os._exit(77)\n' + statement))
            review = ("review", "--force", "--project-dir", project, "--claude", claude)
            if crash == "policy":
                fix.write_text(fix_source.replace(publication, publication + '''
    (Path(os.environ["CLAUDE_CONFIG_DIR"]) / "agent-kaizen.json").write_text('{"maxChangesPerRun":false}')
'''))
                # This policy-change review exceeded 30 seconds in the full sandbox suite.
                command(runner, *review, timeout=90, KAIZEN_SKIP_CHECKS="1")
                self.assertFalse(marker.exists())
                policy.write_text(enabled)
                fix.write_text(fix_source)
                command(runner, *review, KAIZEN_SKIP_CHECKS="1")
                self.assertEqual(ledger.read_text(), self.table)
                receipts = json.loads((config / "audits/host-actions.json").read_text())["receipts"]
                self.assertNotIn("pending", json.dumps(receipts[str(project)]))
                continue
            if crash not in ("effect", "row"):
                journals = config / "backups/friction"
                command(runner, *review, KAIZEN_SKIP_CHECKS="1", FIXTURE_FAULT=crash,
                        KAIZEN_REVIEW_TIMEOUT="1" if crash == "timeout" else "30")
                self.assertFalse(marker.exists(), crash)
                self.assertFalse(list(journals.glob("broker-fa1_*.json")), crash)
                self.assertEqual(ledger.read_text(), self.table, crash)
                self.assertFalse(any("acknowledged_generation" in json.loads(path.read_text())
                                     for path in journals.glob("prepare-*.json")), crash)
                if crash in ("target", "takeover"):
                    receipts = json.loads((config / "audits/host-actions.json").read_text())["receipts"]
                    self.assertIn("pending", json.dumps(receipts[str(project)]))
                runner.write_text(source)
                continue
            command(runner, *review, code=77, KAIZEN_SKIP_CHECKS="1")
            state = config / "audits/host-actions.json"
            rows = json.loads(state.read_text())["actions"]
            ident, = (ident for ident, row in rows.items() if row["canonical_project"] == str(project))
            self.assertTrue(marker.is_file())
            stamp = marker.stat().st_ino
            self.assertEqual(ledger.read_text().count(ident), int(crash == "row"))
            prepare_state = next(path for path in (config / "backups/friction").glob("prepare-*.json")
                                 if json.loads(path.read_text())["project"] == str(project))
            self.assertNotIn("acknowledged_generation", json.loads(prepare_state.read_text()))
            runner.write_text(source)
            runtime.write_text(runtime_source)
            command(runner, *review, KAIZEN_SKIP_CHECKS="1")
            self.assertEqual(marker.stat().st_ino, stamp)
            self.assertEqual(ledger.read_text().count(ident), 1)
            self.assertIn("acknowledged_generation", json.loads(prepare_state.read_text()))
            command(runner, "actions", "undo", ident, "--for", project)
            self.assertFalse(marker.exists())
            self.assertIn("reverted", ledger.read_text())
        project = installed.parent.parent / "target"
        command(runner, "review", "--force", "--project-dir", project, "--claude", claude, KAIZEN_SKIP_CHECKS="1")
        self.assertTrue((project / "build/.nomedia").exists())
        self.assertEqual((project / apply.LEDGER).read_text().count("[action:"), 1)

        policy.write_text(json.dumps(dict(scheduledAutonomy="auto", schedule="always", maxChangesPerRun=2)))
        for fault in ("unstarted", "started", "two-slots", "config-created"):
            with self.subTest(fault=fault):
                project, ledger = init_project(fault, ("build", "dist"))
                review = ("review", "--force", "--project-dir", project, "--claude", claude)
                if fault in ("unstarted", "started"):
                    statement = '            self.save(record, "marker-pending")'
                    runner_source = runner.read_text()
                    if fault == "unstarted":
                        runtime.write_text(runtime_source.replace(statement, statement + '\n            os._exit(77)', 1))
                    else:
                        native_save = "                write_record(state, name, store, record)"
                        fix.write_text(fix_source.replace(native_save, native_save + "\n                os._exit(77)", 1))
                        error = '            raise ValueError("native marker transaction is unavailable or ambiguous")'
                        runner.write_text(runner_source.replace(error, "            os._exit(77)", 1))
                    command(runner, *review, code=77, KAIZEN_SKIP_CHECKS="1")
                    runner.write_text(runner_source)
                    runtime.write_text(runtime_source)
                    fix.write_text(fix_source)
                    records = config / "backups/friction"
                    journal, = (path for path in records.glob("broker-fa1_*.json")
                                if json.loads(path.read_text())["scope"][0] == str(project))
                    reservation = json.loads(journal.read_text())
                    native = Path(reservation["tool_record"])
                    self.assertEqual(native.exists(), fault == "started")
                    target = Path(reservation["target"])
                    target.rename(project.with_name(project.name + "-replaced-output"))
                    target.mkdir()
                    other = project / ("dist" if target.name == "build" else "build")
                    command(runner, *review, KAIZEN_SKIP_CHECKS="1")
                    after = json.loads(journal.read_text())
                    store = json.loads((config / "audits/host-actions.json").read_text())
                    generation = "scheduled:" + reservation["generation"]
                    state = store["receipts"][str(project)][generation][reservation["id"]]
                    if fault == "unstarted":
                        self.assertNotIn("reservation", after)
                        self.assertIn("native journal never started", after["reason"])
                        self.assertEqual(after["phase"], "cancelled")
                        self.assertEqual(state, "terminal")
                    else:
                        self.assertEqual(after, reservation)
                        self.assertEqual(state, "pending")
                    self.assertFalse((target / ".nomedia").exists())
                    self.assertTrue((other / ".nomedia").is_file())
                    self.assertEqual(ledger.read_text().count("[action:"), 1)
                    continue

                project_policy = project / "docs/kaizen/config.json"
                if fault == "config-created":
                    statement = '        self.finish_ledger_exchange(record, "recorded", backups)'
                    runtime.write_text(runtime_source.replace(
                        statement, statement + '\n        (self.project / "docs/kaizen/config.json").write_text("{}")', 1))
                command(runner, *review, KAIZEN_SKIP_CHECKS="1")
                runtime.write_text(runtime_source)
                expected = 1 if fault == "config-created" else 2
                self.assertEqual(project_policy.exists(), fault == "config-created")
                self.assertEqual(sum((project / name / ".nomedia").is_file() for name in ("build", "dist")), expected)
                self.assertEqual(ledger.read_text().count("[action:"), expected)
        (config / "agent-kaizen.json").unlink()

    def scheduled_local_commits(self, installed, command, env, runtime_source, init_project):
        runner, runtime, claude, backup = (installed / name for name in (
            "kaizen-scheduled", "kaizen_friction_apply.py", "fixture-claude", "kaizen-backup"))
        policy = installed.parent / "agent-kaizen.json"
        fixture = (Path(__file__).parent / "fixtures/ledger_attestation_v1.json").read_text()
        cases = ("closed", "propose", "dirty", "empty", "budget", "head", "index", "ambiguous", "valid",
                 "proof-missing", "proof-forged", "proof-mismatch", "timeout", "before-journal", "after-cas", "after-row")
        for case in cases:
            with self.subTest(commit=case):
                project, ledger = init_project("commit-" + case, ("build",))
                (project / "tracked").write_text("before")
                if case == "valid" or case.startswith("proof-"):
                    ledger.write_bytes(base64.b64decode(json.loads(fixture)["valid"]["before_b64"]))

                def git(*args):
                    return subprocess.check_output(["git", "-C", str(project), *args], env=env, text=True).strip()

                git("add", ".")
                git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "tracked")
                git("config", "user.name", "Fixture")
                git("config", "user.email", "fixture@example.invalid")
                if case == "dirty":
                    (project / "tracked").write_text("user edit")
                quota = {"budget": 1, "ambiguous": 3}.get(case, 2)
                policy.write_text(json.dumps(dict(scheduledAutonomy="propose-only" if case == "propose" else "auto",
                                                 schedule="always", maxChangesPerRun=quota)))
                review = ("review", "--force", "--project-dir", project, "--claude", claude)
                backup = installed / "kaizen-backup"
                native = backup.read_text()
                runner_source = runner.read_text()
                if case == "closed":
                    runtime.write_text((SCRIPTS / runtime.name).read_text())
                elif case.startswith("proof-"):
                    invalid = json.loads(fixture)["invalid_overrides"]
                    expression = {"proof-missing": "None", "proof-forged":
                                  f'dict(handoff["ledger_attestation"], **{invalid["forged_prefix"]!r})',
                                  "proof-mismatch": f'dict(handoff["ledger_attestation"], **{invalid["wrong_session"]!r})'}[case]
                    statement = '                    payload = json.dumps(handoff, sort_keys=True)'
                    runner.write_text(runner_source.replace(statement, f'                    handoff["ledger_attestation"] = {expression}\n' + statement))
                elif case == "before-journal":
                    statement = '                    record = ledger.reserve_commit('
                    runner.write_text(runner_source.replace(statement, '                    os._exit(77)\n' + statement))
                elif case == "timeout":
                    # The 15-second fixture limit expired before journaling under sandbox load.
                    statement = '                exchange("commit\\n", b"commit: ok\\n")'
                    backup.write_text(native.replace(statement, '                time.sleep(60)\n' + statement))
                elif case == "after-cas":
                    statement = '    if checked_ref(record, records, phase, git_exe) != effect["new"]:'
                    backup.write_text(native.replace(statement, '    if phase == "commit":\n        os._exit(77)\n' + statement))
                    statement = '                    terminal(ident, applied=finish_commit(record) == "recorded")'
                    runner.write_text(runner_source.replace(statement, '                    os._exit(77)'))
                elif case == "after-row":
                    statement = '        self.finish_ledger_exchange(record, "recorded", backups)'
                    runtime.write_text(runtime_source.replace(statement, statement +
                        '\n        if record["operation"] == LOCAL_COMMIT:\n            os._exit(77)', 1))
                interrupted = case.startswith(("before-", "after-"))
                # These initial local-commit reviews exceeded 30 seconds in sandbox runs.
                review_timeout = 90 if case in ("valid", "timeout", "after-cas", "after-row") else 30
                command(runner, *review, code=77 if interrupted else 0,
                        timeout=review_timeout,
                        FIXTURE_COMMIT=case, FIXTURE_LEDGER=fixture, KAIZEN_SKIP_CHECKS="1")
                backup.write_text(native)
                runner.write_text(runner_source)
                runtime.write_text(runtime_source)
                refs = git("for-each-ref", "--format=%(refname)", "refs/kaizen/2*")
                if case == "timeout":
                    self.assertTrue(git("for-each-ref", "refs/kaizen/pending/"))
                if interrupted or case == "timeout":
                    command(runner, *review, KAIZEN_SKIP_CHECKS="1")
                    self.assertEqual(git("for-each-ref", "--format=%(refname)", "refs/kaizen/2*"), refs)
                    self.assertEqual(git("for-each-ref", "refs/kaizen/pending/"), "")
                if case not in ("valid", "after-cas", "after-row"):
                    self.assertEqual(refs, "")
                    if case in ("closed", "propose"):
                        self.assertEqual((project / "tracked").read_text(), "before")
                    continue
                oid = git("rev-parse", refs)
                self.assertEqual(git("rev-parse", refs), oid)
                self.assertEqual(git("diff", "--name-only", "HEAD", refs), "tracked")
                self.assertEqual(ledger.read_text().count("[action:"), 1)
                if case == "valid":
                    ident = re.search(r"\[action:(fa1_[a-f0-9]{64})\]", ledger.read_text())[1]
                    undo = ("actions", "undo", ident, "--for", project)
                    # The first local-commit undo exceeded 30 seconds in the full sandbox suite.
                    command(runner, *undo, timeout=90)
                    command(runner, *undo)
                    self.assertEqual((project / "tracked").read_text(), "before")
                    self.assertEqual(git("diff", "--name-only", "HEAD", refs), "")
    def test_scheduled_local_commits(self):
        self.copied_install_undo_and_bookkeeping_recovery(commit_only=True)

    def copied_install_undo_and_bookkeeping_recovery(self, *, relative_state=False, commit_only=False):
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

            def command(path, *args, code=0, timeout=30, **extra_env):
                result = subprocess.run([sys.executable, "-I", str(path), *map(str, args)], env=dict(env, **extra_env),
                                        cwd=root, capture_output=True, text=True, timeout=timeout)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)

            command(scripts / "install-schedule", "--apply", "--scheduler", "cron")
            installed = config / "bin"
            shutil.rmtree(cache)
            runtime = installed / "kaizen_friction_apply.py"
            self.assertFalse(runtime.is_symlink())
            if not relative_state:
                self.scheduled_marker_crashes(installed, command, env, commit_only=commit_only)
            if commit_only:
                return
            broker = runpy.run_path(str(runtime))["BrokerLedger"]
            host = runpy.run_path(str(installed / "kaizen_friction_actions.py"))
            runner = installed / "kaizen-scheduled"
            installed_runner = runpy.run_path(str(runner))
            store = host["HostActions"](config / "audits", config / "backups",
                                        installed_runner["action_project"], installed_runner["key"])
            secret = store._secret(create=True)
            extracts = config / "audits/extracts"
            extracts.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Flip only the disposable native helper's live gate to exercise its real transaction and inverse.
            helper = installed / "kaizen-allow-rule"
            helper.write_text(helper.read_text().replace("WRITES_ENABLED = False", "WRITES_ENABLED = True", 1))
            tool = runpy.run_path(str(helper))
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
                now = datetime.now(timezone.utc)
                row = dict(cwd_id=hashlib.sha256(str(project).encode()).hexdigest(), literal=literal,
                           accepted=10, denied=0, ambiguous=0)
                evidence = dict(v=1, since=(now - timedelta(days=1)).isoformat(),
                                scope=dict(v=1, cwd=[str(project)], project=None, project_dirs=[]),
                                friction=dict(v=1, audited_at=(now - timedelta(seconds=1)).isoformat(),
                                              summary=dict(capped=False), permission_acceptance=[row]))
                payload = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("ascii")
                evidence["allow_rule_mac"] = hmac.digest(secret, b"allow-rule-extract-v2\0" + payload, "sha256").hex()
                extract = extracts / "fixture.extract.json"
                extract.write_text(json.dumps(evidence))
                extract.chmod(0o600)
                undo = ("actions", "undo", ident, "--for", project)
                with patch.dict(os.environ, env, clear=True), broker.locked(host, store, project) as journal:
                    ledger.write_text("```md\n" + six + "```\n")
                    with self.assertRaises(ValueError):
                        journal.begin_allow_rule(ident)
                    ledger.write_text(six)
                    native_id = journal.begin_allow_rule(ident)
                    pending = journal.load(ident)
                    self.assertNotEqual(ident, native_id)
                    with self.assertRaisesRegex(tool["Refused"], "unknown broker transaction binding"):
                        tool["transact"](project, literal, action_id=ident)
                    result = tool["transact"](project, literal, action_id=native_id)
                    self.assertEqual(result, dict(status="applied", record=native_id))
                    verification = hashlib.sha256(target.read_bytes()).hexdigest()
                    extract.unlink()  # Receipt recovery and undo use the pinned binding.
                    with self.assertRaisesRegex(ValueError, "verified native transaction"):
                        journal.record_verified(ident, "allow-rule", ident, verification,
                                                pending["generation"], pending["count"], evidence_scope=[str(project)])
                    ledger.unlink()
                    with self.assertRaises(FileNotFoundError):
                        journal.reconcile(ident)
                    receipt = journal.load(ident)
                    self.assertEqual(receipt, dict(pending, verification=verification, phase="effect-verified"))
                    ledger.write_text(six)
                    save = journal.save

                    def fail_after_row(record, phase):
                        if record.get("ledger_backups"):
                            raise OSError("after row")
                        return save(record, phase)

                    with patch.object(journal, "save", side_effect=fail_after_row), \
                            self.assertRaisesRegex(OSError, "after row"):
                        journal.reconcile(ident)
                    if enabled:
                        self.assertEqual(journal.reconcile(ident), "recorded")
                    self.assertEqual(ledger.read_text().count(ident), 1)
                    self.assertIn(legacy, ledger.read_text())
                    action_row = next(line for line in ledger.read_text().splitlines() if ident in line)
                    metric = apply.cells(action_row)[6]
                    self.assertEqual(shlex.split(metric.strip("`")), ["kaizen-token-audit", "--cwd", str(project)])
                    self.assertNotIn(str(project), ledger.read_text().replace(metric, ""))

                    (config / "agent-kaizen.json").write_text(json.dumps(dict(enabled=enabled)))
                    if not enabled:

                        def interrupted(operation, record):
                            self.assertEqual(operation, "allow-rule")
                            self.assertEqual(record, native_id)
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
                poison = root / "shadow-import"
                for module in ("signal", "select"):
                    (project / (module + ".py")).write_text(
                        f"open({str(poison)!r}, 'a').write({module!r})\nraise SystemExit(0)\n")
                state_paths = {"CLAUDE_CONFIG_DIR": "config", "KAIZEN_BACKUP_DIR": "config/backups"} if relative_state else {}
                if relative_state and enabled:
                    # Check the actual child environment before executing the native inverse.
                    entry = '    sys.exit(main())\n'
                    checks = (f'    assert os.environ["CLAUDE_CONFIG_DIR"] == {str(config)!r}\n'
                              f'    assert os.environ["KAIZEN_BACKUP_DIR"] == {str(config / "backups")!r}\n')
                    helper.write_text(helper.read_text().replace(entry, checks + entry, 1))
                command(runner, *undo, PYTHONPATH=str(project), **state_paths)
                self.assertFalse(poison.exists())
                self.assertFalse(target.exists())
                self.assertIn(f"reverted ({date.today()})", ledger.read_text())
                store.mark(project, ident, "done")
                command(runner, "actions", "reopen", ident, "--for", project)
                self.assertEqual(store.scoped(project)[0]["status"], "open")
                with broker.locked(host, store, project) as journal:
                    self.assertEqual(journal.reconcile(ident), "reverted")
                    with self.assertRaises(ValueError):
                        journal.preflight(ident, "allow-rule", evidence_scope=[str(project)])
