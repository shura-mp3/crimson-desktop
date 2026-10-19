"""Import first in every Python test module: points HOME and all XDG dirs at a throw-away directory
*before* crimson.paths computes its constants, so tests can never touch the real user config."""

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

TOS = Path(__file__).resolve().parent.parent
for p in (str(TOS), str(TOS.parent)):   # crimson_tos and the Crimson Desktop `crimson` package
    if p not in sys.path:
        sys.path.insert(0, p)

if "CRIMSON_TOS_TEST_HOME" not in os.environ:
    ROOT = Path(tempfile.mkdtemp(prefix="ctos-ui-"))
    atexit.register(shutil.rmtree, ROOT, True)
    os.environ.update({
        "CRIMSON_TOS_TEST_HOME": str(ROOT), "HOME": str(ROOT),
        "XDG_CONFIG_HOME": str(ROOT / ".config"), "XDG_DATA_HOME": str(ROOT / ".local/share"),
        "XDG_STATE_HOME": str(ROOT / ".local/state"), "XDG_CACHE_HOME": str(ROOT / ".cache"),
        "XDG_RUNTIME_DIR": str(ROOT / "run"),
    })
    (ROOT / "run").mkdir(mode=0o700)
HOME = Path(os.environ["CRIMSON_TOS_TEST_HOME"])
