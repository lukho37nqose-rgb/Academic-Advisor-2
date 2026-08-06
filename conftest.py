r"""
Root conftest.py - workspace-level pytest configuration.

On Windows the default pytest temp root (AppData\Local\Temp\pytest-of-<user>)
can become ACL-locked after a crashed run, causing every test that uses
tmp_path to fail at setup with PermissionError [WinError 5].

This hook redirects tmp_path to a fresh project-local directory that is excluded
from version control. Reusing the same base can inherit a stale Windows ACL lock
after an interrupted run, so each pytest process receives its own base path.
"""

import os
import sys


def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    if sys.platform == "win32" and config.option.basetemp is None:
        parent = os.path.join(os.path.dirname(__file__), ".pytest-runs")
        os.makedirs(parent, exist_ok=True)
        basetemp = os.path.join(parent, f"run-{os.getpid()}")
        config.option.basetemp = basetemp
