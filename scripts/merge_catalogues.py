"""One-time migration: merge model_catalogue.json into model_catalogue_manual.json.

Run from the project root:
    python scripts/merge_catalogues.py

After running, model_catalogue_manual.json becomes the single source of truth.
The original model_catalogue.json is archived (not deleted) as model_catalogue_imported_archive.json.
"""
import json
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")
CATALOGUE_PATH = os.path.join(DATA_DIR, "model_catalogue.json")
MANUAL_PATH    = os.path.join(DATA_DIR, "model_catalogue_manual.json")
ARCHIVE_PATH   = os.path.join(DATA_DIR, "model_catalogue_imported_archive.json")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def main():
    if not os.path.exists(CATALOGUE_PATH):
        print(f"ERROR: {CATALOGUE_PATH} not found — nothing to merge.")
        return
    if not os.path.exists(MANUAL_PATH):
        print(f"ERROR: {MANUAL_PATH} not found.")
        return

    main_doc   = load_json(CATALOGUE_PATH)
    manual_doc = load_json(MANUAL_PATH)

    main_records   = main_doc.get("model_releases", [])
    manual_records = manual_doc.get("model_releases", [])

    main_ids = {r["id"] for r in main_records}
    manual_only = [r for r in manual_records if r["id"] not in main_ids]
    overlapping  = [r for r in manual_records if r["id"] in main_ids]

    print(f"Auto-imported records : {len(main_records)}")
    print(f"Manual-only records   : {len(manual_only)}")
    if overlapping:
        print(f"Overlapping IDs (manual takes precedence): {len(overlapping)}")
        for r in overlapping:
            print(f"  {r['id']}")

    # Build merged list: auto-imported first (sorted as-is), manual-only appended.
    # For any ID in both files the auto-imported copy is kept (manual overrides
    # would already be in the resolutions file).
    merged = list(main_records) + manual_only

    print(f"Total after merge     : {len(merged)}")

    # Archive original before overwriting
    shutil.copy2(CATALOGUE_PATH, ARCHIVE_PATH)
    print(f"\nArchived original to  : {ARCHIVE_PATH}")

    manual_doc["model_releases"] = merged
    manual_doc["notes"] = (
        "Single source of truth for all model releases. "
        "Merged from model_catalogue.json (auto-import) and model_catalogue_manual.json "
        "on 2026-06-02. model_catalogue.json is now archived and no longer read by the app."
    )
    write_json(MANUAL_PATH, manual_doc)
    print(f"Written merged file to: {MANUAL_PATH}")
    print("\nDone. You can now run the app — it reads only model_catalogue_manual.json.")


if __name__ == "__main__":
    main()
