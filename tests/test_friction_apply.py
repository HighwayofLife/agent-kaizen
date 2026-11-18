"""Offline runtime-envelope and real backup-helper tests for the dormant broker."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import shlex
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
