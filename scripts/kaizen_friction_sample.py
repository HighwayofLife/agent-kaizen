"""Best-effort Claude Bash sampler for an asynchronous PostToolUse command."""

from contextlib import ExitStack, contextmanager
import ctypes
from datetime import datetime, timezone
import errno
import hashlib
from heapq import nlargest
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
PROCESS_INTERVAL_NS = 300_000_000_000
PROCESS_QUERY_BUDGET = 0.050
PROCESS_LIMIT = 256 * 1024
CATALOGUE_LIMIT = 64 * 1024
PROCESS_COMMAND = ("/bin/ps", "-A", "-ww", "-o", "pcpu=,comm=")
CANCEL_SIGNALS = (signal.SIGALRM, signal.SIGTERM, signal.SIGINT) if fcntl is not None else ()
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


def read_bounded(fd, deadline, limit, cancelled=None):
    data = bytearray()
    while len(data) <= limit:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or (cancelled and cancelled()):
            return None
        if not select.select([fd], [], [], min(remaining, 0.005) if cancelled else remaining)[0]:
            continue
        chunk = os.read(fd, min(65536, limit + 1 - len(data)))
        if not chunk:
            return bytes(data)
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


def boot_identity():
    """Read a boot identifier without launching a synchronous subprocess."""
    try:
        if sys.platform == "darwin":
            class Timeval(ctypes.Structure):
                _fields_ = [("seconds", ctypes.c_long), ("microseconds", ctypes.c_int)]
            value = Timeval()
            size = ctypes.c_size_t(ctypes.sizeof(value))
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.sysctlbyname(b"kern.boottime", ctypes.byref(value), ctypes.byref(size), None, 0):
                return None
            identity = (str(value.seconds) + ":" + str(value.microseconds)).encode("ascii")
        else:
            with open("/proc/sys/kernel/random/boot_id", "rb") as stream:
                identity = stream.read(129).strip()
            if not identity or len(identity) > 128:
                return None
        return hashlib.sha256(identity).digest()[:16]
    except (OSError, AttributeError, ValueError):
        return None


def claim_process(lock):
    # Unknown boot identity fails open rather than persisting an ambiguous stamp.
    boot = boot_identity()
    previous = os.pread(lock, 25, 0)
    now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    if boot is not None and len(previous) == 24 and previous[:16] == boot:
        stamp = int.from_bytes(previous[16:], "big")
        if now >= stamp and now - stamp < PROCESS_INTERVAL_NS:
            return False
    if sys.platform == "darwin" and has_extended_acl(lock):
        return False
    if boot is None:
        os.ftruncate(lock, 0)
        return True
    record = boot + now.to_bytes(8, "big")
    claimed = os.pwrite(lock, record, 0) == len(record)
    os.ftruncate(lock, len(record) if claimed else 0)
    return claimed


def append(path, day, row, deadline, want_process=False, process_min_size=32):
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
                    elif (want_process and size + len(row) + process_min_size <= DAY_LIMIT
                          and deadline - time.monotonic() >= PROCESS_QUERY_BUDGET):
                        file_info(directory, LOCK_NAME, lock)
                        return claim_process(lock)


def sibling(*names):
    here = Path(__file__).resolve().parent
    return next((here / name for name in names if (here / name).is_file()), here / names[-1])


def catalogue_names():
    path = sibling("kaizen-friction-catalog.json", "friction-catalog.json")
    with open(path, "rb", opener=lambda name, flags: os.open(name, flags | os.O_NONBLOCK)) as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            return set()
        data = stream.read(CATALOGUE_LIMIT + 1)
    catalog = decode(data) if len(data) <= CATALOGUE_LIMIT else None
    if (not isinstance(catalog, dict) or type(catalog.get("v")) is not int or catalog["v"] != 1
            or not isinstance(catalog.get("processes"), dict)):
        return set()
    names = set()
    for spec in catalog["processes"].values():
        if not isinstance(spec, dict) or not isinstance(spec.get("names"), list):
            return set()
        # A wildcard match could disclose a private suffix chosen by another process.
        names.update(name.encode("ascii") for name in spec["names"]
                     if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name))
    return names


def wait_for_query(pid, deadline, cancelled=lambda: False):
    while not cancelled():
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            return status
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(0.001, remaining))


def query_processes(deadline):
    # Leave part of the worker's budget to kill and reap a timed-out query.
    query_deadline = deadline - LOCK_RETRY_BUDGET
    if time.monotonic() >= query_deadline:
        return None
    cancelled = False

    def cancel(_signum, _frame):
        # Raising here could lose the pid at spawn or interrupt teardown.
        nonlocal cancelled
        cancelled = True

    with ExitStack() as stack:
        for sig in CANCEL_SIGNALS:
            stack.callback(signal.signal, sig, signal.signal(sig, cancel))
        reader, writer = os.pipe()
        stack.callback(os.close, reader)
        pid = None
        try:
            try:
                if cancelled or time.monotonic() >= query_deadline:
                    return None
                actions = [(os.POSIX_SPAWN_DUP2, writer, 1),
                           # Keep the pipe open if a descendant redirects stdout.
                           (os.POSIX_SPAWN_DUP2, writer, 3),
                           (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
                           (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0)]
                pid = os.posix_spawn(PROCESS_COMMAND[0], PROCESS_COMMAND, {"LC_ALL": "C"},
                                     file_actions=actions, setpgroup=0)
            finally:
                os.close(writer)
            output = read_bounded(reader, query_deadline, PROCESS_LIMIT, lambda: cancelled)
            status = wait_for_query(pid, query_deadline, lambda: cancelled) if output is not None else None
            if status is not None:
                pid = None
        finally:
            if pid is not None:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                # A killed process group cannot continue running even if the bounded
                # reap expires; the incomplete query is never used.
                if wait_for_query(pid, deadline) is None:
                    return None
    return output if status == 0 and not cancelled else None


def process_basename_fields(output, names):
    if not output or not output.endswith(b"\n"):
        return []
    rows = []
    for line in output[:-1].split(b"\n"):
        fields = line.split(None, 1)
        if len(fields) != 2 or not re.fullmatch(rb"[0-9]{1,12}(?:\.[0-9]{1,6})?", fields[0]):
            return []
        rows.append((float(fields[0]), os.path.basename(fields[1])))
    return [name for _, name in nlargest(10, rows) if name in names]


def sample(fd, deadline=None):
    if deadline is None:
        deadline = time.monotonic() + BUDGET
    if fcntl is None or host() != "claude":
        return
    home = Path(os.getenv("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
    if not enabled(home):
        return
    data = read_bounded(fd, deadline, INPUT_LIMIT)
    event = decode(data) if data is not None else None
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
    path = audits / "samples"
    want_process = bool(load and cores and float(load) >= int(cores))
    process_min_size = len("\t".join(("P", str(ms), load, cores, "x")) + "\n")
    if append(path, day, ("\t".join(fields) + "\n").encode("ascii"), deadline,
              want_process, process_min_size):
        names = catalogue_names()
        if names:
            hits = process_basename_fields(query_processes(deadline), names)
            if hits:
                prefix = "\t".join(("P", str(ms), load, cores)).encode("ascii")
                append(path, day, b"\t".join([prefix] + hits) + b"\n", deadline)


def deadline_expired(_signum, _frame):
    raise RuntimeError("sampler deadline expired")


def main():
    if fcntl is None:
        return
    deadline = time.monotonic() + BUDGET
    previous = {sig: signal.signal(sig, deadline_expired) for sig in CANCEL_SIGNALS}
    try:
        try:
            signal.setitimer(signal.ITIMER_REAL, max(0, deadline - time.monotonic()))
            sample(sys.stdin.fileno(), deadline)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    except (OSError, ValueError, RuntimeError):
        pass
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
