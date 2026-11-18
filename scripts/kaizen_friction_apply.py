"""Runner-owned mutation evidence for the dormant scheduled broker."""
import argparse
import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import re
import select
import shlex
import stat
import tempfile
from threading import Event, Thread


# Add a version only after S7 verifies the real print-mode lifecycle and permissions.
VERIFIED_STREAM_VERSIONS = frozenset()
STREAM_LIMIT = 8 << 20


def require(condition):
    if not condition:
        raise ValueError("scheduled mutation evidence is incomplete or inconsistent")


def reject_constant(_value):
    raise ValueError("non-JSON constant in mutation evidence")


def observe_review(run, command, version, *, backup, scope, project, **kwargs):
    """Capture bounded stdout through an anonymous pipe owned by the runner."""
    require(version in VERIFIED_STREAM_VERSIONS)
    executable = Path(command[0])
    require(executable.is_absolute())
    executable = executable.resolve(strict=True)
    stamp = backup["file_version"](executable.stat())
    raw = bytearray()
    done = Event()
    complete = Event()
    reader, writer = os.pipe()

    def collect():
        try:
            while len(raw) <= STREAM_LIMIT:
                if not select.select([reader], [], [], 0.1)[0]:
                    if done.is_set():
                        return
                    continue
                chunk = os.read(reader, min(65536, STREAM_LIMIT + 1 - len(raw)))
                if not chunk:
                    complete.set()
                    return
                raw.extend(chunk)
        except OSError:
            return
        finally:
            os.close(reader)

    thread = Thread(target=collect)
    thread.start()
    try:
        result = run([str(executable), *command[1:], "--output-format", "stream-json", "--verbose"],
                     stdout=writer, **kwargs)
    finally:
        os.close(writer)
        done.set()
        thread.join()
    try:
        require(complete.is_set() and result.returncode == 0 and backup["file_version"](executable.stat()) == stamp)
        review, calls = runtime_calls(bytes(raw), version, scope, project, backup["unique_fields"])
    except (AttributeError, KeyError, OSError, RecursionError, TypeError, ValueError):
        return result, "Scheduled review stream is incomplete.\n", None
    return result, review, calls


def runtime_calls(raw, version, scope, project, unique_fields):
    """Return rendered review text and ordered dispatch/completion pairs."""
    require(version in VERIFIED_STREAM_VERSIONS and len(raw) <= STREAM_LIMIT and raw.endswith(b"\n"))
    events = raw[:-1].split(b"\n")
    seen, calls, results, assistant = set(), {}, {}, False
    for index, line in enumerate(events):
        event = json.loads(line.decode("utf-8"), object_pairs_hook=unique_fields, parse_constant=reject_constant)
        require(event["session_id"] == scope["session_id"] and isinstance(event["uuid"], str)
                and event["uuid"] and event["uuid"] not in seen)
        seen.add(event["uuid"])
        kind = event["type"]
        if index == 0:
            require(kind == "system" and event["subtype"] == "init"
                    and event["claude_code_version"] == version and event["cwd"] == str(project))
        elif index == len(events) - 1:
            require(assistant and kind == "result" and event["subtype"] == "success" and event["is_error"] is False
                    and isinstance(event["result"], str) and calls.keys() == results.keys())
            return event["result"], [(start, *results[tool_id], name, args)
                                     for tool_id, (start, name, args) in calls.items()]
        else:
            require(kind in ("assistant", "user") and event["parent_tool_use_id"] is None)
            assistant |= kind == "assistant"
            message = event["message"]
            require(message["role"] == kind and isinstance(message["content"], list) and message["content"])
            for block in message["content"]:
                if kind == "assistant" and block["type"] in ("text", "thinking"):
                    require(isinstance(block[block["type"]], str))
                    continue
                if kind == "assistant":
                    require(block["type"] == "tool_use" and isinstance(block["id"], str)
                            and block["id"] and block["id"] not in calls and isinstance(block["input"], dict))
                    calls[block["id"]] = index, block["name"], block["input"]
                else:
                    tool_id, failed = block["tool_use_id"], block.get("is_error", False)
                    require(block["type"] == "tool_result" and tool_id in calls and tool_id not in results
                            and type(failed) is bool)
                    results[tool_id] = index, failed
    raise ValueError("missing runtime result")


def single_link_bytes(backup, path, limit):
    live = backup["checked_bytes"](path, limit)
    info = path.lstat()
    require(info.st_nlink == 1 and backup["file_version"](info) == live[2])
    return live


def snapshot_ledger(backup, project):
    path = project / backup["LEDGER_PATH"]
    try:
        return single_link_bytes(backup, path, backup["MAX_LEDGER_BYTES"])[1]
    except FileNotFoundError:
        return None


def ledger_proof(backup, scope, project, before, manifest_ids):
    path = backup["LEDGER_PATH"]
    require(isinstance(before, bytes) and len(before) <= backup["MAX_LEDGER_BYTES"]
            and all(backup["nonempty"](scope[key]) for key in ("run_id", "session_id")))
    _, after, version = single_link_bytes(backup, project / path, backup["MAX_LEDGER_BYTES"])
    proof = dict(v=1, run_id=scope["run_id"], session_id=scope["session_id"], ledger_relpath=path,
                 before_b64=base64.b64encode(before).decode("ascii"),
                 before_sha256=hashlib.sha256(before).hexdigest(),
                 after_sha256=hashlib.sha256(after).hexdigest(), manifest_ids=sorted(manifest_ids))
    _, _, live = backup["ledger_append"](proof, scope, project)
    require(live[2] == version)
    return proof, live


def bash_args(command, backup_script, notes_script, python):
    # Accept only simple literal invocations of the existing scheduled grants.
    require(not re.search(r'[\x00-\x1f\x7f$;&|<>()\\`*?\[\]{}~#!]', command))
    argv = shlex.split(command)
    interpreted = bool(argv and argv[0] in ("python3", python))
    if interpreted:
        argv.pop(0)
    require(len(argv) >= 2)
    helper, operation, *args = argv
    if helper == str(backup_script):
        require(operation in ("begin", "finish", "list"))
        return operation, args
    require(interpreted and helper == str(notes_script) and operation == "add")
    return operation, args


def snapshot_notes(backup, paths):
    """Capture configured notes targets from runner config before launch."""
    require(len(set(paths.values())) == len(paths))
    return {kind: (path, single_link_bytes(backup, path, STREAM_LIMIT)) for kind, path in paths.items()}


def verify_notes(backup, notes, entries, commands):
    """Replay verified literal adds on private copies and compare the guarded ledgers."""
    if not commands and not entries:
        return
    paths = {}
    with tempfile.TemporaryDirectory(prefix="kaizen-notes-proof-") as temporary:
        for kind, (_, before) in entries.items():
            paths[kind] = Path(temporary) / kind
            paths[kind].write_bytes(before[1])
        required = {"--date", "--category", "--change", "--why", "--measure", "--source"}
        for args in commands:
            fields = dict(zip(args[::2], args[1::2]))
            require("csv" in paths and len(fields) * 2 == len(args)
                    and fields.keys() in (required, required | {"--status"})
                    and all(not value.startswith("-") for value in fields.values()))
            values = {key[2:]: value for key, value in fields.items()}
            values.setdefault("status", "active")
            require(values["status"] in ("active", "planned"))
            with redirect_stdout(io.StringIO()):
                notes(argparse.Namespace(dry_run=False, **values), paths["csv"], paths.get("timeline"))
        for kind, (path, before) in entries.items():
            live = single_link_bytes(backup, path, STREAM_LIMIT)
            require(live[1] == paths[kind].read_bytes()
                    and (kind != "csv" or live[2][:2] == before[2][:2]))


def prove_budget(calls, *, backup, root, scope, project, baseline, ledger_before, config_before, config_after,
                 backup_script, notes_script, python, notes_add, notes_before):
    """Prove allowance after guarded exit, with the runner holding the notes lock."""
    try:
        require(config_before == config_after and type(config_before[0]) is int and config_before[0] >= 0
                and baseline["root"] == str(project))
        with backup["open_directory"](root) as fd:
            stamp = backup["backup_root_stamp"](root, fd)
        initial_stamp = scope["root_identity"]
        require(stamp["ctime_ns"] >= initial_stamp["ctime_ns"]
                and dict(stamp, ctime_ns=initial_stamp["ctime_ns"]) == initial_stamp)
        folders_after = {path for path in root.iterdir() if stat.S_ISDIR(path.lstat().st_mode)}
        ledger = project / backup["LEDGER_PATH"]
        edits, originals, finished, notes = {}, {}, {}, []
        active, charge, prior_end, ledger_written = None, 0, -1, False
        remaining_bytes = backup["MAX_COMMIT_BYTES"]
        for start, end, failed, name, args in calls:
            if name in ("Read", "Grep", "Glob"):
                continue
            # Do not infer ordering between effects dispatched in parallel.
            require(start > prior_end)
            prior_end = end
            if name in ("Edit", "Write"):
                path = Path(args["file_path"])
                require(path.is_absolute() and str(path) == args["file_path"] and path.resolve() == path
                        and path.is_relative_to(project)
                        and not path.is_relative_to(backup_script.parent)
                        and not path.is_relative_to(notes_script.parent)
                        and path != Path(python).resolve())
                if path == ledger:
                    require(active is None and not failed and not ledger_written and finished)
                    ledger_written = True
                else:
                    require(active is not None and path in active[2])
                    active[3].add(path)
                    charge += 1
                continue
            require(name == "Bash" and args.keys() <= {
                "command", "description", "timeout", "run_in_background", "dangerouslyDisableSandbox"
            } and args.get("run_in_background", False) is False
                and args.get("dangerouslyDisableSandbox", False) is False)
            op, argv = bash_args(args["command"], backup_script, notes_script, python)
            require(not failed)
            if op == "list":
                require(argv in ([], ["--all"]))
            elif op == "add":
                notes.append(argv)
            elif op == "begin":
                require(active is None and not ledger_written and len(argv) >= 5
                        and argv[0] == "--skill" and argv[2] == "--ledger"
                        and not any(arg.startswith("-") for arg in argv[4:]))
                paths = [project / arg for arg in argv[4:]]
                require(len(paths) == len(set(paths)))
                active = argv[1], argv[3], paths, set()
            else:
                require(active is not None and (len(argv) == 1 or argv[1:] == ["--verification", "passed"]))
                folder = Path(argv[0])
                require(folder not in finished and folder in folders_after)
                data, identity, digest = backup["validate_change_handoff"](root, folder, **scope)
                raw = backup["checked_bytes"](folder / "manifest.json", STREAM_LIMIT)[1]
                require(hashlib.sha256(raw).hexdigest() == digest)
                json.loads(raw, object_pairs_hook=backup["unique_fields"], parse_constant=reject_constant)
                skill, description, paths, written = active
                require(data["finished"] is True and data["verification"] == "passed" and data["reverted"] is None
                        and "committed" not in data and "git" not in data and data["actions"] == []
                        and (data["skill"], data["ledger"]) == (skill, description)
                        and [entry["path"] for entry in data["files"]] == list(map(str, paths))
                        and set(paths) == written and not written.intersection(edits))
                for entry in data["files"]:
                    path = backup["validate_entry"](folder, entry)
                    live = single_link_bytes(backup, path, remaining_bytes)
                    remaining_bytes -= len(live[1])
                    require(hashlib.sha256(live[1]).hexdigest() == entry["after_sha256"]
                            and not (entry["created"] and entry["backup"] is not None))
                    edits[path] = live
                    originals[path] = None if entry["created"] else folder / entry["backup"]
                finished[folder] = identity, digest
                active = None
        require(active is None and folders_after - scope["before"][0] == finished.keys())
        verify_notes(backup, notes_add, notes_before, notes)
        proof = None
        if ledger_written:
            proof, edits[ledger] = ledger_proof(backup, scope, project, ledger_before, [f.name for f in finished])
        _, entries, check = backup["capture_git_tree"](project, baseline=baseline, edits=edits)
        for path, old in originals.items():
            blob = entries.get(path)
            require((old is None and blob is None and edits[path][0] == b"100644")
                    or (old is not None and blob is not None and edits[path][0] == blob[0]
                        and backup["matches_blob"](old, *blob)))
        if proof is not None:
            mode, oid = entries[ledger]
            require(mode == edits[ledger][0] and backup["object_id"]("blob", ledger_before, len(oid)) == oid)
        for folder, (identity, digest) in finished.items():
            backup["verify_change_handoff"](root, folder, root_identity=initial_stamp,
                                            identity=identity, manifest_sha256=digest)
        backup["check_backup_root"](root, stamp)
        require(backup["still_clean"](*check))
        return max(0, config_before[0] - charge), proof
    except (AttributeError, KeyError, OSError, RecursionError, RuntimeError, TypeError, ValueError):
        return None, None
