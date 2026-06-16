"""Collection helpers: owned totals, model records, unit data parsing."""
from html import unescape
import json
import re

from data_store import get_store, strip_html as _strip_html
from db import db


def owned_totals():
    """unit_bsdata_id -> total minis owned (one record = one physical mini)."""
    with db() as c:
        rows = c.execute(
            "SELECT unit_bsdata_id, COUNT(*) cnt FROM minis"
            " WHERE unit_bsdata_id IS NOT NULL GROUP BY unit_bsdata_id"
        )
        return {r["unit_bsdata_id"]: r["cnt"] for r in rows}


def favourite_factions():
    with db() as c:
        rows = c.execute("SELECT faction_id FROM favourite_factions").fetchall()
        return {r["faction_id"] for r in rows}


def _minis_for(c, did):
    rows = c.execute(
        "SELECT * FROM minis WHERE unit_bsdata_id=? ORDER BY created_at", (did,)).fetchall()
    out = []
    for r in rows:
        photos = c.execute(
            "SELECT id, filename, caption FROM photos WHERE mini_id=? ORDER BY uploaded_at",
            (r["id"],)).fetchall()
        try:
            wg = json.loads(r["wargear"] or "[]")
        except ValueError:
            wg = []
        stage = r["stage"] if "stage" in r.keys() else (
            "finished" if bool(r["finished"]) else "unbuilt"
        )
        out.append({
            "id": r["id"],
            "catalogue_model_id": r["catalogue_model_id"] if "catalogue_model_id" in r.keys() else None,
            "label": r["label"] or "",
            "wargear": wg if isinstance(wg, list) else [],
            "notes": r["notes"] or "",
            "stage": stage,
            "multikit_group": r["multikit_group"] if "multikit_group" in r.keys() else None,
            "photos": [{"id": p["id"], "url": f"/uploads/{p['filename']}",
                        "caption": p["caption"]} for p in photos],
        })
    return out


def _base_wargear_name(name):
    name = _strip_html(unescape(name or "")).strip()
    name = re.sub(r"\s+[-\u2013\u2014]\s+(standard|supercharge)$", "", name, flags=re.I)
    return name.strip()


def _choice_key(name):
    name = _base_wargear_name(name).lower()
    name = re.sub(r"^(?:up to\s+)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+", "", name)
    return re.sub(r"\s+", " ", name).strip(" .")


def _display_choice(name, canonical):
    cleaned = _strip_html(unescape(name or "")).strip()
    cleaned = re.sub(r"^(?:up to\s+)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+", "", cleaned, flags=re.I)
    cleaned = cleaned.strip(" .")
    key = _choice_key(cleaned)
    if key in canonical:
        return canonical[key]
    return cleaned[:1].upper() + cleaned[1:] if cleaned else ""


def _canonical_wargear(detail):
    canonical = {}
    for w in detail.get("ranged", []) + detail.get("melee", []):
        name = _base_wargear_name(w.get("name", ""))
        key = _choice_key(name)
        if key and key not in canonical:
            canonical[key] = name
    return canonical


def _choices_from_loadout(loadout, canonical):
    text = _strip_html(unescape(loadout or ""))
    if ":" in text:
        text = text.split(":", 1)[1]
    parts = re.split(r"\s*;\s*", text)
    return [_display_choice(p, canonical) for p in parts if _display_choice(p, canonical)]


def _choices_from_option(description, canonical):
    raw = unescape(description or "")
    html_items = re.findall(r"<li[^>]*>(.*?)</li>", raw, flags=re.I | re.S)
    if html_items:
        return [_display_choice(item, canonical) for item in html_items if _display_choice(item, canonical)]

    text = _strip_html(raw)
    match = re.search(
        r"(?:replaced with|equipped with)\s+(?:one of the following:\s*)?(.+)$",
        text,
        flags=re.I,
    )
    if not match:
        return []
    choice = re.sub(r"\s+This model.*$", "", match.group(1), flags=re.I).strip(" .")
    display = _display_choice(choice, canonical)
    return [display] if display and display.lower() != "none" else []


def _wargear_choice_groups(detail):
    canonical = _canonical_wargear(detail)
    groups = []
    default_choices = _choices_from_loadout(detail.get("loadout", ""), canonical)
    if default_choices:
        groups.append({
            "title": "Default loadout",
            "description": "Every model is equipped with:",
            "choices": default_choices,
        })

    for row in detail.get("options", []):
        desc = row.get("description", "")
        choices = _choices_from_option(desc, canonical)
        if not choices:
            continue
        groups.append({
            "title": f"Option {row.get('line', '')}".strip(),
            "description": _strip_html(unescape(desc)),
            "choices": choices,
        })
    return groups


def _wargear_choices(detail):
    seen = []
    for group in _wargear_choice_groups(detail):
        for choice in group["choices"]:
            if choice and choice not in seen:
                seen.append(choice)
    for w in detail.get("ranged", []) + detail.get("melee", []):
        name = _base_wargear_name(w.get("name", ""))
        if name and name not in seen:
            seen.append(name)
    return seen


def _parse_comp_range(comp_rows):
    groups = [[]]
    for row in comp_rows:
        desc = _strip_html(row.get("description") or row.get("name", "")).strip()
        if re.fullmatch(r"or:?", desc, re.I):
            if groups[-1]:
                groups.append([])
            continue
        groups[-1].append(desc)
    parsed = []
    for group in groups:
        group_min = group_max = 0
        found = False
        for desc in group:
            clean = re.sub(r"\([^)]*\)", "", desc)
            for m in re.finditer(r"(?:^|,\s*|\band\s+)(\d+)(?:\s*[-–]\s*(\d+))?\s+\S", clean):
                lo = int(m.group(1))
                hi = int(m.group(2) or lo)
                group_min += lo
                group_max += hi
                found = True
        if found:
            parsed.append((group_min, group_max))
    if not parsed:
        return None
    return {"min": min(p[0] for p in parsed), "max": max(p[1] for p in parsed)}


def _squad_suggestions(owned_count, comp_range):
    """Compute valid squad groupings from owned model count and composition range."""
    if not comp_range or owned_count == 0:
        return {"squads": [], "leftover": owned_count, "total": owned_count}
    min_s = comp_range.get("min") or 1
    max_s = comp_range.get("max") or min_s
    remaining = owned_count
    squads = []
    while remaining >= max_s:
        squads.append(max_s)
        remaining -= max_s
    if remaining >= min_s:
        squads.append(remaining)
        remaining = 0
    return {"squads": squads, "leftover": remaining, "total": owned_count}
