"""Test package setup: the unit suite must never read or write the real saves/ folder.

Runs before any test module is collected, for both `python -m unittest discover -s tests` and
`python -m unittest tests.test_x`. Every save_manager call then lands in a throwaway folder.
"""
import atexit
import os
import shutil
import sys
import tempfile

_SANDBOX = tempfile.mkdtemp(prefix="hardwood_test_saves_")
os.environ["HARDWOOD_SAVES_DIR"] = _SANDBOX
atexit.register(shutil.rmtree, _SANDBOX, ignore_errors=True)

# If save_manager was imported before this package (unusual), redirect it as well.
if "core.save_manager" in sys.modules:
    sys.modules["core.save_manager"].SAVES_DIR = _SANDBOX
