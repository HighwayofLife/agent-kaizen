"""Machine-local identity and manual state for scoped host actions."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import tempfile

try:
    import fcntl
except ImportError:
    fcntl = None

STORE_LIMIT = 1024 * 1024
EVIDENCE_LIMIT = 500
STATES = {"done": "done", "dismiss": "dismissed", "reopen": "open"}
CATALOG_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
ROW_FIELDS = set("canonical_project catalog_id selector_key subject projects status first_seen updated_at "
                 "evidence eligible done_by".split())
ID_FIELDS = ("canonical_project", "catalog_id", "selector_key")


def _identity(scope, catalog_id, value, path, allowed):
    """Use an in-scope path, a closed literal, or a validated redacted flag key."""
    if path:
        target = (scope / value).resolve(strict=True)
        if not target.is_relative_to(scope):
            raise ValueError("action target is outside the project")
        value = str(target)
    elif not isinstance(value, str) or isinstance(allowed, str) or value not in allowed:
        raise ValueError("unknown action selector")
    if not (_text(str(scope), 4096) and _text(value, 4096)
            and _text(catalog_id, 64) and CATALOG_ID.fullmatch(catalog_id)):
        raise ValueError("invalid host-action identity")
    return str(scope), catalog_id, value


def _id(secret, project, catalog_id, selector):
    payload = json.dumps([1, project, catalog_id, selector], ensure_ascii=True, separators=(",", ":"))
    return "fa1_" + hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _directory(path, create=False, private=False):
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    mask = 0o077 if private else 0o022
    if (not stat.S_ISDIR(info.st_mode) or (hasattr(os, "geteuid") and
            (info.st_uid != os.geteuid() or info.st_mode & mask))):
        raise ValueError("unsafe host-action directory")


@contextmanager
def _private_file(path, flags=os.O_RDONLY):
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "geteuid"):
        path.lstat()  # Preserve the missing-file case on unsupported platforms.
        raise ValueError("private host-action files are unavailable")
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        # A reader can hold the previous inode after an atomic replacement.
        links = (0, 1) if flags == os.O_RDONLY else (1,)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink not in links):
            raise ValueError("unsafe host-action file")
        yield fd
    finally:
        os.close(fd)


def _read(path, limit):
    with _private_file(path) as fd, os.fdopen(fd, "rb", closefd=False) as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("host-action file exceeds size limit")
    return raw


@contextmanager
def _locked(path):
    if fcntl is None:
        raise ValueError("host-action writes require file locking")
    _directory(path.parent, create=True)
    with _private_file(path.with_name(path.name + ".lock"), os.O_RDWR | os.O_CREAT) as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield


def _replace(path, raw):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _unique(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate host-action field or ID")
    return result


def _text(value, limit):
    return isinstance(value, str) and 0 < len(value) <= limit and not any(c in value for c in "\0\r\n")


def _stamp(value):
    try:
        return datetime.fromisoformat(value).tzinfo == timezone.utc
    except (TypeError, ValueError):
        return False


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
        _directory(self.friction.parent, create)
        _directory(self.friction, create, private=True)
        path = self.friction / "machine.key"
        if create:
            # Called after validating the store. Separate stores can share one key.
            with _locked(path):
                if not os.path.lexists(path):
                    _replace(path, os.urandom(32))
        secret = _read(path, 32)
        if len(secret) != 32:
            raise ValueError("invalid host-action machine key")
        return secret

    def _load(self):
        try:
            _directory(self.path.parent)
            raw = _read(self.path, STORE_LIMIT)
        except FileNotFoundError:
            return {}, None
        try:
            store = json.loads(raw, object_pairs_hook=_unique)
        except (ValueError, RecursionError):
            raise ValueError("invalid host-action store JSON") from None
        if (not isinstance(store, dict) or set(store) != {"v", "actions"}
                or type(store["v"]) is not int or store["v"] != 1 or not isinstance(store["actions"], dict)):
            raise ValueError("invalid host-action store format")
        rows = store["actions"]
        secret = self._secret() if rows else None
        for ident, row in rows.items():
            if not self._valid_row(row) or ident != _id(secret, *(row[k] for k in ID_FIELDS)):
                raise ValueError("invalid host-action record or machine key")
        return rows, secret

    def _valid_row(self, row):
        if not isinstance(row, dict) or row.keys() != ROW_FIELDS:
            return False
        project, status, updated = row["canonical_project"], row["status"], row["updated_at"]
        return (_text(project, 4096) and Path(project).is_absolute()
                and project == os.path.normpath(project)
                and row["projects"] == [self.project_key(project, resolved=True)]
                and _text(row["catalog_id"], 64) and CATALOG_ID.fullmatch(row["catalog_id"])
                and _text(row["selector_key"], 4096) and row["subject"] == row["selector_key"]
                and isinstance(row["evidence"], str) and len(row["evidence"]) <= EVIDENCE_LIMIT
                and status in STATES.values() and _stamp(row["first_seen"]) and _stamp(updated)
                and row["done_by"] == ("user" if status == "done" else None)
                and row["eligible"] is False)

    def _save(self, rows):
        raw = (json.dumps({"v": 1, "actions": rows}, separators=(",", ":")) + "\n").encode("ascii")
        if len(raw) > STORE_LIMIT:
            raise ValueError("host-action store exceeds size limit")
        _replace(self.path, raw)

    def action_id(self, project, catalog_id, value, *, path=False, allowed=()):
        return self.record(project, catalog_id, value, path=path, allowed=allowed)

    def record(self, project, catalog_id, value, evidence=None, *, path=False, allowed=()):
        """Return a candidate ID and record it ineligible when evidence is supplied."""
        if evidence is not None and not isinstance(evidence, str):
            raise ValueError("invalid host-action evidence")
        identity = _identity(self._scope(project), catalog_id, value, path, allowed)
        project, catalog_id, selector = identity
        with _locked(self.path):
            rows, secret = self._load()
            ident = _id(secret or self._secret(create=True), *identity)
            if ident in rows and identity != tuple(rows[ident][k] for k in ID_FIELDS):
                raise ValueError("host-action ID collision")
            if evidence is not None and ident not in rows:
                stamp = datetime.now(timezone.utc).isoformat()
                rows[ident] = dict(canonical_project=project, catalog_id=catalog_id, selector_key=selector,
                                   subject=selector, projects=[self.project_key(project, resolved=True)], status="open",
                                   first_seen=stamp, updated_at=stamp, evidence=evidence[:EVIDENCE_LIMIT],
                                   eligible=False, done_by=None)
                self._save(rows)
            return ident

    def scoped(self, project):
        project = str(self._scope(project))
        rows, _ = self._load()
        return [dict(row, id=ident) for ident, row in sorted(rows.items())
                if row["canonical_project"] == project]

    def mark(self, project, ident, command):
        project = str(self._scope(project))
        status = STATES[command]
        with _locked(self.path):
            rows, _ = self._load()
            row = rows.get(ident)
            if row is None or row["canonical_project"] != project:
                raise ValueError("unknown host-action ID in this project")
            if row["status"] == status:
                return
            row.update(status=status, updated_at=datetime.now(timezone.utc).isoformat(),
                       done_by="user" if status == "done" else None)
            self._save(rows)
