"""Machine-local identity, import receipts and verification for scoped host actions."""
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import runpy
import stat
import subprocess
import sys

try:
    import fcntl
except ImportError:
    fcntl = None

STORE_LIMIT = 1024 * 1024
RECEIPT_LIMIT = 2 * STORE_LIMIT
EVIDENCE_LIMIT = 500
CREATE_RETRIES = 100
STATES = {"done": "done", "dismiss": "dismissed", "reopen": "open"}
CATALOG_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
ACTION_ID = re.compile(r"fa1_[0-9a-f]{64}")
INTENTS = {"suggest": "terminal", "apply": "pending"}
COMPACT_APPLY = "a"
RECEIPT_STATES = (*INTENTS.values(), COMPACT_APPLY)
BLOCK_PREFIX = "<!-- kaizen-host-actions "
ROW_OPTIONAL = {"steps", "metric_at_done", "flaps"}
ROW_FIELDS = set("canonical_project catalog_id selector_key subject projects status first_seen updated_at "
                 "evidence eligible done_by".split())
ID_FIELDS = ("canonical_project", "catalog_id", "selector_key")


def _identity(scope, catalog_id, value):
    if not (_text(str(scope), 4096, path=True) and _text(value, 4096, path=True)
            and _text(catalog_id, 64) and CATALOG_ID.fullmatch(catalog_id)):
        raise ValueError("invalid host-action identity")
    return str(scope), catalog_id, value


def _id(secret, project, catalog_id, selector):
    payload = json.dumps([1, project, catalog_id, selector], ensure_ascii=True, separators=(",", ":"))
    return "fa1_" + hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _has_extended_acl(fd, *, allow_deny_only=False):
    # Mirrors kaizen_friction_sample.has_extended_acl: Darwin ACLs can grant access the mode bits hide.
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        get_acl, free_acl = libc.acl_get_fd_np, libc.acl_free
    except (ImportError, AttributeError) as error:
        raise OSError("cannot verify host-action ACL") from error
    get_acl.argtypes = (ctypes.c_int, ctypes.c_int)
    get_acl.restype = ctypes.c_void_p
    free_acl.argtypes = (ctypes.c_void_p,)
    acl = get_acl(fd, 0x100)  # ACL_TYPE_EXTENDED in sys/acl.h
    if acl:
        try:
            if not allow_deny_only:
                return True
            # A deny-only ACL (including the default on macOS home folders) cannot grant access.
            get_entry, get_tag = libc.acl_get_entry, libc.acl_get_tag_type
            get_entry.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
            get_tag.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
            entry, tag = ctypes.c_void_p(), ctypes.c_int()
            ctypes.set_errno(0)
            result = get_entry(acl, 0, ctypes.byref(entry))  # ACL_FIRST_ENTRY
            while result == 0:
                if get_tag(entry, ctypes.byref(tag)) != 0 or tag.value != 2:  # ACL_EXTENDED_DENY
                    return True
                ctypes.set_errno(0)
                result = get_entry(acl, -1, ctypes.byref(entry))  # ACL_NEXT_ENTRY
            if ctypes.get_errno() != errno.EINVAL:  # No more entries.
                raise OSError("cannot verify host-action ancestor ACL")
            return False
        finally:
            free_acl(acl)
    error = ctypes.get_errno()
    if error != errno.ENOENT:  # Darwin returns ENOENT for an inode without an ACL.
        raise OSError(error, "cannot verify host-action ACL")
    return False


def _check_acl(fd, kind):
    if sys.platform == "darwin" and _has_extended_acl(fd):
        raise ValueError(f"extended ACL on host-action {kind}")


def _check_directory(fd, owner=False, private=False, store=False):
    info = os.fstat(fd)
    uid = os.geteuid()
    # A root-owned sticky ancestor (such as /tmp) protects each verified child from unlink or rename.
    sticky = not owner and info.st_uid == 0 and info.st_mode & stat.S_ISVTX
    if (info.st_uid not in ((uid,) if owner else (0, uid))
            or (info.st_mode & (0o077 if private else 0o022) and not sticky)):
        raise ValueError("unsafe host-action directory")
    if store:
        _check_acl(fd, "directory")
    elif sys.platform == "darwin" and _has_extended_acl(fd, allow_deny_only=True):
        raise ValueError("extended ACL on host-action ancestor directory")


@contextmanager
def _directory(path, create=False, private=False):
    if create and fcntl is None:
        raise ValueError("host-action writes require file locking")
    if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW", "geteuid")):
        raise ValueError("private host-action directories are unavailable")
    path = path.absolute()
    if ".." in path.parts:
        raise ValueError("unsafe host-action directory")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        _check_directory(fd, owner=path.parent == path, private=private and path.parent == path)
        for index, name in enumerate(path.parts[1:], 1):
            try:
                child = os.open(name, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(name, 0o700, dir_fd=fd)
                except FileExistsError:  # Another writer created the directory.
                    pass
                child = os.open(name, flags, dir_fd=fd)
            try:
                if create and os.fstat(child).st_uid == os.geteuid():
                    # This or a concurrent writer may have just created the entry: make it durable first.
                    os.fsync(fd)
            except BaseException:
                os.close(child)
                raise
            os.close(fd)
            fd = child
            remaining = len(path.parts) - index - 1
            _check_directory(fd, owner=remaining == 0 or (private and remaining == 1),
                             private=private and remaining == 0, store=remaining == 0)
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _private_file(directory, name, flags=os.O_RDONLY, replaced=False):
    for attempt in range(CREATE_RETRIES):
        try:
            fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
            break
        except FileNotFoundError:
            # Darwin can fail concurrent O_CREAT opens of one new name with ENOENT.
            if not flags & os.O_CREAT or attempt == CREATE_RETRIES - 1:
                raise
    try:
        info = os.fstat(fd)
        # A reader can hold the previous inode after an atomic replacement.
        links = (0, 1) if replaced else (1,)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink not in links):
            raise ValueError("unsafe host-action file")
        _check_acl(fd, "file")
        yield fd
    finally:
        os.close(fd)


def _read(directory, name, limit, replaced=False, *, durable=True):
    with _private_file(directory, name, replaced=replaced) as fd, os.fdopen(fd, "rb", closefd=False) as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("host-action file exceeds size limit")
    if durable:
        os.fsync(directory)  # A prior writer may have stopped after rename.
    return raw


@contextmanager
def _locked(directory, name):
    name += ".lock"
    with _private_file(directory, name, os.O_RDWR | os.O_CREAT) as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        # A replaced lock entry would let a later writer lock a different inode.
        if not os.path.samestat(os.fstat(fd), os.stat(name, dir_fd=directory, follow_symlinks=False)):
            raise ValueError("host-action lock was replaced")
        yield


def _replace(directory, name, raw):
    temporary = name + "." + os.urandom(16).hex()
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def _unique(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate host-action field or ID")
    return result


def _read_broker_record(state, ident, secret):
    try:
        raw = _read(state, "broker-" + ident + ".json", 64 << 10, replaced=True)
    except FileNotFoundError:
        return None
    record = json.loads(raw, object_pairs_hook=_unique)
    mac = record.pop("mac", None) if isinstance(record, dict) else None
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("ascii")
    expected = hmac.digest(secret, b"broker-ledger-v1\0" + payload, "sha256").hex()
    if not isinstance(mac, str) or not mac.isascii() or not hmac.compare_digest(mac, expected):
        raise ValueError("invalid legacy host-action broker record")
    return record


def _broker_scope_matches(record, ident, project):
    info = os.stat(project, follow_symlinks=False)
    return record.get("id") == ident and record.get("scope") == [project, info.st_dev, info.st_ino]


def _object_values(raw):
    """Keep the original JSON value text for fields that must remain untouched."""
    decoder = json.JSONDecoder()
    pos = raw.index("{") + 1
    values = {}
    while True:
        while raw[pos].isspace() or raw[pos] == ",":
            pos += 1
        if raw[pos] == "}":
            return values
        name, pos = decoder.raw_decode(raw, pos)
        while raw[pos].isspace() or raw[pos] == ":":
            pos += 1
        start = pos
        _, pos = decoder.raw_decode(raw, pos)
        values[name] = raw[start:pos]


class _Rows(dict):
    def __init__(self, *args):
        super().__init__(*args)
        self.apply_intents = {}
        self.preserved = {}
        self.preserved_receipts = {}
        self.receipt_metadata = {}
        self.loaded_generations = set()
        self.compact_applies = set()


def _text(value, limit, *, path=False):
    return (isinstance(value, str) and 0 < len(value) <= limit
            and not any(c in value for c in ("\0" if path else "\0\r\n")))


def _stamp(value):
    try:
        return datetime.fromisoformat(value).tzinfo == timezone.utc
    except (TypeError, ValueError):
        return False


def _requests(block):
    if (not _text(block, 8192) or len(block.encode("utf-8", "surrogatepass")) > 8192
            or not block.startswith(BLOCK_PREFIX) or not block.endswith(" -->")):
        raise ValueError("expected one bounded host-actions line")
    try:
        data = json.loads(block[len(BLOCK_PREFIX):-4], object_pairs_hook=_unique)
    except (ValueError, RecursionError):
        raise ValueError("invalid host-actions JSON") from None
    if (type(data) is not dict or data.keys() != {"v", "actions"} or type(data["v"]) is not int
            or data["v"] != 1 or type(data["actions"]) is not list or len(data["actions"]) > 16):
        raise ValueError("invalid host-actions envelope")
    requests = {}
    for item in data["actions"]:
        if (type(item) is not dict or item.keys() != {"id", "intent"}
                or type(item["id"]) is not str or not ACTION_ID.fullmatch(item["id"])
                or item["id"] in requests or type(item["intent"]) is not str or item["intent"] not in INTENTS):
            raise ValueError("invalid or duplicate host-action request")
        requests[item["id"]] = item["intent"]
    return requests


def _catalogue():
    here = Path(__file__).resolve().parent
    for name in ("kaizen-friction-catalog.json", "friction-catalog.json"):
        path = here / name
        if path.is_file():
            return {entry["id"]: entry for entry in json.loads(path.read_bytes())["actions"]}
    return {}


def _pending(generations):
    # A journaled action retains its pending receipt until reconciliation completes.
    return {ident for receipt in generations.values() for ident, state in receipt.items() if state == "pending"}


def _terminal_slots(generations):
    for generation, receipt in sorted(generations.items()):
        for ident in sorted(ident for ident, state in receipt.items() if state == "terminal"):
            yield generation, ident


class HostActions:
    def __init__(self, audits, backups, canonical_project, project_key):
        self.path = Path(audits) / "host-actions.json"
        self.friction = Path(backups) / "friction"
        self.canonical_project = canonical_project
        self.project_key = project_key

    def _scope(self, path):
        path = Path(path).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise ValueError("expected a project directory")
        return self.canonical_project(path)

    def _secret(self, create=False):
        with _directory(self.friction, create, private=True) as directory:
            name = "machine.key"
            # Called after validating the store. Separate stores can share one key.
            if create:
                with _locked(directory, name):
                    try:
                        secret = _read(directory, name, 32)
                    except FileNotFoundError:
                        secret = os.urandom(32)
                        _replace(directory, name, secret)
            else:
                secret = _read(directory, name, 32)
        if len(secret) != 32:
            raise ValueError("invalid host-action machine key")
        return secret

    def _receipt_versions(self, directory, suffix):
        try:
            versions = json.loads(_read(directory, self.path.name + suffix, RECEIPT_LIMIT,
                                        replaced=True), object_pairs_hook=_unique)
        except FileNotFoundError:
            return {}
        except (ValueError, RecursionError):
            raise ValueError("invalid host-action receipt metadata") from None
        if (not isinstance(versions, dict) or len(versions) > 2
                or any(not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(saved, dict)
                       or set(saved) - {"guarded"} != {"receipts", "apply_intents"}
                       or ("guarded" in saved and saved["guarded"] is not True)
                       or not isinstance(saved["receipts"], dict) or not isinstance(saved["apply_intents"], dict)
                       for digest, saved in versions.items())):
            raise ValueError("invalid host-action receipt metadata")
        return versions

    def _load(self, directory):
        for _ in range(CREATE_RETRIES):
            try:
                raw = _read(directory, self.path.name, STORE_LIMIT, replaced=True)
            except FileNotFoundError:
                return _Rows(), None, {}
            digest = hashlib.sha256(raw).hexdigest()
            # Read the main sidecar first. Its prior snapshot is spilled before replacement.
            versions = self._receipt_versions(directory, ".receipts")
            if digest not in versions:
                previous = self._receipt_versions(directory, ".receipts-previous")
                versions = {**previous, **versions}
            if not versions or raw == _read(directory, self.path.name, STORE_LIMIT, replaced=True):
                break
        else:
            raise ValueError("host-action store changed during read")
        matched = digest in versions
        # An older runner can update the shared v1 file without touching the sidecar.
        metadata = [versions[digest]] if matched else [saved for saved in versions.values() if not saved.get("guarded")]
        try:
            store = json.loads(raw, object_pairs_hook=_unique)
        except (ValueError, RecursionError):
            raise ValueError("invalid host-action store JSON") from None
        if (not isinstance(store, dict) or set(store) - {"receipts", "apply_intents"} != {"v", "actions"}
                or not isinstance(store.get("receipts", {}), dict)
                or not isinstance(store.get("apply_intents", {}), dict)
                or type(store["v"]) is not int or store["v"] not in (1, 2) or not isinstance(store["actions"], dict)
                or (store["v"] == 2) != bool(matched and versions[digest].get("guarded"))):
            raise ValueError("invalid host-action store format")
        guarded = store["v"] == 2
        rows = store["actions"]
        secret = self._secret() if rows else None
        skipped = set()
        for ident, row in rows.items():
            if not self._valid_row(row, check_key=False) or ident != _id(secret, *(row[k] for k in ID_FIELDS)):
                raise ValueError("invalid host-action record or machine key")
            try:
                valid_key = row["projects"] == [self.project_key(row["canonical_project"], resolved=True)]
            except UnicodeError:
                valid_key = False
            if not valid_key:
                skipped.add(ident)
        if skipped:
            print(f"host actions: skipped {len(skipped)} row(s) with unreadable project keys", file=sys.stderr)
        receipts = store.get("receipts", {})
        intents, archived = {}, {}
        for saved in metadata:
            for project, generations in saved["receipts"].items():
                if not isinstance(generations, dict):
                    raise ValueError("invalid host-action receipt metadata")
                for generation, receipt in generations.items():
                    if (not isinstance(receipt, dict)
                            or any(state not in ("terminal", COMPACT_APPLY) for state in receipt.values())):
                        raise ValueError("invalid host-action receipt metadata")
                    current = receipts.setdefault(project, {})
                    if not isinstance(current, dict):
                        raise ValueError("invalid host-action receipt scope")
                    if guarded and generation in current:
                        inline = current[generation]
                        if not isinstance(inline, dict) or inline.keys() & receipt.keys():
                            raise ValueError("conflicting host-action receipt metadata")
                        inline.update(receipt)
                        archived.setdefault(project, {})[generation] = receipt
                    elif generation not in current and (matched or all(ident in rows for ident in receipt)):
                        current[generation] = dict(receipt)
                        archived.setdefault(project, {})[generation] = receipt
            for project, generations in saved["apply_intents"].items():
                if not isinstance(generations, dict):
                    raise ValueError("invalid host-action receipt metadata")
                for generation, ids in generations.items():
                    if not isinstance(ids, list) or any(not isinstance(ident, str) for ident in ids):
                        raise ValueError("invalid host-action receipt metadata")
                    current = receipts.get(project, {})
                    if not isinstance(current, dict) or not isinstance(current.get(generation, {}), dict):
                        raise ValueError("invalid host-action receipt")
                    current = current.get(generation, {})
                    if matched and (not ids or len(set(ids)) != len(ids) or not set(ids) <= current.keys()):
                        raise ValueError("invalid host-action receipt metadata")
                    intents.setdefault(project, {}).setdefault(generation, set()).update(set(ids) & current.keys())
        for project, generations in receipts.items():
            if not (_text(project, 4096, path=True) and Path(project).is_absolute()
                    and project == os.path.normpath(project) and isinstance(generations, dict)):
                raise ValueError("invalid host-action receipt scope")
            for generation, receipt in generations.items():
                if (not _text(generation, 128) or not isinstance(receipt, dict) or len(receipt) > 16
                        or any(ident not in rows or rows[ident]["canonical_project"] != project
                               or state not in RECEIPT_STATES
                               or (state == "pending" and rows[ident]["status"] != "open")
                               for ident, state in receipt.items())):
                    raise ValueError("invalid host-action receipt")
        rows = _Rows((ident, row) for ident, row in rows.items() if ident not in skipped)
        if matched:
            rows.receipt_metadata = {digest: versions[digest]}
        elif versions:
            saved_intents = {project: {generation: sorted(ids) for generation, ids in generations.items()}
                             for project, generations in intents.items()}
            rows.receipt_metadata = {digest: dict(receipts=archived, apply_intents=saved_intents)}
        rows.loaded_generations = {(project, generation) for project, generations in receipts.items()
                                   for generation in generations}
        rows.apply_intents = intents
        for project, saved in store.get("apply_intents", {}).items():
            if project not in receipts:
                raise ValueError("invalid host-action import intents")
            if isinstance(saved, str) and re.fullmatch(r"[1-9a-f][0-9a-f]*", saved):
                slots = list(_terminal_slots(receipts[project]))
                mask = int(saved, 16)
                if mask.bit_length() > len(slots):
                    raise ValueError("invalid host-action import intents")
                for bit, (generation, ident) in enumerate(slots):
                    if mask & (1 << bit):
                        rows.apply_intents.setdefault(project, {}).setdefault(generation, set()).add(ident)
                continue
            if not isinstance(saved, dict):
                raise ValueError("invalid host-action import intents")
            for generation, ids in saved.items():
                receipt = receipts[project].get(generation, {})
                if (not isinstance(ids, list) or not ids or len(ids) > len(receipt)
                        or any(not isinstance(ident, str) or ident not in receipt for ident in ids)
                        or len(set(ids)) != len(ids) or _pending({generation: receipt}) - set(ids)):
                    raise ValueError("invalid host-action import intents")
                rows.apply_intents.setdefault(project, {})[generation] = set(ids)
        # Both pending and compact closed receipts encode their original apply intent.
        for project, generations in receipts.items():
            for generation, receipt in generations.items():
                for ident, state in receipt.items():
                    if state in ("pending", COMPACT_APPLY):
                        rows.apply_intents.setdefault(project, {}).setdefault(generation, set()).add(ident)
                    if state == COMPACT_APPLY:
                        rows.compact_applies.add((project, generation, ident))
                        receipt[ident] = "terminal"
                    elif guarded and state == "terminal" and ident in intents.get(project, {}).get(generation, ()):
                        rows.compact_applies.add((project, generation, ident))
        if skipped:
            fields = _object_values(raw.decode("utf-8"))
            row_values = _object_values(fields["actions"])
            rows.preserved = {ident: row_values[ident] for ident in skipped}
            receipt_values = _object_values(fields.get("receipts", "{}"))
            for project, generations in receipts.items():
                raw_generations = _object_values(receipt_values.get(project, "{}"))
                for generation, receipt in generations.items():
                    if skipped.intersection(receipt) and generation in raw_generations:
                        rows.preserved_receipts[(project, generation)] = raw_generations[generation]
        return rows, secret, receipts

    def _valid_row(self, row, check_key=True):
        if not isinstance(row, dict) or row.keys() - ROW_OPTIONAL != ROW_FIELDS:
            return False
        project, status, updated = row["canonical_project"], row["status"], row["updated_at"]
        return (_text(project, 4096, path=True) and Path(project).is_absolute()
                and project == os.path.normpath(project)
                and isinstance(row["projects"], list) and len(row["projects"]) == 1
                and isinstance(row["projects"][0], str)
                and (not check_key or row["projects"] == [self.project_key(project, resolved=True)])
                and _text(row["catalog_id"], 64) and CATALOG_ID.fullmatch(row["catalog_id"])
                and _text(row["selector_key"], 4096, path=True) and row["subject"] == row["selector_key"]
                and isinstance(row["evidence"], str) and len(row["evidence"]) <= EVIDENCE_LIMIT
                and status in STATES.values() and _stamp(row["first_seen"]) and _stamp(updated)
                and row["done_by"] in (("user", "verify") if status == "done" else (None,))
                and type(row.get("flaps", 0)) is int and 0 <= row.get("flaps", 0) <= 2
                and isinstance(row.get("steps", []), list)
                and all(isinstance(step, str) for step in row.get("steps", []))
                and (row.get("metric_at_done") is None or isinstance(row["metric_at_done"], dict))
                and row["eligible"] is False)

    def _save(self, directory, rows, receipts):
        # Mark preserved values before serializing, then restore their exact original JSON bytes.
        preserved = {}
        def marker(value):
            token = "__kaizen_preserved_" + os.urandom(32).hex()
            preserved[json.dumps(token)] = value
            return token

        output_rows = dict(rows)
        output_rows.update((ident, marker(value)) for ident, value in getattr(rows, "preserved", {}).items())
        output_receipts = {project: {generation: dict(receipt) for generation, receipt in generations.items()}
                           for project, generations in receipts.items()}
        for (project, generation), value in getattr(rows, "preserved_receipts", {}).items():
            receipt = output_receipts[project][generation]
            original = json.loads(value)
            if receipt == {ident: "terminal" if state == COMPACT_APPLY else state for ident, state in original.items()}:
                output_receipts[project][generation] = marker(value)
            else:
                output_receipts[project][generation] = dict(receipt, **{
                    ident: marker(raw) for ident, raw in _object_values(value).items()
                    if ident in rows.preserved})
        # Prefer the release v1 wire format when it fits without hiding receipts.
        output = {"v": 1, "actions": output_rows, "receipts": output_receipts}
        def encode(compact=False):
            text = json.dumps(output, ensure_ascii=not compact, separators=(",", ":"))
            for token, value in preserved.items():
                text = text.replace(token, value)
            return (text if compact else text + "\n").encode("utf-8", "backslashreplace")

        completed = {}
        for project, generations in receipts.items():
            for generation, receipt in generations.items():
                ids = rows.apply_intents.get(project, {}).get(generation, ())
                closed = sorted(ident for ident in ids if receipt.get(ident) == "terminal")
                if closed:
                    completed.setdefault(project, {})[generation] = closed
        compact_ids = set(rows.compact_applies)

        def compact_applies(force=False):
            for project, generations in completed.items():
                for generation, ids in generations.items():
                    receipt = output_receipts[project][generation]
                    if isinstance(receipt, dict):
                        for ident in ids:
                            slot = project, generation, ident
                            if ident not in rows.preserved and (force or slot in compact_ids):
                                receipt[ident] = COMPACT_APPLY
                                compact_ids.add(slot)

        compact_applies()
        raw = encode()
        if len(raw) > STORE_LIMIT:
            compact_applies(force=True)
            raw = encode(compact=True)

        # An old runner must reject a store whose sidecar holds any receipt entries.
        archived = {}
        excess = len(raw) - STORE_LIMIT
        for project, generations in output_receipts.items():
            if excess <= 0:
                break
            for generation, inline in list(generations.items()):
                if excess <= 0:
                    break
                if (project, generation) not in rows.loaded_generations or not isinstance(inline, dict):
                    continue
                receipt = receipts[project][generation]
                terminal = {ident: inline[ident] for ident, state in receipt.items()
                            if state == "terminal" and ident not in rows.preserved}
                if receipt and not terminal:
                    continue
                remaining = {ident: state for ident, state in inline.items() if ident not in terminal}
                # Receipt keys and states are ASCII, even in the compact encoding.
                excess -= len(json.dumps(inline, separators=(",", ":")))
                if remaining:
                    generations[generation] = remaining
                    excess += len(json.dumps(remaining, separators=(",", ":")))
                else:
                    excess -= len(json.dumps(generation, ensure_ascii=False).encode("utf-8", "backslashreplace"))
                    excess -= 1 + (len(generations) > 1)
                    del generations[generation]
                archived.setdefault(project, {})[generation] = terminal
        if archived:
            output["v"] = 2
            raw = encode(compact=True)
        if len(raw) > STORE_LIMIT:
            raise ValueError("host-action store exceeds size limit")
        for project, generations in completed.items():
            for generation, ids in list(generations.items()):
                inline = output_receipts[project].get(generation)
                if isinstance(inline, dict):
                    ids = [ident for ident in ids if inline.get(ident) != COMPACT_APPLY]
                parked = archived.get(project, {}).get(generation, {})
                ids = [ident for ident in ids if parked.get(ident) != COMPACT_APPLY]
                if ids:
                    generations[generation] = ids
                else:
                    del generations[generation]
        completed = {project: generations for project, generations in completed.items() if generations}
        metadata = dict(receipts=archived, apply_intents=completed)
        if archived:
            metadata["guarded"] = True
        digest = hashlib.sha256(raw).hexdigest()
        versions = dict(rows.receipt_metadata, **{digest: metadata})
        previous_name = self.path.name + ".receipts-previous"
        has_metadata = bool(archived or completed or rows.receipt_metadata)
        if has_metadata:
            def encode_versions(entries):
                return json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8", "backslashreplace")

            encoded = encode_versions(versions)
            if len(encoded) > RECEIPT_LIMIT:
                encoded = encode_versions({digest: metadata})
                previous = encode_versions(rows.receipt_metadata)
                if max(len(encoded), len(previous)) > RECEIPT_LIMIT:
                    raise ValueError("host-action receipt metadata exceeds size limit")
                # Spill the prior snapshot before replacing the main sidecar.
                _replace(directory, previous_name, previous)
            # Keep the previous metadata until the shared file is durably replaced.
            _replace(directory, self.path.name + ".receipts", encoded)
        _replace(directory, self.path.name, raw)
        try:
            os.unlink(previous_name, dir_fd=directory)
        except FileNotFoundError:
            pass
        else:
            os.fsync(directory)
        rows.receipt_metadata = {digest: metadata} if has_metadata else {}
        rows.loaded_generations = {(project, generation) for project, generations in receipts.items()
                                   for generation in generations}
        rows.compact_applies = compact_ids

    def _new_row(self, identity, evidence, stamp):
        project, catalog_id, selector = identity
        return dict(canonical_project=project, catalog_id=catalog_id, selector_key=selector,
                    subject=selector, projects=[self.project_key(project, resolved=True)], status="open",
                    first_seen=stamp, updated_at=stamp, evidence=evidence[:EVIDENCE_LIMIT], eligible=False, done_by=None)

    def action_id(self, project, catalog_id, value, *, path=False, allowed=()):
        return self.record(project, catalog_id, value, path=path, allowed=allowed)

    def record(self, project, catalog_id, value, evidence=None, *, path=False, allowed=()):
        """Return a candidate ID and record it ineligible when evidence is supplied."""
        if evidence is not None and not isinstance(evidence, str):
            raise ValueError("invalid host-action evidence")
        if path:
            if not isinstance(value, (str, os.PathLike)):
                raise ValueError("invalid action path selector")
            scope, target = self.canonical_project(project, selector=value)
            value = str(target)
        else:
            if not _text(value, 4096) or isinstance(allowed, str) or value not in allowed:
                raise ValueError("unknown action selector")
            scope = self._scope(project)
        identity = _identity(scope, catalog_id, value)
        with _directory(self.path.parent, create=True) as directory, _locked(directory, self.path.name):
            rows, secret, receipts = self._load(directory)
            ident = _id(secret or self._secret(create=True), *identity)
            if ident in getattr(rows, "preserved", {}):
                raise ValueError("unavailable host-action ID")
            if ident in rows and identity != tuple(rows[ident][k] for k in ID_FIELDS):
                raise ValueError("host-action ID collision")
            if evidence is not None and ident not in rows:
                stamp = datetime.now(timezone.utc).isoformat()
                rows[ident] = self._new_row(identity, evidence, stamp)
                self._save(directory, rows, receipts)
            return ident

    def scoped(self, project):
        project = str(self._scope(project))
        with ExitStack() as stack:
            try:
                directory = stack.enter_context(_directory(self.path.parent))
            except FileNotFoundError:
                return []
            rows, _, receipts = self._load(directory)
        pending = _pending(receipts.get(project, {}))
        return [dict(row, id=ident, **({"pending": True} if ident in pending else {}))
                for ident, row in sorted(rows.items())
                if row["canonical_project"] == project]

    def _prune_receipts(self, rows, project, generations, generation):
        current = re.fullmatch(r"(?:interactive|scheduled):([0-9]{20})", generation)
        if current is None:
            return
        acknowledged = ""
        key = self.project_key(project, resolved=True)
        try:
            with _directory(self.friction, private=True) as directory:
                state = json.loads(_read(directory, "prepare-" + key + ".json", STORE_LIMIT), object_pairs_hook=_unique)
            if (state["project"] == project and type(state["v"]) is int and state["v"] == 1
                    and re.fullmatch(r"[0-9]{20}", state["acknowledged_generation"])):
                acknowledged = state["acknowledged_generation"]
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            pass
        for name, receipt in list(generations.items()):
            old = re.fullmatch(r"(?:(?:interactive|scheduled):([0-9]{20})|scheduled-local:([0-9]{20}):.+)", name)
            if old is None or (project, name) in rows.preserved_receipts:
                continue
            number = old[1] or old[2]
            # A superseded interactive generation can no longer be acknowledged.
            if (number < current[1] and "pending" not in receipt.values()
                    and (not receipt or number <= acknowledged or name.startswith("interactive:"))):
                del generations[name]
                rows.apply_intents.get(project, {}).pop(name, None)

    def _legacy_applies(self, project, generation, ids, secret):
        if not ids or not re.fullmatch(r"scheduled:[0-9]{20}", generation):
            return set()
        applied = set()
        with _directory(self.friction, private=True) as state:
            for ident in ids:
                record = _read_broker_record(state, ident, secret)
                if (record is not None and record.get("operation") == "host-fix"
                        and generation == f"scheduled:{record.get('generation')}"):
                    if not _broker_scope_matches(record, ident, project):
                        raise ValueError("legacy host-action broker scope changed")
                    applied.add(ident)
        return applied

    def _legacy_marker_applies(self, project, generation, ids, secret):
        if not ids:
            return set()
        applied = set()
        with _directory(self.friction, private=True) as state:
            for ident in ids:
                try:
                    record = _read_broker_record(state, ident, secret)
                except (OSError, ValueError, RecursionError):
                    record = None
                if record is not None and record.get("operation") == "host-fix":
                    if (generation != f"scheduled:{record.get('generation')}"
                            or not _broker_scope_matches(record, ident, project)):
                        continue
                applied.add(ident)
        return applied

    def import_actions(self, block, frozen_map, project, generation):
        """Use the private map's identity, comparable evidence text and mode-filtered intents."""
        requests = _requests(block)
        if not _text(generation, 128):
            raise ValueError("invalid host-action generation")
        original_project = project
        project = str(self._scope(project))
        secret = self._secret() if requests else None
        candidates = {}
        for ident, intent in requests.items():
            row = frozen_map.get(ident)
            identity = tuple(row.get(field) for field in ID_FIELDS) if isinstance(row, dict) else ()
            if (not identity or identity[0] != project or _identity(*identity) != identity
                    or _id(secret, *identity) != ident or not isinstance(row.get("intents"), (tuple, list))
                    or intent not in row["intents"] or not _text(row.get("evidence"), EVIDENCE_LIMIT)):
                raise ValueError("unavailable host-action ID or intent for this project")
            candidates[ident] = identity, row["evidence"]
        entries = _catalogue() if candidates else {}
        if any(identity[1] not in entries for identity, _ in candidates.values()):
            raise ValueError("host-action catalogue entry is unavailable")
        receipt = {ident: INTENTS[intent] for ident, intent in requests.items()}
        with _directory(self.path.parent, create=True) as directory, _locked(directory, self.path.name):
            if str(self._scope(original_project)) != project:
                raise ValueError("host-action scope changed; try again")
            rows, stored_secret, receipts = self._load(directory)
            if candidates and secret != (stored_secret or self._secret()):
                raise ValueError("host-action machine key changed")
            generations = receipts.setdefault(project, {})
            if generation in generations:
                saved = generations[generation]
                if saved.keys() != receipt.keys():
                    raise ValueError("different requests for an imported host-action generation")
                applied = set(rows.apply_intents.get(project, {}).get(generation, ()))
                requested_apply = _pending({generation: receipt})
                marker_retries = set()
                if (all(state == "terminal" for state in saved.values())
                        and re.fullmatch(r"scheduled:[0-9]{20}", generation)):
                    for ident in saved.keys() - applied:
                        row = rows.get(ident, {})
                        # The old marker broker omitted the metric field that verify() always wrote.
                        # A row shared by multiple generations still needs a signed reservation.
                        if (row.get("catalog_id") == "linux-localsearch" and row.get("done_by") == "verify"
                                and "metric_at_done" not in row and row["evidence"] == candidates[ident][1]
                                and not any(ident in other for name, other in generations.items() if name != generation)):
                            marker_retries.add(ident)
                applied.update(self._legacy_marker_applies(project, generation, marker_retries, stored_secret))
                legacy_ids = saved.keys() - applied - marker_retries
                applied.update(self._legacy_applies(project, generation, legacy_ids, stored_secret))
                if applied != requested_apply:
                    raise ValueError("different requests for an imported host-action generation")
                return saved
            pending = _pending(generations)
            stamp = datetime.now(timezone.utc).isoformat()
            for ident, (identity, evidence) in candidates.items():
                if ident in getattr(rows, "preserved", {}):
                    raise ValueError("unavailable host-action ID")
                row = rows.setdefault(ident, self._new_row(identity, evidence, stamp))
                if ident not in pending and row["status"] != "dismissed":
                    if row["status"] == "done" and row["evidence"] and row["evidence"] != evidence:
                        row.update(status="open", done_by=None, flaps=min(2, row.get("flaps", 0) + 1))
                    if row["status"] == "open":
                        row.update(evidence=evidence, updated_at=stamp, steps=entries[identity[1]]["steps"])
                if receipt[ident] == "pending" and (row["status"] != "open" or row.get("flaps", 0) >= 2):
                    raise ValueError("host action requires manual resolution")
            generations[generation] = receipt
            if apply_ids := _pending({generation: receipt}):
                rows.apply_intents.setdefault(project, {})[generation] = apply_ids
            self._prune_receipts(rows, project, generations, generation)
            self._save(directory, rows, receipts)
        return receipt

    def _metric(self, row, entry):
        metric = entry.get("metric", {})
        if metric.get("kind") != "probe":
            return None
        folder = self.path.parent / "projects" / row["projects"][0]
        try:
            with _directory(folder) as directory:
                newest = max(name for name in os.listdir(directory)
                             if name.startswith("host-probe-") and name.endswith(".json"))
                proof = json.loads(_read(directory, newest, STORE_LIMIT, durable=False), object_pairs_hook=_unique)
            if (proof.get("project") != row["canonical_project"] or type(proof.get("v")) is not int
                    or proof["v"] != 1 or not _stamp(proof.get("generated_at"))):
                return None
            value = proof
            for part in metric["key"].split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if type(value) in (int, bool) or (isinstance(value, list) and all(isinstance(s, str) for s in value)):
                return dict(metric, value=value, measured_at=proof["generated_at"])
        except (OSError, ValueError, AttributeError, RecursionError):
            pass
        return None

    def _localsearch_excluded(self, project, selector):
        runner = self.canonical_project.__globals__
        (scope,), _ = runner["discover"](None, None, {}, [project])
        if scope.unknown or scope.canonical != project or selector.resolve() != selector:
            return None
        relative = selector.relative_to(project)
        found = False
        for anchor in scope.anchors:
            target = anchor / relative
            if not target.exists():
                continue
            if target.resolve(strict=True) != target or not target.is_dir():
                return None
            owner = runner["enrolled_project"](target)
            if owner is not None and self._scope(owner) != project:
                return None
            try:
                if not stat.S_ISREG((target / ".nomedia").lstat().st_mode):
                    return False
            except FileNotFoundError:
                return False
            found = True
        return True if found else None

    def _probe(self, project, row):
        name, selector = row["catalog_id"], Path(row["selector_key"])
        try:
            if name == "inotify-limit" and sys.platform.startswith("linux"):
                here = Path(__file__).resolve().parent
                tool = here / "kaizen-host-probe"
                probe = runpy.run_path(str(tool if tool.is_file() else here / "host-probe"))
                check = probe["Probe"](Path(project), "linux", Path("/proc"), probe["sibling"](
                    "kaizen-friction-catalog.json", "friction-catalog.json"))
                value = check.read_proc("sys/fs/inotify/max_user_watches")
                files = check.git(project, "ls-files", "-z")
                if value is not None and files is not None:
                    return value >= 2 * min(500000, files.count("\0")), dict(
                        kind="probe", key="facts.inotify_max_user_watches", value=value)
            if name == "linux-localsearch" and sys.platform.startswith("linux") and selector.is_absolute():
                return self._localsearch_excluded(Path(project), selector), None
            if name == "timemachine-output" and sys.platform == "darwin" and selector.is_absolute():
                if self.canonical_project(project, selector=selector) != (Path(project), selector):
                    return None, None
                check = subprocess.run(["/usr/bin/tmutil", "isexcluded", str(selector)], capture_output=True,
                                       stdin=subprocess.DEVNULL, timeout=5)
                if check.returncode == 0 and re.match(rb"^\[(Excluded|Included)\](?:\s|$)", check.stdout):
                    return check.stdout.startswith(b"[Excluded]"), None
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError, subprocess.TimeoutExpired):
            pass
        return None, None

    def verify(self, project):
        results, passed = {}, {}
        for row in self.scoped(project):
            if row["status"] != "open":
                continue
            ident = row.pop("id")
            if row.get("pending"):
                results[ident] = "pending"
                continue
            success, metric = (None, None) if row.get("flaps", 0) >= 2 else self._probe(row["canonical_project"], row)
            results[ident] = "unavailable" if success is None else "open"
            if success:
                passed[ident] = row, metric
        if passed:
            entries = _catalogue()
            with _directory(self.path.parent, create=True) as directory, _locked(directory, self.path.name):
                rows, _, receipts = self._load(directory)
                project = str(self._scope(project))
                pending = _pending(receipts.get(project, {}))
                for ident, (snapshot, metric) in passed.items():
                    if ident in pending:
                        results[ident] = "pending"
                    elif snapshot["canonical_project"] == project and rows.get(ident) == snapshot:
                        entry = entries.get(snapshot["catalog_id"], {})
                        rows[ident].update(status="done", done_by="verify",
                                           updated_at=datetime.now(timezone.utc).isoformat(),
                                           metric_at_done=metric if metric is not None else self._metric(snapshot, entry))
                        results[ident] = "done"
                if "done" in results.values():
                    self._save(directory, rows, receipts)
        return results

    def mark(self, project, ident, command):
        original_project = project
        project = str(self._scope(project))
        status = STATES[command]
        with _directory(self.path.parent, create=True) as directory, _locked(directory, self.path.name):
            if str(self._scope(original_project)) != project:
                raise ValueError("host-action scope changed; try again")
            rows, _, receipts = self._load(directory)
            row = rows.get(ident)
            if row is None or row["canonical_project"] != project:
                raise ValueError("unknown host-action ID in this project")
            if row["status"] == status:
                return
            if ident in _pending(receipts.get(project, {})):
                raise ValueError("host action has pending work")
            row.update(status=status, updated_at=datetime.now(timezone.utc).isoformat(),
                       done_by="user" if status == "done" else None)
            if status == "done":
                row["metric_at_done"] = self._metric(row, _catalogue().get(row["catalog_id"], {}))
            self._save(directory, rows, receipts)
