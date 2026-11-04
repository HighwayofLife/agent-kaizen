"""Shared credential paths for scheduled permissions and backup preflight."""
import fnmatch
import os
from pathlib import Path


# Config patterns are top-level; project dotenv patterns cover every directory.
# Keep in sync with docs/scheduling.md and the independent permission test pin.
CREDENTIAL_PATHS = {
    "config": (".credentials.json", "auth.json", "*token*.json", "*secret*.json"),
    "home": (".ssh/**", ".aws/**", ".gnupg/**", ".netrc", ".config/gh/**", ".docker/config.json"),
    "project": ("**/.env", "**/.env.*"),
}


def credential_paths(project_dir=None):
    """Yield absolute glob patterns, including aliases and resolved targets."""
    roots = {
        "config": (Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser(),
                   Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()),
        "home": (Path.home(),),
        "project": (Path(project_dir) if project_dir is not None else Path.cwd(),),
    }
    for scope, patterns in CREDENTIAL_PATHS.items():
        for root in roots[scope]:
            for pattern in patterns:
                parts = pattern.split("/")
                first_glob = next((n for n, part in enumerate(parts) if "*" in part), len(parts))
                base = root.joinpath(*parts[:first_glob])
                suffix = "/" + "/".join(parts[first_glob:]) if first_glob < len(parts) else ""
                for resolve in (False, True):
                    yield root.resolve() if resolve else root, "/" + pattern
                    yield base.resolve() if resolve else base, suffix
                if scope == "config" and first_glob < len(parts):
                    for match in root.glob(pattern):
                        yield match.resolve(), ""


def matches_parts(parts, patterns):
    """Match glob components without allowing * to cross directories."""
    if not patterns:
        return not parts
    if patterns[0] == "**":
        return (matches_parts(parts, patterns[1:])
                or bool(parts) and matches_parts(parts[1:], patterns))
    return (bool(parts) and fnmatch.fnmatchcase(parts[0], patterns[0])
            and matches_parts(parts[1:], patterns[1:]))


def is_credential(path):
    path = Path(path).expanduser().absolute()
    candidates = (path, path.resolve())
    for base, suffix in credential_paths():
        for candidate in candidates:
            try:
                relative = candidate.relative_to(base.absolute())
            except ValueError:
                continue
            # Base paths are literal, even when directory names contain glob syntax.
            if matches_parts(relative.parts, tuple(suffix.lstrip("/").split("/")) if suffix else ()):
                return True
    return False
