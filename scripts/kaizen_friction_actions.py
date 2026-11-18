"""Machine-local identity and manual state for scoped host actions."""
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys

try:
    import fcntl
except ImportError:
    fcntl = None

STORE_LIMIT = 1024 * 1024
EVIDENCE_LIMIT = 500
CREATE_RETRIES = 100
STATES = {"done": "done", "dismiss": "dismissed", "reopen": "open"}
CATALOG_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
ROW_FIELDS = set("canonical_project catalog_id selector_key subject projects status first_seen updated_at "
                 "evidence eligible done_by".split())
ID_FIELDS = ("canonical_project", "catalog_id", "selector_key")


def _identity(scope, catalog_id, value):
    if not (_text(str(scope), 4096) and _text(value, 4096)
            and _text(catalog_id, 64) and CATALOG_ID.fullmatch(catalog_id)):
        raise ValueError("invalid host-action identity")
    return str(scope), catalog_id, value


def _id(secret, project, catalog_id, selector):
    payload = json.dumps([1, project, catalog_id, selector], ensure_ascii=True, separators=(",", ":"))
    return "fa1_" + hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _has_extended_acl(fd):
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
        free_acl(acl)
        return True
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


def _read(directory, name, limit, replaced=False):
    with _private_file(directory, name, replaced=replaced) as fd, os.fdopen(fd, "rb", closefd=False) as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("host-action file exceeds size limit")
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

    def _load(self, directory):
        try:
            raw = _read(directory, self.path.name, STORE_LIMIT, replaced=True)
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

    def _save(self, directory, rows):
        raw = (json.dumps({"v": 1, "actions": rows}, separators=(",", ":")) + "\n").encode("ascii")
        if len(raw) > STORE_LIMIT:
            raise ValueError("host-action store exceeds size limit")
        _replace(directory, self.path.name, raw)

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
            if not isinstance(value, str) or isinstance(allowed, str) or value not in allowed:
                raise ValueError("unknown action selector")
            scope = self._scope(project)
        identity = _identity(scope, catalog_id, value)
        project, catalog_id, selector = identity
        with _directory(self.path.parent, create=True) as directory, _locked(directory, self.path.name):
            rows, secret = self._load(directory)
            ident = _id(secret or self._secret(create=True), *identity)
            if ident in rows and identity != tuple(rows[ident][k] for k in ID_FIELDS):
                raise ValueError("host-action ID collision")
            if evidence is not None and ident not in rows:
                stamp = datetime.now(timezone.utc).isoformat()
                rows[ident] = dict(canonical_project=project, catalog_id=catalog_id, selector_key=selector,
                                   subject=selector, projects=[self.project_key(project, resolved=True)], status="open",
                                   first_seen=stamp, updated_at=stamp, evidence=evidence[:EVIDENCE_LIMIT],
                                   eligible=False, done_by=None)
                self._save(directory, rows)
            return ident

    def scoped(self, project):
        project = str(self._scope(project))
        with ExitStack() as stack:
            try:
                directory = stack.enter_context(_directory(self.path.parent))
            except FileNotFoundError:
                return []
            rows, _ = self._load(directory)
        return [dict(row, id=ident) for ident, row in sorted(rows.items())
                if row["canonical_project"] == project]

    def mark(self, project, ident, command):
        project = str(self._scope(project))
        status = STATES[command]
        with _directory(self.path.parent, create=True) as directory, _locked(directory, self.path.name):
            rows, _ = self._load(directory)
            row = rows.get(ident)
            if row is None or row["canonical_project"] != project:
                raise ValueError("unknown host-action ID in this project")
            if row["status"] == status:
                return
            row.update(status=status, updated_at=datetime.now(timezone.utc).isoformat(),
                       done_by="user" if status == "done" else None)
            self._save(directory, rows)
