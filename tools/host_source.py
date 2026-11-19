"""Copy worktree files for local host installation checks."""
from pathlib import Path
import shutil


STATUS_LINKS = {
    'scripts/kaizen-status-git/sha1/info/attributes': Path('/dev/stdin'),
    'scripts/kaizen-status-git/sha256/info/attributes': Path('/dev/stdin'),
    'scripts/kaizen-status-git/sha256/config': Path('config.patterns'),
}


def copy_worktree_files(source, destination, listing):
    for name in set(listing.split('\0')) - {''}:
        src, dst = source / name, destination / name
        parts = Path(name).parts
        if any(source.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts))):
            continue
        if src.is_symlink():
            # The isolated Git template needs these exact links in a local export.
            link = STATUS_LINKS.get(name)
            if link is not None and src.readlink() == link:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.symlink_to(link)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
