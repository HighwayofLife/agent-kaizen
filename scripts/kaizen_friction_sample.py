"""Best-effort Claude Bash sampler for an asynchronous PostToolUse command."""

from contextlib import ExitStack, contextmanager
import ctypes
from datetime import datetime, timezone
import errno
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import stat
import sys
import time

try:
    import fcntl
except ImportError:
    fcntl = None


INPUT_LIMIT = 1024 * 1024
DAY_LIMIT = 5 * 1024 * 1024
ROW_LIMIT = 4096
BUDGET = 0.250
LOCK_RETRY_BUDGET = 0.020
LOCK_NAME = ".lock"
NOFOLLOW = os.O_NOFOLLOW | os.O_NONBLOCK if fcntl is not None else 0


def host():
    override = os.getenv("KAIZEN_HOST")
    if override in ("claude", "copilot", "codex"):
        return override
    if os.getenv("COPILOT_PLUGIN_ROOT"):
        return "copilot"
    return "codex" if os.getenv("PLUGIN_ROOT") else "claude"


def decode(data):
    # Python 3.9 may spend seconds converting a single decimal integer.
    return json.loads(data.decode("utf-8"), parse_int=lambda token: int(token) if len(token) <= 33 else None)


def enabled(home):
    try:
        stream = open(home / "agent-kaizen.json", "rb",
                      opener=lambda path, flags: os.open(path, flags | os.O_NONBLOCK))
    except FileNotFoundError:
        return True
    with stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            return False
        data = stream.read(INPUT_LIMIT + 1)
    if len(data) > INPUT_LIMIT:
        return False
    config = decode(data)
    return (isinstance(config, dict) and config.get("enabled") is not False
            and config.get("frictionSampler") != "off")


def read_event(fd, deadline):
    data = bytearray()
    while len(data) <= INPUT_LIMIT:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            return None
        chunk = os.read(fd, min(65536, INPUT_LIMIT + 1 - len(data)))
        if not chunk:
            return decode(data)
        data.extend(chunk)
    return None


def sample_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) else ""


def metrics():
    try:
        load = os.getloadavg()[0]
    except OSError:
        load = math.nan
    return str(load) if math.isfinite(load) and load >= 0 else "", str(os.cpu_count() or "")


def has_extended_acl(fd):
    # Darwin's fd-based ACL API checks the pinned inode without spawning a subprocess.
    libc = ctypes.CDLL(None, use_errno=True)
    get_acl = libc.acl_get_fd_np
    get_acl.argtypes = (ctypes.c_int, ctypes.c_int)
    get_acl.restype = ctypes.c_void_p
    free_acl = libc.acl_free
    free_acl.argtypes = (ctypes.c_void_p,)
    acl = get_acl(fd, 0x100)  # ACL_TYPE_EXTENDED in sys/acl.h
    if acl:
        free_acl(acl)
        return True
    error = ctypes.get_errno()
    if error != errno.ENOENT:  # Darwin returns ENOENT for an inode without an ACL.
        raise OSError(error, "cannot verify sample ACL")
    return False


@contextmanager
def storage(path, deadline):
    """Pin every directory without following symlinks, including in AUDIT_DIR."""
    if not path.is_absolute():
        path = Path.cwd() / path
    flags = os.O_RDONLY | os.O_DIRECTORY | NOFOLLOW
    uid = os.geteuid()
    parts = path.parts[1:]
    with ExitStack() as stack:
        fd = os.open(path.anchor, flags)
        stack.callback(os.close, fd)
        for part in parts:
            if part == ".." or time.monotonic() >= deadline:
                raise ValueError("invalid or expired sample path")
            try:
                child = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass  # Another sampler created it first.
                child = os.open(part, flags, dir_fd=fd)
            stack.callback(os.close, child)
            info = os.fstat(child)
            if (info.st_uid not in (0, uid)
                    or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)):
                raise PermissionError("unsafe sample ancestor")
            fd = child
        info = os.fstat(fd)
        if info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
            raise PermissionError("unsafe sample directory")
        if sys.platform == "darwin" and has_extended_acl(fd):
            raise PermissionError("extended ACL on sample directory")
        yield fd


def file_info(directory, name, fd):
    info = os.fstat(fd)
    current = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
            or not os.path.samestat(info, current)):
        raise PermissionError("unsafe sample file")
    return info


@contextmanager
def state_file(directory, name, flags):
    fd = os.open(name, flags | os.O_CREAT | NOFOLLOW, 0o600, dir_fd=directory)
    try:
        yield fd
    finally:
        os.close(fd)


def lock_exclusive(fd, deadline):
    retry_until = min(deadline, time.monotonic() + LOCK_RETRY_BUDGET)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as error:
            remaining = retry_until - time.monotonic()
            if error.errno not in (errno.EAGAIN, errno.EACCES) or remaining <= 0:
                raise
            time.sleep(min(0.001, remaining))


def repair_tail(fd, size):
    """Discard any incomplete row left by an interrupted writer, under both locks."""
    end = size
    while end:
        start = max(0, end - ROW_LIMIT)
        tail = os.pread(fd, end - start, start)
        if len(tail) != end - start:
            raise OSError("sample file changed during tail check")
        newline = tail.rfind(b"\n")
        if newline >= 0:
            end = start + newline + 1
            break
        end = start
    if end < size:
        os.ftruncate(fd, end)
    return end


def append(path, day, row, deadline):
    if len(row) >= ROW_LIMIT or time.monotonic() >= deadline:
        return
    with storage(path, deadline) as directory:
        with state_file(directory, LOCK_NAME, os.O_RDWR) as lock:
            file_info(directory, LOCK_NAME, lock)
            lock_exclusive(lock, deadline)
            name = day + ".tsv"
            with state_file(directory, name, os.O_RDWR | os.O_APPEND) as fd:
                # Keep cap checks and rollback serialized even if the lock name is replaced.
                lock_exclusive(fd, deadline)
                file_info(directory, LOCK_NAME, lock)
                size = file_info(directory, name, fd).st_size
                if sys.platform == "darwin" and has_extended_acl(fd):
                    raise PermissionError("extended ACL on sample file")
                if size > DAY_LIMIT:
                    return
                size = repair_tail(fd, size)
                if size + len(row) <= DAY_LIMIT and time.monotonic() < deadline:
                    if os.write(fd, row) != len(row):
                        os.ftruncate(fd, size)  # Roll back a partial row before unlocking.


def sample(fd):
    deadline = time.monotonic() + BUDGET
    if fcntl is None or host() != "claude":
        return
    home = Path(os.getenv("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
    if not enabled(home):
        return
    event = read_event(fd, deadline)
    if (not isinstance(event, dict) or event.get("hook_event_name") != "PostToolUse"
            or event.get("tool_name") != "Bash" or event.get("is_interrupt") is True):
        return
    duration = event.get("duration_ms")
    duration_ms = ""
    if type(duration) in (int, float) and 0 <= duration < 10**32:
        duration_ms = str(int(duration))
    load, cores = metrics()
    ms = time.time_ns() // 1_000_000
    day = datetime.fromtimestamp(ms // 1000, timezone.utc).date().isoformat()
    fields = (str(ms), sample_id(event.get("session_id")), sample_id(event.get("tool_use_id")),
              duration_ms, load, cores)
    audits = Path(os.getenv("AUDIT_DIR") or home / "audits").expanduser()
    append(audits / "samples", day, ("\t".join(fields) + "\n").encode("ascii"), deadline)


def deadline_expired(_signum, _frame):
    raise RuntimeError("sampler deadline expired")


def main():
    if fcntl is None:
        return
    previous = signal.signal(signal.SIGALRM, deadline_expired)
    try:
        try:
            signal.setitimer(signal.ITIMER_REAL, BUDGET)
            sample(sys.stdin.fileno())
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    except (OSError, ValueError, RuntimeError):
        pass
    finally:
        signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    main()
