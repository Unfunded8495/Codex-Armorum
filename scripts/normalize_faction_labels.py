"""One-time migration: normalise denormalised faction_label strings in
model_catalogue_manual.json onto their canonical display form.

Legacy spreadsheet imports seeded faction_label from the worksheet tab title
while newer add/edit paths wrote the data store's canonical faction name, so a
single faction_id could carry two different label strings (e.g. "Orks" vs
"Xenos - Orks"). This rewrites every known drift variant using the shared
FACTION_LABEL_ALIASES map so the stored data matches what the app renders.

The alias map lives in catalogue_review.py — this script is just the data pass.
Safe to re-run; it only rewrites labels that appear in the alias map. Pass
--dry-run to preview without writing.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from catalogue_review import (  # noqa: E402
    MANUAL_PATH,
    canonical_faction_label,
    _load_json,
    _write_json,
)


def main(dry_run=False):
    data = _load_json(MANUAL_PATH, {"model_releases": []})
    records = data.get("model_releases", [])
    changes = collections.Counter()

    for record in records:
        old = record.get("faction_label", "")
        new = canonical_faction_label(old)
        if new != old:
            record["faction_label"] = new
            changes[(old, new)] += 1

    total = sum(changes.values())
    if not total:
        print("No faction_label changes needed.")
        return

    for (old, new), count in sorted(changes.items()):
        print(f"  {count:4d}  {old!r} -> {new!r}")
    print(f"{'Would rewrite' if dry_run else 'Rewriting'} {total} record(s) "
          f"of {len(records)} releases.")

    if dry_run:
        return
    _write_json(MANUAL_PATH, data)
    print(f"Wrote {MANUAL_PATH}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
