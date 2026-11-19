"""Shared fixtures for tests that install or cache a copy of the plugin."""
import shutil


def copy_plugin_tree(source, target, *, ignore=None):
    # The read-only Git template contains attributes links to /dev/stdin.
    return shutil.copytree(source, target, symlinks=True, ignore=ignore)
