#!/usr/bin/env bash
# Opt-in PreToolUse(Agent). Only a successful policy decision can emit a denial.
command -v jq >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1 || exit 0

deny_json() {
    jq -c --unbuffered '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",
        permissionDecisionReason:.}}' 2>/dev/null
}

python3 -I - 3<&0 2>/dev/null <<'PY' | deny_json || true
import errno
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager, suppress
from datetime import datetime, timezone


def read_json(stream, limit):
    def unique_object(pairs):
        obj = dict(pairs)
        if len(obj) != len(pairs):
            raise ValueError("duplicate JSON key")
        return obj

    def invalid_constant(value):
        raise ValueError(value)

    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("JSON size limit")
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def match_rule(config, agent):
    with os.fdopen(os.open(config, os.O_RDONLY | os.O_NONBLOCK), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("expected a config file")
        settings = read_json(stream, 64 * 1024)
    if settings.get("enabled") is False:
        return None
    rows = settings.get("guardrails", {}).get("agentTiers", [])
    if not isinstance(rows, list):
        raise ValueError("expected a list of tier rules")
    match = None
    for row in rows:
        if not isinstance(row, dict) or row.keys() != {"pattern", "freeSpawns", "reasonRegex"}:
            raise ValueError("invalid tier rule")
        pattern, free, regex = row["pattern"], row["freeSpawns"], row["reasonRegex"]
        if (not isinstance(pattern, str) or not pattern.strip() or type(free) is not int
                or free < 0 or not isinstance(regex, str) or not regex.strip()):
            raise ValueError("invalid tier rule fields")
        compiled = re.compile(regex, re.MULTILINE)
        if match is None and fnmatch.fnmatchcase(agent, pattern):
            match = pattern, free, compiled
    return match


def private(info, kind, mode):
    if (not kind(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != mode):
        raise PermissionError("unsafe tier guard state")


def state_file(path, flags):
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        private(info, stat.S_ISREG, 0o600)
        if info.st_nlink != 1:
            raise PermissionError("linked tier guard state")
        return fd
    except Exception:
        os.close(fd)
        raise


def remove_empty_lock(lock):
    try:
        lock.rmdir()
    except OSError as error:
        if error.errno not in (errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST):
            raise


def process_identity(pid):
    if sys.platform == "darwin":
        import ctypes

        # PROC_PIDTBSDINFO returns struct proc_bsdinfo, ending in two uint64
        # fields for the process start time (seconds and microseconds).
        info = ctypes.create_string_buffer(136)
        query = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True).proc_pidinfo
        if query(pid, 3, ctypes.c_uint64(0), info, len(info)) != len(info):
            raise OSError(ctypes.get_errno() or errno.EIO, "process start lookup failed")
        start = info.raw[-16:]
    elif sys.platform.startswith("linux"):
        boot = Path("/proc/sys/kernel/random/boot_id").read_bytes()
        fields = Path(f"/proc/{pid}/stat").read_bytes().rpartition(b") ")[2].split()
        start = boot + fields[19]  # Field 22, start time in ticks since boot.
    else:
        result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True,
                                env={**os.environ, "LC_ALL": "C", "TZ": "UTC"}, timeout=0.1)
        start = result.stdout.strip()
        if result.returncode or not start:
            raise OSError("process start lookup failed")
    return hashlib.sha256(start).hexdigest().encode("ascii")


def live_owner(pid, identity):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    if not identity:  # Older versions recorded only the PID.
        return True
    if not re.fullmatch(rb"[0-9a-f]{64}", identity):
        raise ValueError("invalid lock owner identity")
    try:
        return process_identity(pid) == identity
    except OSError:
        try:
            os.kill(pid, 0)  # The owner may have exited during the lookup.
        except ProcessLookupError:
            return False
        raise


def reap_lock(lock):
    # A directory descriptor ties stale cleanup to the original lock inode.
    try:
        fd = os.open(lock, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return True
    try:
        private(os.fstat(fd), stat.S_ISDIR, 0o700)
        entries = os.listdir(fd)
        if entries:
            owner, = entries
            if not re.fullmatch(r"[1-9][0-9]{0,9}", owner):
                raise ValueError("invalid lock owner")
            try:
                owner_fd = os.open(owner, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            except FileNotFoundError:
                # The owner may have just released the lock.
                remove_empty_lock(lock)
                return True
            with os.fdopen(owner_fd, "rb") as stream:
                private(os.fstat(stream.fileno()), stat.S_ISREG, 0o600)
                if live_owner(int(owner), stream.read(65)):
                    return False
            with suppress(FileNotFoundError):  # Another contender may have reaped this owner.
                os.unlink(owner, dir_fd=fd)
        remove_empty_lock(lock)
        return True
    finally:
        os.close(fd)


def publish_lock(candidate, lock):
    with suppress(FileNotFoundError):
        private(lock.lstat(), stat.S_ISDIR, 0o700)
    try:
        # Publish a nonempty mkdir lock atomically. Rename cannot replace a live lock.
        candidate.rename(lock)
        return True
    except OSError as error:
        if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
            raise
        return False


@contextmanager
def held_lock(lock, identity, *, wait=False):
    owner = str(os.getpid())
    candidate = Path(tempfile.mkdtemp(prefix=".lock-", dir=lock.parent))
    owned = candidate
    try:
        (candidate / owner).write_bytes(identity)
        deadline = time.monotonic() + (0.4 if wait else 0)
        while True:
            if publish_lock(candidate, lock):
                owned = lock
                break
            cleared = reap_lock(lock)
            if time.monotonic() >= deadline:
                if cleared and publish_lock(candidate, lock):
                    owned = lock
                break
            if not cleared:
                time.sleep(0.02)
        yield owned == lock
    finally:
        (owned / owner).unlink(missing_ok=(owned == candidate))
        remove_empty_lock(owned)


def supplied_reason(prompt, regex):
    def regex_timeout(*_):
        raise TimeoutError("tier reason match timed out")

    signal.signal(signal.SIGALRM, regex_timeout)
    try:
        signal.setitimer(signal.ITIMER_REAL, 0.1)
        for line in re.finditer(r"^Tier reason:([^\r\n]*)", prompt, re.MULTILINE):
            reason = line[1].strip()
            if reason and regex.search(line[0]):
                return reason
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return ""


def decide(state, key, rule, prompt):
    pattern, free, regex = rule
    counter = state / (key + ".count")
    log = state / (key + ".reasons.jsonl")
    try:
        with os.fdopen(state_file(counter, os.O_RDONLY), "rb") as stream:
            value = stream.read(33)
            age = time.time() - os.fstat(stream.fileno()).st_mtime
        if not re.fullmatch(rb"(0|[1-9][0-9]{0,30})\n", value):
            raise ValueError("invalid counter")
        # A counter older than the prune age is treated as already pruned.
        count = int(value) if age <= STATE_MAX_AGE else 0
    except FileNotFoundError:
        count = 0

    reason = supplied_reason(prompt, regex) if count >= free else ""
    flags = os.O_WRONLY | os.O_APPEND | (os.O_CREAT if reason else 0)
    try:
        fd = state_file(log, flags)
    except FileNotFoundError:
        if reason:
            raise
    else:
        try:
            if reason:
                entry = {"timestamp": datetime.now(timezone.utc).isoformat(),
                         "rule": pattern, "reason": reason if len(reason) <= 200 else reason[:199] + "…"}
                record = (json.dumps(entry) + "\n").encode("ascii")
                offset = os.fstat(fd).st_size
                if os.write(fd, record) != len(record):
                    os.ftruncate(fd, offset)
                    raise OSError("incomplete reason log write")
        finally:
            os.close(fd)

    if count >= free and not reason:
        return True
    with tempfile.NamedTemporaryFile(dir=state, delete=False) as stream:
        pending = Path(stream.name)
        try:
            stream.write(f"{count + 1}\n".encode("ascii"))
            stream.close()
            pending.replace(counter)
        finally:
            pending.unlink(missing_ok=True)
    return False


STATE_MAX_AGE = 30 * 86400
PRUNE_MAX_ENTRIES = 2000
PRUNE_MAX_SECONDS = 0.25


def expired(path):
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and time.time() - info.st_mtime > STATE_MAX_AGE


def prune(state, identity):
    with held_lock(state / ".prune.lock", identity) as acquired:
        if not acquired:
            return
        # Bounded so the hook stays fast; a huge directory is only partly pruned.
        deadline = time.monotonic() + PRUNE_MAX_SECONDS
        for seen, path in enumerate(state.iterdir()):
            if seen >= PRUNE_MAX_ENTRIES or time.monotonic() >= deadline:
                break
            match = re.fullmatch(r"(.+)\.(?:count|reasons\.jsonl)", path.name)
            if match is None:
                continue
            with suppress(OSError):
                if expired(path):
                    # The scan can see an old file while a writer replaces it.
                    # Read its age again under the same key lock the writer uses.
                    with held_lock(state / (match[1] + ".lock"), identity) as acquired:
                        if acquired and expired(path):
                            path.unlink()


def visible_config(value):
    # Printable text is shown as written; anything else as a Python literal,
    # whose escaping is unambiguous (backslashes are escaped too).
    return value if value.isprintable() else ascii(value)


def guard(event):
    if event.get("hook_event_name") != "PreToolUse" or event.get("tool_name") != "Agent":
        return
    session = event.get("session_id")
    agent = event["tool_input"].get("subagent_type")
    prompt = event["tool_input"].get("prompt")
    if not all(isinstance(value, str) and value.strip() for value in (session, agent, prompt)):
        return
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    rule = match_rule(config_dir / "agent-kaizen.json", agent)
    if rule is None:
        return
    parent = config_dir.stat()
    if parent.st_uid != os.getuid() or parent.st_mode & 0o022:
        return
    os.umask(0o077)
    state = config_dir / "kaizen-tier-guard"
    state.mkdir(mode=0o700, exist_ok=True)
    private(state.lstat(), stat.S_ISDIR, 0o700)
    key = hashlib.sha256(json.dumps([session, rule[0]]).encode("ascii")).hexdigest()
    identity = process_identity(os.getpid())
    with held_lock(state / (key + ".lock"), identity, wait=True) as acquired:
        if not acquired:
            return
        denied = decide(state, key, rule, prompt)
    if denied:
        reason = ("Agent tier allowance reached. Retry with a separate line: Tier reason: <why>. "
                  f"Rule: {visible_config(rule[0])}; reason regex: {visible_config(rule[2].pattern)}")
        print(json.dumps(reason), flush=True)
    # Maintenance runs after the decision and the release of the request lock.
    with suppress(OSError):
        prune(state, identity)


if __name__ == "__main__":
    try:
        with os.fdopen(3, "rb") as stream:
            event = read_json(stream, 256 * 1024)
        guard(event)
    except Exception:
        pass
PY
exit 0
