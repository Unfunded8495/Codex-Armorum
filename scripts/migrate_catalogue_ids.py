"""
Migrate catalogue model IDs from slug format (adepta-sororitas-2025-01-adjuror)
to sequential numeric format (MD-50001).

Updates:
  - data/model_catalogue_manual.json   — the `id` field on every record
  - data/model_catalogue_resolutions.json — `catalogue_model_id` fields
  - data/model_catalogue_issues.json   — `catalogue_model_id` fields
  - data/model_catalogue_images.json   — `catalogue_model_id` + `local_path`
  - cache/images/catalogue/            — physical file renames
  - collection.db                      — minis + custom_box_set_contents tables

Run from the project root:
    python scripts/migrate_catalogue_ids.py
"""

import json
import os
import re
import shutil
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MANUAL_PATH       = os.path.join(BASE, "data", "model_catalogue_manual.json")
RESOLUTIONS_PATH  = os.path.join(BASE, "data", "model_catalogue_resolutions.json")
ISSUES_PATH       = os.path.join(BASE, "data", "model_catalogue_issues.json")
IMAGES_PATH       = os.path.join(BASE, "data", "model_catalogue_images.json")
IMAGE_DIR         = os.path.join(BASE, "cache", "images", "catalogue")
DB_PATH           = os.path.join(BASE, "collection.db")

START = 50001


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def build_mapping(releases):
    mapping = {}
    counter = START
    for r in releases:
        old_id = r.get("id", "")
        if old_id and old_id not in mapping:
            mapping[old_id] = f"MD-{counter:05d}"
            counter += 1
    return mapping


def migrate_manual(mapping):
    doc = load(MANUAL_PATH)
    for r in doc.get("model_releases", []):
        old = r.get("id")
        if old in mapping:
            r["id"] = mapping[old]
    save(MANUAL_PATH, doc)
    print(f"  model_catalogue_manual.json — {len(mapping)} IDs updated")


def migrate_json_field(path, field, mapping, label):
    doc = load(path)
    if doc is None:
        print(f"  {label} — not found, skipping")
        return
    changed = 0
    items = doc.get(list(doc.keys())[-1], [])
    for key in doc:
        if isinstance(doc[key], list):
            for item in doc[key]:
                if isinstance(item, dict) and field in item and item[field] in mapping:
                    item[field] = mapping[item[field]]
                    changed += 1
    save(path, doc)
    print(f"  {label} — {changed} references updated")


def migrate_images(mapping):
    doc = load(IMAGES_PATH)
    if doc is None:
        print("  model_catalogue_images.json — not found, skipping")
        return

    renamed_files = 0
    updated_records = 0

    for row in doc.get("images", []):
        old_id = row.get("catalogue_model_id", "")
        if old_id not in mapping:
            continue
        new_id = mapping[old_id]
        row["catalogue_model_id"] = new_id
        updated_records += 1

        local_path = row.get("local_path", "")
        if not local_path:
            continue

        filename = os.path.basename(local_path)
        if filename.startswith(old_id):
            remainder = filename[len(old_id):]
            new_filename = new_id + remainder
        else:
            new_filename = new_id + os.path.splitext(filename)[1]

        old_file = os.path.join(BASE, local_path)
        new_file = os.path.join(IMAGE_DIR, new_filename)
        new_local = "cache/images/catalogue/" + new_filename
        row["local_path"] = new_local

        if os.path.exists(old_file):
            try:
                shutil.move(old_file, new_file)
                renamed_files += 1
            except OSError as e:
                print(f"    WARNING: could not rename {filename} -> {new_filename}: {e}")
        else:
            print(f"    WARNING: image file not found: {local_path}")

    save(IMAGES_PATH, doc)
    print(f"  model_catalogue_images.json — {updated_records} records, {renamed_files} files renamed")


def migrate_database(mapping):
    if not os.path.exists(DB_PATH):
        print("  collection.db — not found, skipping")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        total = 0
        for table in ("minis", "custom_box_set_contents"):
            cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not cur.fetchone():
                continue
            for old_id, new_id in mapping.items():
                cur.execute(
                    f"UPDATE {table} SET catalogue_model_id=? WHERE catalogue_model_id=?",
                    (new_id, old_id),
                )
                total += cur.rowcount
        conn.commit()
        print(f"  collection.db — {total} rows updated")
    finally:
        conn.close()


def main():
    print("Loading catalogue...")
    doc = load(MANUAL_PATH)
    if not doc:
        print("ERROR: could not load model_catalogue_manual.json")
        sys.exit(1)

    releases = doc.get("model_releases", [])
    mapping = build_mapping(releases)
    print(f"Built mapping: {len(mapping)} IDs, MD-{START:05d} to MD-{START + len(mapping) - 1:05d}\n")

    print("Migrating files...")
    migrate_manual(mapping)
    migrate_json_field(RESOLUTIONS_PATH, "catalogue_model_id", mapping, "model_catalogue_resolutions.json")
    migrate_json_field(ISSUES_PATH, "catalogue_model_id", mapping, "model_catalogue_issues.json")
    migrate_images(mapping)
    migrate_database(mapping)

    print("\nDone. Save the mapping below if you need it for reference:")
    for old, new in list(mapping.items())[:5]:
        print(f"  {old} -> {new}")
    print(f"  ... ({len(mapping)} total)")


if __name__ == "__main__":
    main()
