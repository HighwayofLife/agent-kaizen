"""Read bounded, advisory Git worktree facts without modifying a repository."""
import os
from pathlib import Path
import re
import select
import subprocess
import time

MAX_OUTPUT = 1024 * 1024
MAX_TREES = 256
TIMEOUT = 5


def git(directory, *args):
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
    process = None
    try:
        process = subprocess.Popen(['git', '--no-optional-locks', '-C', str(directory),
                                    '-c', 'core.fsmonitor=false', *args], env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + TIMEOUT
        output = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                return None
            chunk = os.read(process.stdout.fileno(), min(65536, MAX_OUTPUT + 1 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > MAX_OUTPUT:
                return None
        return process.wait(timeout=max(0.001, deadline - time.monotonic())), bytes(output)
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()


def records(directory):
    result = git(directory, 'worktree', 'list', '--porcelain', '-z')
    nul = result is not None and result[0] == 0
    if not nul:
        result = git(directory, 'worktree', 'list', '--porcelain')
    if result is None or result[0] or not result[1]:
        return None
    data = result[1]
    separator = b'\0' if nul else b'\n'
    if not data.endswith(separator + separator):
        return None
    entries = []
    for block in data.split(separator + separator):
        if not block:
            continue
        entry = {}
        for field in block.split(separator):
            name, _, value = field.partition(b' ')
            if name in entry or name not in (b'worktree', b'HEAD', b'branch', b'bare',
                                                b'detached', b'locked', b'prunable'):
                return None
            entry[name] = value
        path = entry.get(b'worktree')
        # Old Git quotes unusual paths; newline records cannot safely decode them.
        if not path or (not nul and path.startswith(b'"')):
            return None
        entries.append(entry)
    return entries if entries and len(entries) <= MAX_TREES else None


def read_facts(directory):
    """Return facts for registered trees, or None when registration is unavailable.

    clean and merged are True, False, or None (unknown); they are advisory and
    must not be used alone to authorize deletion.
    """
    entries = records(directory)
    if not entries:
        return None
    primary = entries[0]
    primary_branch = primary.get(b'branch', b'')
    primary_tip = primary.get(b'HEAD', b'')
    valid_tip = lambda value: bool(re.fullmatch(rb'[0-9a-f]{40}|[0-9a-f]{64}', value)) and any(c != 48 for c in value)
    if not primary_branch.startswith(b'refs/heads/'):
        primary_branch = b''
    if primary_branch and valid_tip(primary_tip) and b'detached' not in primary:
        check = git(directory, 'rev-parse', '--verify', os.fsdecode(primary_branch))
        if check is None or check[0] or check[1].strip() != primary_tip:
            primary_tip = b''
    else:
        primary_tip = b''
    facts = []
    for index, entry in enumerate(entries):
        path = Path(os.fsdecode(entry[b'worktree'])).resolve()
        branch = entry.get(b'branch', b'')
        tip = entry.get(b'HEAD', b'')
        detached = b'detached' in entry
        clean = merged = None
        status = git(path, '-c', 'status.showUntrackedFiles=all', 'status', '--porcelain=v1',
                     '-z', '--untracked-files=all', '--ignored=matching')
        if status is not None and status[0] == 0:
            clean = not bool(status[1])
        if primary_tip and valid_tip(tip):
            ancestry = git(directory, 'merge-base', '--is-ancestor', os.fsdecode(tip), os.fsdecode(primary_tip))
            if ancestry is not None and ancestry[0] in (0, 1):
                merged = ancestry[0] == 0
        facts.append(dict(path=path, branch=os.fsdecode(branch[11:]) if branch.startswith(b'refs/heads/') else None,
                          tip=os.fsdecode(tip) if valid_tip(tip) else None, primary=index == 0,
                          linked=index != 0, locked=b'locked' in entry, detached=detached,
                          clean=clean, merged=merged))
    return facts
