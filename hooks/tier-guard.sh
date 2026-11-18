#!/usr/bin/env bash
# Opt-in PreToolUse(Agent). Only a successful policy decision can emit a denial.
command -v jq >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1 || exit 0

decision=$(python3 -I - 3<&0 2>/dev/null <<'PY'
import errno
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tempfile
import time
from contextlib import suppress
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


def reap_lock(lock):
    # A directory descriptor ties stale cleanup to the original lock inode.
    try:
        fd = os.open(lock, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return
    try:
        private(os.fstat(fd), stat.S_ISDIR, 0o700)
        entries = os.listdir(fd)
        if entries:
            if len(entries) != 1 or not re.fullmatch(r"[1-9][0-9]{0,9}", entries[0]):
                raise ValueError("invalid lock owner")
            try:
                owner_info = os.stat(entries[0], dir_fd=fd, follow_symlinks=False)
                if time.time() - owner_info.st_mtime <= 30:
                    os.kill(int(entries[0]), 0)
                    return
            except ProcessLookupError:
                pass
            with suppress(FileNotFoundError):  # Another contender may have reaped this owner.
                os.unlink(entries[0], dir_fd=fd)
        remove_empty_lock(lock)
    finally:
        os.close(fd)


def acquire(lock, owner):
    candidate = Path(tempfile.mkdtemp(prefix=".lock-", dir=lock.parent))
    try:
        (candidate / owner).touch()
        for _ in range(20):
            with suppress(FileNotFoundError):
                private(lock.lstat(), stat.S_ISDIR, 0o700)
            try:
                # Publish a nonempty mkdir lock atomically. Rename cannot replace a live lock.
                candidate.rename(lock)
                return True
            except OSError as error:
                if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                    raise
                reap_lock(lock)
                time.sleep(0.02)
        return False
    finally:
        (candidate / owner).unlink(missing_ok=True)
        if candidate.exists():
            candidate.rmdir()


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
        if not re.fullmatch(rb"(0|[1-9][0-9]{0,30})\n", value):
            raise ValueError("invalid counter")
        count = int(value)
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


def guard():
    with os.fdopen(3, "rb") as stream:
        event = read_json(stream, 256 * 1024)
    if event.get("hook_event_name") != "PreToolUse" or event.get("tool_name") != "Agent":
        return False
    session = event.get("session_id")
    agent = event["tool_input"].get("subagent_type")
    prompt = event["tool_input"].get("prompt")
    if not all(isinstance(value, str) and value.strip() for value in (session, agent, prompt)):
        return False
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    rule = match_rule(config_dir / "agent-kaizen.json", agent)
    if rule is None:
        return False
    parent = config_dir.stat()
    if parent.st_uid != os.getuid() or parent.st_mode & 0o022:
        return False
    os.umask(0o077)
    state = config_dir / "kaizen-tier-guard"
    state.mkdir(mode=0o700, exist_ok=True)
    private(state.lstat(), stat.S_ISDIR, 0o700)
    key = hashlib.sha256(json.dumps([session, rule[0]]).encode("ascii")).hexdigest()
    lock = state / (key + ".lock")
    owner = str(os.getpid())
    if not acquire(lock, owner):
        return False
    try:
        with suppress(OSError):
            for path in state.iterdir():
                if path.name.endswith((".count", ".reasons.jsonl")):
                    with suppress(OSError):
                        info = path.lstat()
                        if stat.S_ISREG(info.st_mode) and time.time() - info.st_mtime > 30 * 86400:
                            path.unlink()
        if decide(state, key, rule, prompt):
            return rule[0], rule[2].pattern
        return None
    finally:
        (lock / owner).unlink()
        remove_empty_lock(lock)


try:
    denied = guard()
    if denied:
        print(json.dumps({"pattern": denied[0], "regex": denied[1]}))
except Exception:
    pass
PY
)
if [[ -n $decision ]]; then
    pattern=$(printf '%s' "$decision" | jq -er '.pattern + "x"' 2>/dev/null) || exit 0
    regex=$(printf '%s' "$decision" | jq -er '.regex + "x"' 2>/dev/null) || exit 0
    jq -nc --arg pattern "${pattern%x}" --arg regex "${regex%x}" \
        '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",
        permissionDecisionReason:("Agent tier allowance reached. Retry with a separate line: Tier reason: <why>. Rule: " + $pattern + "; reason regex: " + $regex)}}' 2>/dev/null
fi
exit 0
