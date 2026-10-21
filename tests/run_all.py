"""Run HYPOLAB's tests one file at a time, each in its own Python process (1.10.1).

    python tests/run_all.py            # every test file
    python tests/run_all.py phase8 web # only files whose name contains one of the words

`python -m unittest discover -s tests` still works, but it keeps every sandbox market of every file in ONE process
(about 6 GB at the end): on an 8 GB laptop that can be killed for memory. One process per file stays under ~1.5 GB.
Your real ~/.hypolab is never touched: each file gets its own empty HYPOLAB_HOME.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    words = list(sys.argv[1:] if argv is None else argv)
    files = sorted(p for p in HERE.glob("test_*.py") if not words or any(w in p.stem for w in words))
    total = failed = skipped = 0
    bad = []
    t0 = time.time()
    for p in files:
        env = dict(os.environ, HYPOLAB_HOME=tempfile.mkdtemp(prefix="hypolab_test_"))
        t = time.time()
        r = subprocess.run([sys.executable, "-W", "ignore", "-m", "unittest", f"tests.{p.stem}"], cwd=HERE.parent,
                           env=env, capture_output=True, text=True)
        out = r.stderr
        ran = int((re.search(r"Ran (\d+) test", out) or [0, 0])[1])
        sk = int((re.search(r"skipped=(\d+)", out) or [0, 0])[1])
        total, skipped = total + ran, skipped + sk
        ok = r.returncode == 0
        print(f"{'ok  ' if ok else 'FAIL'} {p.stem:<28} {ran:>4} tests{f', {sk} skipped' if sk else ''}"
              f"  {time.time() - t:5.1f} s", flush=True)
        if not ok:
            failed += 1
            bad.append((p.stem, out))
    for name, out in bad:
        print(f"\n===== {name}\n{out[-4000:]}")
    print(f"\n{total} tests in {len(files)} files, {time.time() - t0:.0f} s: "
          + ("all passed" if not failed else f"{failed} file(s) FAILED") + (f" ({skipped} skipped)" if skipped else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
