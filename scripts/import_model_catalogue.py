"""Import the 40K model release workbook into repo data files.

The output is source data only. The Flask app can read it later without needing
openpyxl at runtime.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher

import openpyxl


BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")
DEFAULT_WORKBOOK = os.path.join(
    os.path.expanduser("~"),
    "Downloads",
    "40K_-_Current_model_range_release_dates_Updated.xlsx",
)

IGNORED_SHEETS = {
    "Table of Contents",
    "Data - All Factions",
    "Data - All Factions - Coloured ",
    "40K Editions",
}

FACTION_BY_SHEET = {
    "Craftworlds": "AE",
    "Drukhari": "DRU",
    "Harlequins": "AE",
    "Ynnari": "AE",
    "Genestealer Cult": "GC",
    "Tyranids": "TYR",
    "Necrons": "NEC",
    "Orks": "ORK",
    "Tau Empire": "TAU",
    "Space Marines": "SM",
    "Supplement Marines": "SM",
    "Blood Angels": "SM",
    "Dark Angels": "SM",
    "Space Wolves": "SM",
    "Deathwatch": "SM",
    "Grey Knights": "GK",
    "Astra Militarum": "AM",
    "Adepta Sororitas": "AS",
    "Adeptus Custodes": "AC",
    "Adeptus Mechanicus": "AdM",
    "Imperial Assassins": "AoI",
    "Inquisition": "AoI",
    "Imperial Knights": "QI",
    "Chaos Daemons": "CD",
    "Chaos Knights": "QT",
    "Chaos Space Marines": "CSM",
    "Death Guard": "DG",
    "Thousand Sons": "TS",
    "World Eaters": "WE",
    "Emperors Children": "EC",
    "Emperor's Children": "EC",
}


def slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return value or "unknown"


def read_pipe_csv(name: str) -> list[dict[str, str]]:
    with open(os.path.join(DATA_DIR, name), encoding="utf-8-sig", newline="") as fh:
        return [
            {k: (v or "").strip() for k, v in row.items() if k}
            for row in csv.DictReader(fh, delimiter="|")
        ]


def normalise_name(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace("\u2019", "'").replace("\ufffd", "")
    text = text.replace("t'au", "tau").replace("t\u2019au", "tau")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"\b(primaris|adeptus|astra|space marine|space marines)\b", " ", text)
    # Strip chaos-god qualifiers so "Daemonettes of Slaanesh" matches "Daemonettes"
    text = re.sub(r"\bof\s+(?:slaanesh|khorne|nurgle|tzeentch|chaos)\b", " ", text)
    # Normalise Shalaxi spelling variant (Hellbane vs Helbane appear in different sources)
    text = text.replace("hellbane", "helbane")
    # Normalise "Sorcerer Lord" \u2192 "Sorcerer" so terminator-armour variants match across factions
    text = re.sub(r"\bsorcerer lord\b", "sorcerer", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    drop = {
        "a",
        "an",
        "and",
        "kit",
        "model",
        "models",
        "of",
        "or",
        "set",
        "the",
        "with",
    }
    _no_strip_s = {"chaos", "bonus", "nexus", "virus", "status", "focus", "class"}
    words = []
    for word in text.split():
        if word in drop:
            continue
        if len(word) > 3 and word.endswith("s") and word not in _no_strip_s:
            word = word[:-1]
        words.append(word)
    return " ".join(words)


def release_date_parts(value) -> tuple[str, int | None]:
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m"), value.year
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m"), value.year
    text = str(value or "").strip()
    match = re.search(r"((?:19|20)\d{2})(?:[-/](\d{1,2}))?", text)
    if not match:
        return "", None
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    return f"{year:04d}-{month:02d}", year


def is_finecast(material: str) -> bool:
    return "finecast" in str(material or "").lower().replace(" ", "")


def status_from_fields(note: str, extra_flags: list[str]) -> str:
    text = " ".join([note or "", *extra_flags]).lower()
    if "discontinued" in text:
        return "discontinued"
    return "current_or_unknown"


def build_datasheet_index() -> tuple[dict[str, list[dict]], list[str], dict[str, dict]]:
    datasheets = read_pipe_csv("Datasheets.csv")
    model_rows = read_pipe_csv("Datasheets_models.csv")
    comp_rows = read_pipe_csv("Datasheets_unit_composition.csv")
    ds_by_id = {row["id"]: row for row in datasheets if row.get("id")}
    index: dict[str, list[dict]] = defaultdict(list)

    def add(name: str, ds: dict, source: str, raw_name: str | None = None):
        key = normalise_name(name)
        if not key or ds.get("virtual", "").lower() == "true":
            return
        entry = {
            "datasheet_id": ds["id"],
            "datasheet_name": ds.get("name", ""),
            "faction_id": ds.get("faction_id", ""),
            "matched_name": raw_name or name,
            "matched_from": source,
        }
        if entry not in index[key]:
            index[key].append(entry)

    for ds in datasheets:
        if ds.get("id"):
            add(ds.get("name", ""), ds, "datasheet")

    for row in model_rows:
        ds = ds_by_id.get(row.get("datasheet_id", ""))
        if ds:
            add(row.get("name", ""), ds, "statline", row.get("name", ""))

    for row in comp_rows:
        ds = ds_by_id.get(row.get("datasheet_id", ""))
        if not ds:
            continue
        desc = re.sub(r"<[^>]+>", " ", row.get("description", ""))
        desc = re.sub(r"^\s*(?:or:?\s*)?\d+(?:\s*[-\u2013]\s*\d+)?\s+", "", desc).strip()
        if desc and not re.fullmatch(r"or:?", desc, re.I):
            add(desc, ds, "composition", desc)

    return index, list(index.keys()), ds_by_id


def find_candidate_models(
    name: str,
    expected_faction_id: str,
    index: dict[str, list[dict]],
    keys: list[str],
) -> list[dict]:
    names = [name]
    if "/" in name:
        names.extend(part.strip() for part in name.split("/") if part.strip())

    seen = set()
    candidates = []
    for raw in names:
        target = normalise_name(raw)
        if not target:
            continue
        exact = index.get(target, [])
        for entry in exact:
            add_candidate(candidates, seen, entry, 1.0, "exact", expected_faction_id)

        target_tokens = set(target.split())
        for key in keys:
            key_tokens = set(key.split())
            if not target_tokens or not key_tokens:
                continue
            score = 2 * len(target_tokens & key_tokens) / (len(target_tokens) + len(key_tokens))
            if score >= 0.72:
                for entry in index[key]:
                    add_candidate(candidates, seen, entry, score, "token", expected_faction_id)

            ratio = SequenceMatcher(None, target, key).ratio()
            if ratio >= 0.82:
                for entry in index[key]:
                    add_candidate(candidates, seen, entry, ratio, "fuzzy", expected_faction_id)

    candidates = collapse_candidate_datasheets(candidates)
    candidates.sort(
        key=lambda item: (
            item["confidence"],
            item["faction_id"] == expected_faction_id,
            item["match_method"] == "exact",
        ),
        reverse=True,
    )
    return candidates[:8]


def collapse_candidate_datasheets(candidates: list[dict]) -> list[dict]:
    best_by_datasheet = {}
    source_rank = {"datasheet": 3, "composition": 2, "statline": 1}
    method_rank = {"exact": 3, "token": 2, "fuzzy": 1}
    for item in candidates:
        did = item["datasheet_id"]
        current = best_by_datasheet.get(did)
        rank = (
            item["confidence"],
            method_rank.get(item["match_method"], 0),
            source_rank.get(item["matched_from"], 0),
        )
        if not current:
            best_by_datasheet[did] = item
            continue
        current_rank = (
            current["confidence"],
            method_rank.get(current["match_method"], 0),
            source_rank.get(current["matched_from"], 0),
        )
        if rank > current_rank:
            best_by_datasheet[did] = item
    return list(best_by_datasheet.values())


def add_candidate(
    candidates: list[dict],
    seen: set[tuple[str, str]],
    entry: dict,
    confidence: float,
    method: str,
    expected_faction_id: str,
) -> None:
    key = (entry["datasheet_id"], entry["matched_from"])
    if key in seen:
        return
    seen.add(key)
    item = dict(entry)
    item["confidence"] = round(confidence, 3)
    item["match_method"] = method
    item["faction_match"] = not expected_faction_id or item["faction_id"] == expected_faction_id
    candidates.append(item)


def classify_issue(record: dict, candidates: list[dict]) -> str | None:
    text = f"{record['name']} {record.get('note', '')}".lower()
    if record.get("faction_label") == "Supplement Marines":
        return "supplement_row"
    if "codex" in text:
        return "book_or_codex"
    if any(term in text for term in ("upgrade", "sprue", "transfer", "head")):
        return "upgrade_or_sprue"
    if any(term in text for term in ("kill team", "warhammer 40,000", "warhammer 40000", "box", "army set", "battleforce")):
        return "box_or_product"
    if not candidates:
        return "no_datasheet_candidate"
    confident = [c for c in candidates if c["confidence"] >= 0.86 and c["faction_match"]]
    if len(confident) > 1:
        return "ambiguous_datasheet_candidate"
    if not confident:
        if any(c["confidence"] >= 0.86 for c in candidates):
            return "faction_mismatch_candidate"
        return "low_confidence_candidate"
    return None


def recommended_action(issue_type: str) -> str:
    return {
        "ambiguous_datasheet_candidate": "choose_datasheet",
        "book_or_codex": "exclude_book_or_confirm_model",
        "box_or_product": "confirm_model_release_context",
        "faction_mismatch_candidate": "confirm_cross_faction_link",
        "low_confidence_candidate": "confirm_candidate_or_add_alias",
        "no_datasheet_candidate": "add_alias_or_mark_no_current_datasheet",
        "supplement_row": "exclude_supplement_row",
        "upgrade_or_sprue": "mark_accessory_or_link_parent_model",
    }.get(issue_type, "review")


def write_review_csv(path: str, issues: list[dict]) -> None:
    candidate_slots = 4
    fields = [
        "catalogue_model_id",
        "issue_type",
        "recommended_action",
        "resolved_action",
        "resolved_catalogue_type",
        "resolved_datasheet_ids",
        "resolved_notes",
        "name",
        "faction_label",
        "expected_faction_id",
        "release_date",
        "material",
        "note",
        "flags",
        "source_sheet",
        "source_row",
    ]
    for idx in range(1, candidate_slots + 1):
        fields.extend([
            f"candidate_{idx}_datasheet_id",
            f"candidate_{idx}_datasheet_name",
            f"candidate_{idx}_faction_id",
            f"candidate_{idx}_confidence",
            f"candidate_{idx}_matched_from",
            f"candidate_{idx}_matched_name",
        ])

    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for issue in issues:
            row = {
                "catalogue_model_id": issue["catalogue_model_id"],
                "issue_type": issue["issue_type"],
                "recommended_action": recommended_action(issue["issue_type"]),
                "resolved_action": "",
                "resolved_catalogue_type": "",
                "resolved_datasheet_ids": "",
                "resolved_notes": "",
                "name": issue["name"],
                "faction_label": issue["faction_label"],
                "expected_faction_id": issue["expected_faction_id"],
                "release_date": issue["release_date"],
                "material": issue["material"],
                "note": issue["note"],
                "flags": "; ".join(issue.get("flags", [])),
                "source_sheet": issue["source"]["sheet"],
                "source_row": issue["source"]["row"],
            }
            for idx, candidate in enumerate(issue.get("candidates", [])[:candidate_slots], start=1):
                row.update({
                    f"candidate_{idx}_datasheet_id": candidate["datasheet_id"],
                    f"candidate_{idx}_datasheet_name": candidate["datasheet_name"],
                    f"candidate_{idx}_faction_id": candidate["faction_id"],
                    f"candidate_{idx}_confidence": candidate["confidence"],
                    f"candidate_{idx}_matched_from": candidate["matched_from"],
                    f"candidate_{idx}_matched_name": candidate["matched_name"],
                })
            writer.writerow(row)


def main() -> int:
    workbook_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WORKBOOK
    index, keys, _ds_by_id = build_datasheet_index()
    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)

    records = []
    issues = []
    id_counts: Counter[str] = Counter()
    skipped = Counter()

    for ws in wb.worksheets:
        if ws.title in IGNORED_SHEETS:
            continue
        faction_id = FACTION_BY_SHEET.get(ws.title, "")
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            release_date, year = release_date_parts(row[0])
            name = str(row[1] or "").strip()
            note = str(row[2] or "").strip()
            material = str(row[3] or "").strip()
            extra_flags = [str(value).strip() for value in row[4:] if value not in (None, "")]

            if not name:
                continue
            if name.lower().startswith("warhammer 40k:"):
                skipped["edition_marker"] += 1
                continue
            if not year or year < 2005:
                skipped["pre_2005_or_missing_date"] += 1
                continue
            if is_finecast(material):
                skipped["finecast"] += 1
                continue

            base_id = slug(f"{ws.title}-{release_date or year}-{name}")
            id_counts[base_id] += 1
            record_id = base_id if id_counts[base_id] == 1 else f"{base_id}-{id_counts[base_id]}"
            candidates = find_candidate_models(name, faction_id, index, keys)
            confirmed = [
                c for c in candidates
                if c["confidence"] >= 0.86 and c["faction_match"]
            ][:3]
            # Exact cross-faction datasheets: same physical kit usable in other armies
            cross_faction = [
                c for c in candidates
                if c["confidence"] == 1.0 and not c["faction_match"] and c["match_method"] == "exact"
            ][:5]

            def _link(c, is_cross: bool) -> dict:
                return {
                    "datasheet_id": c["datasheet_id"],
                    "datasheet_name": c["datasheet_name"],
                    "faction_id": c["faction_id"],
                    "matched_from": c["matched_from"],
                    "matched_name": c["matched_name"],
                    "confidence": c["confidence"],
                    "match_method": c["match_method"],
                    "cross_faction": is_cross,
                }

            record = {
                "id": record_id,
                "name": name,
                "faction_label": ws.title,
                "faction_id": faction_id,
                "release_date": release_date,
                "release_year": year,
                "material": material,
                "status": status_from_fields(note, extra_flags),
                "note": note,
                "flags": extra_flags,
                "datasheet_links": (
                    [_link(c, False) for c in confirmed]
                    + [_link(c, True) for c in cross_faction]
                ),
                "source": {
                    "workbook": os.path.basename(workbook_path),
                    "sheet": ws.title,
                    "row": row_num,
                },
            }
            records.append(record)

            issue_type = classify_issue(record, candidates)
            if issue_type:
                issues.append({
                    "catalogue_model_id": record_id,
                    "issue_type": issue_type,
                    "name": name,
                    "faction_label": ws.title,
                    "expected_faction_id": faction_id,
                    "release_date": release_date,
                    "note": note,
                    "material": material,
                    "flags": extra_flags,
                    "candidates": candidates,
                    "source": record["source"],
                })

    records.sort(key=lambda item: (item["faction_label"], item["release_date"], item["name"], item["id"]))
    issues.sort(key=lambda item: (item["issue_type"], item["faction_label"], item["release_date"], item["name"]))

    catalogue = {
        "schema_version": 1,
        "source": {
            "workbook": os.path.basename(workbook_path),
            "filters": {
                "minimum_release_year": 2005,
                "excluded_materials": ["Finecast"],
            },
            "skipped_counts": dict(skipped),
        },
        "model_releases": records,
    }
    review = {
        "schema_version": 1,
        "source": catalogue["source"],
        "summary": {
            "model_release_count": len(records),
            "issue_count": len(issues),
            "issue_counts": dict(Counter(issue["issue_type"] for issue in issues)),
            "linked_release_count": sum(1 for item in records if item["datasheet_links"]),
        },
        "issues": issues,
    }

    with open(os.path.join(DATA_DIR, "model_catalogue.json"), "w", encoding="utf-8") as fh:
        json.dump(catalogue, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    with open(os.path.join(DATA_DIR, "model_catalogue_issues.json"), "w", encoding="utf-8") as fh:
        json.dump(review, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    write_review_csv(os.path.join(DATA_DIR, "model_catalogue_review.csv"), issues)

    print(f"Wrote {len(records)} model releases")
    print(f"Linked {review['summary']['linked_release_count']} releases to datasheet candidates")
    print(f"Wrote {len(issues)} review issues")
    print("Wrote data/model_catalogue_review.csv")
    print("Issue counts:", json.dumps(review["summary"]["issue_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
