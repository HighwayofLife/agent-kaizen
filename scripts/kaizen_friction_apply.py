"""Runner-owned mutation evidence for the dormant scheduled broker."""
import argparse
import base64
from contextlib import contextmanager, redirect_stdout
from datetime import date, datetime, timedelta, timezone
import errno
from functools import cached_property
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import runpy
import select
import shlex
import stat
import tempfile
from threading import Event, Thread
from types import SimpleNamespace


# Add a version only after S7 verifies the real print-mode lifecycle and permissions.
VERIFIED_STREAM_VERSIONS = frozenset()
STREAM_LIMIT = 8 << 20
LEDGER_LIMIT = 1 << 20
RECEIPT_LIMIT = 64 << 10
UNWRITABLE_FLAGS = stat.UF_IMMUTABLE | stat.UF_APPEND | stat.SF_IMMUTABLE | stat.SF_APPEND
LEDGER = Path("docs/kaizen/LEDGER.md")
HEADER = "date|change|why (which audit finding)|expected effect|measured effect|keep/revert|metric command|review date".split("|")
OPERATIONS = {
    "host-fix": ("Mark regenerable output", "LocalSearch output activity", "Less indexing of generated output"),
    "allow-rule": ("Add an exact allow rule", "Repeated accepted calls", "Fewer permission prompts"),
    "worktree-prune": ("Remove a merged worktree", "Clean merged worktree", "Less disk space used"),
}


def require(condition):
    if not condition:
        raise ValueError("scheduled mutation evidence is incomplete or inconsistent")


def reject_constant(_value):
    raise ValueError("non-JSON constant in mutation evidence")


def cells(line):
    if line.startswith(("    ", "\t")):
        return []
    line = line.strip()
    parts = re.split(r"(?<!\\)\|", line.removeprefix("|").removesuffix("|"))
    return [part.strip() for part in parts] if len(parts) > 1 or line.startswith("|") or line.endswith("|") else []


def row_line(row, newline):
    return "| " + " | ".join(row) + " |" + newline


def ledger_headers(lines):
    fence, comment = "", False
    for index, line in enumerate(lines):
        if fence:
            closing = line.strip()
            if not line.startswith(("    ", "\t")) and closing.startswith(fence) and not closing.strip(fence[0]):
                fence = ""
            continue
        if not comment:
            opening = re.match(r" {0,3}(`{3,}|~{3,})", line)
            if opening:
                fence = opening[1]
                continue
            if cells(line)[:2] == HEADER[:2]:
                yield index
        for marker in re.findall(r"<!--|-->", line):
            comment = marker == "<!--"


class BrokerLedger:
    """Private effect receipts and the editable project ledger, under one scoped writer lock."""

    @classmethod
    @contextmanager
    def locked(cls, host, store, project):
        self = cls()
        self.host, self.store, self.project = host, store, project
        if store.friction.resolve().is_relative_to(project):
            raise ValueError("broker state must be outside the project")
        self.secret = store._secret()
        self.path = project / LEDGER
        lock = "broker-" + hashlib.sha256(os.fsencode(project)).hexdigest() + ".lock"
        with host["_directory"](store.friction, private=True) as state, \
                host["_private_file"](state, lock, os.O_RDWR | os.O_CREAT) as lease:
            host["fcntl"].flock(lease, host["fcntl"].LOCK_EX)
            if not os.path.samestat(os.fstat(lease), os.stat(lock, dir_fd=state, follow_symlinks=False)):
                raise ValueError("broker project lock was replaced")
            with host["_directory"](project) as root:
                info = os.fstat(root)
            self.lease, self.state, self.identity = lease, state, [str(project), info.st_dev, info.st_ino]
            yield self

    def record_name(self, ident):
        if not self.host["ACTION_ID"].fullmatch(ident):
            raise ValueError("invalid broker action ID")
        return "broker-" + ident + ".json"

    def seal(self, record):
        raw = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii")
        return hmac.digest(self.secret, b"broker-ledger-v1\0" + raw, "sha256").hex()

    def load(self, ident):
        try:
            raw = self.host["_read"](self.state, self.record_name(ident), RECEIPT_LIMIT)
        except FileNotFoundError:
            return None
        record = json.loads(raw, object_pairs_hook=self.host["_unique"], parse_constant=reject_constant)
        mac = record.pop("mac", None) if isinstance(record, dict) else None
        if (not isinstance(mac, str) or not mac.isascii() or not hmac.compare_digest(mac, self.seal(record))
                or record.get("id") != ident or record.get("scope") != self.identity):
            raise ValueError("broker record does not authenticate this project and action")
        if record["operation"] == "allow-rule" and "literal" not in record:
            # Older ledgers always used ".", and older receipts must prove the
            # generation binding before they can authorize an inverse.
            _, scope = self.live_scope()
            literal = self.allow_rule_literal(ident, list(map(str, scope.paths)))
            if self.allow_rule["broker_id"](self.secret, scope, literal, record["generation"]) != record["tool_record"]:
                raise ValueError("invalid verified allow-rule binding")
        record.setdefault("evidence_scope", [str(self.project)])
        return record

    def save(self, record, phase):
        record["phase"] = phase
        raw = json.dumps(dict(record, mac=self.seal(record))).encode("ascii")
        if len(raw) > RECEIPT_LIMIT:
            raise ValueError("private broker record exceeds size limit")
        self.host["_replace"](self.state, self.record_name(record["id"]), raw)

    @cached_property
    def allow_rule(self):
        here = Path(__file__).resolve().parent
        helper = here / "kaizen-allow-rule"
        if not helper.exists():
            helper = here / "allow-rule"
        if helper.resolve() != helper or not helper.is_file():
            raise ValueError("fixed allow-rule helper is unavailable")
        return runpy.run_path(str(helper))

    def live_scope(self):
        tool = self.allow_rule
        runner = tool["runner_for"]()
        try:
            scope = tool["project_scope"](self.project, runner)
        except tool["Refused"] as error:
            raise ValueError(str(error)) from error
        if scope.canonical != self.project:
            raise ValueError("broker project scope changed")
        return runner, scope

    def evidence_scope(self, roots, scope):
        if (not isinstance(roots, list) or not roots or not all(isinstance(root, str) for root in roots)
                or len(set(roots)) != len(roots) or not set(roots) <= set(map(str, scope.paths))):
            raise ValueError("broker evidence scope is unavailable")
        return sorted(roots)

    def check_allow_rule_id(self, ident, literal, paths):
        selector = json.dumps([literal, *paths], separators=(",", ":"))
        if self.host["_id"](self.secret, str(self.project), "allow-rule", selector) != ident:
            raise ValueError("invalid verified allow-rule binding")

    def allow_rule_literal(self, ident, paths):
        action = next((row for row in self.store.scoped(self.project) if row["id"] == ident), None)
        if not action or action["catalog_id"] != "allow-rule":
            raise ValueError("invalid verified allow-rule binding")
        selector = json.loads(action["selector_key"])
        if not isinstance(selector, list) or len(selector) < 2:
            raise ValueError("invalid verified allow-rule binding")
        literal = selector[0]
        self.check_allow_rule_id(ident, literal, paths)
        tool = self.allow_rule
        try:
            tool["grant_rule"](literal)
        except tool["Refused"] as error:
            raise ValueError("invalid verified allow-rule binding") from error
        return literal

    def begin_allow_rule(self, ident):
        """Authenticate and persist the pending action before the fixed native grant runs."""
        tool = self.allow_rule
        runner, scope = self.live_scope()
        paths = list(map(str, scope.paths))
        literal = self.allow_rule_literal(ident, paths)
        try:
            count, (generation, _) = tool["evidence"](runner, scope, literal, self.secret)
            extract, _ = tool["find_extract"](runner["audits_dir"](), scope, datetime.now(timezone.utc))
        except tool["Refused"] as error:
            raise ValueError(str(error)) from error
        # P18d authenticates the entire extract. Match its digest before using
        # the exact audit roots, which can be a subset of the native project scope.
        extract.pop("allow_rule_mac", None)
        payload = json.dumps(extract, sort_keys=True, separators=(",", ":")).encode("ascii")
        if hashlib.sha256(payload).hexdigest() != generation or not 0 <= count <= 10**9:
            raise ValueError("broker audit evidence changed or exceeds its limit")
        roots = self.evidence_scope(extract["scope"]["cwd"], scope)
        native_id = tool["broker_id"](self.secret, scope, literal, generation)
        self.preflight(ident, "allow-rule", evidence_scope=roots)
        self.save(dict(id=ident, operation="allow-rule", tool_record=native_id, literal=literal,
                       native_scope=paths, evidence_scope=roots, generation=generation, count=count,
                       scope=self.identity, date=date.today().isoformat()), "apply-pending")
        return native_id

    def verify_allow_rule(self, record):
        """Verify the bound native journal without consulting or refreshing the extract."""
        tool = self.allow_rule
        ident, literal, paths = (record[key] for key in ("id", "literal", "native_scope"))
        self.check_allow_rule_id(ident, literal, paths)
        scope = SimpleNamespace(canonical=self.project, paths=paths)
        native_id = tool["broker_id"](self.secret, scope, literal, record["generation"])
        if native_id != record["tool_record"]:
            raise ValueError("invalid verified allow-rule binding")
        root, rule = str(self.project), tool["grant_rule"](literal)
        with self.host["_locked"](self.state, "allow-rules"):
            raw = self.host["_read"](self.state, tool["STATE"], tool["EXTRACT_LIMIT"])
            journal = json.loads(raw, object_pairs_hook=self.host["_unique"], parse_constant=reject_constant)
            mac = journal.pop("mac", None) if isinstance(journal, dict) else None
            if (not isinstance(mac, str) or not mac.isascii() or not hmac.compare_digest(
                    mac, hmac.digest(self.secret, b"allow-rules-v1\0" + tool["json_bytes"](journal), "sha256").hex())):
                raise ValueError("native allow-rule journal does not authenticate")
            entry = journal["projects"].get(root)
            native = journal["records"].get(native_id)
            if not entry or entry["bound"][0][:2] != self.identity[1:]:
                raise ValueError("native allow-rule record does not match this project")
            if native == [root, rule, "applied"] and entry["file"]:
                return entry["file"][1][2]
            pending = entry["pending"]
            if (native == [root, rule, "pending"] and pending and pending["id"] == native_id
                    and pending["rule"] == rule and pending["undo"] is False and pending["after"]):
                if pending.get("published"):
                    return pending["published"][1][2]
                # A native crash just after rename can precede its publication receipt.
                path = self.project / tool["TARGET"].parent
                with self.host["_directory"](path) as settings:
                    current = tool["effect_id"](*tool["snapshot"](settings))
                    parked = tool["effect_id"](*tool["snapshot"](settings, pending["temp"]))
                    info = os.fstat(settings)
                    if (entry["bound"][1][:2] == [info.st_dev, info.st_ino]
                            and current == pending["after"] and parked == pending["before"][1]):
                        os.fsync(settings)
                        return current[2]
            raise ValueError("no verified native allow-rule effect")

    def tool_record(self, ident, operation):
        self.record_name(ident)
        if operation == "host-fix":
            return str(self.store.friction / "host-fixes" / (ident + ".json"))
        if operation == "worktree-prune":
            return str(Path.home().resolve() / ".claude/audits/worktree-prunes" / (ident + ".json"))
        raise ValueError("unknown broker operation")

    def row(self, record):
        change, signal, expected = OPERATIONS[record["operation"]]
        day = date.fromisoformat(record["date"])
        # Run from the enrolled project root, using the exact canonical roots of the audit.
        args = ["kaizen-token-audit"]
        if not record.get("evidence_scope"):
            raise ValueError("broker evidence scope is unavailable")
        for root in record["evidence_scope"]:
            path = os.path.relpath(root, self.project)
            if any(char in path for char in "`|\r\n") or "\\" in path:
                raise ValueError("broker evidence scope cannot be written in the ledger")
            args.extend(("--cwd", "./" + path if path.startswith("-") else path))
        return [day.isoformat(), f"{change} [action:{record['id']}]", f"{signal} ({record['count']})",
                expected, "pending", "pending", f"`{shlex.join(args)}`", (day + timedelta(days=7)).isoformat()]

    def check_acl(self, fd, kind, linux_attr):
        self.host["_check_acl"](fd, kind)
        if hasattr(os, "getxattr"):
            try:
                os.getxattr(fd, linux_attr)
            except OSError as error:
                if error.errno not in (errno.ENODATA, errno.ENOTSUP):
                    raise
            else:
                raise ValueError("extended ACL on broker ledger " + kind)

    def snapshot(self, directory, name=None):
        name = self.path.name if name is None else name
        with os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                               dir_fd=directory), "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_size > LEDGER_LIMIT or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or info.st_mode & 0o7022
                    or getattr(info, "st_flags", 0) & UNWRITABLE_FLAGS):
                raise ValueError("unsafe broker ledger file")
            self.check_acl(stream.fileno(), "file", "system.posix_acl_access")
            raw = stream.read(LEDGER_LIMIT + 1)
            live = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if len(raw) != info.st_size or not os.path.samestat(info, live) or live.st_ctime_ns != info.st_ctime_ns:
                raise ValueError("broker ledger changed while being read")
        return raw, (info.st_dev, info.st_ino, info.st_mode, info.st_gid, info.st_mtime_ns, info.st_ctime_ns)

    @contextmanager
    def table(self, ident):
        with self.host["_directory"](self.project) as root, self.host["_directory"](self.path.parent) as directory:
            info = os.fstat(root)
            if self.identity[1:] != [info.st_dev, info.st_ino]:
                raise ValueError("broker project directory was replaced")
            if (getattr(os.fstat(directory), "st_flags", 0) & UNWRITABLE_FLAGS
                    or not os.access(self.path.parent, os.W_OK | os.X_OK)):
                raise ValueError("broker ledger directory is not writable")
            self.check_acl(directory, "directory", "system.posix_acl_default")
            before = self.snapshot(directory)
            raw = before[0]
            digest = hashlib.sha256(raw).digest()
            if len(raw) > LEDGER_LIMIT or re.search(rb"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]|\r(?!\n)", raw):
                raise ValueError("invalid broker ledger contents")
            lines = re.findall(r"[^\n]*\n|[^\n]+$", raw.decode("utf-8"))
            headers = list(ledger_headers(lines))
            if len(headers) != 1:
                raise ValueError("expected one broker ledger table")
            start = headers[0]
            header = cells(lines[start])
            width = len(header)
            if header[2:3] == ["why"]:
                header[2] = HEADER[2]
            separator = cells(lines[start + 1]) if start + 1 < len(lines) else []
            if (width not in (6, 8) or header != HEADER[:width] or len(separator) != width
                    or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)):
                raise ValueError("invalid broker ledger table header")
            end = start + 2
            while end < len(lines) and (row := cells(lines[end])):
                if len(row) not in (6, width):
                    raise ValueError("invalid broker ledger table row")
                end += 1
            matches = [i for i, line in enumerate(lines) if ident in line]
            if len(matches) > 1 or matches and not (width == 8 and start + 2 <= matches[0] < end):
                raise ValueError("conflicting broker action ledger rows")

            def write():
                updated = "".join(lines).encode("utf-8")
                if len(updated) > LEDGER_LIMIT:
                    raise ValueError("broker ledger exceeds size limit")
                temporary = ".kaizen-ledger-" + os.urandom(16).hex()
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                fd = os.open(temporary, flags, 0o600, dir_fd=directory)
                staged = os.fstat(fd)
                displaced = None
                try:
                    with os.fdopen(fd, "wb") as stream:
                        if os.fstat(stream.fileno()).st_gid != before[1][3]:
                            os.fchown(stream.fileno(), -1, before[1][3])
                        os.fchmod(stream.fileno(), stat.S_IMODE(before[1][2]))
                        stream.write(updated)
                        stream.flush()
                        os.fsync(stream.fileno())
                    with self.host["_directory"](self.path.parent) as live:
                        if not os.path.samestat(os.fstat(live), os.fstat(directory)):
                            raise ValueError("broker ledger changed during transaction")
                        raw, version = self.snapshot(live)
                        if (version != before[1] or hashlib.sha256(raw).digest() != digest
                                or not os.path.samestat(staged, os.stat(temporary, dir_fd=live, follow_symlinks=False))):
                            raise ValueError("broker ledger changed during transaction")
                        displaced = self.exchange_ledger(live, temporary, staged, before, digest, updated)
                finally:
                    try:
                        info = os.stat(temporary, dir_fd=directory, follow_symlinks=False)
                        if os.path.samestat(info, staged) or (info.st_dev, info.st_ino) == displaced:
                            os.unlink(temporary, dir_fd=directory)
                    except FileNotFoundError:
                        pass
                os.fsync(directory)

            os.fsync(directory)  # A prior attempt may have stopped after rename.
            yield lines, start, end, width, matches[0] if matches else None, write

    def exchange_ledger(self, directory, temporary, staged, before, digest, updated):
        # Exchange preserves a save made after the final snapshot. Without an
        # inode-conditional rename, another save can still race restoration.
        target = self.path.name
        tool = self.allow_rule
        exchange, stamp = tool["rename_effect"], tool["named_version"]
        try:
            exchange(directory, temporary, target, exchange=True)
        except tool["Refused"] as error:
            raise ValueError(str(error)) from error
        parked, published = stamp(directory, temporary), stamp(directory, target)
        ours = False
        try:
            result, installed = self.snapshot(directory)
            ours = installed[:2] == (staged.st_dev, staged.st_ino) and result == updated
            raw, version = self.snapshot(directory, temporary)
            # Rename can change ctime on the parked inode.
            if ours and version[:-1] == before[1][:-1] and hashlib.sha256(raw).digest() == digest:
                return version[:2]
        except (OSError, ValueError):
            pass
        if (ours and parked is not None and published and published[:2] == [staged.st_dev, staged.st_ino]
                and stamp(directory, temporary) == parked and stamp(directory, target) == published):
            exchange(directory, temporary, target, exchange=True)
            os.fsync(directory)
        raise ValueError("broker ledger changed during publication")

    def preflight(self, ident, operation, *, evidence_scope):
        """Call before starting a new effect, with the lock held through bookkeeping."""
        if self.load(ident) is not None:
            raise ValueError("broker action already has an effect receipt")
        _, scope = self.live_scope()
        evidence_scope = self.evidence_scope(evidence_scope, scope)
        row = self.row(dict(id=ident, operation=operation, count=10**9, date=date.today().isoformat(),
                            evidence_scope=evidence_scope))
        with self.table(ident) as (lines, _, _, _, match, _):
            growth = len(row_line(row, "\r\n").encode()) + 64  # Include a six-column header upgrade.
            if match is not None or len("".join(lines).encode("utf-8")) + growth > LEDGER_LIMIT:
                raise ValueError("broker ledger has a conflicting row or insufficient space")

    def record_verified(self, ident, operation, tool_record, verification, generation, count, *, evidence_scope):
        """Record a tool-owned effect already verified by the runner, including on recovery."""
        if (not re.fullmatch(r"[a-f0-9]{64}", verification) or not self.host["_text"](generation, 128)
                or type(count) is not int or not 0 <= count <= 10**9):
            raise ValueError("invalid verified broker effect")
        if operation == "allow-rule":
            raise ValueError("allow-rule receipts require a verified native transaction")
        if tool_record != self.tool_record(ident, operation):
            raise ValueError("invalid verified broker effect")
        record = self.load(ident)
        if record is not None:
            evidence_scope = sorted(evidence_scope)
        else:
            _, scope = self.live_scope()
            evidence_scope = self.evidence_scope(evidence_scope, scope)
        binding = dict(id=ident, operation=operation, tool_record=tool_record, verification=verification,
                       generation=generation, count=count, scope=self.identity, evidence_scope=evidence_scope)
        if record is None:
            record = dict(binding, date=date.today().isoformat())
            self.save(record, "effect-verified")
        elif any(record[key] != value for key, value in binding.items()):
            raise ValueError("conflicting private broker effects")
        return self.reconcile(ident)

    def reconcile(self, ident):
        record = self.load(ident)
        if record is None:
            raise ValueError("unknown verified broker effect in this project")
        if record["phase"] == "apply-pending":
            record["verification"] = self.verify_allow_rule(record)
            self.save(record, "effect-verified")
        phase = record["phase"]
        expected = self.row(record)
        with self.table(ident) as (lines, start, end, width, match, write):
            if phase != "effect-verified":
                row = self.linked_row(lines, match, expected)
                if phase == "recorded" and row[5].startswith("reverted"):
                    raise ValueError("broker ledger claims an unverified reversal")
                if phase == "reverted" and row[5] != f"reverted ({record['undo_date']})":
                    raise ValueError("broker ledger is missing the verified reversal")
                return phase
            if match is None:
                newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
                if width == 6:
                    for index, extra in ((start, HEADER[6:]), (start + 1, ["---", "---"])):
                        lines[index] = row_line(cells(lines[index]) + extra, newline)
                if not lines[end - 1].endswith("\n"):
                    lines[end - 1] += newline
                lines.insert(end, row_line(expected, newline))
                write()
            elif cells(lines[match]) != expected:
                raise ValueError("broker ledger row conflicts with verified effect")
        self.save(record, "recorded")
        return "recorded"

    @staticmethod
    def linked_row(lines, match, expected):
        row = cells(lines[match]) if match is not None else []
        if len(row) != 8 or row[:4] != expected[:4] or row[6:] != expected[6:]:
            raise ValueError("broker ledger row is missing or conflicts with the private record")
        return row

    def undo(self, ident, inverse):
        record = self.load(ident)
        if record is None or record["phase"] == "apply-pending":
            raise ValueError("no verified broker effect in this project")
        expected = self.row(record)
        phase = record["phase"]
        with self.table(ident) as (lines, _, _, _, match, write):
            row = self.linked_row(lines, match, expected)
            if phase == "effect-verified":
                if row != expected:
                    raise ValueError("broker ledger row conflicts with verified effect")
                self.save(record, "recorded")
                phase = "recorded"
            status = hashlib.sha256(row[5].encode("utf-8")).hexdigest()
            undo_date = record.get("undo_date") or date.today().isoformat()
            reverted = f"reverted ({undo_date})"
            update = row[5] != reverted
            if update:
                new_row = row_line([*row[:5], reverted, *row[6:]],
                                   "\r\n" if lines[match].endswith("\r\n") else "\n")
                lines[match] = new_row
                if len("".join(lines).encode("utf-8")) > LEDGER_LIMIT:
                    raise ValueError("broker ledger has insufficient space for reversal")
            if phase == "recorded":
                if row[5].startswith("reverted"):
                    raise ValueError("broker ledger claims an unverified reversal")
                record.update(undo_date=undo_date, prior_status=status)
                self.save(record, "undo-pending")
                phase = "undo-pending"
            if phase == "reverted" and not update:
                return
            if ((phase == "undo-pending" and status != record["prior_status"])
                    or (phase == "undo-verified" and status != record["prior_status"] and row[5] != reverted)
                    or phase not in ("undo-pending", "undo-verified")):
                raise ValueError("conflicting broker reversal state")
            if phase == "undo-pending":
                inverse(record["operation"], record["tool_record"])
                self.save(record, "undo-verified")
            if update:
                write()
        self.save(record, "reverted")


def observe_review(run, command, version, *, backup, scope, project, **kwargs):
    """Capture bounded stdout through an anonymous pipe owned by the runner."""
    require(version in VERIFIED_STREAM_VERSIONS)
    executable = Path(command[0])
    require(executable.is_absolute())
    executable = executable.resolve(strict=True)
    stamp = backup["file_version"](executable.stat())
    raw = bytearray()
    done = Event()
    complete = Event()
    reader, writer = os.pipe()

    def collect():
        try:
            while True:
                if not select.select([reader], [], [], 0.1)[0]:
                    if done.is_set():
                        return
                    continue
                chunk = os.read(reader, 65536)
                if not chunk:
                    complete.set()
                    return
                raw.extend(chunk[:max(0, STREAM_LIMIT + 1 - len(raw))])
                if len(raw) > STREAM_LIMIT and done.is_set():
                    return
        except OSError:
            return
        finally:
            os.close(reader)

    thread = Thread(target=collect)
    thread.start()
    try:
        result = run([str(executable), *command[1:], "--output-format", "stream-json", "--verbose"],
                     stdout=writer, **kwargs)
    finally:
        os.close(writer)
        done.set()
        thread.join()
    try:
        require(complete.is_set() and result.returncode == 0 and backup["file_version"](executable.stat()) == stamp)
        review, calls = runtime_calls(bytes(raw), version, scope, project, backup["unique_fields"])
    except (AttributeError, KeyError, OSError, RecursionError, TypeError, ValueError):
        return result, "Scheduled review stream is incomplete.\n", None
    return result, review, calls


def runtime_calls(raw, version, scope, project, unique_fields):
    """Return rendered review text and ordered dispatch/completion pairs."""
    require(version in VERIFIED_STREAM_VERSIONS and len(raw) <= STREAM_LIMIT and raw.endswith(b"\n"))
    events = raw[:-1].split(b"\n")
    seen, calls, results, assistant = set(), {}, {}, False
    for index, line in enumerate(events):
        event = json.loads(line.decode("utf-8"), object_pairs_hook=unique_fields, parse_constant=reject_constant)
        require(event["session_id"] == scope["session_id"] and isinstance(event["uuid"], str)
                and event["uuid"] and event["uuid"] not in seen)
        seen.add(event["uuid"])
        kind = event["type"]
        if index == 0:
            require(kind == "system" and event["subtype"] == "init"
                    and event["claude_code_version"] == version and event["cwd"] == str(project))
        elif index == len(events) - 1:
            require(assistant and kind == "result" and event["subtype"] == "success" and event["is_error"] is False
                    and isinstance(event["result"], str) and calls.keys() == results.keys())
            denials = event.get("permission_denials", [])
            require(isinstance(denials, list))
            denied = set()
            for denial in denials:
                ident = denial["tool_use_id"]
                require(ident in calls and ident not in denied and results[ident][1]
                        and calls[ident][1:] == (denial["tool_name"], denial["tool_input"]))
                denied.add(ident)
            return event["result"], [(start, *results[tool_id], name, args)
                                     for tool_id, (start, name, args) in calls.items()]
        else:
            require(kind in ("assistant", "user") and event["parent_tool_use_id"] is None)
            assistant |= kind == "assistant"
            message = event["message"]
            require(message["role"] == kind and isinstance(message["content"], list) and message["content"])
            for block in message["content"]:
                if kind == "assistant" and block["type"] in ("text", "thinking"):
                    require(isinstance(block[block["type"]], str))
                    continue
                if kind == "assistant":
                    require(block["type"] == "tool_use" and isinstance(block["id"], str)
                            and block["id"] and block["id"] not in calls and isinstance(block["input"], dict))
                    calls[block["id"]] = index, block["name"], block["input"]
                else:
                    tool_id, failed = block["tool_use_id"], block.get("is_error", False)
                    require(block["type"] == "tool_result" and tool_id in calls and tool_id not in results
                            and type(failed) is bool)
                    results[tool_id] = index, failed
    raise ValueError("missing runtime result")


def single_link_bytes(backup, path, limit):
    live = backup["checked_bytes"](path, limit)
    info = path.lstat()
    require(info.st_nlink == 1 and backup["file_version"](info) == live[2])
    return live


def snapshot_ledger(backup, project):
    path = project / backup["LEDGER_PATH"]
    try:
        return single_link_bytes(backup, path, backup["MAX_LEDGER_BYTES"])[1]
    except FileNotFoundError:
        return None


def ledger_proof(backup, scope, project, before, manifest_ids):
    path = backup["LEDGER_PATH"]
    require(isinstance(before, bytes) and len(before) <= backup["MAX_LEDGER_BYTES"]
            and all(backup["nonempty"](scope[key]) for key in ("run_id", "session_id")))
    _, after, version = single_link_bytes(backup, project / path, backup["MAX_LEDGER_BYTES"])
    proof = dict(v=1, run_id=scope["run_id"], session_id=scope["session_id"], ledger_relpath=path,
                 before_b64=base64.b64encode(before).decode("ascii"),
                 before_sha256=hashlib.sha256(before).hexdigest(),
                 after_sha256=hashlib.sha256(after).hexdigest(), manifest_ids=sorted(manifest_ids))
    _, _, live = backup["ledger_append"](proof, scope, project)
    require(live[2] == version)
    return proof, live


def bash_args(command, backup_script, notes_script, python):
    # Accept only simple literal invocations of the existing scheduled grants.
    require(not re.search(r'[\x00-\x1f\x7f$;&|<>()\\`*?\[\]{}~#!]', command))
    argv = shlex.split(command)
    interpreted = bool(argv and argv[0] in ("python3", python))
    if interpreted:
        argv.pop(0)
    require(len(argv) >= 2)
    helper, operation, *args = argv
    if helper == str(backup_script):
        require(operation in ("begin", "finish", "list"))
        return operation, args
    require(interpreted and helper == str(notes_script) and operation == "add")
    return operation, args


def snapshot_notes(backup, paths):
    """Capture configured notes targets from runner config before launch."""
    require(len(set(paths.values())) == len(paths))
    return {kind: (path, single_link_bytes(backup, path, STREAM_LIMIT)) for kind, path in paths.items()}


def verify_notes(backup, notes, entries, commands):
    """Replay verified literal adds on private copies and compare the guarded ledgers."""
    if not commands and not entries:
        return
    paths = {}
    with tempfile.TemporaryDirectory(prefix="kaizen-notes-proof-") as temporary:
        for kind, (_, before) in entries.items():
            paths[kind] = Path(temporary) / kind
            paths[kind].write_bytes(before[1])
        required = {"--date", "--category", "--change", "--why", "--measure", "--source"}
        for args in commands:
            fields = dict(zip(args[::2], args[1::2]))
            require("csv" in paths and len(fields) * 2 == len(args)
                    and fields.keys() in (required, required | {"--status"})
                    and all(not value.startswith("-") for value in fields.values()))
            values = {key[2:]: value for key, value in fields.items()}
            values.setdefault("status", "active")
            require(values["status"] in ("active", "planned"))
            with redirect_stdout(io.StringIO()):
                notes(argparse.Namespace(dry_run=False, **values), paths["csv"], paths.get("timeline"))
        for kind, (path, before) in entries.items():
            live = single_link_bytes(backup, path, STREAM_LIMIT)
            require(live[1] == paths[kind].read_bytes()
                    and (kind != "csv" or live[2][:2] == before[2][:2]))


def prove_budget(calls, *, backup, root, scope, project, baseline, ledger_before, config_before, config_after,
                 backup_script, notes_script, python, notes_add, notes_before):
    """Prove allowance after guarded exit, with the runner holding the notes lock."""
    try:
        require(config_before == config_after and type(config_before[0]) is int and config_before[0] >= 0
                and baseline["root"] == str(project))
        with backup["open_directory"](root) as fd:
            stamp = backup["backup_root_stamp"](root, fd)
        initial_stamp = scope["root_identity"]
        require(stamp["ctime_ns"] >= initial_stamp["ctime_ns"]
                and dict(stamp, ctime_ns=initial_stamp["ctime_ns"]) == initial_stamp)
        folders_after = {path for path in root.iterdir() if stat.S_ISDIR(path.lstat().st_mode)}
        ledger = project / backup["LEDGER_PATH"]
        edits, originals, finished, notes = {}, {}, {}, []
        active, charge, prior_end, ledger_written = None, 0, -1, False
        remaining_bytes = backup["MAX_COMMIT_BYTES"]
        for start, end, failed, name, args in calls:
            if name in ("Read", "Grep", "Glob"):
                continue
            # Do not infer ordering between effects dispatched in parallel.
            require(start > prior_end)
            prior_end = end
            if name in ("Edit", "Write"):
                path = Path(args["file_path"])
                require(path.is_absolute() and str(path) == args["file_path"] and path.resolve() == path
                        and path.is_relative_to(project)
                        and not path.is_relative_to(backup_script.parent)
                        and not path.is_relative_to(notes_script.parent)
                        and path != Path(python).resolve())
                if path == ledger:
                    require(active is None and not failed and not ledger_written and finished)
                    ledger_written = True
                else:
                    require(active is not None and path in active[2])
                    active[3].add(path)
                    charge += 1
                continue
            require(name == "Bash" and args.keys() <= {
                "command", "description", "timeout", "run_in_background", "dangerouslyDisableSandbox"
            } and args.get("run_in_background", False) is False
                and args.get("dangerouslyDisableSandbox", False) is False)
            op, argv = bash_args(args["command"], backup_script, notes_script, python)
            require(not failed)
            if op == "list":
                require(argv in ([], ["--all"]))
            elif op == "add":
                notes.append(argv)
            elif op == "begin":
                require(active is None and not ledger_written and len(argv) >= 5
                        and argv[0] == "--skill" and argv[2] == "--ledger"
                        and not any(arg.startswith("-") for arg in argv[4:]))
                paths = [project / arg for arg in argv[4:]]
                require(len(paths) == len(set(paths)))
                active = argv[1], argv[3], paths, set()
            else:
                require(active is not None and (len(argv) == 1 or argv[1:] == ["--verification", "passed"]))
                folder = Path(argv[0])
                require(folder not in finished and folder in folders_after)
                data, identity, digest = backup["validate_change_handoff"](root, folder, **scope)
                raw = backup["checked_bytes"](folder / "manifest.json", STREAM_LIMIT)[1]
                require(hashlib.sha256(raw).hexdigest() == digest)
                json.loads(raw, object_pairs_hook=backup["unique_fields"], parse_constant=reject_constant)
                skill, description, paths, written = active
                require(data["finished"] is True and data["verification"] == "passed" and data["reverted"] is None
                        and "committed" not in data and "git" not in data and data["actions"] == []
                        and (data["skill"], data["ledger"]) == (skill, description)
                        and [entry["path"] for entry in data["files"]] == list(map(str, paths))
                        and set(paths) == written and not written.intersection(edits))
                for entry in data["files"]:
                    path = backup["validate_entry"](folder, entry)
                    live = single_link_bytes(backup, path, remaining_bytes)
                    remaining_bytes -= len(live[1])
                    require(hashlib.sha256(live[1]).hexdigest() == entry["after_sha256"]
                            and not (entry["created"] and entry["backup"] is not None))
                    edits[path] = live
                    originals[path] = None if entry["created"] else folder / entry["backup"]
                finished[folder] = identity, digest
                active = None
        require(active is None and folders_after - scope["before"][0] == finished.keys())
        verify_notes(backup, notes_add, notes_before, notes)
        proof = None
        if ledger_written:
            proof, edits[ledger] = ledger_proof(backup, scope, project, ledger_before, [f.name for f in finished])
        _, entries, check = backup["capture_git_tree"](project, baseline=baseline, edits=edits)
        for path, old in originals.items():
            blob = entries.get(path)
            require((old is None and blob is None and edits[path][0] == b"100644")
                    or (old is not None and blob is not None and edits[path][0] == blob[0]
                        and backup["matches_blob"](old, *blob)))
        if proof is not None:
            mode, oid = entries[ledger]
            require(mode == edits[ledger][0] and backup["object_id"]("blob", ledger_before, len(oid)) == oid)
        for folder, (identity, digest) in finished.items():
            backup["verify_change_handoff"](root, folder, root_identity=initial_stamp,
                                            identity=identity, manifest_sha256=digest)
        backup["check_backup_root"](root, stamp)
        require(backup["still_clean"](*check))
        return max(0, config_before[0] - charge), proof
    except (AttributeError, KeyError, OSError, RecursionError, RuntimeError, TypeError, ValueError):
        return None, None
