"""Scheduled friction preparation and transactional reconciliation."""
import hmac
import json
import runpy
import shutil
from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from plugin_fixtures import copy_plugin_tree
from test_friction_prepare import PATH, PreparationTests, prepare


class ScheduledFrictionTests(PreparationTests):
    def setUp(self):
        super().setUp()
        claude = self.write(self.root / 'claude', '#!/bin/sh\nexit 0\n')
        claude.chmod(0o755)
        self.review_args = SimpleNamespace(claude=str(claude))
        clock = patch.dict(self.runner["reconcile_scheduled"].__globals__,
                           {"now": lambda: self.current + timedelta(seconds=3)})
        clock.start()
        self.addCleanup(clock.stop)

    def scheduled(self, mode="propose-only"):
        return prepare.prepare(self.config / "audits", self.backups, self.obj, self.report,
                               self.runner["effective"](self.project), mode, self.current + timedelta(seconds=2),
                               self.runner["action_project"], self.runner["key"], retain=True)

    def test_suggestion_import_acknowledges_and_strips(self):
        inputs, receipt = self.scheduled()
        output = self.write(self.obj.folder / "review.md", 'Review\n<!-- kaizen-host-actions {"v":1,"actions":[]} -->\n')
        terminal, requested = self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt)
        self.assertTrue(terminal)
        self.assertFalse(requested)
        self.assertEqual(output.read_text(), 'Review\n')
        self.assertIsNone(self.scheduled())
        self.assertTrue(inputs.exists())

    def test_stripping_uses_the_open_output_after_path_is_replaced(self):
        _, receipt = self.scheduled()
        output = self.write(self.obj.folder / "review.md", 'Review\n' + self.actions().read_text())
        victim = self.write(self.root / "unrelated", "Keep\n")
        host = runpy.run_path(str(self.runner["HERE"] / "kaizen_friction_actions.py"))
        import_actions = host["HostActions"].import_actions

        def swap(store, *args, **kwargs):
            output.unlink()
            output.symlink_to(victim)
            return import_actions(store, *args, **kwargs)

        load = runpy.run_path
        with patch.object(host["HostActions"], "import_actions", swap), patch.object(
                runpy, "run_path", side_effect=lambda path: host if path.endswith("kaizen_friction_actions.py") else load(path)):
            self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt)
        self.assertEqual(victim.read_text(), "Keep\n")

    def marker_request(self):
        target = self.project / "build"
        target.mkdir()
        self.probe["findings"] = [dict(id="indexed-output", catalog_id="linux-localsearch", subject=str(target),
                                       evidence=dict(size_bytes=1))]
        self.probe["regenerable_dirs"] = [dict(path=str(target), size_bytes=1)]
        self.write_evidence()
        inputs, receipt = self.scheduled("auto")
        ident = json.loads(inputs.read_text())["actions"][0]["id"]
        output = self.write(self.obj.folder / "review.md", '<!-- kaizen-host-actions ' + json.dumps(
            dict(v=1, actions=[dict(id=ident, intent="apply")])) + ' -->\n')
        return target, ident, output, receipt

    def test_closed_marker_apply_is_imported_as_suggestion_and_acknowledged(self):
        target, ident, output, receipt = self.marker_request()
        terminal, requested = self.runner["reconcile_scheduled"](
            self.config / "audits", self.obj, output, receipt, authorize=self.fail)
        self.assertTrue(terminal)
        self.assertFalse(requested)
        self.assertEqual(output.read_text(), "")
        store = json.loads((self.config / "audits/host-actions.json").read_text())
        self.assertEqual(store["receipts"][str(self.project)]["scheduled:" + receipt["generation"]], {ident: "terminal"})
        self.assertEqual(store["actions"][ident]["status"], "open")
        self.assertFalse((target / ".nomedia").exists())
        self.assertIsNone(self.scheduled("auto"))

    def test_mixed_batch_downgrades_proposal_only_and_closed_marker_apply(self):
        target = self.project / "build"
        target.mkdir()
        self.probe["findings"] = [
            dict(id="low-disk", catalog_id="low-disk", subject="project-volume", evidence=dict(free_disk_bytes=1)),
            dict(id="indexed-output", catalog_id="linux-localsearch", subject=str(target), evidence=dict(size_bytes=1)),
            dict(id="inotify", catalog_id="inotify-limit", subject="inotify", evidence=dict(watches=1, tracked_files=1)),
        ]
        self.probe["regenerable_dirs"] = [dict(path=str(target), size_bytes=1)]
        self.write_evidence()
        _, receipt = self.scheduled("auto")
        ids = {row["catalog_id"]: ident for ident, row in receipt["allowed"].items()}
        actions = [dict(id=ids[catalog], intent=intent) for catalog, intent in (
            ("low-disk", "apply"), ("linux-localsearch", "apply"), ("inotify-limit", "suggest"))]
        output = self.write(self.obj.folder / "review.md", 'Review\n<!-- kaizen-host-actions ' + json.dumps(
            dict(v=1, actions=actions)) + ' -->\n')

        terminal, requested = self.runner["reconcile_scheduled"](
            self.config / "audits", self.obj, output, receipt, authorize=self.fail)
        self.assertTrue(terminal)
        self.assertFalse(requested)
        self.assertEqual(output.read_text(), 'Review\n')
        store = json.loads((self.config / "audits/host-actions.json").read_text())
        self.assertEqual(store["receipts"][str(self.project)]["scheduled:" + receipt["generation"]],
                         {ident: "terminal" for ident in ids.values()})
        self.assertEqual({ident: row["status"] for ident, row in store["actions"].items()},
                         {ident: "open" for ident in ids.values()})
        self.assertFalse((target / ".nomedia").exists())
        self.assertIsNone(self.scheduled("auto"))

    def test_apply_stays_pending_and_does_not_acknowledge(self):
        _, ident, output, receipt = self.marker_request()
        reconcile = self.runner["reconcile_scheduled"]
        with patch.dict(reconcile.__globals__, scheduled_action_refusal=lambda _: None):
            terminal, requested = reconcile(self.config / "audits", self.obj, output, receipt)
        self.assertFalse(terminal)
        self.assertFalse(requested)
        self.assertIsNotNone(self.scheduled("auto"))
        store = json.loads((self.config / "audits/host-actions.json").read_text())
        self.assertEqual(store["receipts"][str(self.project)]["scheduled:" + receipt["generation"]], {ident: "pending"})

    def test_completed_scheduled_apply_accepts_identical_review_retry(self):
        _, ident, output, receipt = self.marker_request()
        request = output.read_text()
        audits = self.config / "audits"
        reconcile = self.runner["reconcile_scheduled"]
        helper = self.runner["review_helper"]
        host, runtime = helper("kaizen_friction_actions.py"), helper("kaizen_friction_apply.py")
        store = host["HostActions"](audits, self.backups, self.runner["action_project"], self.runner["key"])
        with patch.dict(reconcile.__globals__, scheduled_action_refusal=lambda _: None,
                        scheduled_authority=Mock(return_value=(None, ()))):
            self.assertEqual(reconcile(audits, self.obj, output, receipt, acknowledge=False), (False, False))
            with host["_directory"](store.friction, private=True) as state:
                record = dict(phase="marker-pending", operation="linux-localsearch", reservation="fixture",
                              target_identity=[1, 2])
                ledger = Mock(state=state, load=Mock(return_value=record),
                              cancel_unstarted_marker=Mock(return_value=False),
                              scheduled_marker=Mock(return_value="recorded"))
                # A native reservation exists. Stub only its verified outcome.
                self.write(store.friction / ("broker-" + ident + ".json"), "{}")
                with patch.object(runtime["BrokerLedger"], "locked", return_value=nullcontext(ledger)):
                    self.runner["run_scheduled_broker"](audits, self.obj, self.runner["command_options"](self.review_args))
            self.assertEqual(store.scoped(self.project)[0]["status"], "done")
            before = store.path.read_bytes()
            self.write(output, request)
            self.assertEqual(reconcile(audits, self.obj, output, receipt), (True, False))
            self.write(output, request)
            self.assertEqual(reconcile(audits, self.obj, output, receipt), (True, False))
            self.assertEqual(store.path.read_bytes(), before)
            self.write(output, self.actions([ident]).read_text())
            with self.assertRaisesRegex(ValueError, "different requests"):
                reconcile(audits, self.obj, output, receipt)

    def completed_518da76_request(self):
        _, ident, output, receipt = self.marker_request()
        audits = self.config / "audits"
        scripts = self.mixed_scripts("kaizen-scheduled", "kaizen_friction_actions.py")
        runner = runpy.run_path(str(scripts / "kaizen-scheduled"))
        host = runpy.run_path(str(scripts / "kaizen_friction_actions.py"))
        store = host["HostActions"](audits, self.backups, runner["action_project"], runner["key"])
        generation = "scheduled:" + receipt["generation"]
        request = output.read_text()
        self.assertEqual(store.import_actions(request.strip(), receipt["allowed"], self.project, generation),
                         {ident: "pending"})
        self.write(store.friction / ("broker-" + ident + ".json"), "{}")
        with host["_directory"](store.friction, private=True) as state:
            record = dict(phase="marker-pending", operation="linux-localsearch",
                          reservation="fixture", target_identity=[1, 2])
            ledger = Mock(state=state, load=Mock(return_value=record),
                          cancel_unstarted_marker=Mock(return_value=False),
                          scheduled_marker=Mock(return_value="recorded"))
            runtime = dict(BrokerLedger=Mock(locked=Mock(return_value=nullcontext(ledger))),
                           LOCAL_COMMIT="local-commit")
            broker = runner["run_scheduled_broker"]
            with patch.dict(broker.__globals__, scheduled_authority=Mock(return_value=(None, ()))), \
                    patch.object(runpy, "run_path", side_effect=[host, runtime]):
                broker(audits, self.obj, runner["command_options"](self.review_args))
        self.assertEqual(store.scoped(self.project)[0]["status"], "done")
        saved = json.loads(store.path.read_text())
        self.assertEqual(saved["receipts"][str(self.project)][generation], {ident: "terminal"})
        self.assertFalse(store.path.with_suffix(".json.receipts").exists())
        return store, ident, output, receipt

    def test_completed_518da76_apply_accepts_identical_review_retry(self):
        store, ident, output, receipt = self.completed_518da76_request()
        audits = self.config / "audits"
        request = output.read_text()
        before = store.path.read_bytes()
        reconcile = self.runner["reconcile_scheduled"]
        with patch.dict(reconcile.__globals__, scheduled_action_refusal=lambda _: None):
            self.assertEqual(reconcile(audits, self.obj, output, receipt), (True, False))
            self.write(output, request)
            self.assertEqual(reconcile(audits, self.obj, output, receipt), (True, False))
            self.write(output, self.actions([ident]).read_text())
            with self.assertRaisesRegex(ValueError, "different requests"):
                reconcile(audits, self.obj, output, receipt)
        self.assertEqual(store.path.read_bytes(), before)

    def test_completed_518da76_retry_checks_signed_reservation(self):
        store, ident, output, receipt = self.completed_518da76_request()
        audits = self.config / "audits"
        before = store.path.read_bytes()
        request = output.read_text()
        reconcile = self.runner["reconcile_scheduled"]
        journal = store.friction / ("broker-" + ident + ".json")
        journal.chmod(0o600)
        info = self.project.stat()
        scope = [str(self.project), info.st_dev, info.st_ino]
        other_generation = f"{int(receipt['generation']) + 1:020d}"
        cases = ((other_generation, scope, False),
                 (receipt["generation"], [str(self.project), info.st_dev, info.st_ino + 1], False),
                 (receipt["generation"], scope, True))
        for generation, project_scope, matches in cases:
            with self.subTest(generation=generation, scope=project_scope), \
                    patch.dict(reconcile.__globals__, scheduled_action_refusal=lambda _: None):
                record = dict(id=ident, operation="host-fix", phase="recorded", generation=generation,
                              reservation="fixture-run", scope=project_scope)
                payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii")
                record["mac"] = hmac.digest(store._secret(), b"broker-ledger-v1\0" + payload, "sha256").hex()
                journal.write_text(json.dumps(record))
                self.write(output, request)
                if matches:
                    self.assertEqual(reconcile(audits, self.obj, output, receipt), (True, False))
                else:
                    with self.assertRaisesRegex(ValueError, "different requests"):
                        reconcile(audits, self.obj, output, receipt)
                    self.assertEqual(output.read_text(), request)
                self.assertEqual(store.path.read_bytes(), before)

    def test_malformed_output_cannot_acknowledge(self):
        _, receipt = self.scheduled()
        output = self.write(self.obj.folder / "review.md", '<!-- kaizen-host-actions broken -->\n')
        with self.assertRaises(ValueError):
            self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt)
        self.assertIsNotNone(self.scheduled())

    def test_recheck_refuses_changed_policy_age_and_generation(self):
        from unittest.mock import patch
        for change in ("policy", "age", "generation"):
            with self.subTest(change=change):
                _, receipt = self.scheduled()
                output = self.write(self.obj.folder / "review.md", '<!-- kaizen-host-actions {"v":1,"actions":[]} -->\n')
                original = output.read_text()
                if change == "policy":
                    self.write(self.config / "agent-kaizen.json", '{"friction":"off"}')
                elif change == "age":
                    import runpy
                    from test_friction_prepare import PATH
                    host = runpy.run_path(str(PATH.parent / "kaizen_friction_actions.py"))
                    store = host["HostActions"](self.config / "audits", self.backups,
                                                self.runner["action_project"], self.runner["key"])
                    receipt["created"] = (self.current - timedelta(hours=2)).isoformat()
                    receipt["signature"] = prepare._signature(receipt, store._secret())
                elif change == "generation":
                    state_path = next((self.backups / "friction").glob("prepare-*.json"))
                    state = json.loads(state_path.read_text())
                    state["generation"] += 1
                    state_path.write_text(json.dumps(state))
                clock = self.current + timedelta(seconds=3)
                with patch.dict(self.runner["reconcile_scheduled"].__globals__, {"now": lambda: clock}):
                    with self.assertRaises(ValueError):
                        self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt)
                self.assertEqual(output.read_text(), original)
                self.assertFalse((self.config / "audits/host-actions.json").exists())
                if change == "policy":
                    (self.config / "agent-kaizen.json").unlink()

    def test_publication_failure_and_recovery(self):
        import os
        _, receipt = self.scheduled()
        output = self.write(self.obj.folder / "review.tmp", '<!-- kaizen-host-actions {"v":1,"actions":[]} -->\n')
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        terminal, requested = self.runner["reconcile_scheduled"](
            self.config / "audits", self.obj, output, receipt, acknowledge=False)
        self.assertTrue(terminal)
        self.assertFalse(requested)
        recover = self.runner["recover_scheduled_publication"]
        recover(self.config / "audits", self.obj, receipt, proposal, output)
        # A failed rename leaves no publication and must not acknowledge.
        self.assertFalse(recover(self.config / "audits", self.obj))
        self.assertNotIn("acknowledged_generation", json.loads(next((self.backups / "friction").glob("prepare-*.json")).read_text()))
        recover(self.config / "audits", self.obj, receipt, proposal, output)
        os.replace(output, proposal)  # Simulate a crash after publication.
        self.assertEqual(recover(self.config / "audits", self.obj), proposal)
        self.assertFalse(recover(self.config / "audits", self.obj))
        self.assertEqual(len(list(self.obj.folder.glob("cycle-*.md"))), 1)
        self.assertEqual(json.loads(next((self.backups / "friction").glob("prepare-*.json")).read_text())["acknowledged_generation"], receipt["generation"])

    def test_recovers_legacy_publication_marker(self):
        _, receipt = self.scheduled()
        audits = self.config / "audits"
        output = self.write(self.obj.folder / "review.tmp", "Review\n" + self.actions().read_text())
        self.runner["reconcile_scheduled"](audits, self.obj, output, receipt, acknowledge=False)
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        legacy = runpy.run_path(str(self.mixed_scripts(PATH.name) / PATH.name))
        legacy["scheduled_publication"](audits, self.backups, self.obj, self.runner["action_project"],
                                        self.runner["key"], receipt, proposal, output)
        output.rename(proposal)
        marker = next((self.backups / "friction").glob("publication-*.json"))
        self.assertNotIn("reviewed_at", json.loads(marker.read_text()))
        self.assertEqual(self.runner["recover_scheduled_publication"](audits, self.obj), proposal)
        self.assertTrue(self.runner["read_state"](self.obj)["reviewed_at"])
        self.assertFalse(marker.exists())

    def test_foreign_518da76_publication_cannot_be_overwritten(self):
        _, receipt = self.scheduled()
        audits = self.config / "audits"
        output = self.write(self.obj.folder / "review.tmp", "Review\n" + self.actions().read_text())
        self.runner["reconcile_scheduled"](audits, self.obj, output, receipt, acknowledge=False)
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        legacy = runpy.run_path(str(self.mixed_scripts(PATH.name) / PATH.name))
        ownership = self.runner["action_project"], self.runner["key"]
        legacy["scheduled_publication"](audits, self.backups, self.obj, *ownership, receipt, proposal, output)
        output.rename(proposal)
        marker = next((self.backups / "friction").glob("publication-*.json"))
        original = marker.read_bytes()
        state = self.backups / "friction" / ("prepare-" + self.obj.key + ".json")
        prior_state = state.read_bytes()
        self.assertNotIn("audits", json.loads(original))
        other = self.root / "other-audits"
        other_project = self.runner["Project"](self.project, [self.project], other / "projects" / self.obj.key)
        other_output = self.write(other_project.folder / "review.tmp", "Other review\n")
        other_proposal = other_project.folder / proposal.name
        other_report = self.write(other_project.folder / self.report.name, self.report.read_text())
        self.write(other / "extracts" / self.extract.name, self.extract.read_text())
        self.write(other_project.folder / self.probe_path.name, self.probe_path.read_text())
        with self.assertRaisesRegex(ValueError, "earlier review publication"):
            prepare.prepare(other, self.backups, other_project, other_report, self.runner["effective"](self.project),
                            "propose-only", self.current + timedelta(seconds=2), *ownership, retain=True)
        self.assertEqual(state.read_bytes(), prior_state)
        recover = self.runner["recover_scheduled_publication"]
        for publish in (
                lambda: prepare.scheduled_publication(other, self.backups, other_project, *ownership,
                                                      receipt, other_proposal, other_output),
                lambda: recover(other, other_project, receipt, other_proposal, other_output)):
            with self.subTest(publish=publish):
                with self.assertRaisesRegex(ValueError, "earlier review publication"):
                    publish()
                self.assertEqual(marker.read_bytes(), original)
                self.assertEqual(other_output.read_text(), "Other review\n")
        self.assertEqual(recover(audits, self.obj), proposal)
        self.assertEqual(json.loads(state.read_bytes())["acknowledged_generation"], receipt["generation"])

    def test_same_root_can_retry_publication_with_pending_apply(self):
        _, _, output, receipt = self.marker_request()
        audits = self.config / "audits"
        reconcile = self.runner["reconcile_scheduled"]
        with patch.dict(reconcile.__globals__, scheduled_action_refusal=lambda _: None):
            self.assertEqual(reconcile(audits, self.obj, output, receipt, acknowledge=False), (False, False))
        recover = self.runner["recover_scheduled_publication"]
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        recover(audits, self.obj, receipt, proposal, output)
        output.rename(proposal)
        published = proposal.read_bytes()
        self.assertFalse(recover(audits, self.obj))
        _, retry = self.scheduled("auto")
        output.write_text("Retried review\n")
        new_proposal = self.obj.folder / "cycle-2026-11-18-2.md"
        recover(audits, self.obj, retry, new_proposal, output)
        self.assertEqual(proposal.read_bytes(), published)
        marker = next((self.backups / "friction").glob("publication-*.json"))
        self.assertEqual(json.loads(marker.read_text())["proposal"], new_proposal.name)

    def test_unpublished_suggestion_survives_new_evidence_generation(self):
        self.candidate()
        inputs, receipt = self.scheduled()
        ident = json.loads(inputs.read_text())["actions"][0]["id"]
        output = self.write(self.obj.folder / "review.tmp", self.actions([ident]).read_text())
        self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt, acknowledge=False)
        self.probe["generated_at"] = (self.current + timedelta(seconds=1)).isoformat()
        self.write_evidence()
        retry, _ = self.scheduled()
        self.assertIn(ident, [action["id"] for action in json.loads(retry.read_text())["actions"]])

    def test_later_publication_does_not_hide_omitted_unpublished_suggestion(self):
        self.candidate()
        inputs, receipt = self.scheduled()
        ident = json.loads(inputs.read_text())["actions"][0]["id"]
        output = self.write(self.obj.folder / "review.tmp", self.actions([ident]).read_text())
        self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt, acknowledge=False)
        self.probe["generated_at"] = (self.current + timedelta(seconds=1)).isoformat()
        self.write_evidence()
        _, retry = self.scheduled()
        output.write_text(self.actions().read_text())
        self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, retry)
        next_inputs, _ = self.scheduled()
        self.assertIn(ident, [action["id"] for action in json.loads(next_inputs.read_text())["actions"]])

    def test_schedule_off_refuses_inflight_import(self):
        _, receipt = self.scheduled()
        self.write(self.project / "docs/kaizen/config.json", '{"schedule":"off"}')
        output = self.write(self.obj.folder / "review.tmp", '<!-- kaizen-host-actions {"v":1,"actions":[]} -->\n')
        with self.assertRaises(ValueError):
            self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt)
        self.assertFalse((self.config / "audits/host-actions.json").exists())

    def test_edited_publication_recovers_without_overwriting(self):
        import os
        _, receipt = self.scheduled()
        output = self.write(self.obj.folder / "review.tmp", '<!-- kaizen-host-actions {"v":1,"actions":[]} -->\n')
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt, acknowledge=False)
        recover = self.runner["recover_scheduled_publication"]
        recover(self.config / "audits", self.obj, receipt, proposal, output)
        os.replace(output, proposal)
        proposal.write_text("User edit\n")
        self.assertEqual(recover(self.config / "audits", self.obj), proposal)
        self.assertEqual(proposal.read_text(), "User edit\n")
        self.assertFalse(recover(self.config / "audits", self.obj))

    def test_new_interactive_generation_preserves_published_cutoff(self):
        _, receipt = self.scheduled()
        audits = self.config / "audits"
        output = self.write(self.obj.folder / "review.tmp", "Review\n" + self.actions().read_text())
        self.runner["reconcile_scheduled"](audits, self.obj, output, receipt, acknowledge=False)
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        cutoff = self.runner["timestamp"](self.current)
        recover = self.runner["recover_scheduled_publication"]
        recover(audits, self.obj, receipt, proposal, output, reviewed_at=cutoff)
        output.rename(proposal)
        self.assertIsNotNone(self.run_prepare(self.report))
        marker = next((self.backups / "friction").glob("publication-*.json"))

        def fail_state_write(*args, **kwargs):
            raise OSError("injected state write failure")

        with patch.dict(recover.__globals__, write_state=fail_state_write):
            with self.assertRaisesRegex(OSError, "injected state write failure"):
                recover(audits, self.obj)
        self.assertTrue(marker.exists())
        self.assertEqual(recover(audits, self.obj), proposal)
        self.assertEqual(self.runner["read_state"](self.obj)["reviewed_at"], cutoff)
        self.assertFalse(marker.exists())
        prepared = json.loads(next((self.backups / "friction").glob("prepare-*.json")).read_text())
        self.assertEqual(prepared["generation"], int(receipt["generation"]) + 1)
        self.assertNotIn("acknowledged_generation", prepared)

    def test_oversized_superseded_publication_recovers_without_reading_report(self):
        _, receipt = self.scheduled()
        audits = self.config / "audits"
        output = self.write(self.obj.folder / "review.tmp", "Review\n" + self.actions().read_text())
        self.runner["reconcile_scheduled"](audits, self.obj, output, receipt, acknowledge=False)
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        cutoff = self.runner["timestamp"](self.current)
        recover = self.runner["recover_scheduled_publication"]
        recover(audits, self.obj, receipt, proposal, output, reviewed_at=cutoff)
        output.rename(proposal)
        self.assertIsNotNone(self.run_prepare(self.report))
        edited = b"x" * (prepare.LIMIT + 1)
        proposal.write_bytes(edited)
        prepared = next((self.backups / "friction").glob("prepare-*.json"))
        newer_state = prepared.read_bytes()

        self.assertEqual(recover(audits, self.obj), proposal)
        self.assertEqual(self.runner["read_state"](self.obj)["reviewed_at"], cutoff)
        self.assertFalse(list((self.backups / "friction").glob("publication-*.json")))
        self.assertEqual(prepared.read_bytes(), newer_state)
        self.assertEqual(proposal.read_bytes(), edited)

    def test_degraded_recovery_acknowledges_terminal_publication(self):
        import os
        _, receipt = self.scheduled()
        output = self.write(self.obj.folder / "review.tmp", '<!-- kaizen-host-actions {"v":1,"actions":[]} -->\n')
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        self.runner["reconcile_scheduled"](self.config / "audits", self.obj, output, receipt, acknowledge=False)
        recover = self.runner["recover_scheduled_publication"]
        recover(self.config / "audits", self.obj, receipt, proposal, output)
        os.replace(output, proposal)
        self.assertEqual(recover(self.config / "audits", self.obj, degraded=True), proposal)
        state = json.loads(next((self.backups / "friction").glob("prepare-*.json")).read_text())
        self.assertEqual(state["acknowledged_generation"], receipt["generation"])

    def test_other_audits_root_leaves_publication_marker(self):
        _, receipt = self.scheduled()
        audits = self.config / "audits"
        output = self.write(self.obj.folder / "review.tmp", "Review\n" + self.actions().read_text())
        self.runner["reconcile_scheduled"](audits, self.obj, output, receipt, acknowledge=False)
        recover = self.runner["recover_scheduled_publication"]
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        recover(audits, self.obj, receipt, proposal, output)
        output.rename(proposal)
        other = self.root / "other-audits"
        other_project = self.runner["Project"](self.project, [self.project], other / "projects" / self.obj.key)
        self.assertFalse(recover(other, other_project))
        self.assertEqual(recover(audits, self.obj), proposal)

    def assert_pending_recovery_precedes_marker_check(self, field, value, error=None):
        _, ident, output, receipt = self.marker_request()
        audits = self.config / "audits"
        reconcile = self.runner["reconcile_scheduled"]
        recover = self.runner["recover_scheduled_publication"]
        with patch.dict(reconcile.__globals__, scheduled_action_refusal=lambda _: None):
            self.assertEqual(reconcile(audits, self.obj, output, receipt, acknowledge=False), (False, False))
        recover(audits, self.obj, receipt, self.obj.folder / "cycle-2026-11-18.md", output)
        marker = next((self.backups / "friction").glob("publication-*.json"))
        original = json.dumps(dict(json.loads(marker.read_text()), **{field: value}))
        marker.write_text(original)
        options = self.runner["command_options"](self.review_args)
        with patch.dict(recover.__globals__, scheduled_action_refusal=lambda _: "proposal-only"):
            if error:
                with self.assertRaisesRegex(ValueError, error):
                    recover(audits, self.obj, options=options)
            else:
                self.assertIsNone(recover(audits, self.obj, options=options))
        store = json.loads((audits / "host-actions.json").read_text())
        self.assertEqual(store["receipts"][str(self.project)]["scheduled:" + receipt["generation"]], {ident: "terminal"})
        self.assertEqual(marker.read_text(), original)
        self.assertNotIn("reviewed_at", self.runner["read_state"](self.obj))

    def test_invalid_marker_generation_still_recovers_broker(self):
        self.assert_pending_recovery_precedes_marker_check("generation", "invalid", "invalid publication marker")

    def test_foreign_audits_marker_still_recovers_local_broker(self):
        self.assert_pending_recovery_precedes_marker_check("audits", str(self.root / "other-audits"))

    def test_degraded_recovery_does_not_acknowledge_pending_project_actions(self):
        import os
        _, _, output, receipt = self.marker_request()
        reconcile = self.runner["reconcile_scheduled"]
        with patch.dict(reconcile.__globals__, scheduled_action_refusal=lambda _: None):
            terminal, _ = reconcile(self.config / "audits", self.obj, output, receipt, acknowledge=False)
        self.assertFalse(terminal)
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        recover = self.runner["recover_scheduled_publication"]
        recover(self.config / "audits", self.obj, receipt, proposal, output)
        os.replace(output, proposal)
        with patch.dict(recover.__globals__, recover_scheduled_suggestions=lambda *args, **kwargs: True):
            self.assertFalse(recover(self.config / "audits", self.obj, degraded=True))
        state = json.loads(next((self.backups / "friction").glob("prepare-*.json")).read_text())
        self.assertNotIn("acknowledged_generation", state)

    def test_malformed_publication_cutoff_still_recovers_pending_actions(self):
        target, ident, output, receipt = self.marker_request()
        audits = self.config / "audits"
        generation = "scheduled:" + receipt["generation"]
        reconcile = self.runner["reconcile_scheduled"]
        with patch.dict(reconcile.__globals__, scheduled_action_refusal=lambda _: None):
            terminal, _ = reconcile(audits, self.obj, output, receipt, acknowledge=False)
        self.assertFalse(terminal)
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        recover = self.runner["recover_scheduled_publication"]
        recover(audits, self.obj, receipt, proposal, output)
        output.rename(proposal)
        marker = next((self.backups / "friction").glob("publication-*.json"))
        marker.write_text(json.dumps(dict(json.loads(marker.read_text()), reviewed_at=None)))
        options = self.runner["command_options"](self.review_args)

        with patch.dict(recover.__globals__, scheduled_action_refusal=lambda _: "proposal-only"):
            with self.assertRaisesRegex(ValueError, "invalid evidence time"):
                recover(audits, self.obj, options=options)

        store = json.loads((audits / "host-actions.json").read_text())
        self.assertEqual(store["receipts"][str(self.project)][generation], {ident: "terminal"})
        self.assertFalse((target / ".nomedia").exists())
        self.assertTrue(marker.exists())
        self.assertNotIn("reviewed_at", self.runner["read_state"](self.obj))

    def test_malformed_publication_cutoff_is_reported_when_broker_stays_pending(self):
        _, ident, output, receipt = self.marker_request()
        audits = self.config / "audits"
        reconcile = self.runner["reconcile_scheduled"]
        with patch.dict(reconcile.__globals__, scheduled_action_refusal=lambda _: None):
            terminal, _ = reconcile(audits, self.obj, output, receipt, acknowledge=False)
        self.assertFalse(terminal)
        proposal = self.obj.folder / "cycle-2026-11-18.md"
        recover = self.runner["recover_scheduled_publication"]
        recover(audits, self.obj, receipt, proposal, output)
        output.rename(proposal)
        marker = next((self.backups / "friction").glob("publication-*.json"))
        malformed = json.dumps(dict(json.loads(marker.read_text()), reviewed_at=None))
        marker.write_text(malformed)
        options = self.runner["command_options"](self.review_args)
        broker = Mock()

        with patch.dict(recover.__globals__, run_scheduled_broker=broker):
            with self.assertRaisesRegex(ValueError, "invalid evidence time"):
                recover(audits, self.obj, options=options)

        broker.assert_called_once_with(audits, self.obj, options)
        store = json.loads((audits / "host-actions.json").read_text())
        generation = "scheduled:" + receipt["generation"]
        self.assertEqual(store["receipts"][str(self.project)][generation], {ident: "pending"})
        self.assertEqual(marker.read_text(), malformed)
        self.assertNotIn("reviewed_at", self.runner["read_state"](self.obj))

    def test_audit_policy_global_and_scoped(self):
        options = self.runner["command_options"](type("Args", (), {"dry_run": True})())
        self.write(self.config / "agent-kaizen.json", '{"friction":"off","frictionSlowCallSeconds":123}')
        command = self.runner["audit_command"](options, self.config / "audits")
        scoped = self.runner["audit_command"](options, self.obj.folder, self.obj)
        for argv in (command, scoped):
            self.assertIn('--no-friction', argv)
            self.assertEqual(argv[argv.index('--friction-slow-seconds') + 1], '123')


class ScheduledReviewIntegrationTests(PreparationTests):
    def setUp(self):
        super().setUp()
        import os
        import sys
        self.env = dict(self.environment, HOME=str(self.root), REVIEW_RECORD=str(self.root / 'calls'))
        self.audit = self.write(self.root / 'audit.py', '#!' + sys.executable + '\nprint(' + repr(str(self.report)) + ')\n')
        self.audit.chmod(0o755)
        self.claude = self.write(self.root / 'claude', '#!' + sys.executable + '''
import json, os, pathlib, sys, time
args = sys.argv[1:]
home = pathlib.Path(os.environ['KAIZEN_BACKUP_DIR'])
marker = list(home.glob('.active-run*.json'))
with open(os.environ['REVIEW_RECORD'], 'a') as out:
    out.write(json.dumps({'argv': args, 'marker': bool(marker)}) + '\\n')
print('Review', flush=True)
print('<!-- kaizen-host-actions {"v":1,"actions":[]} -->', flush=True)
if os.environ.get('REVIEW_SLEEP'): time.sleep(10)
''')
        self.claude.chmod(0o755)
        self.runner_path = self.root.parent / 'unused'
        from test_friction_prepare import PATH
        self.runner_path = PATH.parent / 'kaizen-scheduled'

    def review_run(self, *extra, runner=None, env=None, force=True):
        import subprocess
        import sys
        command = [sys.executable, str(runner or self.runner_path), 'review',
                   '--project-dir', str(self.project), '--audits', str(self.config / 'audits'),
                   '--token-audit', str(self.audit), '--claude', str(self.claude), *extra]
        if force:
            command.append('--force')
        return subprocess.run(command, env=env or self.env, capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in (self.root / 'calls').read_text().splitlines()]

    def state(self):
        return json.loads(next((self.backups / 'friction').glob('prepare-*.json')).read_text())

    def assert_mixed_review_publishes_in_auto(self, legacy, revision="518da76"):
        scripts = self.mixed_scripts(legacy, revision=revision)
        linked = self.root / "linked"
        self.add_test_worktrees(linked)
        target = linked / "build"
        target.mkdir()
        self.probe["findings"] = [dict(id="indexed-output", catalog_id="spotlight-output", subject=str(target),
                                       evidence=dict(size_bytes=1))]
        self.probe["regenerable_dirs"] = [dict(path=str(target), size_bytes=1)]
        self.write_evidence()
        self.write(scripts / "host-probe", "print('fixture probe')\n")
        self.write(self.config / "agent-kaizen.json", '{"scheduledAutonomy":"auto"}')
        result = self.review_run(runner=scripts / "kaizen-scheduled")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("reviewed (auto)", result.stdout)
        prompt = self.calls()[0]["argv"][1]
        self.assertIn("friction-inputs=", prompt)
        inputs = self.obj.folder / "friction-inputs-00000000000000000001.json"
        self.assertEqual(len(json.loads(inputs.read_text())["actions"]), 1)
        self.assertEqual(self.state()["acknowledged_generation"], "00000000000000000001")
        review_state = self.runner["read_state"](self.obj)
        self.assertTrue(review_state["reviewed_at"])
        self.assertEqual(self.obj.folder.joinpath(review_state["proposal"]).read_text().strip(), "Review")
        self.assertFalse(list((self.backups / "friction").glob("publication-*.json")))

    def test_legacy_runner_with_new_prepare_helper(self):
        self.assert_mixed_review_publishes_in_auto("kaizen-scheduled")

    def test_new_runner_with_legacy_prepare_helper(self):
        self.assert_mixed_review_publishes_in_auto(PATH.name)

    def test_candidate_runner_with_new_prepare_helper(self):
        self.assert_mixed_review_publishes_in_auto("kaizen-scheduled", "03325cd")

    def test_new_runner_with_candidate_prepare_helper(self):
        self.assert_mixed_review_publishes_in_auto(PATH.name, "03325cd")

    def test_unsafe_publication_directory_still_allows_ordinary_review(self):
        import os
        self.write(self.config / 'agent-kaizen.json', '{"friction":"off"}')
        self.backups.mkdir()
        unsafe = self.root / 'unsafe'
        unsafe.mkdir()
        (self.backups / 'friction').symlink_to(unsafe, target_is_directory=True)
        transcript = self.write(self.config / 'projects/fixture/activity.jsonl', json.dumps({'cwd': str(self.project)}))
        os.utime(transcript, (self.current.timestamp() - 1,) * 2)
        result = self.review_run('--now', self.current.isoformat(), force=False)
        self.assertIn('publication recovery failed', result.stdout)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.runner['read_state'](self.obj)['reviewed_at'], self.runner['timestamp'](self.current))
        self.assertIn('skipped: no activity', self.review_run(force=False).stdout)
        self.assertEqual(len(self.calls()), 1)

    def test_publication_uses_state_from_before_auto_review(self):
        self.write(self.config / 'agent-kaizen.json', '{"scheduledAutonomy":"auto"}')
        audits = self.project / 'custom-audits'
        shutil.copytree(self.config / 'audits', audits)
        report = audits / self.report.relative_to(self.config / 'audits')
        self.audit.write_text(self.audit.read_text().replace(repr(str(self.report)), repr(str(report))))
        state_path = report.parent / 'state.json'
        forged = json.dumps({'reviewed_at': '2099-01-01T00:00:00Z'})
        with self.claude.open('a') as stream:
            stream.write(f'pathlib.Path({str(state_path)!r}).write_text({forged!r})\n')

        result = self.review_run('--audits', str(audits), '--now', self.current.isoformat())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('reviewed (auto)', result.stdout)
        self.assertEqual(self.state().get('acknowledged_generation'), '00000000000000000001')
        state = json.loads(state_path.read_text())
        self.assertEqual(state['reviewed_at'], self.runner['timestamp'](self.current))
        self.assertEqual(state['ignore_sessions'], [self.calls()[0]['argv'][3]])

    def test_malformed_marker_cutoff_continues_to_later_projects(self):
        audits = self.config / 'audits'
        cfg = self.runner['effective'](self.project)
        _, receipt = self.runner['friction_prepare'](
            audits, self.obj, self.report, None, cfg, 'propose-only', self.runner['now'], retain=True)
        output = self.write(self.obj.folder / 'review.tmp', 'Review\n' + self.actions().read_text())
        self.runner['reconcile_scheduled'](audits, self.obj, output, receipt, acknowledge=False)
        proposal = self.obj.folder / 'cycle-2026-11-18.md'
        self.runner['recover_scheduled_publication'](audits, self.obj, receipt, proposal, output)
        output.rename(proposal)
        marker = next((self.backups / 'friction').glob('publication-*.json'))
        original = json.loads(marker.read_text())
        later = self.root / 'z-later-project'
        (later / 'docs/kaizen').mkdir(parents=True)
        for count, cutoff in enumerate((None, 42), 1):
            with self.subTest(cutoff=cutoff):
                marker.write_text(json.dumps(dict(original, reviewed_at=cutoff)))
                result = self.review_run('--project-dir', str(later))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('publication recovery failed', result.stdout)
                self.assertIn(f'{later}: reviewed', result.stdout)
                self.assertEqual(len(self.calls()), 2 * count)
                self.assertTrue(marker.exists())
                self.assertNotIn('acknowledged_generation', self.state())

    def test_unknown_git_scope_with_shared_store_allows_ordinary_auto_review(self):
        self.write(self.config / 'agent-kaizen.json', '{"scheduledAutonomy":"auto"}')
        self.write(self.project / '.git', 'gitdir: missing\n')
        self.write(self.config / 'audits/host-actions.json', '{"v":1,"actions":{}}')
        result = self.review_run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('reviewed (auto)', result.stdout)
        self.assertNotIn('friction-inputs=', self.calls()[0]['argv'][1])

    def test_publish_failure_and_crash_recovery_in_review(self):
        scripts = self.root / 'publication-scripts'
        copy_plugin_tree(self.runner_path.parent, scripts)
        runner = scripts / 'kaizen-scheduled'
        source = runner.read_text()
        statement = '                os.replace(temporary, proposal)'
        runner.write_text(source.replace(statement, '                raise OSError("injected publish failure")', 1))
        result = self.review_run(runner=runner)
        self.assertIn('injected publish failure', result.stdout)
        self.assertNotIn('acknowledged_generation', self.state())
        self.assertTrue(list(self.obj.folder.glob('cycle-*.failed.md')))
        self.assertFalse([p for p in self.obj.folder.glob('cycle-*.md') if not p.name.endswith('.failed.md')])
        runner.write_text(source.replace(statement, statement + '\n                os._exit(77)', 1))
        result = self.review_run(runner=runner)
        self.assertEqual(result.returncode, 77)
        proposals = [p for p in self.obj.folder.glob('cycle-*.md') if not p.name.endswith('.failed.md')]
        self.assertEqual(len(proposals), 1)
        self.assertNotIn('acknowledged_generation', self.state())
        marker = next((self.backups / 'friction').glob('publication-*.json'))
        cutoff = json.loads(marker.read_text())['reviewed_at']
        persist = '        write_state(project, state, durable=True)'
        runner.write_text(source.replace(persist, '        os._exit(78)', 1))
        self.assertEqual(self.review_run(runner=runner).returncode, 78)
        self.assertTrue(marker.exists())
        review_state = self.obj.folder / 'state.json'
        self.assertNotIn('reviewed_at', json.loads(review_state.read_text()))
        runner.write_text(source)
        calls_before = len(self.calls())
        result = self.review_run('--now', (self.current + timedelta(days=1)).isoformat(), runner=runner)
        self.assertIn('recovered published review', result.stdout)
        self.assertEqual(len(self.calls()), calls_before)
        self.assertEqual([p for p in self.obj.folder.glob('cycle-*.md') if not p.name.endswith('.failed.md')], proposals)
        self.assertEqual(self.state()['acknowledged_generation'], '00000000000000000001')
        self.assertEqual(json.loads(review_state.read_text())['reviewed_at'], cutoff)
        self.assertFalse(marker.exists())

    def test_legacy_pending_receipts_stop_blocking_scheduled_acknowledgement(self):
        host = runpy.run_path(str(self.runner_path.parent / "kaizen_friction_actions.py"))
        store = host["HostActions"](self.config / "audits", self.backups,
                                    self.runner["action_project"], self.runner["key"])
        target = self.project / "build"
        target.mkdir()
        legacy = {}
        for number, (catalog, selector) in enumerate((("low-disk", "project-volume"),
                                                      ("linux-localsearch", str(target))), 1):
            ident = store.action_id(self.project, catalog, selector, allowed=[selector])
            generation = f"scheduled:{number:020d}"
            frozen = {ident: dict(canonical_project=str(self.project), catalog_id=catalog, selector_key=selector,
                                  intents=["suggest", "apply"], evidence="fixture")}
            block = '<!-- kaizen-host-actions ' + json.dumps(dict(v=1, actions=[dict(id=ident, intent="apply")])) + ' -->'
            self.assertEqual(store.import_actions(block, frozen, self.project, generation), {ident: "pending"})
            legacy[generation] = {ident: "terminal"}
        self.write(self.backups / "friction" / ("prepare-" + self.obj.key + ".json"),
                   json.dumps(dict(v=1, project=str(self.project), generation=2, acknowledged={}))).chmod(0o600)
        result = self.review_run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipts = json.loads(store.path.read_text())["receipts"][str(self.project)]
        for generation, expected in legacy.items():
            self.assertEqual(receipts[generation], expected)
        self.assertIn("proposal-only", result.stdout)
        self.assertIn("gate is closed", result.stdout)
        self.assertEqual(self.state().get("acknowledged_generation"), "00000000000000000003",
                         result.stdout + result.stderr)
        self.assertFalse((target / ".nomedia").exists())
        self.assertFalse(list(store.friction.glob("broker-*.json")))
        self.assertFalse((store.friction / "host-fixes").exists())

    def test_recovery_exception_still_closes_recordless_suggestion(self):
        host = runpy.run_path(str(self.runner_path.parent / "kaizen_friction_actions.py"))
        store = host["HostActions"](self.config / "audits", self.backups,
                                    self.runner["action_project"], self.runner["key"])
        target = self.project / "build"
        target.mkdir()
        ident = store.action_id(self.project, "linux-localsearch", str(target), allowed=[str(target)])
        frozen = {ident: dict(canonical_project=str(self.project), catalog_id="linux-localsearch",
                              selector_key=str(target), intents=["suggest", "apply"], evidence="fixture")}
        block = '<!-- kaizen-host-actions ' + json.dumps(dict(v=1, actions=[dict(id=ident, intent="apply")])) + ' -->'
        store.import_actions(block, frozen, self.project, "scheduled:00000000000000000001")
        scripts = self.root / "recovery-scripts"
        copy_plugin_tree(self.runner_path.parent, scripts)
        runner = scripts / "kaizen-scheduled"
        source = runner.read_text().replace('    root = backup_root().resolve()\n    statuses = []',
                                            '    raise OSError("injected recovery error")\n    statuses = []', 1)
        runner.write_text(source)
        result = self.review_run(runner=runner)
        self.assertIn("injected recovery error", result.stdout)
        receipts = json.loads(store.path.read_text())["receipts"][str(self.project)]
        self.assertEqual(receipts["scheduled:00000000000000000001"][ident], "terminal")
        self.assertFalse((target / ".nomedia").exists())

    def test_group_writable_checkout_recovers_suggestion_and_refuses_broker_apply(self):
        audits = self.config / "audits"
        host = runpy.run_path(str(self.runner_path.parent / "kaizen_friction_actions.py"))
        store = host["HostActions"](audits, self.backups, self.runner["action_project"], self.runner["key"])
        self.write(self.config / "agent-kaizen.json", '{"scheduledAutonomy":"auto"}')
        target = self.project / "build"
        target.mkdir()
        generation = "00000000000000000001"
        frozen = {}
        for catalog, selector in (("low-disk", "project-volume"), ("linux-localsearch", str(target))):
            ident = store.action_id(self.project, catalog, selector, allowed=[selector])
            frozen[ident] = dict(canonical_project=str(self.project), catalog_id=catalog, selector_key=selector,
                                 intents=["suggest", "apply"], evidence="fixture")
        suggestion, marker = frozen
        block = '<!-- kaizen-host-actions ' + json.dumps(dict(
            v=1, actions=[dict(id=ident, intent="apply") for ident in frozen])) + ' -->'
        scheduled = "scheduled:" + generation
        self.assertEqual(store.import_actions(block, frozen, self.project, scheduled), dict.fromkeys(frozen, "pending"))
        self.write(self.backups / "friction" / ("prepare-" + self.obj.key + ".json"),
                   json.dumps(dict(v=1, project=str(self.project), generation=1, acknowledged={}))).chmod(0o600)

        options = self.runner["command_options"](SimpleNamespace(claude=str(self.claude)))
        command = self.runner["review_command"](options, "auto", "", "", self.project, audits)
        _, config = self.runner["scheduled_authority"](audits, self.project, options, command, self.backups)
        info = target.stat()
        self.project.chmod(0o775)
        with self.assertRaisesRegex(ValueError, "unsafe host-action directory"):
            self.runner["run_scheduled_broker"](
                audits, self.obj, options, receipt=dict(generation=generation, allowed=frozen, scope=self.scope),
                attempt=(1, "fixture", {marker: [info.st_dev, info.st_ino]}, config))

        result = self.review_run("--propose-only")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(store.path.read_text())
        self.assertEqual(data["receipts"][str(self.project)][scheduled][suggestion], "terminal", result.stdout)
        self.assertEqual(data["receipts"][str(self.project)][scheduled][marker], "terminal", result.stdout)
        self.assertEqual(data["actions"][suggestion]["status"], "open")
        self.assertEqual(data["actions"][marker]["status"], "open")
        self.assertFalse((target / ".nomedia").exists())
        self.assertFalse(list(store.friction.glob("broker-*.json")))

    def test_probe_refresh_fresh_stale_and_failure(self):
        import os
        import sys
        scripts = self.root / 'probe-scripts'
        copy_plugin_tree(self.runner_path.parent, scripts)
        probe = scripts / 'host-probe'
        probe.write_text("#!" + sys.executable + "\n" + """
import datetime, json, pathlib, sys
if __import__('os').environ.get('PROBE_FAIL'):
    print('injected probe failure', file=sys.stderr)
    sys.exit(1)
args = sys.argv
out = pathlib.Path(args[args.index('--out') + 1])
project = args[args.index('--project') + 1]
(out / 'host-probe-999.json').write_text(json.dumps(dict(v=1, project=project,
    generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), findings=[], regenerable_dirs=[])))
""")
        self.probe_path.unlink()
        for case in ('fresh', 'stale', 'failure'):
            with self.subTest(case=case):
                shutil.rmtree(self.backups, ignore_errors=True)
                for path in self.obj.folder.glob('host-probe-*.json'):
                    path.unlink()
                if case != 'fresh':
                    self.probe['generated_at'] = (self.current - timedelta(hours=2)).isoformat()
                    stale = self.write(self.obj.folder / 'host-probe-000.json', json.dumps(self.probe))
                    old = (self.current - timedelta(hours=2)).timestamp()
                    os.utime(stale, (old, old))
                env = dict(self.env, **({'PROBE_FAIL': '1'} if case == 'failure' else {}))
                result = self.review_run(runner=scripts / 'kaizen-scheduled', env=env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual('friction-inputs=' in self.calls()[-1]['argv'][1], case != 'failure')
                if case == 'failure':
                    self.assertIn('injected probe failure', result.stdout)

    def test_audit_policy_through_all_scheduled_paths(self):
        import subprocess
        import sys
        scripts = self.root / 'audit-scripts'
        copy_plugin_tree(self.runner_path.parent, scripts)
        recorder = scripts / 'token-audit'
        recorder.write_text("#!" + sys.executable + "\n" + """
import json, os, sys
with open(os.environ['AUDIT_RECORD'], 'a') as out:
    out.write(json.dumps(sys.argv[1:]) + '\\n')
print(os.environ['AUDIT_REPORT'])
""")
        env = dict(self.env, AUDIT_RECORD=str(self.root / 'audit-calls'), AUDIT_REPORT=str(self.report), KAIZEN_SKIP_CHECKS='1')
        self.write(self.config / 'agent-kaizen.json', '{"friction":"off","frictionSlowCallSeconds":123,"frictionHeavySeconds":77}')
        self.write(self.project / 'docs/kaizen/config.json', '{"friction":"on","frictionSlowCallSeconds":124,"frictionHeavySeconds":78}')
        runner = scripts / 'kaizen-scheduled'
        subprocess.run([sys.executable, str(runner), 'audit'], env=env, capture_output=True, text=True, check=True)
        (self.config / 'audits/auto-audit-state.json').unlink()
        subprocess.run([sys.executable, str(runner), 'auto-audit'], env=env, capture_output=True, text=True, check=True)
        self.audit = recorder
        self.review_run(runner=runner, env=env)
        calls = [json.loads(line) for line in (self.root / 'audit-calls').read_text().splitlines()]
        self.assertEqual(sum(argv[:1] == ['ingest'] for argv in calls), 2)
        calls = [argv for argv in calls if '--extract-out' in argv]
        self.assertEqual(len(calls), 3)
        for argv in calls[:2]:
            self.assertIn('--no-friction', argv)
            self.assertEqual(argv[argv.index('--friction-slow-seconds') + 1], '123')
            self.assertEqual(argv[argv.index('--friction-heavy-seconds') + 1], '77')
        self.assertNotIn('--no-friction', calls[2])
        self.assertEqual(calls[2][calls[2].index('--friction-slow-seconds') + 1], '124')
        self.assertEqual(calls[2][calls[2].index('--friction-heavy-seconds') + 1], '78')

    def test_copied_install_runs_installed_preparation(self):
        import os
        import sys
        import subprocess
        from test_schedule import CRONTAB
        plugin = self.root / 'plugins/cache/agent-kaizen/version'
        copy_plugin_tree(self.runner_path.parent, plugin / 'scripts')
        binary = self.root / 'bin'
        cron = self.write(binary / 'crontab', CRONTAB.replace('#!/usr/bin/env python3', '#!' + sys.executable))
        cron.chmod(0o755)
        env = dict(self.env, CRON_FILE=str(self.root / 'cron'), PATH=str(binary) + os.pathsep + os.environ['PATH'])
        installed = subprocess.run([sys.executable, str(plugin / 'scripts/install-schedule'), '--apply', '--scheduler', 'cron'], env=env, capture_output=True, text=True)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        target = self.config / 'bin'
        self.assertTrue((target / 'kaizen_friction_prepare.py').is_file())
        self.assertFalse((target / 'kaizen_friction_prepare.py').is_symlink())
        shutil.rmtree(plugin)
        result = self.review_run(runner=target / 'kaizen-scheduled', env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('friction-inputs=', self.calls()[0]['argv'][1])
        self.assertEqual(self.state()['acknowledged_generation'], '00000000000000000001')

    def test_timeout_leaves_generation_pending(self):
        env = dict(self.env, REVIEW_SLEEP='1', KAIZEN_REVIEW_TIMEOUT='0.3')
        result = self.review_run(env=env)
        self.assertIn('timed out', result.stdout)
        state = self.state()
        self.assertEqual(state['generation'], 1)
        self.assertNotIn('acknowledged_generation', state)
        self.assertIsNotNone(self.scheduled() if hasattr(self, 'scheduled') else self.run_prepare())

    def test_closed_gate_and_open_gate_argv(self):
        result = self.review_run()
        self.assertEqual(result.returncode, 0, result.stderr)
        first = self.calls()[0]
        prompt = first['argv'][1]
        self.assertEqual(prompt.count('friction-inputs='), 1)
        argument = prompt.split(' friction-inputs=', 1)[1]
        self.assertTrue(json.loads(argument).endswith('friction-inputs-00000000000000000001.json'))
        self.assertIn(str(self.report), prompt)
        self.assertIn('--allowedTools', first['argv'])
        self.assertIn('--disallowedTools', first['argv'])
        self.assertTrue(first['marker'])
        self.review_run()
        second = self.calls()[1]
        self.assertNotIn('friction-inputs=', second['argv'][1])
        self.assertTrue(second['marker'])
        def stable_argv(argv):
            argv = list(argv)
            argv[argv.index('-p') + 1] = '<prompt>'
            argv[argv.index('--session-id') + 1] = '<session>'
            return argv
        self.assertEqual(stable_argv(first['argv']), stable_argv(second['argv']))
        before = len(self.calls())
        dry = self.review_run('--dry-run')
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn('--allowedTools', dry.stdout)
        self.assertNotIn('friction-inputs=', dry.stdout)
        self.assertEqual(len(self.calls()), before)

    def test_optional_preparation_failures_fall_back(self):
        for failure in ('missing', 'exception', 'malformed'):
            with self.subTest(failure=failure):
                scripts = self.root / ('scripts-' + failure)
                copy_plugin_tree(self.runner_path.parent, scripts)
                helper = scripts / 'kaizen_friction_prepare.py'
                if failure == 'missing':
                    helper.unlink()
                elif failure == 'exception':
                    helper.write_text('def prepare(*args, **kwargs):\n    raise ValueError("failed")\n')
                else:
                    helper.write_text('def prepare(*args, **kwargs):\n    return "malformed"\n')
                result = self.review_run(runner=scripts / 'kaizen-scheduled')
                self.assertEqual(result.returncode, 0, result.stderr)
                prompt = self.calls()[-1]['argv'][1]
                self.assertIn(str(self.report), prompt)
                self.assertNotIn('friction-inputs=', prompt)
                self.assertFalse(list((self.backups / 'friction').glob('prepare-*.json')))

    def test_retry_after_failed_import_preserves_generation(self):
        scripts = self.root / 'retry-scripts'
        copy_plugin_tree(self.runner_path.parent, scripts)
        helper = scripts / 'kaizen_friction_actions.py'
        original = helper.read_text()
        # Fail only the transactional import, after preparation has succeeded.
        helper.write_text(original.replace('def import_actions(self,', 'def import_actions_disabled(self,', 1))
        first = self.review_run(runner=scripts / 'kaizen-scheduled')
        self.assertIn('could not be reconciled', first.stdout)
        review_state = json.loads((self.obj.folder / 'state.json').read_text())
        self.assertNotIn('reviewed_at', review_state)
        state = self.state()
        self.assertNotIn('acknowledged_generation', state)
        receipt_path = next((self.backups / 'friction').glob('receipt-*.json'))
        first_receipt = json.loads(receipt_path.read_text())
        first_prompt = self.calls()[0]['argv'][1]
        helper.write_text(original)
        second = self.review_run(runner=scripts / 'kaizen-scheduled')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.calls()[1]['argv'][1].split(' friction-inputs=')[1],
                         first_prompt.split(' friction-inputs=')[1])
        self.assertEqual(self.state()['acknowledged_generation'], '00000000000000000001')
        final_state = self.state()
        self.assertEqual(final_state['acknowledged'], first_receipt['comparison'])
        self.assertEqual(json.loads(receipt_path.read_text())['comparison'], first_receipt['comparison'])
        store = json.loads((self.config / 'audits/host-actions.json').read_text())
        self.assertEqual(json.dumps(store).count('scheduled:00000000000000000001'), 1)
        self.review_run(runner=scripts / 'kaizen-scheduled')
        self.assertNotIn('friction-inputs=', self.calls()[2]['argv'][1])
        self.assertEqual(self.state(), final_state)
