"""Find datasheets that have no model release pointing at them.

Outputs:
  data/datasheet_gaps.json       — machine-readable gaps report
  data/datasheet_gaps.csv        — human-readable triage sheet

Gap types:
  cross_faction_shared   — a model release exists under a different faction with the same name;
                           the fix is to extend that release's datasheet_links
  genuinely_missing      — no model release of any faction matches this name;
                           the fix is to add a manual model release entry
  needs_review           — low-confidence cross-faction candidate found
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")

FACTION_NAMES = {
    "SM": "Space Marines", "CSM": "Chaos Space Marines", "CD": "Chaos Daemons",
    "DG": "Death Guard", "TS": "Thousand Sons", "WE": "World Eaters",
    "EC": "Emperor's Children", "AE": "Aeldari", "DRU": "Drukhari",
    "GC": "Genestealer Cults", "TYR": "Tyranids", "NEC": "Necrons",
    "ORK": "Orks", "TAU": "T'au Empire", "AM": "Astra Militarum",
    "AS": "Adepta Sororitas", "AC": "Adeptus Custodes", "AdM": "Adeptus Mechanicus",
    "AoI": "Agents of the Imperium", "QI": "Imperial Knights", "QT": "Chaos Knights",
    "GK": "Grey Knights", "LoV": "Leagues of Votann", "UN": "Unaligned", "TL": "Tau Legends",
}


def read_pipe_csv(name: str) -> list[dict[str, str]]:
    with open(os.path.join(DATA_DIR, name), encoding="utf-8-sig", newline="") as fh:
        return [
            {k: (v or "").strip() for k, v in row.items() if k}
            for row in csv.DictReader(fh, delimiter="|")
        ]


def normalise(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace("’", "'").replace("�", "")
    text = text.replace("t'au", "tau").replace("t’au", "tau")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"\b(primaris|adeptus|astra|space marine|space marines)\b", " ", text)
    text = re.sub(r"\bof\s+(?:slaanesh|khorne|nurgle|tzeentch|chaos)\b", " ", text)
    text = text.replace("hellbane", "helbane")
    text = re.sub(r"\bsorcerer lord\b", "sorcerer", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    _no_strip_s = {"chaos", "bonus", "nexus", "virus", "status", "focus", "class"}
    drop = {"a", "an", "and", "kit", "model", "models", "of", "or", "set", "the", "with"}
    words = []
    for word in text.split():
        if word in drop:
            continue
        if len(word) > 3 and word.endswith("s") and word not in _no_strip_s:
            word = word[:-1]
        words.append(word)
    return " ".join(words)


def _linked_ids() -> set[str]:
    linked = set()

    path = os.path.join(DATA_DIR, "model_catalogue_manual.json")
    if os.path.exists(path):
        catalogue = json.load(open(path, encoding="utf-8"))
        for record in catalogue.get("model_releases", []):
            for link in record.get("datasheet_links", []):
                if link.get("datasheet_id"):
                    linked.add(link["datasheet_id"])

    res_path = os.path.join(DATA_DIR, "model_catalogue_resolutions.json")
    if os.path.exists(res_path):
        resolutions = json.load(open(res_path, encoding="utf-8"))
        for r in resolutions.get("resolutions", []):
            if r.get("action") not in ("exclude", "mark_accessory", "mark_box_product", "no_current_datasheet"):
                for did in r.get("datasheet_ids", []):
                    if did:
                        linked.add(did)
    return linked


def _model_release_index(catalogue) -> dict[str, list[dict]]:
    """Index model releases by normalised name."""
    index: dict[str, list[dict]] = defaultdict(list)
    for record in catalogue["model_releases"]:
        key = normalise(record["name"])
        if key:
            index[key].append(record)
    return index


def find_cross_faction_candidates(
    ds_name: str, ds_faction: str, release_index: dict[str, list[dict]]
) -> list[dict]:
    target = normalise(ds_name)
    if not target:
        return []

    candidates = []
    target_tokens = set(target.split())

    for key, releases in release_index.items():
        key_tokens = set(key.split())

        exact = target == key
        dice = (2 * len(target_tokens & key_tokens) / (len(target_tokens) + len(key_tokens))
                if target_tokens and key_tokens else 0)
        fuzzy = SequenceMatcher(None, target, key).ratio()

        if exact:
            confidence, method = 1.0, "exact"
        elif dice >= 0.72:
            confidence, method = round(dice, 3), "token"
        elif fuzzy >= 0.82:
            confidence, method = round(fuzzy, 3), "fuzzy"
        else:
            continue

        for release in releases:
            if release["faction_id"] == ds_faction:
                continue  # same faction — already covered
            candidates.append({
                "catalogue_model_id": release["id"],
                "release_name": release["name"],
                "release_faction_id": release["faction_id"],
                "release_date": release["release_date"],
                "confidence": confidence,
                "match_method": method,
            })

    candidates.sort(key=lambda c: -c["confidence"])
    return candidates[:4]


def classify_gap(candidates: list[dict]) -> str:
    if not candidates:
        return "genuinely_missing"
    if candidates[0]["confidence"] >= 0.86:
        return "cross_faction_shared"
    return "needs_review"


def main() -> int:
    datasheets_raw = read_pipe_csv("Datasheets.csv")
    datasheets = {
        row["id"]: row for row in datasheets_raw
        if row.get("id") and row.get("virtual", "").lower() != "true"
    }

    linked = _linked_ids()
    unlinked = {did: ds for did, ds in datasheets.items() if did not in linked}

    catalogue = json.load(open(os.path.join(DATA_DIR, "model_catalogue_manual.json"), encoding="utf-8"))
    release_index = _model_release_index(catalogue)

    gaps = []
    for did, ds in sorted(unlinked.items()):
        name = ds.get("name", "")
        faction_id = ds.get("faction_id", "")
        legend = ds.get("legend", "")
        role = ds.get("role", "")
        is_legend = legend.strip().lower() == "true"

        candidates = find_cross_faction_candidates(name, faction_id, release_index)
        gap_type = classify_gap(candidates)

        gaps.append({
            "datasheet_id": did,
            "datasheet_name": name,
            "faction_id": faction_id,
            "faction_name": FACTION_NAMES.get(faction_id, faction_id),
            "role": role,
            "is_legend": is_legend,
            "gap_type": gap_type,
            "candidates": candidates,
        })

    gaps.sort(key=lambda g: (g["gap_type"], g["faction_id"], g["datasheet_name"]))

    from collections import Counter
    summary = {
        "unlinked_datasheet_count": len(gaps),
        "by_type": dict(Counter(g["gap_type"] for g in gaps)),
        "by_faction": dict(Counter(g["faction_id"] for g in gaps).most_common()),
    }

    output = {
        "schema_version": 1,
        "summary": summary,
        "gaps": gaps,
    }

    out_json = os.path.join(DATA_DIR, "datasheet_gaps.json")
    tmp = out_json + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, out_json)

    csv_path = os.path.join(DATA_DIR, "datasheet_gaps.csv")
    csv_fields = [
        "gap_type", "datasheet_id", "datasheet_name", "faction_id", "faction_name", "role",
        "is_legend",
        "candidate_1_id", "candidate_1_name", "candidate_1_faction", "candidate_1_confidence",
        "candidate_2_id", "candidate_2_name", "candidate_2_faction", "candidate_2_confidence",
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_fields)
        writer.writeheader()
        for g in gaps:
            row = {
                "gap_type": g["gap_type"],
                "datasheet_id": g["datasheet_id"],
                "datasheet_name": g["datasheet_name"],
                "faction_id": g["faction_id"],
                "faction_name": g["faction_name"],
                "role": g["role"],
                "is_legend": g["is_legend"],
            }
            for i, c in enumerate(g["candidates"][:2], start=1):
                row[f"candidate_{i}_id"] = c["catalogue_model_id"]
                row[f"candidate_{i}_name"] = c["release_name"]
                row[f"candidate_{i}_faction"] = c["release_faction_id"]
                row[f"candidate_{i}_confidence"] = c["confidence"]
            writer.writerow(row)

    print(f"Unlinked datasheets: {len(gaps)}")
    print(f"By type: {summary['by_type']}")
    print()
    print("Top factions with gaps:")
    for fid, count in list(summary["by_faction"].items())[:10]:
        print(f"  {fid:6s} ({FACTION_NAMES.get(fid, fid)}): {count}")
    print()
    print(f"Wrote {out_json}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
