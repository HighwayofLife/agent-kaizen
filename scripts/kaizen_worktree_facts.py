"""Read bounded, advisory Git worktree facts without modifying a repository."""
from functools import partial
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import time

MAX_OUTPUT = 1024 * 1024
MAX_TREES = 256
TIMEOUT = 5
GIT_PATHS = ('/usr/bin/git', '/opt/homebrew/bin/git', '/usr/local/bin/git')
GIT_ENV = dict(PATH='/usr/bin:/bin', LC_ALL='C', GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
               GIT_OPTIONAL_LOCKS='0', GIT_NO_LAZY_FETCH='1', GIT_ALLOW_PROTOCOL='',
               GIT_NO_REPLACE_OBJECTS='1', GIT_GRAFT_FILE=os.devnull)
GIT_CONFIG = ('core.hooksPath=/dev/null', 'core.fsmonitor=false',
              'core.untrackedCache=false', 'core.commitGraph=false',
              'core.multiPackIndex=false', 'fetch.writeCommitGraph=false')


def file_id(info):
    return info.st_dev, info.st_ino


def within(path, identity):
    for parent in (path, *path.parents):
        try:
            if file_id(parent.stat()) == identity:
                return True
        except (FileNotFoundError, NotADirectoryError):
            continue
    return False


def regular_bytes(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('expected a regular file')
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('metadata exceeds its size limit')
    return data


def repository_dirs(directory):
    """Find the local checkout and metadata without running a candidate executable."""
    for root in (directory, *directory.parents):
        marker = root / '.git'
        if os.path.lexists(marker):
            if marker.is_dir():
                return root, marker.resolve(strict=True)
            pointer = regular_bytes(marker, 8192)
            if not pointer.startswith(b'gitdir: '):
                raise ValueError('invalid Git marker')
            admin = (root / os.fsdecode(pointer[8:].rstrip(b'\n'))).resolve(strict=True)
            common_file = admin / 'commondir'
            common = ((admin / os.fsdecode(regular_bytes(common_file, 8192).rstrip(b'\n')))
                      .resolve(strict=True) if os.path.lexists(common_file) else admin)
            return (root, admin, common, common.parent) if common.name == '.git' else (root, admin, common)
        if (root / 'HEAD').is_file() and (root / 'objects').is_dir():
            return (root,)
    return ()


def resolve_git(directory, *protected):
    override = Path(os.environ.get('KAIZEN_GIT', ''))
    directory = Path(directory).resolve(strict=True)
    try:
        roots = repository_dirs(directory)
    except (OSError, ValueError, RuntimeError):
        roots = ()
    protected_ids = {file_id(p.stat()) for p in (directory, *roots, *protected)}
    for index, requested in enumerate((override, *map(Path, GIT_PATHS))):
        if not requested.is_absolute() or (index == 0 and not roots):
            continue
        try:
            candidate = requested.resolve(strict=True)
            if not candidate.is_file() or not os.access(candidate, os.X_OK):
                continue
            if any(within(candidate, identity) for identity in protected_ids):
                continue
            if index == 0 and any(file_id(p.stat()) in protected_ids
                                  for p in repository_dirs(candidate.parent)):
                continue
            return candidate
        except (OSError, ValueError, RuntimeError):
            continue
    return None


def git(executable, directory, *args):
    if executable is None:
        return None
    process = None
    try:
        config = [arg for value in GIT_CONFIG for arg in ('-c', value)]
        process = subprocess.Popen([str(executable), '--no-pager', '--no-optional-locks',
                                    '-C', str(directory), *config, *args], env=GIT_ENV,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
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


def records(run, directory):
    result = run(directory, 'worktree', 'list', '--porcelain', '-z')
    nul = result is not None and result[0] == 0
    if not nul:
        result = run(directory, 'worktree', 'list', '--porcelain')
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


def read_facts(directory, read_status):
    """Return facts for registered trees, or None when registration is unavailable.

    clean and merged are True, False, or None (unknown); they are advisory and
    must not be used alone to authorize deletion.
    """
    try:
        run = partial(git, resolve_git(directory))
    except (OSError, ValueError, RuntimeError):
        return None
    entries = records(run, directory)
    if not entries:
        return None
    primary = entries[0]
    primary_branch = primary.get(b'branch', b'')
    primary_tip = primary.get(b'HEAD', b'')
    valid_tip = lambda value: bool(re.fullmatch(rb'[0-9a-f]{40}|[0-9a-f]{64}', value)) and any(c != 48 for c in value)
    if not primary_branch.startswith(b'refs/heads/'):
        primary_branch = b''
    if primary_branch and valid_tip(primary_tip) and b'detached' not in primary:
        check = run(directory, 'rev-parse', '--verify', os.fsdecode(primary_branch))
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
        status = read_status(run, path)
        if status is not None and status[0] == 0:
            clean = not bool(status[1])
        if primary_tip and valid_tip(tip):
            ancestry = run(directory, 'merge-base', '--is-ancestor', os.fsdecode(tip), os.fsdecode(primary_tip))
            if ancestry is not None and ancestry[0] in (0, 1):
                merged = ancestry[0] == 0
        facts.append(dict(path=path, branch=os.fsdecode(branch[11:]) if branch.startswith(b'refs/heads/') else None,
                          tip=os.fsdecode(tip) if valid_tip(tip) else None, primary=index == 0,
                          linked=index != 0, locked=b'locked' in entry, detached=detached,
                          clean=clean, merged=merged))
    return facts
