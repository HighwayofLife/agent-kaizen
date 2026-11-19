"""Read bounded, advisory Git worktree facts without modifying a repository."""
from functools import partial
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
import time
import threading

MAX_OUTPUT = 1024 * 1024
MAX_TREES = 256
TIMEOUT = 5
TOTAL_TIMEOUT = 20
GIT_PATHS = ('/Library/Developer/CommandLineTools/usr/bin/git',
             '/Applications/Xcode.app/Contents/Developer/usr/bin/git',
             '/usr/bin/git', '/opt/homebrew/bin/git', '/usr/local/bin/git')
GIT_ENV = dict(PATH='/usr/bin:/bin', LC_ALL='C', GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
               GIT_OPTIONAL_LOCKS='0', GIT_NO_LAZY_FETCH='1', GIT_ALLOW_PROTOCOL='',
               GIT_NO_REPLACE_OBJECTS='1', GIT_GRAFT_FILE=os.devnull)
GIT_CONFIG = ('core.hooksPath=/dev/null', 'core.fsmonitor=false',
              'core.untrackedCache=false', 'core.commitGraph=false',
              'core.multiPackIndex=false', 'fetch.writeCommitGraph=false',
              'diff.ignoreSubmodules=none')
STATUS_KEYS = (rb'core\.(repositoryformatversion|filemode|ignorecase|symlinks|excludesfile|'
               rb'attributesfile|autocrlf|eol|safecrlf|checkstat|trustctime|precomposeunicode|'
               rb'sparsecheckout|sparsecheckoutcone)|index\.sparse|extensions\.(objectformat|refstorage)')


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


def dispatch_scope(directory):
    dirs = repository_dirs(directory)
    if len(dirs) < 2:
        return None
    info = (dirs[2] if len(dirs) > 2 else dirs[1]).stat()
    return f'--kaizen-scope={info.st_dev}:{info.st_ino}'


def resolve_git(directory, *protected, deadline=None):
    override = os.environ.get('KAIZEN_GIT')
    directory = Path(directory).resolve(strict=True)
    try:
        roots = repository_dirs(directory)
    except (OSError, ValueError, RuntimeError):
        roots = ()
    protected_ids = {file_id(p.stat()) for p in (directory, *roots, *protected)}

    def outside(requested):
        try:
            candidate = requested.resolve(strict=True)
            if (candidate.is_file() and os.access(candidate, os.X_OK)
                    and not any(within(candidate, identity) for identity in protected_ids)):
                return candidate
        except (OSError, ValueError, RuntimeError):
            pass

    fixed = next(filter(None, map(outside, map(Path, GIT_PATHS))), None)
    if override is None:
        return fixed
    requested = Path(override)
    try:
        if not roots or not requested.is_absolute() or not stat.S_ISREG(requested.lstat().st_mode):
            return None
        candidate = outside(requested)
        if candidate is None:
            return None
        # Use the fixed Git to establish scope before running the override.
        entries = records(partial(git, fixed, deadline=deadline), directory)
        if not entries:
            return None
        for entry in entries:
            path = Path(os.fsdecode(entry[b'worktree']))
            if not path.is_absolute():
                return None
            path = path.resolve()
            if candidate.is_relative_to(path) or (path.exists() and within(candidate, file_id(path.stat()))):
                return None
        if any(file_id(p.stat()) in protected_ids for p in repository_dirs(candidate.parent)):
            return None
        return candidate
    except (OSError, ValueError, RuntimeError):
        return None


def git(executable, directory, *args, input_data=b'', deadline=None, select_record=None,
        status_env=None, worktree_only=False, attributes=None):
    if executable is None:
        return None
    timeout = TIMEOUT if deadline is None else min(TIMEOUT, deadline - time.monotonic())
    if timeout <= 0:
        return None
    process = None
    reader = None
    output = bytearray()
    incomplete = False

    def stop(force=False):
        if process.poll() is not None and not force:
            return
        try:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            elif process.poll() is None:
                process.kill()
        except OSError:
            if process.poll() is None:
                process.kill()

    try:
        config = [arg for value in GIT_CONFIG for arg in ('-c', value)]
        # Override per-submodule ignore settings as well as diff.ignoreSubmodules.
        status = 'status' in args
        if status:
            end_options = args.index('--') if '--' in args else len(args)
            ignore = 'dirty' if status_env is not None else 'none'
            options = ('--no-renames',) if worktree_only else ()
            args = (*args[:end_options], f'--ignore-submodules={ignore}', *options, *args[end_options:])
        process = subprocess.Popen([str(executable), '--no-pager', '--no-optional-locks',
                                    '-C', str(directory), *config, *args], env=status_env or GIT_ENV,
                                   stdin=subprocess.PIPE if input_data else (
                                       attributes if attributes is not None else subprocess.DEVNULL),
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   start_new_session=(os.name == 'posix'))
        stdout = process.stdout
        process.stdout = None  # The bounded reader owns this pipe, not communicate().

        def read_output():
            nonlocal incomplete
            remainder = b''
            while len(output) <= MAX_OUTPUT:
                chunk = stdout.read1(65536)
                if not chunk:
                    incomplete = bool(remainder)
                    break
                if status and status_env is not None and not worktree_only:
                    output[:] = b'1'  # Only the presence of a status record matters.
                elif select_record is None and not worktree_only:
                    output.extend(chunk)
                else:
                    *fields, remainder = (remainder + chunk).split(b'\0')
                    for field in fields:
                        if worktree_only and field[1:2] != b' ':
                            output[:] = b'1'
                        elif not worktree_only and select_record(field):
                            output.extend(field + b'\0')
                    if len(remainder) > MAX_OUTPUT:
                        output.extend(remainder)
            if len(output) > MAX_OUTPUT:
                stop()
            stdout.close()

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        end = time.monotonic() + timeout
        process.communicate(input=input_data or None, timeout=timeout)
        reader.join(max(0, end - time.monotonic()))
        if reader.is_alive() or incomplete or len(output) > MAX_OUTPUT:
            return None
        return process.returncode, bytes(output)
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if process is not None:
            stop(force=reader is not None and reader.is_alive())
            process.wait()
            if reader is not None:
                reader.join(timeout=0.1)



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


def index_version(admin):
    try:
        info = (admin / 'index').stat()
    except FileNotFoundError:
        return None
    return file_id(info), info.st_ctime_ns, info.st_mtime_ns, info.st_size


def submodule_checkout(path, name):
    try:
        child = (path / os.fsdecode(name)).resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError):
        return ()
    if child.is_dir() and not os.path.lexists(child / '.git'):
        with os.scandir(child) as children:
            if next(children, None) is None:
                return ()
    dirs = repository_dirs(child)
    if child == path or not child.is_relative_to(path) or not dirs or dirs[0] != child:
        raise ValueError('invalid submodule checkout')
    return dirs


def status_inputs(run, path, dirs, depth=0):
    if depth > 16:
        raise ValueError('submodule depth exceeds its limit')
    admin = dirs[1]
    common = dirs[2] if len(dirs) > 2 else admin
    config = run(path, 'config', '--null', '--includes', '--get-regexp',
                 os.fsdecode(b'^(' + STATUS_KEYS + rb')$|^filter\.'))
    if config is None or config[0] not in (0, 1) or (config[1] and not config[1].endswith(b'\0')):
        raise ValueError('cannot read status configuration')
    safe = []
    for item in config[1].split(b'\0')[:-1]:
        key, has_value, value = item.partition(b'\n')
        if not re.fullmatch(STATUS_KEYS, key):
            raise ValueError('cannot interpret status with configured filters')
        safe.append((key, value if has_value else None))

    hidden = False
    def gitlink(item):
        nonlocal hidden
        hidden |= not item.startswith(b'H ')
        return item[2:].startswith(b'160000 ')

    stamp = index_version(admin)
    index = run(path, 'ls-files', '--stage', '-v', '-z', select_record=gitlink)
    if index is None or index[0] or stamp != index_version(admin):
        raise ValueError('cannot read stable status index')
    children = {}
    for item in index[1].split(b'\0')[:-1]:
        _, sep, name = item.partition(b'\t')
        if not sep or not name or b'..' in name.split(b'/'):
            raise ValueError('invalid submodule path')
        if name not in children:
            children[name] = submodule_checkout(path, name)
    topology = {name: tuple(file_id(directory.stat()) for directory in child)
                for name, child in children.items()}
    yield path, admin, common, safe, stamp, hidden, topology
    for child in children.values():
        if child:
            yield from status_inputs(run, child[0], child, depth + 1)


def isolated_status(run, read_status, checkout, admin, common, config):
    try:
        with tempfile.TemporaryDirectory() as name:
            isolated = Path(name)
            # Only data paths are shared with the live repo. Child status is explicit.
            for item in ('objects', 'refs', 'packed-refs', 'shallow', 'info', 'reftable'):
                (isolated / item).symlink_to(common / item)
            with (isolated / 'config').open('wb') as stream:
                for key, value in config:
                    section, option = key.split(b'.', 1)
                    stream.write(b'[' + section + b']\n' + option)
                    if value is not None:
                        for old, new in ((b'\\', b'\\\\'), (b'"', b'\\"'), (b'\n', b'\\n'),
                                         (b'\t', b'\\t'), (b'\b', b'\\b')):
                            value = value.replace(old, new)
                        stream.write(b' = "' + value + b'"')
                    stream.write(b'\n')
            env = dict(GIT_ENV, GIT_DIR=str(admin), GIT_COMMON_DIR=name, GIT_WORK_TREE=str(checkout))
            return read_status(partial(run, status_env=env), checkout)
    except OSError:
        return readonly_status(run, read_status, checkout, admin, common, config)


def readonly_status(run, read_status, checkout, admin, common, config):
    # Without writable storage, use an installed config with empty refs.
    # Compare the index to the real HEAD first, using worktree-free plumbing.
    head = run(checkout, 'rev-parse', '--verify', 'HEAD')
    if head is None or head[0] not in (0, 128):
        return None
    if head[0] == 0:
        oid = head[1].strip()
        if not re.fullmatch(rb'[0-9a-f]{40}|[0-9a-f]{64}', oid):
            return None
        staged = run(checkout, 'diff-index', '--cached', '--quiet', '--no-ext-diff', '--no-textconv',
                     '--ignore-submodules=dirty', os.fsdecode(oid), '--')
        if staged != (0, b''):
            return (0, b'1') if staged == (1, b'') else None
    else:
        branch = run(checkout, 'symbolic-ref', '-q', 'HEAD')
        if branch is None or branch[0] or not branch[1].startswith(b'refs/heads/'):
            return None
    fmt = dict(config).get(b'extensions.objectformat', b'sha1')
    if fmt not in (b'sha1', b'sha256'):
        return None
    isolated = Path(__file__).resolve().with_name('kaizen-status-git') / os.fsdecode(fmt)
    env = dict(GIT_ENV, GIT_DIR=str(admin), GIT_COMMON_DIR=str(isolated), GIT_WORK_TREE=str(checkout),
               GIT_OBJECT_DIRECTORY=str(common / 'objects'), GIT_CONFIG_COUNT=str(len(config)))
    for index, (key, value) in enumerate(config):
        env[f'GIT_CONFIG_KEY_{index}'] = os.fsdecode(key)
        env[f'GIT_CONFIG_VALUE_{index}'] = 'true' if value is None else os.fsdecode(value)
    # The template reads its info/attributes through /dev/stdin so repository
    # attributes keep their normal precedence without sharing its config.
    try:
        fd = os.open(common / 'info/attributes', os.O_RDONLY | os.O_NONBLOCK)
    except FileNotFoundError:
        fd = os.open(os.devnull, os.O_RDONLY)
    else:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            return None
    with os.fdopen(fd, 'rb') as attributes:
        status_run = partial(run, status_env=env, worktree_only=head[0] == 0, attributes=attributes)
        result = read_status(status_run, checkout)
    return result if head == run(checkout, 'rev-parse', '--verify', 'HEAD') else None


def cleanliness(run, path, dirs, read_status):
    try:
        for _ in range(2):
            inputs = list(status_inputs(run, path, dirs))
            clean = True
            stable = True
            for checkout, admin, common, config, stamp, hidden, _ in inputs:
                result = isolated_status(run, read_status, checkout, admin, common, config)
                if result is None or result[0]:
                    clean = None
                elif result[1]:
                    return False
                elif hidden:
                    clean = None
            for checkout, admin, _, _, stamp, _, topology in inputs:
                if index_version(admin) != stamp:
                    return None
                for name, identities in topology.items():
                    current = tuple(file_id(directory.stat()) for directory in submodule_checkout(checkout, name))
                    stable &= current == identities
            if stable:
                return clean
    except (OSError, ValueError, RuntimeError):
        pass
    return None


def read_facts(directory, read_status):
    """Return facts for registered trees, or None when registration is unavailable.

    clean and merged are True, False, or None (unknown); they are advisory and
    must not be used alone to authorize deletion.
    """
    deadline = time.monotonic() + TOTAL_TIMEOUT
    try:
        executable = resolve_git(directory, deadline=deadline)
    except (OSError, ValueError, RuntimeError):
        return None
    run = partial(git, executable, deadline=deadline)
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
        # Verify the registration still points to this repository before status.
        try:
            dirs = repository_dirs(path)
            source_dirs = repository_dirs(Path(directory).resolve())
            same_repo = (dirs and source_dirs and dirs[0] == path
                         and file_id(dirs[2 if len(dirs) > 2 else 1].stat())
                         == file_id(source_dirs[2 if len(source_dirs) > 2 else 1].stat()))
        except (OSError, ValueError, RuntimeError, IndexError):
            same_repo = False
        if same_repo:
            head = run(path, 'rev-parse', '--verify', 'HEAD')
            symbolic = run(path, 'symbolic-ref', '-q', 'HEAD')
            head_matches = head is not None and (
                (head[0] == 0 and head[1].strip() == tip)
                or (not detached and branch.startswith(b'refs/heads/')
                    and tip in (b'0' * 40, b'0' * 64) and head == (128, b'')))
            same_repo = (head_matches
                         and symbolic is not None and
                         ((detached and symbolic[0] == 1) or
                          (not detached and symbolic[0] == 0 and symbolic[1].strip() == branch)))
        if same_repo and time.monotonic() < deadline:
            clean = cleanliness(run, path, dirs, read_status)
        if primary_tip and valid_tip(tip):
            ancestry = run(directory, 'merge-base', '--is-ancestor', os.fsdecode(tip), os.fsdecode(primary_tip))
            if ancestry is not None and ancestry[0] in (0, 1):
                merged = ancestry[0] == 0
        facts.append(dict(path=path, branch=os.fsdecode(branch[11:]) if branch.startswith(b'refs/heads/') else None,
                          tip=os.fsdecode(tip) if valid_tip(tip) else None, primary=index == 0,
                          linked=index != 0, locked=b'locked' in entry, detached=detached,
                          clean=clean, merged=merged))
    return facts
