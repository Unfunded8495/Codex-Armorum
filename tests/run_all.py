"""Run the whole army-builder test suite.

  python tests/run_all.py            # engine + api + golden(verify) + fuzz
  python tests/run_all.py --ui       # also the Playwright UI journeys
  python tests/run_all.py --golden-build   # (re)bless golden snapshots first

Each layer is a standalone script run as a subprocess; this aggregates exit
codes. No server is left running. The engine layer needs no server or browser;
api/golden/fuzz use an in-process client on an isolated DB copy; --ui starts and
stops its own server.
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

LAYERS = [
    ("engine invariants", ["engine_invariants.py"]),
    ("api round-trip", ["api_roundtrip.py"]),
    ("multi-detachment", ["multi_detachment.py"]),
    ("golden master (verify)", ["golden_master.py"]),
    ("fuzz", ["fuzz_armies.py", "80"]),
]


def run_one(name, argv):
    print(f"\n{'=' * 64}\n>>> {name}\n{'=' * 64}")
    rc = subprocess.call([PY, os.path.join(HERE, argv[0])] + argv[1:], cwd=os.path.dirname(HERE))
    return rc


def main():
    if "--golden-build" in sys.argv:
        run_one("golden master (build)", ["golden_master.py", "--build"])

    layers = list(LAYERS)
    if "--ui" in sys.argv:
        layers.append(("ui journeys", ["ui_journeys.py"]))

    results = {}
    for name, argv in layers:
        results[name] = run_one(name, argv)

    print(f"\n{'=' * 64}\nSUITE SUMMARY\n{'=' * 64}")
    failed = 0
    for name, rc in results.items():
        print(f"  {'PASS' if rc == 0 else 'FAIL'}  {name}" + (f"  (exit {rc})" if rc else ""))
        failed += 1 if rc else 0
    print(f"\n{'ALL LAYERS PASS' if not failed else f'{failed} LAYER(S) FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
