"""Deterministic comparison of scoped friction evidence.

Preparation computes a proposed snapshot; only a successful reconciliation may
persist it as acknowledged state.
"""

import json
import math
import fnmatch
import hashlib
import os
from pathlib import Path
import re
import runpy
import stat
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
    seen = set()
    new = []
    for flag in flags:
        if (not isinstance(flag, dict) or not isinstance(flag.get("id"), str)
                or not flag["id"] or not isinstance(flag.get("subject"), str)):
            raise ValueError("invalid flag identity")
        value = flag.get("value")
        if (type(value) not in (int, float) or value <= 0
                or (isinstance(value, float) and not math.isfinite(value))):
            raise ValueError("invalid flag value")
        ident = json.dumps([flag["id"], flag["subject"]], ensure_ascii=True, separators=(",", ":"))
        if ident in seen:
            raise ValueError("duplicate flag identity")
        seen.add(ident)
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


def _read(path, host, current=None, age=None):
    """No symlink components, devices, writable foreign files or unbounded reads."""
    with host["_directory"](path.parent) as directory:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or info.st_mode & 0o022):
                raise ValueError("unsafe evidence file")
            host["_check_acl"](stream.fileno(), "evidence")
            raw = stream.read(LIMIT + 1)
            after = os.fstat(stream.fileno())
    if (len(raw) > LIMIT or (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
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
            raise ValueError("missing or ambiguous audit marker")
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


def prepare(audits, backups, project, report, cfg, mode, current, canonical_project, project_key):
    """Freeze a private receipt and a redacted view; never import, verify or ack."""
    if cfg["enabled"]["value"] is False or cfg["friction"]["value"] == "off":
        return None
    if mode not in ("propose-only", "auto"):
        raise ValueError("unsupported preparation mode")
    if (project.unknown or canonical_project(project.canonical) != project.canonical
            or project.key != project_key(project.canonical)
            or project.folder != audits / "projects" / project.key):
        raise ValueError("noncanonical preparation scope")
    here = Path(__file__).resolve().parent
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
                    evidence = _evidence(candidate, audits, project, cfg, current, host)
                    candidates.append((evidence[2]["report"]["mtime_ns"], candidate.name, evidence))
                except (OSError, ValueError, KeyError, TypeError):
                    continue
        if not candidates:
            raise ValueError("no fresh scoped audit")
        scope, block, identities = max(candidates, key=lambda item: item[:2])[2]
    if block is None:
        return None
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
    rows = {row["id"]: row for row in store.scoped(project.canonical)}
    catalog_path = next((here / name for name in ("kaizen-friction-catalog.json", "friction-catalog.json")
                         if (here / name).is_file()), None)
    catalog_raw, identities["catalog"] = _read(catalog_path, host)
    catalog_data = _json(catalog_raw, host)
    catalog = {row["id"]: row for row in catalog_data["actions"]}
    with host["_directory"](store.friction, True, private=True) as directory, host["_locked"](directory, "prepare"):
        state_name = "prepare-" + project.key + ".json"
        try:
            state = _json(host["_read"](directory, state_name, LIMIT), host)
        except FileNotFoundError:
            state = {"v": 1, "project": str(project.canonical), "generation": 0, "acknowledged": {}}
        generation = state.get("generation")
        if (state.get("project") != str(project.canonical) or type(generation) is not int
                or not 0 <= generation < 10**20 - 1):
            raise ValueError("invalid preparation generation")
        cohort = json.dumps([str(project.canonical), scope], sort_keys=True, separators=(",", ":"))
        if (not isinstance(block.get("flags"), list)
                or any(not isinstance(flag, dict) or flag.get("id") not in LABELS
                       or not isinstance(flag.get("subject"), str) or len(flag["subject"]) > 4096
                       for flag in block["flags"])):
            raise ValueError("unsupported flag")
        flags, snapshot = compare_flags(cohort, block["window"], block["thresholds"], block["basis"],
                                        block.get("flags"), state.get("acknowledged"))
        secret = store._secret(create=True)
        visible_flags, allowed, actions = [], {}, []
        for flag in flags:
            ident = host["_id"](secret, str(project.canonical), flag["id"], flag["subject"])
            visible_flags.append(dict(id=ident, label=LABELS[flag["id"]], value=flag["value"]))
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
                _, target = canonical_project(project.canonical, selector=selector)
                if str(target) != selector:
                    raise ValueError("noncanonical selector")
                if finding["id"] == "sprawl" and target != project.canonical:
                    raise ValueError("invalid sprawl selector")
                if finding["id"] == "indexed-output" and not any(
                        isinstance(row, dict) and row.get("path") == selector
                        and row.get("size_bytes") == finding["evidence"].get("size_bytes")
                        for row in probe["regenerable_dirs"]):
                    raise ValueError("missing regenerable-directory provenance")
            elif (entry["id"], selector) not in (("low-disk", "project-volume"), ("inotify-limit", "inotify")) and not (
                    entry["id"] == "cloud-sync-repo" and selector in project.canonical.parts
                    and any(fnmatch.fnmatchcase(selector, pattern) for pattern in catalog_data["cloud_sync_names"])):
                raise ValueError("unsupported literal selector")
            ident = host["_id"](secret, str(project.canonical), entry["id"], selector)
            evidence = json.dumps(finding["evidence"], sort_keys=True, separators=(",", ":"), allow_nan=False)
            if len(evidence) > host["EVIDENCE_LIMIT"]:
                raise ValueError("oversized candidate evidence")
            old = rows.get(ident, {})
            if not old.get("pending") and (old.get("status") == "dismissed"
                    or old.get("status") in ("open", "done") and old.get("evidence") == evidence):
                continue
            if ident in allowed:
                raise ValueError("duplicate candidate identity")
            allowed[ident] = dict(canonical_project=str(project.canonical), catalog_id=entry["id"],
                                 selector_key=selector, evidence=evidence, intents=["suggest"], provenance=finding)
            actions.append(dict(id=ident, label=entry["problem"], evidence=list(finding["evidence"].values())))
        if not visible_flags and not actions:
            return None
        generation = f"{generation + 1:020d}"
        receipt = dict(v=1, generation=generation, created=current.isoformat(), project=str(project.canonical), scope=scope,
                       identities=identities, policy=dict(mode=mode, window=block["window"],
                       thresholds=block["thresholds"], basis=block["basis"], hostActions=cfg["hostActions"]["value"]),
                       comparison=snapshot, allowed=allowed, permission_provenance=block.get("permission_acceptance", []))
        view = dict(v=1, generation=generation, flags=visible_flags, actions=actions)
        encode = lambda value: (json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
        frozen, public = encode(receipt), encode(view)
        if max(len(frozen), len(public)) > LIMIT:
            raise ValueError("preparation exceeds size limit")
        state["generation"] = int(generation)
        host["_replace"](directory, state_name, encode(state))
        host["_replace"](directory, "receipt-" + project.key + "-" + generation + ".json", frozen)
        path = project.folder / ("friction-inputs-" + generation + ".json")
        with host["_directory"](path.parent, True) as output:
            host["_replace"](output, path.name, public)
        return path
