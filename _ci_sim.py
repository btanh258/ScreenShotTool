"""Reproduce the CI condition for the Escape tests as closely as possible.

GitHub's windows runner has a desktop session, but the test process window is
not the foreground window and there is no user moving focus around. The closest
local approximation: run the suite exactly as CI does (fresh interpreter, no
config file, the process never focused manually) but ALSO verify the mechanism
bind_all relies on - that a focus owner exists - rather than trusting it.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE

# 1. Remove any real config so the CI condition holds.
cfg = REPO / "ScreenShotTool_config.json"
backup = None
if cfg.exists():
    backup = tempfile.mktemp(suffix=".json")
    os.replace(cfg, backup)
    print(f"[setup] moved {cfg.name} away")

try:
    # 2. Run only the reachability tests, as CI does.
    result = subprocess.run(
        [sys.executable, "-m", "unittest",
         "tests.test_ui_smoke.EditorReachabilityTests", "-v"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=180,
    )
    tail = "\n".join(result.stdout.strip().splitlines()[-6:])
    print(tail)
    print("exit:", result.returncode)
    ok = result.returncode == 0
finally:
    if backup:
        os.replace(backup, cfg)
        print("[teardown] config restored")

sys.exit(0 if ok else 1)
