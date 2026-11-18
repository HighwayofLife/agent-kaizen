"""Exact allow-rule proposals and offline installed-runner boundaries."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch

from test_friction_claude import end, start
from test_schedule_security import SecurityCase
from test_scripts import SCRIPTS, jsonl, write


class AllowRuleTests(SecurityCase):
    def setUp(self):
        super().setUp()
        self.repo = self.project("enrolled")
        self.target = self.repo / ".claude/settings.local.json"
        self.extracts = self.cfg / "audits/extracts"

    def install(self):
        self.run_script("kaizen-link", "--apply", "--mode", "copy", "--only",
                        "kaizen-allow-rule,kaizen-scheduled,kaizen_credentials.py,"
                        "kaizen_worktree_facts.py,kaizen-backup,notes-ledger")
        return self.cfg / "bin"

    def row(self, accepted=10, denied=0, ambiguous=0, literal="ls", root=None):
        return dict(cwd_id=hashlib.sha256(str(root or self.repo).encode()).hexdigest(),
                    literal=literal, accepted=accepted, denied=denied, ambiguous=ambiguous)

    def extract(self, *rows, roots=None, name="fixture", **updates):
        since = datetime.now(timezone.utc) - timedelta(days=1)
        data = dict(v=1, since=since.isoformat(),
                    scope=dict(v=1, cwd=[str(path) for path in roots or [self.repo]],
                               project=None, project_dirs=[]),
                    friction=dict(v=1, audited_at=(since + timedelta(hours=12)).isoformat(),
                                  summary=dict(capped=False),
                                  permission_acceptance=list(rows)))
        data.update(updates)
        return write(self.extracts / (name + ".extract.json"), json.dumps(data))

    def add(self, literal="ls", project=None, code=0):
        return self.run_script("allow-rule", "add", "--project", project or self.repo,
                               "--command", literal, code=code)

    def test_exact_vocabulary_and_no_writes(self):
        self.extract(*(self.row(literal=literal) for literal in ("ls", "ls -a", "ls -l")))
        installed = self.install() / "kaizen-allow-rule"
        env = dict(self.env)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        before = set(installed.parent.iterdir())
        for literal in ("ls", "ls -a", "ls -l"):
            with self.subTest(literal=literal):
                result = subprocess.run([str(installed), "add", "--project", str(self.repo),
                                         "--command", literal], env=env,
                                        capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(result.stdout), dict(
                    operation="add", target=".claude/settings.local.json", rule=f"Bash({literal})",
                    status="proposal-only", accepted=10))
        self.assertEqual(set(installed.parent.iterdir()), before)
        for literal in ("ls .", "ls -a .", "ls -l .", "'ls'", 'ls "-a"', "ls  -a", "ls ",
                        "ls *", "ls > out", "ls; pwd", "ls && pwd", "ls | head",
                        "ls $(pwd)", "ls -a <(pwd)", "ls -al", "/bin/ls", "echo ls"):
            with self.subTest(literal=literal):
                self.assertIn("one exact command", self.add(literal, code=2).stderr)
        self.assertFalse(self.target.parent.exists())
        self.assertFalse((self.cfg / "audits/allow-rules").exists())

    def test_counts_are_exact_and_never_pooled(self):
        for rows in ((self.row(9, denied=1),), (self.row(denied=1),), (self.row(ambiguous=1),),
                     (self.row(5), self.row(5, literal="ls -a")), (self.row(), self.row()),
                     (self.row("10"),), (self.row(ambiguous=False),), (self.row(denied=-1),),
                     (self.row(literal="ls -l"),), (self.row(root=self.root),)):
            self.extract(*rows)
            self.add(code=2)
            self.assertFalse(self.target.parent.exists())
        self.extract(self.row(), self.row(denied=1, literal="ls -a"))
        self.add()

    def test_fresh_exact_scope_and_known_schema(self):
        scope = dict(v=1, cwd=[str(self.repo)], project=None, project_dirs=[])
        now = datetime.now(timezone.utc)
        for update in (
            dict(v=True), dict(v=2), dict(scope=dict(scope, v=2)),
            dict(scope=dict(scope, cwd=None)), dict(scope=dict(scope, cwd=None, project="enrolled")),
            dict(scope=dict(scope, project="enrolled")), dict(scope=dict(scope, project_dirs=["other"])),
            dict(scope=dict(scope, cwd=[str(self.root)])),
            dict(scope=dict(scope, cwd=[str(self.repo), str(self.root)])),
            dict(scope=dict(scope, cwd=[str(self.repo), str(self.repo)])),
            dict(since=(now - timedelta(days=7, seconds=1)).isoformat()),
            dict(since=(now + timedelta(days=1)).isoformat()),
            dict(friction=dict(v=2)),
            dict(friction=dict(v=1, summary=dict(capped=False), permission_acceptance=[self.row()])),
            dict(friction=dict(v=1, audited_at=now.isoformat(), summary=dict(capped=True),
                               permission_acceptance=[self.row()])),
        ):
            with self.subTest(update=update):
                self.extract(self.row(), **update)
                self.add(code=2)
        old = self.extract(self.row())
        stale = (now - timedelta(days=8)).timestamp()
        os.utime(old, (stale, stale))
        self.add(code=2)
        self.add(project=self.work, code=2)
        self.assertFalse(self.target.parent.exists())

    def test_newest_scoped_denial_does_not_fall_back(self):
        old = self.extract(self.row(), name="old")
        older = (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()
        os.utime(old, (older, older))
        denial = self.extract(self.row(denied=1), name="denial")
        self.add(code=2)
        legacy = self.cfg / "audits/projects" / self.runner.key(self.repo)
        legacy.mkdir(parents=True)
        denial.rename(legacy / denial.name)
        self.add(code=2)

    def test_unenrolled_nested_checkout_is_not_a_worktree_peer(self):
        main, linked = self.root / "outer", self.root / "linked"
        self.repo = write(main / "inner/docs/kaizen/config.json", "{}").parents[2]
        self.git(main, "init")
        self.git(main, "commit", "--allow-empty", "-m", "fixture")
        self.git(main, "worktree", "add", "--detach", str(linked))
        foreign = linked / "inner"
        foreign.mkdir()
        self.git(foreign, "init")
        self.extract(self.row(root=foreign), roots=[foreign])
        self.add(code=2)

    def test_scope_probes_cannot_append_git_traces(self):
        self.git(self.repo, "init")
        traces = [self.root / name for name in ("environment-trace", "configuration-trace")]
        config = write(self.root / "gitconfig", f'[trace2]\n\teventTarget = "{traces[1]}"\n')
        self.env["GIT_CONFIG_GLOBAL"] = str(config)
        self.env["GIT_TRACE"] = str(traces[0])
        self.extract(self.row())
        self.add()
        self.assertFalse(any(path.exists() for path in traces))

    def test_invalid_cli_arguments_do_not_echo_private_tokens(self):
        secret = "private-fixture-argument"
        for argv in ((secret,), ("add", "--project", self.repo, "--command", "ls", secret)):
            result = self.run_script("allow-rule", *argv, code=2)
            self.assertNotIn(secret, result.stderr)

    def test_copy_without_helpers_has_help_and_a_clean_refusal(self):
        self.run_script("kaizen-link", "--apply", "--mode", "copy", "--only", "kaizen-allow-rule")
        installed = self.cfg / "bin/kaizen-allow-rule"
        for argv, expected in ((["--help"], 0),
                               (["add", "--project", str(self.repo), "--command", "ls"], 2)):
            result = subprocess.run([str(installed), *argv], env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, expected)
            self.assertNotIn("Traceback", result.stderr)

    def test_linked_worktree_counters_and_canonical_settings(self):
        linked = self.root / "linked"
        self.git(self.repo, "init")
        self.git(self.repo, "commit", "--allow-empty", "-m", "fixture")
        self.git(self.repo, "worktree", "add", "--detach", str(linked))
        (linked / "docs/kaizen").mkdir(parents=True)
        self.extract(self.row(5), self.row(5, root=linked), roots=[self.repo, linked])
        self.add(project=linked, code=2)
        self.extract(self.row(9, denied=1), self.row(root=linked), roots=[self.repo, linked])
        write(self.target, '{"permissions":{"deny":["Bash(ls)"]}}')
        self.assertIn("conflicting local", self.add(project=linked, code=2).stderr)
        self.target.unlink()
        self.add(project=linked)
        self.assertFalse((linked / ".claude").exists())

    def test_p05_distinct_acceptances_from_synthetic_transcript(self):
        now = datetime.now(timezone.utc) - timedelta(minutes=1)
        events = []
        for i in range(10):
            begin = start(str(i), 0, "ls", cwd=str(self.repo))
            finish = end(str(i), 1, cwd=str(self.repo),
                         permissionDecision=dict(source="user", decision="accept"),
                         toolUseResult=dict(durationMs=1))
            begin["timestamp"] = now.isoformat()
            finish["timestamp"] = (now + timedelta(seconds=1)).isoformat()
            events.extend([begin, finish])
        session = self.cfg / "projects/fixture/trace.jsonl"
        jsonl(session, events[:2] * 10)
        self.run_script("token-audit", "--cwd", self.repo)
        self.add(code=2)
        jsonl(session, events)
        self.run_script("token-audit", "--cwd", self.repo, "--days", "7")
        self.assertIn("--days 6", self.add(code=2).stderr)
        self.run_script("token-audit", "--cwd", self.repo)
        self.assertEqual(json.loads(self.add().stdout)["accepted"], 10)
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        jsonl(session, [dict(event, timestamp=future) for event in events])
        self.run_script("token-audit", "--cwd", self.repo)
        self.add(code=2)
        self.assertFalse(self.target.parent.exists())

    def transaction(self):
        tool = runpy.run_path(str(SCRIPTS / "allow-rule"))["transact"]
        for enabled in (patch.dict(tool.__globals__, WRITES_ENABLED=True),
                        patch.dict(os.environ, KAIZEN_HOST="claude")):
            enabled.start()
            self.addCleanup(enabled.stop)
        self.extract(self.row(), self.row(literal="ls -a"))
        return tool

    def test_managed_undo_preserves_user_settings_and_existing_rules(self):
        tool = self.transaction()
        original = dict(permissions=dict(allow=["Bash(ls -l)"], deny=["Bash(rm:*)"]))
        write(self.target, json.dumps(original))
        first = tool(self.repo, "ls")["record"]
        second = tool(self.repo, "ls -a")["record"]
        data = json.loads(self.target.read_bytes())
        data["other"] = original["other"] = 7
        self.target.write_text(json.dumps(data))
        tool(self.repo, record=first)
        tool(self.repo, record=second)
        self.assertEqual(json.loads(self.target.read_bytes()), original)
        self.assertEqual(tool(self.repo, record=second)["status"], "undone")
        first = tool(self.repo, "ls")["record"]
        self.target.write_text(json.dumps(original))  # User revokes the managed rule.
        tool(self.repo, "ls -a")
        data = json.loads(self.target.read_bytes())
        data["permissions"]["allow"].append("Bash(ls)")
        self.target.write_text(json.dumps(data))
        tool(self.repo, record=first)
        self.assertEqual(json.loads(self.target.read_bytes()), data)

    def test_creation_revocation_and_replacement(self):
        tool = self.transaction()
        first = tool(self.repo, "ls")["record"]
        tool(self.repo, record=first)
        self.assertFalse(self.target.exists())
        write(self.target, '{"permissions":{"allow":[]}}')
        second = tool(self.repo, "ls")["record"]
        tool(self.repo, record=second)
        self.assertTrue(self.target.exists())
        latest = tool(self.repo, "ls")["record"]
        copy = self.target.with_name("replacement")
        copy.write_bytes(self.target.read_bytes())
        copy.replace(self.target)
        with self.assertRaises(tool.__globals__["Refused"]):
            tool(self.repo, record=latest)
        self.target.unlink()
        self.assertEqual(tool(self.repo, record=latest)["status"], "undone")

    def test_interrupted_broker_transaction_reconciles_only_its_own_key(self):
        tool = self.transaction()
        state = tool.__globals__
        action = "fa1_" + "a" * 64
        def interrupt_stage(directory, name, *_):
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
            os.close(fd)
            raise OSError("fixture interruption")
        with patch.dict(state, stage=interrupt_stage), self.assertRaises(OSError):
            tool(self.repo, "ls", action_id=action)
        self.assertFalse(self.target.exists())
        perform = state["write_effect"]
        for after in (False, True):
            def interrupt(*args):
                if after:
                    perform(*args)
                raise OSError("fixture interruption")
            with patch.dict(state, write_effect=interrupt), self.assertRaises(OSError):
                tool(self.repo, "ls", action_id=action)
            self.assertEqual(self.target.exists(), after)
        with ThreadPoolExecutor(2) as workers:
            results = list(workers.map(lambda _: tool(self.repo, "ls", action_id=action), range(2)))
        self.assertEqual(results, [dict(status="applied", record=action)] * 2)
        self.assertEqual(json.loads(self.target.read_bytes())["permissions"]["allow"], ["Bash(ls)"])
        for repo, literal, key in ((self.project("other"), "ls", action), (self.repo, "ls -a", action),
                                   (self.repo, "ls", "fa1_" + "b" * 64)):
            with self.assertRaises(state["Refused"]):
                tool(repo, literal, action_id=key)
            if repo != self.repo:
                self.assertFalse((repo / ".claude").exists())
        with patch.dict(os.environ, KAIZEN_RUN_ID=""), self.assertRaises(state["Refused"]):
            tool(self.repo, record=action)
        with patch.dict(os.environ, KAIZEN_HOST="codex"), self.assertRaises(state["Refused"]):
            tool(self.repo, record=action)
        with patch.dict(state, write_effect=interrupt), self.assertRaises(OSError):
            tool(self.repo, record=action)
        self.assertFalse(self.target.exists())
        self.assertEqual(tool(self.repo, record=action)["status"], "undone")

    def test_journal_loss_or_forgery_never_adopts_existing_permission(self):
        tool = self.transaction()
        record = tool(self.repo, "ls")["record"]
        journal = self.cfg / "kaizen-backups/friction/allow-rules.json"
        raw = self.target.read_bytes()
        data = json.loads(journal.read_bytes())
        data["records"][record][1] = "Bash(ls -a)"
        journal.write_text(json.dumps(data))
        with self.assertRaises(tool.__globals__["Refused"]):
            tool(self.repo, record=record)
        journal.unlink()
        with self.assertRaises(tool.__globals__["Refused"]):
            tool(self.repo, "ls")
        self.assertEqual(self.target.read_bytes(), raw)

    def test_pending_path_swap_refuses_replacement(self):
        tool = self.transaction()
        state = tool.__globals__
        before = write(self.target, '{"unrelated":1}').read_bytes()
        real_stage = state["stage"]
        def swap(*args):
            planned = real_stage(*args)
            self.target.parent.rename(self.repo / "parked")
            write(self.target, '{"unrelated":2}')
            return planned
        with patch.dict(state, stage=swap), self.assertRaises(state["Refused"]):
            tool(self.repo, "ls")
        self.assertEqual(self.target.read_text(), '{"unrelated":2}')
        self.assertEqual((self.repo / "parked" / self.target.name).read_bytes(), before)

    def test_changed_staged_settings_are_never_installed(self):
        tool = self.transaction()
        state = tool.__globals__
        real_stage = state["stage"]
        def change(directory, name, raw, mode):
            planned = real_stage(directory, name, raw, mode)
            (self.target.parent / name).write_text('{"permissions":{"allow":["Bash(*)"]}}')
            return planned
        with patch.dict(state, stage=change), self.assertRaises(state["Refused"]):
            tool(self.repo, "ls")
        self.assertFalse(self.target.exists())

    def test_settings_conflicts_and_undo_leave_bytes_alone(self):
        self.extract(self.row())
        for field in ("deny", "ask"):
            for rule in ("Bash", "Bash(*)", "Bash(ls)", "Bash(ls:*)"):
                raw = json.dumps(dict(permissions={"allow": ["Bash(ls)"], field: [rule]}))
                write(self.target, raw)
                self.assertIn(f"permissions.{field}", self.add(code=2).stderr)
                self.assertEqual(self.target.read_text(), raw)
        raw = '{"permissions":{"allow":["Bash(ls)"],"deny":["Bash(rm:*)"]},"other":42}'
        write(self.target, raw)
        self.assertEqual(json.loads(self.add().stdout)["status"], "already-present")
        record = write(self.root / "record.json", "{}")
        self.run_script("allow-rule", "undo", record, "--project", self.repo, code=2)
        self.assertEqual(record.read_text(), "{}")
        self.assertEqual(self.target.read_text(), raw)
        for malformed in ('{"permissions":{"deny":"Bash(ls)"}}',
                          '{"permissions":{},"permissions":{}}', "[]"):
            write(self.target, malformed)
            self.add(code=2)
            self.assertEqual(self.target.read_text(), malformed)
        self.target.unlink()
        self.target.symlink_to(record)
        self.add(code=2)
        self.target.unlink()
        self.target.parent.rmdir()
        self.target.parent.symlink_to(self.root, target_is_directory=True)
        self.add(code=2)
        self.assertEqual(record.read_text(), "{}")

    def test_seeded_local_rule_keeps_installed_runner_arguments_narrow(self):
        # Stub Claude records argv. The live S2 gate must test effective permissions.
        installed = self.install()
        for mode, permission in (("propose-only", "dontAsk"), ("auto", "default")):
            with self.subTest(mode=mode):
                project = self.due(mode, '{"scheduledAutonomy":"auto"}')
                write(self.global_path, json.dumps({"autoProjects": [str(project)] if mode == "auto" else []}))
                raw = '{"permissions":{"allow":["Bash(ls)"]}}'
                target = write(project / ".claude/settings.local.json", raw)
                subprocess.run([str(installed / "kaizen-scheduled"), "review", "--project-dir",
                                str(project), "--audits", str(self.audits), "--claude", str(self.claude),
                                "--token-audit", str(self.audit), "--pricing", str(self.pricing),
                                "--python", sys.executable],
                               env=self.env, capture_output=True, text=True, check=True)
                argv = self.last_argv()
                audit = json.loads(Path(self.env["AUDIT_RECORD"]).read_text().splitlines()[-1])
                self.assertEqual(self.values(audit, "--days"), ["6"])
                self.assertEqual(self.calls()[-1]["cwd"], str(project))
                self.assertIn(f":cycle {mode} ", self.values(argv, "-p")[0])
                self.assertEqual(self.values(argv, "--permission-mode"), [permission])
                allowed = self.values(argv, "--allowedTools")[0].split(",")
                bash = {rule for rule in allowed if rule.startswith("Bash")}
                expected = set()
                if mode == "auto":
                    for python in ("", "python3 ", sys.executable + " "):
                        for action in ("begin", "finish", "list"):
                            expected.add(f"Bash({python}{installed}/kaizen-backup {action}:*)")
                    for python in ("python3 ", sys.executable + " "):
                        expected.add(f"Bash({python}{installed}/notes-ledger add:*)")
                self.assertEqual(bash, expected)
                denied = self.values(argv, "--disallowedTools")[0].split(",")
                self.assertIn("Bash(rm:*)", denied)
                self.assertTrue(any(rule.startswith("Read(") and ".credentials" in rule for rule in denied))
                if mode == "auto":
                    self.assertIn(f"Edit(/{project}/.claude/settings*.json)", denied)
                self.assertEqual(target.read_text(), raw)
