"""Deterministic comparison of scoped friction evidence.

Preparation computes a proposed snapshot; only a successful reconciliation may
persist it as acknowledged state.
"""

import json
import math
import fnmatch
import hashlib
import hmac
import os
from pathlib import Path
import re
import runpy
import stat
import warnings
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone


def comparison_key(project, window, thresholds, basis):
    """Return a canonical cohort key, rejecting unsupported comparison inputs."""
    if not isinstance(project, str) or not project or not isinstance(window, dict):
        raise ValueError("invalid comparison scope or window")
    if window.get("kind") == "rolling" and set(window) == {"kind", "seconds", "policy"}:
        if (type(window["seconds"]) is not int or not 0 <= window["seconds"] <= 36500 * 86400
                or window["policy"] != "utc-now-floor-second"):
            raise ValueError("unsupported rolling window")
        normalized = window
    elif window.get("kind") == "fixed" and set(window) == {"kind", "cutoff"}:
        try:
            cutoff = datetime.fromisoformat(window["cutoff"].replace("Z", "+00:00"))
            if cutoff.utcoffset() != timedelta(0):
                raise ValueError("cutoff must be UTC")
        except (AttributeError, TypeError, ValueError):
            raise ValueError("invalid fixed window")
        normalized = {"kind": "fixed", "cutoff": cutoff.isoformat()}
    else:
        raise ValueError("unsupported window")
    if (not isinstance(thresholds, dict) or not thresholds
            or any(not isinstance(k, str) or type(v) not in (int, float)
                   or (isinstance(v, float) and not math.isfinite(v)) or v <= 0
                   for k, v in thresholds.items())):
        raise ValueError("invalid thresholds")
    if basis not in ("none", "measured", "row_gap", "mixed"):
        raise ValueError("unsupported timing basis")
    return json.dumps([1, project, normalized, sorted(thresholds.items()), basis],
                      ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def compare_flags(project, window, thresholds, basis, flags, acknowledged):
    """Return new flags and a proposed cohort snapshot without mutating state."""
    key = comparison_key(project, window, thresholds, basis)
    if not isinstance(flags, list) or not isinstance(acknowledged, dict):
        raise ValueError("invalid flags or acknowledged state")
    # Only the versioned cohort namespace is considered; legacy fingerprints
    # have no scope or policy and cannot suppress current evidence.
    cohorts = (acknowledged.get("cohorts", {}) if type(acknowledged.get("v")) is int
               and acknowledged["v"] == 1 else {})
    if not isinstance(cohorts, dict):
        raise ValueError("invalid acknowledged cohorts")
    old = cohorts.get(key, {})
    if not isinstance(old, dict):
        raise ValueError("invalid acknowledged cohort")
    proposed = dict(old)
    new = []
    for flag in flags:
        if (not isinstance(flag, dict) or not isinstance(flag.get("id"), str)
                or not flag["id"] or not isinstance(flag.get("subject"), str)):
            raise ValueError("invalid flag identity")
        value = flag.get("value")
        if (type(value) not in (int, float) or value <= 0
                or (isinstance(value, float) and not math.isfinite(value))):
            raise ValueError("invalid flag value")
        ident = json.dumps([flag["id"], flag["subject"], flag.get("basis", "unconfirmed")],
                           ensure_ascii=True, separators=(",", ":"))
        bucket = math.floor(math.log2(value))
        previous = old.get(ident)
        if previous is not None and type(previous) is not int:
            raise ValueError("invalid acknowledged bucket")
        if previous is None or bucket > previous:
            new.append(flag)
        proposed[ident] = max(proposed.get(ident, bucket), bucket)
    return new, {"v": 1, "cohorts": dict(cohorts, **{key: proposed})}


LIMIT = 1 << 20
REPORT_AGE = 7 * 86400
PROBE_AGE = 3600
LABELS = {name: name.replace("-", " ").capitalize() for name in (
    "usage-limits", "timeouts", "interrupts", "lock-contention", "slow-calls",
    "heavy-calls", "contention", "parallel-heavy", "polling", "regression")}


def _json(raw, host):
    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite evidence")
        return number
    def invalid(value):
        raise ValueError("invalid JSON constant")
    value = json.loads(raw, object_pairs_hook=host["_unique"], parse_float=finite,
                       parse_constant=invalid)
    if not isinstance(value, dict) or type(value.get("v")) is not int or value["v"] != 1:
        raise ValueError("unsupported evidence version")
    return value


def _read(path, host, current=None, age=None, limit=LIMIT):
    """No symlink components, devices, writable foreign files or unbounded reads."""
    with host["_directory"](path.parent) as directory:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("unsafe evidence file")
            stream = os.fdopen(fd, "rb")
            fd = None
            with stream:
                if (info.st_uid != os.geteuid() or info.st_nlink != 1 or info.st_mode & 0o022):
                    raise ValueError("unsafe evidence file")
                host["_check_acl"](stream.fileno(), "evidence")
                raw = stream.read(limit + 1)
                after = os.fstat(stream.fileno())
        finally:
            if fd is not None:
                os.close(fd)
    if (len(raw) > limit or (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise ValueError("oversized or changing evidence")
    if age is not None and not 0 <= current.timestamp() - info.st_mtime <= age:
        raise ValueError("stale evidence")
    identity = dict(path=str(path), device=info.st_dev, inode=info.st_ino,
                    size=info.st_size, mtime_ns=info.st_mtime_ns,
                    sha256=hashlib.sha256(raw).hexdigest())
    return raw, identity


def _files(folder, pattern, host):
    try:
        with host["_directory"](folder) as directory, os.scandir(directory) as entries:
            result = []
            for count, entry in enumerate(entries):
                if count >= 512:
                    raise ValueError("too many evidence files")
                if re.fullmatch(pattern, entry.name):
                    result.append(folder / entry.name)
            return result
    except FileNotFoundError:
        return []


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError("invalid evidence time")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() != timedelta(0):
        raise ValueError("evidence time must be UTC")
    return stamp


def _evidence(report, audits, project, cfg, current, host):
    raw, report_identity = _read(report, host, current, REPORT_AGE)
    text = raw.decode("utf-8")
    def marker(name):
        matches = re.findall(r"^<!-- token-audit-" + name + r" (.*?) -->$", text, re.M)
        if len(matches) != 1:
            raise ValueError(f"missing or ambiguous audit {name} marker")
        return json.loads(matches[0], object_pairs_hook=host["_unique"])
    scope, ref = marker("scope"), marker("extract")
    name = report.stem + ".extract.json"
    if (not text.endswith("<!-- token-audit-complete -->\n") or "# Token audit\n" not in text
            or ref != {"v": 1, "file": name} or type(ref.get("v")) is not int
            or not isinstance(scope, dict) or set(scope) != {"v", "codex", "cwd", "project", "project_dirs", "window"}
            or type(scope["v"]) is not int or scope["v"] != 1
            or scope["cwd"] != sorted(str(p) for p in project.paths)
            or scope["project"] is not None or scope["project_dirs"] != []
            or scope["codex"] not in ("cwd", "none")):
        raise ValueError("invalid audit identity or scope")
    extract_raw, extract_identity = _read(audits / "extracts" / name, host, current, REPORT_AGE)
    binding = marker("friction")
    if (not isinstance(binding, dict) or type(binding.get("size")) is not int
            or binding != dict(size=len(extract_raw), sha256=extract_identity["sha256"])):
        raise ValueError("audit extract digest or size does not match the report")
    extract = _json(extract_raw, host)
    block = extract.get("friction")
    identities = dict(report=report_identity, extract=extract_identity)
    if extract.get("report") != report.name or extract.get("scope") != scope:
        raise ValueError("mismatched extract")
    if "friction" not in extract:
        return scope, None, identities
    if (not isinstance(block, dict) or type(block.get("v")) is not int or block["v"] != 1
            or block.get("thresholds") != {"slow_call_seconds": cfg["frictionSlowCallSeconds"]["value"],
                                           "heavy_seconds": cfg["frictionHeavySeconds"]["value"]}):
        raise ValueError("mismatched extract")
    comparison_key(str(project.canonical), block.get("window"), block.get("thresholds"), block.get("basis"))
    window, since = block["window"], _stamp(extract["since"])
    if window["kind"] == "rolling" and window["seconds"] % 86400:
        raise ValueError("unsupported audit lookback width")
    expected = (str(window["seconds"] // 86400) + "d" if window["kind"] == "rolling"
                and window["seconds"] % 86400 == 0 else "since:" + since.strftime("%Y-%m-%d"))
    if (scope["window"] != expected or since > current
            or "Since: " + extract["since"] + " (UTC;" not in text
            or (window["kind"] == "fixed" and since != _stamp(window["cutoff"]))
            or (window["kind"] == "rolling"
                and abs(report_identity["mtime_ns"] / 1e9 - since.timestamp() - window["seconds"]) > 3600)):
        raise ValueError("mismatched audit window")
    return scope, block, identities


def _encode(value):
    return (json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True,
                       allow_nan=False) + "\n").encode()


def _signature(receipt, secret):
    return hmac.new(secret, _encode({k: v for k, v in receipt.items() if k != "signature"}),
                    hashlib.sha256).hexdigest()


def prepare(audits, backups, project, report, cfg, mode, current, canonical_project, project_key,
            *, interactive=False, retain=False, _check=None, _complete=None, host=None):
    """Freeze bounded inputs, or re-derive them under the generation lock for reconciliation."""
    if cfg["enabled"]["value"] is False or cfg["friction"]["value"] == "off":
        if _check is not None:
            raise ValueError("friction is disabled")
        return None
    if not interactive and cfg["schedule"]["value"] == "off":
        if _check is not None:
            raise ValueError("scheduled review is disabled")
        return None
    if mode not in ("propose-only", "auto"):
        raise ValueError("unsupported preparation mode")
    if (project.unknown or canonical_project(project.canonical) != project.canonical
            or project.key != project_key(project.canonical)
            or project.folder != audits / "projects" / project.key):
        raise ValueError("noncanonical preparation scope")
    here = Path(__file__).resolve().parent
    if host is None:
        host = runpy.run_path(str(here / "kaizen_friction_actions.py"))
    current = current.astimezone(timezone.utc)
    folders = (project.folder, project.canonical / "docs/kaizen")
    if report is not None:
        report = Path(report).expanduser().absolute()
        if report.parent not in folders or not re.fullmatch(r"token-audit-[\w.-]+\.md", report.name):
            raise ValueError("report outside canonical audit destinations")
        scope, block, identities = _evidence(report, audits, project, cfg, current, host)
    else:
        candidates = []
        for folder in folders:
            for candidate in _files(folder, r"token-audit-[\w.-]+\.md", host):
                try:
                    info = candidate.lstat()
                    if stat.S_ISREG(info.st_mode) and info.st_size <= LIMIT:
                        candidates.append((info.st_mtime_ns, candidate.name, candidate))
                except OSError:
                    continue
        refusal = None
        for _, _, candidate in sorted(candidates, reverse=True)[:8]:
            try:
                scope, block, identities = _evidence(candidate, audits, project, cfg, current, host)
                break
            except (OSError, ValueError, KeyError, TypeError) as error:
                refusal = error
        else:
            raise ValueError("no fresh scoped audit" + (f" ({refusal})" if refusal else ""))
    probe = {"findings": [], "regenerable_dirs": []}
    if cfg["hostActions"]["value"] != "off":
        probes = _files(project.folder, r"host-probe-[\w.-]+\.json", host)
        if not probes:
            raise ValueError("no recent probe")
        probe_raw, identities["probe"] = _read(max(probes), host, current, PROBE_AGE)
        probe = _json(probe_raw, host)
        if (probe.get("project") != str(project.canonical)
                or not 0 <= (current - _stamp(probe["generated_at"])).total_seconds() <= PROBE_AGE
                or not isinstance(probe.get("findings"), list) or not isinstance(probe.get("regenerable_dirs"), list)):
            raise ValueError("invalid probe")
    store = host["HostActions"](audits, backups, canonical_project, project_key)
    catalog_path = next((here / name for name in ("kaizen-friction-catalog.json", "friction-catalog.json")
                         if (here / name).is_file()), None)
    catalog_raw, identities["catalog"] = _read(catalog_path, host)
    catalog_data = _json(catalog_raw, host)
    catalog = {row["id"]: row for row in catalog_data["actions"]}
    with host["_directory"](store.friction, True, private=True) as directory, host["_locked"](directory, "prepare"):
        if _check is not None:
            live_cfg = canonical_project.__globals__["effective"](project.canonical)
            current = max(current, datetime.now(timezone.utc))
            if live_cfg != cfg or live_cfg["enabled"]["value"] is False or live_cfg["friction"]["value"] == "off":
                raise ValueError("friction policy changed during reconciliation")
            if (cfg["hostActions"]["value"] != "off"
                    and not 0 <= (current - _stamp(probe["generated_at"])).total_seconds() <= PROBE_AGE):
                raise ValueError("probe expired during reconciliation")
        state_name = "prepare-" + project.key + ".json"
        try:
            state = _json(host["_read"](directory, state_name, LIMIT), host)
        except FileNotFoundError:
            state = {"v": 1, "project": str(project.canonical), "generation": 0, "acknowledged": {}}
        generation = state.get("generation")
        if (state.get("project") != str(project.canonical) or type(generation) is not int
                or not 0 <= generation < 10**20 - 1):
            raise ValueError("invalid preparation generation")
        rows = {row["id"]: row for row in store.scoped(project.canonical)}
        baseline, imported = state.get("acknowledged"), None
        secret = store._secret(create=_check is None)
        try:
            with host["_directory"](store.path.parent) as actions_directory:
                _, _, receipts = store._load(actions_directory)
            generations = receipts.get(str(project.canonical), {})
        except FileNotFoundError:
            generations = {}
        unacknowledged = {ident for name, entries in generations.items()
                          if re.fullmatch(r"scheduled:[0-9]{20}", name)
                          and name[10:] > state.get("acknowledged_generation", "")
                          for ident, status in entries.items() if status == "terminal"}
        unacknowledged.update(ident for entries in state.get("unpublished_suggestions", {}).values()
                              for ident in entries)
        if _check is not None:
            if (not hmac.compare_digest(_check.get("signature", ""), _signature(_check, secret))
                    or _check.get("channel") != ("interactive" if interactive else "scheduled")
                    or _check.get("generation") != f"{generation:020d}"
                    or not 0 <= (current - _stamp(_check["created"])).total_seconds() <= PROBE_AGE):
                raise ValueError("invalid, stale or noninteractive preparation receipt")
            baseline = _check["baseline"]
            if state.get("acknowledged") != baseline and not (
                    state.get("acknowledged_generation") == _check["generation"]
                    and state.get("acknowledged") == _check["comparison"]):
                raise ValueError("preparation comparison state changed")
            imported = generations.get(("interactive:" if interactive else "scheduled:") + _check["generation"])
            if interactive and any(value == "pending" for receipt in generations.values() for value in receipt.values()):
                raise ValueError("pending host actions require runner reconciliation")
            if imported is not None and (not set(imported) <= set(_check["allowed"])
                                         or (interactive and any(value != "terminal" for value in imported.values()))):
                raise ValueError("unmatched interactive import receipt")
        cohort = json.dumps([str(project.canonical), scope], sort_keys=True, separators=(",", ":"))
        if block is not None and (not isinstance(block.get("flags"), list)
                or any(not isinstance(flag, dict) or flag.get("id") not in LABELS
                       or ("basis" in flag and flag["basis"] not in ("none", "measured", "row_gap", "mixed"))
                       or not isinstance(flag.get("subject"), str) or len(flag["subject"]) > 4096
                       for flag in block["flags"])):
            raise ValueError("unsupported flag")
        flags, snapshot = (compare_flags(cohort, block["window"], block["thresholds"], block["basis"],
                                         block.get("flags"), baseline) if block is not None else ([], baseline))
        visible_flags, allowed, action_views = [], {}, {}
        for flag in flags:
            subject = flag["subject"]
            view = dict(label=LABELS[flag["id"]], value=flag["value"])
            if "basis" in flag:
                view["basis"] = flag["basis"]
                subject = json.dumps([subject, flag["basis"]])
            view["id"] = host["_id"](secret, str(project.canonical), flag["id"], subject)
            visible_flags.append(view)
        for finding in probe["findings"] if cfg["hostActions"]["value"] != "off" else []:
            entry = catalog.get(finding.get("catalog_id")) if isinstance(finding, dict) else None
            if (not entry or entry.get("needs_research") or finding.get("id") != entry["detect"].get("finding")
                    or not isinstance(finding.get("subject"), str) or not isinstance(finding.get("evidence"), dict)
                    or not finding["evidence"] or any(type(n) not in (int, float) or n < 0
                                                        or isinstance(n, float) and not math.isfinite(n)
                                                        for n in finding["evidence"].values())):
                raise ValueError("unsupported finding")
            selector = finding["subject"]
            if finding["id"] in ("indexed-output", "sprawl"):
                if not selector.startswith("/"):
                    raise ValueError("expected a path selector")
                try:
                    _, target = canonical_project(project.canonical, selector=selector,
                                                  allow_missing=finding["id"] == "indexed-output")
                except (ValueError, OSError):
                    if finding["id"] != "indexed-output":
                        raise
                    warnings.warn("dropping indexed-output finding with invalid selector")
                    continue
                selector = str(target)
                if finding["id"] == "sprawl" and target != project.canonical:
                    raise ValueError("invalid sprawl selector")
                if finding["id"] == "indexed-output":
                    matched = False
                    for row in probe["regenerable_dirs"]:
                        try:
                            if (isinstance(row, dict) and isinstance(row.get("path"), str)
                                    and (row["path"] == finding["subject"]
                                         or canonical_project(project.canonical, selector=row["path"])[1] == target)
                                    and row.get("size_bytes") == finding["evidence"].get("size_bytes")):
                                matched = True
                                break
                        except (ValueError, OSError):
                            continue
                    if not matched:
                        warnings.warn("dropping indexed-output finding without matching provenance")
                        continue
            elif (entry["id"], selector) not in (("low-disk", "project-volume"), ("inotify-limit", "inotify")) and not (
                    entry["id"] == "cloud-sync-repo" and selector in project.canonical.parts
                    and any(fnmatch.fnmatchcase(selector, pattern) for pattern in catalog_data["cloud_sync_names"])):
                raise ValueError("unsupported literal selector")
            ident = host["_id"](secret, str(project.canonical), entry["id"], selector)
            evidence = json.dumps(finding["evidence"], sort_keys=True, separators=(",", ":"), allow_nan=False)
            if len(evidence) > host["EVIDENCE_LIMIT"]:
                raise ValueError("oversized candidate evidence")
            if ident in allowed:
                existing = allowed[ident]
                provenance = existing["provenance"]
                if not isinstance(provenance, list):
                    provenance = [provenance]
                provenance.append(finding)
                existing["provenance"] = provenance
                if sum(finding["evidence"].values()) > sum(json.loads(existing["evidence"]).values()):
                    existing["evidence"] = evidence
                    action_views[ident]["evidence"] = list(finding["evidence"].values())
                continue
            allowed[ident] = dict(canonical_project=str(project.canonical), catalog_id=entry["id"],
                                 selector_key=selector, evidence=evidence,
                                 intents=(["suggest", "apply"] if not interactive and mode == "auto"
                                          and cfg["hostActions"]["value"] == "apply" else ["suggest"]),
                                 provenance=finding)
            action_views[ident] = dict(id=ident, label=entry["problem"], evidence=list(finding["evidence"].values()))
        # Compare stored evidence only after choosing the strongest finding across worktrees.
        for ident, candidate in list(allowed.items()):
            evidence = candidate["evidence"]
            old = rows.get(ident, {})
            # An unpublished suggestion must remain visible in a later preparation.
            if ((ident in unacknowledged or imported is not None and ident in imported) and not old.get("pending")
                    and old.get("status") == "open" and old.get("evidence") == evidence):
                old = {}
            if old.get("flaps", 0) >= 2 or (not old.get("pending") and (old.get("status") == "dismissed"
                    or old.get("status") in ("open", "done") and old.get("evidence") == evidence)):
                del allowed[ident]
                del action_views[ident]
        actions = list(action_views.values())
        if not visible_flags and not actions:
            if _check is not None:
                raise ValueError("empty interactive gate")
            return None
        generation = _check["generation"] if _check is not None else f"{generation + 1:020d}"
        receipt = dict(v=1, generation=generation, created=_check["created"] if _check else current.isoformat(),
                       channel="interactive" if interactive else "scheduled", baseline=baseline,
                       project=str(project.canonical), scope=scope,
                       identities=identities, policy=dict(mode=mode, **({} if interactive else {"schedule": cfg["schedule"]["value"]}),
                       window=block["window"] if block else None,
                       thresholds=block["thresholds"] if block else None, basis=block["basis"] if block else None, hostActions=cfg["hostActions"]["value"]),
                       comparison=snapshot, allowed=allowed, permission_provenance=block.get("permission_acceptance", []) if block else [])
        if retain and _check is None and state.get("acknowledged_generation") != f"{state['generation']:020d}":
            try:
                previous = _json(host["_read"](directory, "receipt-" + project.key + "-" + f"{state['generation']:020d}" + ".json", LIMIT), host)
                ignored = {"generation", "created", "signature", "view_sha256"}
                same = all(previous.get(name) == value for name, value in receipt.items() if name not in ignored)
                if (same and previous.get("channel") == "scheduled"
                        and hmac.compare_digest(previous.get("signature", ""), _signature(previous, secret))
                        and 0 <= (current - _stamp(previous["created"])).total_seconds() <= PROBE_AGE):
                    generation = previous["generation"]
                    receipt["generation"] = generation
                    receipt["created"] = previous["created"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
        view = dict(v=1, generation=generation, flags=visible_flags, actions=actions)
        public = _encode(view)
        receipt["view_sha256"] = hashlib.sha256(public).hexdigest()
        receipt["signature"] = _signature(receipt, secret)
        frozen = _encode(receipt)
        if max(len(frozen), len(public)) > LIMIT:
            raise ValueError("preparation exceeds size limit")
        if _check is not None:
            if receipt != _check:
                raise ValueError("preparation no longer matches live scope, policy or evidence")
            for kind, identity in identities.items():
                age = PROBE_AGE if kind == "probe" else REPORT_AGE if kind in ("report", "extract") else None
                if _read(Path(identity["path"]), host, current, age)[1] != identity:
                    raise ValueError("evidence changed during reconciliation")
            if canonical_project(project.canonical) != project.canonical:
                raise ValueError("project scope changed during reconciliation")
            return _complete(store, host, directory, state_name, state, receipt, imported)
        state["generation"] = int(generation)
        host["_replace"](directory, state_name, _encode(state))
        host["_replace"](directory, "receipt-" + project.key + "-" + generation + ".json", frozen)
        path = project.folder / ("friction-inputs-" + generation + ".json")
        with host["_directory"](path.parent, True) as output:
            host["_replace"](output, path.name, public)
        return (path, receipt) if retain else path


def acknowledge_scheduled(store, project, receipt, host, *, allow_superseded=False):
    with host["_directory"](store.friction, private=True) as directory, host["_locked"](directory, "prepare"):
        name = "prepare-" + project.key + ".json"
        state = _json(host["_read"](directory, name, LIMIT), host)
        receipt_generation = int(receipt["generation"])
        if (allow_superseded and state.get("project") == str(project.canonical)
                and type(state.get("generation")) is int and state["generation"] > receipt_generation):
            # Leave the newer preparation intact. Publication still needs to save its cutoff.
            return
        if (state.get("project") == str(project.canonical)
                and state.get("generation") == receipt_generation
                and state.get("acknowledged_generation") == receipt["generation"]
                and state.get("acknowledged") == receipt["comparison"]):
            return
        if (state.get("project") != str(project.canonical)
                or state.get("generation") != receipt_generation
                or state.get("acknowledged") != receipt["baseline"]):
            raise ValueError("scheduled comparison state changed")
        with host["_directory"](store.path.parent) as actions_directory:
            _, _, receipts = store._load(actions_directory)
        generations = receipts.get(str(project.canonical), {})
        if ("scheduled:" + receipt["generation"] not in generations
                or any(value == "pending" for row in generations.values() for value in row.values())):
            raise ValueError("pending or missing scheduled import")
        unpublished = state.setdefault("unpublished_suggestions", {})
        previous_ack = state.get("acknowledged_generation", "")
        for receipt_name, entries in generations.items():
            if (re.fullmatch(r"scheduled:[0-9]{20}", receipt_name)
                    and previous_ack < receipt_name[10:] < receipt["generation"]):
                unpublished.setdefault(receipt_name[10:], [ident for ident, status in entries.items()
                                                    if status == "terminal"])
        published = generations["scheduled:" + receipt["generation"]].keys()
        for generation in list(unpublished):
            unpublished[generation] = [ident for ident in unpublished[generation] if ident not in published]
            if not unpublished[generation] or generation == receipt["generation"]:
                del unpublished[generation]
        state["acknowledged"] = receipt["comparison"]
        state["acknowledged_generation"] = receipt["generation"]
        host["_replace"](directory, name, _encode(state))


def reconcile(audits, backups, project, inputs, cfg, current, canonical_project, project_key,
              actions=None):
    """Re-derive private authority before importing suggestions or acknowledging work."""
    host = runpy.run_path(str(Path(__file__).resolve().parent / "kaizen_friction_actions.py"))
    store = host["HostActions"](audits, backups, canonical_project, project_key)
    inputs = Path(inputs).expanduser().absolute()
    match = re.fullmatch(r"friction-inputs-([0-9]{20})\.json", inputs.name)
    if inputs.parent != project.folder or match is None:
        raise ValueError("inputs outside current project preparation scope")
    public, _ = _read(inputs, host)
    name = "receipt-" + project.key + "-" + match[1] + ".json"
    with host["_directory"](store.friction, private=True) as directory:
        receipt = _json(host["_read"](directory, name, LIMIT), host)
    if (receipt.get("project") != str(project.canonical) or receipt.get("generation") != match[1]
            or receipt.get("view_sha256") != hashlib.sha256(public).hexdigest()
            or not hmac.compare_digest(receipt.get("signature", ""), _signature(receipt, store._secret()))):
        raise ValueError("unmatched or forged preparation view or receipt")
    block = None
    if actions is not None:
        raw, _ = _read(Path(actions).expanduser().absolute(), host, limit=8192)
        block = raw.decode("utf-8").removesuffix("\n")
        requests = host["_requests"](block)
        if any(intent != "suggest" for intent in requests.values()):
            raise ValueError("interactive import permits suggestions only")

    def complete(store, host, directory, state_name, state, checked, imported):
        if block is not None:
            return store.import_actions(block, checked["allowed"], project.canonical,
                                        "interactive:" + checked["generation"])
        if imported is None:
            raise ValueError("acknowledgement requires a successful validated import")
        unpublished = state.get("unpublished_suggestions", {})
        for generation in list(unpublished):
            unpublished[generation] = [ident for ident in unpublished[generation] if ident not in imported]
            if not unpublished[generation]:
                del unpublished[generation]
        state["acknowledged"] = checked["comparison"]
        state["acknowledged_generation"] = checked["generation"]
        host["_replace"](directory, state_name, _encode(state))

    return prepare(audits, backups, project, Path(receipt["identities"]["report"]["path"]), cfg,
                   "propose-only", current, canonical_project, project_key, interactive=True,
                   _check=receipt, _complete=complete)


def import_scheduled(audits, backups, project, receipt, cfg, current, canonical_project, project_key, block, *, host=None):
    """Recheck the retained scheduled authority under the generation lock before import."""
    def complete(store, host, directory, state_name, state, checked, imported):
        result = store.import_actions(block, checked["allowed"], project.canonical,
                                      "scheduled:" + checked["generation"])
        if state.get("acknowledged_generation") != checked["generation"]:
            state.setdefault("unpublished_suggestions", {})[checked["generation"]] = [
                ident for ident, status in result.items() if status == "terminal"]
            host["_replace"](directory, state_name, _encode(state))
        return result
    return prepare(audits, backups, project, Path(receipt["identities"]["report"]["path"]), cfg,
                   receipt["policy"]["mode"], current, canonical_project, project_key,
                   _check=receipt, _complete=complete, host=host)


def scheduled_publication(audits, store, project, host, persist, ready, *, receipt=None, proposal=None,
                          digest=None, reviewed_at=None):
    """Track a publication until acknowledgement and review state are both durable."""
    name = "publication-" + project.key + ".json"
    with ExitStack() as stack:
        try:
            directory = stack.enter_context(host["_directory"](store.friction, receipt is not None, private=True))
            if receipt is None:
                marker = _json(host["_read"](directory, name, LIMIT), host)
        except FileNotFoundError:
            if receipt is not None:
                raise
            if not project.unknown:
                ready()
            return False
        if receipt is not None:
            host["_replace"](directory, name, _encode(dict(v=1, audits=str(audits), reviewed_at=reviewed_at,
                                                           generation=receipt["generation"], proposal=proposal.name,
                                                           sha256=digest)))
            return False
        generation, filename = marker.get("generation"), marker.get("proposal")
        if (not isinstance(generation, str) or not re.fullmatch(r"[0-9]{20}", generation)
                or not isinstance(filename, str) or not re.fullmatch(r"cycle-[0-9-]+\.md", filename)):
            raise ValueError("invalid publication marker")
        if marker.get("audits", str(audits)) != str(audits):
            return None  # Another audit root owns the generation until its publication is recovered.
        frozen = _json(host["_read"](directory, "receipt-" + project.key + "-" + generation + ".json", LIMIT), host)
        if (frozen.get("channel") != "scheduled" or frozen.get("project") != str(project.canonical)
                or frozen.get("generation") != generation
                or not hmac.compare_digest(frozen.get("signature", ""), _signature(frozen, store._secret()))):
            raise ValueError("invalid publication receipt")
        if "audits" not in marker and Path(frozen["identities"]["extract"]["path"]).parent.parent != audits:
            return None
        if project.unknown:
            raise ValueError("cannot recover publication with unknown project scope")
        cutoff = (_stamp(marker["reviewed_at"]) if "reviewed_at" in marker else
                  datetime.fromtimestamp(os.stat(name, dir_fd=directory, follow_symlinks=False).st_mtime, timezone.utc))
        if not ready():
            return False
        published = project.folder / filename
        if not published.exists():
            os.unlink(name, dir_fd=directory)
            return False
        raw, _ = _read(published, host)
        if hashlib.sha256(raw).hexdigest() != marker.get("sha256"):
            warnings.warn("published review changed before acknowledgement; preserving the edited report")
        acknowledge_scheduled(store, project, frozen, host, allow_superseded=True)
        persist(published, cutoff, frozen["identities"]["report"]["path"])
        os.unlink(name, dir_fd=directory)
        os.fsync(directory)
        return published
