"""Download the full Wahapedia wh40k 10e CSV export into data/.

Saves raw bytes so the UTF-8 BOM and pipe delimiter are preserved exactly.
Run again to refresh the ruleset, then run wahapedia_importer.py.

Usage:
    python scripts/fetch_wahapedia.py
"""
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
BASE_URL = "https://wahapedia.ru/wh40k10ed/"

FILES = [
    "Factions.csv",
    "Source.csv",
    "Datasheets.csv",
    "Datasheets_models.csv",
    "Datasheets_wargear.csv",
    "Datasheets_options.csv",
    "Datasheets_unit_composition.csv",
    "Datasheets_models_cost.csv",
    "Datasheets_keywords.csv",
    "Datasheets_abilities.csv",
    "Datasheets_leader.csv",
    "Datasheets_stratagems.csv",
    "Datasheets_detachment_abilities.csv",
    "Datasheets_enhancements.csv",
    "Abilities.csv",
    "Detachments.csv",
    "Detachment_abilities.csv",
    "Enhancements.csv",
    "Stratagems.csv",
]

UA = "Mozilla/5.0 (codex-armorum data fetch)"


def fetch(name):
    url = BASE_URL + name
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    failures = []
    for name in FILES:
        dest = os.path.join(DATA_DIR, name)
        try:
            data = fetch(name)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {name}: {exc}")
            failures.append(name)
            continue
        if not data:
            print(f"FAIL {name}: empty response")
            failures.append(name)
            continue
        with open(dest, "wb") as fh:
            fh.write(data)
        # First line for a quick sanity check.
        first = data.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace").strip()
        rows = data.count(b"\n")
        print(f"OK   {name:38s} bytes={len(data):>9d} rows~={rows:>6d}")
        print(f"       header: {first}")
        time.sleep(0.4)  # be polite to the host

    if failures:
        print("\nFAILURES:", ", ".join(failures))
        sys.exit(1)
    print("\nAll files downloaded.")


if __name__ == "__main__":
    main()
