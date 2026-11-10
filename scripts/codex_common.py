"""Small, stdlib-only helpers shared by the foreground Codex wrappers."""
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import os
import json
import re
import signal
import subprocess


ERROR = re.compile(r"error|fail|exception|assert", re.I)


def ensure_ignored(repo, pattern="out/"):
    """Keep generated output out of Git without changing tracked files."""
    try:
        command = ["git", "-C", str(repo)]
        ignored = subprocess.run(command + ["check-ignore", "-q", pattern + "x"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if ignored.returncode != 1:
            return
        result = subprocess.run(command + ["rev-parse", "--git-path", "info/exclude"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False)
        if result.returncode:
            return
        exclude = Path(result.stdout.strip())
        if not exclude.is_absolute():
            exclude = Path(repo) / exclude
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell():
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b"\n":
                    stream.write(b"\n")
            stream.write((pattern + "\n").encode())
    except OSError:
        pass


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def one_line(text):
    return " ".join(str(text).splitlines())


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, AttributeError):
        process.kill()


def run_logged(args, cwd, output, stdin=None, shell=False, timeout=None, own_session=False):
    """Never collect an unbounded transcript in memory.

    With a timeout (or own_session) the command runs in its own process group.
    On expiry the whole group is killed, "TIMEOUT after Ns" is logged and 124
    is returned. Any other exception that leaves the wait (Ctrl-C, SystemExit
    from a signal handler) kills the group too, then propagates.
    """
    detached = bool(timeout) or own_session
    with Path(output).open("w") as log:
        try:
            with Path(stdin).open() if stdin else open(os.devnull) as source:
                process = subprocess.Popen(args, cwd=cwd, stdin=source, stdout=log,
                                           stderr=subprocess.STDOUT, shell=shell,
                                           start_new_session=detached)
                try:
                    return process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    kill_group(process)
                    process.wait()
                    log.write(f"TIMEOUT after {timeout:g}s\n")
                    return 124
                except BaseException:
                    if detached:
                        kill_group(process)
                        process.wait()
                    raise
        except OSError as exc:
            log.write(f"ERROR: {exc}\n")
            return 127


def exit_on_signals(*names):
    """Turn termination signals into SystemExit(128 + signal) so cleanup runs."""
    def stop(number, frame):
        raise SystemExit(128 + number)
    for name in names:
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)


def code_locations(cwd, brief, log):
    """Best-effort brief lookup; failures only appear in the run log."""
    tool = cwd / "tools/codemap"
    if not tool.is_file() or not os.access(tool, os.X_OK):
        return ""
    with log.open("w") as errors:
        try:
            result = subprocess.run([str(tool), "brief", str(brief)], cwd=cwd,
                                    stdout=subprocess.PIPE, stderr=errors, text=True,
                                    timeout=float(os.environ.get("CODEMAP_TIMEOUT", "20")),
                                    check=False)
            if result.returncode == 0:
                return result.stdout if result.stdout.strip() else ""
            errors.write(f"Code map exited {result.returncode}\n")
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            errors.write(f"Code map: {exc}\n")
    return ""


def relevant(path, limit=60):
    """Keep recent matching lines AND the tail, in original order."""
    matches, tail = deque(maxlen=limit // 2), deque(maxlen=limit // 2)
    if not Path(path).is_file():
        return []
    with Path(path).open(errors="replace") as stream:
        for number, line in enumerate(stream):
            item = (number, line.rstrip()[:2000])
            tail.append(item)
            if ERROR.search(line):
                matches.append(item)
    return [line for _, line in sorted(dict(list(matches) + list(tail)).items())]


def key_errors(path, limit=3):
    lines = relevant(path)
    return ([line for line in lines if ERROR.search(line)] or lines[-limit:])[-limit:]


def emit(path, lines):
    text = "\n".join(one_line(line) for line in lines) + "\n"
    Path(path).write_text(text)
    print(text, end="")


def mcp_overrides(names):
    """Disable only explicitly requested servers; preserve the user's config."""
    result = []
    for name in names:
        # Quote TOML keys so punctuation in a server name cannot change the key path.
        key = name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else json.dumps(name)
        result += ["-c", f"mcp_servers.{key}.enabled=false"]
    return result
