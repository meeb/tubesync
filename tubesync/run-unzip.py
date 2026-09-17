#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import time

destination = sys.argv[1]
archive = sys.argv[2]

args = [
    "unzip",
    "-q",
    "-o",
    archive,
    "-d",
    destination,
]

started = time.monotonic()

p = subprocess.Popen(
    args,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

print(json.dumps({
    "event": "spawn",
    "pid": p.pid,
    "args": args,
}), flush=True)

stdout, stderr = p.communicate()

elapsed = time.monotonic() - started

result = {
    "event": "reaped",
    "pid": p.pid,
    "returncode": p.returncode,
    "elapsed_seconds": elapsed,
    "stdout": stdout,
    "stderr": stderr,
    "wait_completed": True,
}

print(json.dumps(result), flush=True)

# Preserve unzip's normal exit status.
sys.exit(p.returncode if p.returncode >= 0 else 128 - p.returncode)
