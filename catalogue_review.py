"""Helpers for reviewing imported model catalogue rows."""
import json
import os
import re
import time

import factions_theme as ft


BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
MANUAL_PATH = os.path.join(DATA_DIR, "model_catalogue_manual.json")
RESOLUTIONS_PATH = os.path.join(DATA_DIR, "model_catalogue_resolutions.json")
IMAGES_PATH = os.path.join(DATA_DIR, "model_catalogue_images.json")
CATALOGUE_IMAGE_DIR = os.path.join(BASE, "cache", "images", "catalogue")

_CACHE = {}


# ---------------------------------------------------------------------------
# Faction-label canonicalisation
#
# `faction_label` is a denormalised, per-record display string. Legacy
# spreadsheet imports seeded it from the worksheet tab title (e.g. "Orks"),
# while newer add/edit paths wrote the data store's canonical faction name
# (e.g. "Xenos - Orks"). The result was one faction_id carrying two different
# strings, so a card's meta line and its group header could disagree.
#
# These aliases collapse each known drift variant onto the data store's
# canonical faction name — the single string the rest of the app already uses —
# so cards, group headers and the army picker all agree with no display-time
# string munging. We deliberately do NOT touch faction_ids that legitimately
# carry several sub-faction labels (Space Marine chapters, Aeldari branches,
# Agents of the Imperium); those are meaningful distinctions finer-grained than
# faction_id, not drift.
FACTION_LABEL_ALIASES = {
    "Orks": "Xenos - Orks",
    "Adeptus Mechanicus": "Imperium - Adeptus Mechanicus",
    "Chaos Space Marines": "Chaos - Chaos Space Marines",
    "Genestealer Cult": "Xenos - Genestealer Cults",
    "Genestealer Cults": "Xenos - Genestealer Cults",
    "Emperor's Children": "Chaos - Emperor's Children",
    "Emperorâ€™s Children": "Chaos - Emperor's Children",  # mojibake repair
    "Imperium - Adeptus Astartes - Space Marines": "Space Marines",       # rejoin generic SM group
}


def canonical_faction_label(label):
    """Map a stored faction_label onto its canonical display form (see above)."""
    if not label:
        return label
    stripped = label.strip()
    return FACTION_LABEL_ALIASES.get(stripped, stripped)


def _faction_icon_url(fid, name):
    icon_dir = os.path.join(BASE, "static", "icons")
    candidates = [
        f"{name}.svg",
        f"{name.strip()}.svg",
        f"{fid}.svg",
    ]
    for filename in candidates:
        if filename and os.path.exists(os.path.join(icon_dir, filename)):
            return f"/static/icons/{filename}"
    return ""


def _mtime_key(*paths):
    values = []
    for path in paths:
        try:
            values.append(os.path.getmtime(path))
        except OSError:
            values.append(0)
    return tuple(values)


def _load_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def _write_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _resolution_document():
    return _load_json(RESOLUTIONS_PATH, {
        "schema_version": 1,
        "notes": "Manual catalogue review decisions.",
        "resolution_actions": [
            "link_datasheet",
            "link_multiple_datasheets",
            "no_current_datasheet",
            "mark_accessory",
            "mark_box_product",
            "exclude",
            "add_alias",
            "defer",
        ],
        "resolutions": [],
    })


def _resolution_map():
    key = ("resolution_map", _mtime_key(RESOLUTIONS_PATH))
    if key not in _CACHE:
        doc = _resolution_document()
        _CACHE[key] = {r.get("catalogue_model_id"): r for r in doc.get("resolutions", [])}
    return _CACHE[key]


def _datasheet_lookup():
    from data_store import get_store

    store = get_store()
    return store.ds_by_id


def _image_map():
    key = ("image_map", _mtime_key(IMAGES_PATH))
    if key not in _CACHE:
        doc = _load_json(IMAGES_PATH, {"images": []})
        _CACHE[key] = {row.get("catalogue_model_id"): row for row in doc.get("images", [])}
    return _CACHE[key]


def catalogue_image_path(catalogue_model_id):
    row = _image_map().get(catalogue_model_id)
    if not row or not row.get("local_path"):
        return None
    path = os.path.abspath(os.path.join(BASE, row["local_path"]))
    cache_root = os.path.abspath(os.path.join(BASE, "cache", "images", "catalogue"))
    if not path.startswith(cache_root + os.sep) and path != cache_root:
        return None
    if not os.path.exists(path):
        return None
    return path


def catalogue_image_for_datasheet(datasheet_id):
    """Return the newest saved catalogue-model image linked to a datasheet."""
    models = catalogue_models_for_datasheet(datasheet_id)
    models.sort(key=lambda m: (m.get("release_year") or 0, m.get("name", "")), reverse=True)
    for model in models:
        path = catalogue_image_path(model.get("id"))
        if path:
            return path
    return None


def catalogue_payload():
    key = ("catalogue_payload", _mtime_key(MANUAL_PATH, RESOLUTIONS_PATH, IMAGES_PATH))
    if key in _CACHE:
        return _CACHE[key]
    data = _load_json(MANUAL_PATH, {"model_releases": []})
    all_releases = data.get("model_releases", [])
    resolutions = _resolution_map()
    datasheets = _datasheet_lookup()
    images = _image_map()
    items = []
    factions = {}

    for record in all_releases:
        cid = record.get("id")
        resolution = resolutions.get(cid, {})
        action = resolution.get("action", "")
        if action in {"exclude", "mark_accessory", "mark_box_product"}:
            continue

        if action in {"link_datasheet", "link_multiple_datasheets"}:
            link_ids = resolution.get("datasheet_ids", [])
        elif action == "no_current_datasheet":
            link_ids = []
        else:
            link_ids = [l["datasheet_id"] for l in record.get("datasheet_links", []) if l.get("datasheet_id")]

        links = []
        linked_factions = set()
        for did in link_ids:
            ds = datasheets.get(did)
            if not ds:
                continue
            linked_factions.add(ds.get("faction_id", ""))
            links.append({
                "datasheet_id": did,
                "datasheet_name": ds.get("name", ""),
                "faction_id": ds.get("faction_id", ""),
                "role": ds.get("role", ""),
            })

        source_faction = record.get("faction_id", "")
        army_ids = {source_faction, *linked_factions}
        army_ids.discard("")
        for fid in army_ids:
            factions.setdefault(fid, {"id": fid, "name": fid, "count": 0})
            factions[fid]["count"] += 1

        fo = resolution.get("field_overrides", {})
        items.append({
            "id": cid,
            "name": fo.get("name") or resolution.get("name_override") or record.get("name", ""),
            "faction_label": canonical_faction_label(record.get("faction_label", "")),
            "faction_id": source_faction,
            "army_ids": sorted(army_ids),
            "release_date": fo.get("release_date", record.get("release_date", "")),
            "release_year": fo.get("release_year", record.get("release_year")),
            "material": fo.get("material", record.get("material", "")),
            "status": fo.get("status", record.get("status", "")),
            "note": fo.get("note", record.get("note", "")),
            "flags": fo.get("flags", record.get("flags", [])),
            "datasheet_links": links,
            "catalogue_type": resolution.get("catalogue_type") or "model_release",
            "resolution_action": action or "auto_import",
            "resolution_notes": resolution.get("notes", ""),
            "image": image_payload(cid, images.get(cid)),
            "is_manual": True,
        })

    from data_store import get_store

    store = get_store()
    for fid, faction in factions.items():
        name = store.faction_by_id.get(fid, {}).get("name", faction["name"])
        primary, accent, _ = ft.theme_for(name)
        faction["name"] = name
        faction["primary"] = primary
        faction["accent"] = accent
        faction["icon_url"] = _faction_icon_url(fid, name)

    items.sort(key=lambda item: (
        item.get("faction_label", ""),
        item.get("name", ""),
        item.get("release_date", ""),
        item.get("id", ""),
    ))
    faction_list = sorted(factions.values(), key=lambda f: f["name"])
    payload = {
        "summary": {
            "model_count": len(items),
            "army_count": len(faction_list),
            "linked_count": sum(1 for item in items if item["datasheet_links"]),
            "unlinked_count": sum(1 for item in items if not item["datasheet_links"]),
        },
        "factions": faction_list,
        "items": items,
    }
    _CACHE[key] = payload
    return payload


def image_payload(catalogue_model_id, image_row):
    if not image_row or not image_row.get("local_path"):
        return None
    if not catalogue_image_path(catalogue_model_id):
        return None
    return {
        "url": f"/api/model-catalogue/{catalogue_model_id}/image",
        "caption": image_row.get("caption", ""),
        "source": image_row.get("source", ""),
        "lexicanum_page": image_row.get("lexicanum_page", ""),
        "file_page_url": image_row.get("file_page_url", ""),
        "confidence": image_row.get("match_confidence"),
    }


def catalogue_model_index():
    """Lightweight {catalogue_model_id -> {name, release_year, material, faction_label}} lookup."""
    key = ("catalogue_model_index", _mtime_key(MANUAL_PATH))
    if key in _CACHE:
        return _CACHE[key]
    index = {}
    data = _load_json(MANUAL_PATH, {"model_releases": []})
    for r in data.get("model_releases", []):
        cid = r.get("id")
        if cid:
            index[cid] = {
                "name": r.get("name", ""),
                "release_year": r.get("release_year"),
                "material": r.get("material", ""),
                "faction_label": canonical_faction_label(r.get("faction_label", "")),
            }
    _CACHE[key] = index
    return index



def catalogue_models_for_datasheet(datasheet_id):
    """Return all catalogue model releases that link to the given datasheet_id."""
    by_datasheet = _catalogue_models_by_datasheet()
    return list(by_datasheet.get(datasheet_id, []))


def _catalogue_models_by_datasheet():
    key = ("catalogue_models_by_datasheet", _mtime_key(MANUAL_PATH, RESOLUTIONS_PATH, IMAGES_PATH))
    if key in _CACHE:
        return _CACHE[key]
    by_datasheet = {}
    seen = set()
    resolutions = _resolution_map()

    data = _load_json(MANUAL_PATH, {"model_releases": []})
    for r in data.get("model_releases", []):
        cid = r.get("id")
        if not cid or cid in seen:
            continue
        resolution = resolutions.get(cid, {})
        action = resolution.get("action", "")
        if action in {"exclude", "mark_accessory", "mark_box_product"}:
            continue
        if action in {"link_datasheet", "link_multiple_datasheets"}:
            link_ids = resolution.get("datasheet_ids", [])
        elif action == "no_current_datasheet":
            link_ids = []
        else:
            link_ids = [lnk["datasheet_id"] for lnk in r.get("datasheet_links", [])
                        if lnk.get("datasheet_id")]
        seen.add(cid)
        img_path = catalogue_image_path(cid)
        entry = {
                "id": cid,
                "name": r.get("name", ""),
                "release_year": r.get("release_year"),
                "release_date": r.get("release_date", ""),
                "material": r.get("material", ""),
                "faction_label": canonical_faction_label(r.get("faction_label", "")),
                "note": r.get("note", ""),
                "status": r.get("status", ""),
                "image_url": f"/api/model-catalogue/{cid}/image" if img_path else None,
            }
        for did in link_ids:
            by_datasheet.setdefault(did, []).append(entry)

    for entries in by_datasheet.values():
        entries.sort(key=lambda e: (e.get("release_year") or 0, e.get("name", "")))

    # Also index each entry under its BSData GUID so lookups with BSData GUIDs
    # find model catalogue entries that were imported with Wahapedia IDs.
    try:
        from data_store import get_store as _get_store
        _store = _get_store()
        bsdata_additions = {}
        for wahapedia_id, entries in by_datasheet.items():
            unit = _store.ds_by_id.get(wahapedia_id)
            if unit:
                bsdata_id = unit.get("id")
                if bsdata_id and bsdata_id not in by_datasheet:
                    bsdata_additions[bsdata_id] = entries
        by_datasheet.update(bsdata_additions)
    except Exception:
        pass  # fail silently; model catalogue will just show no linked models

    _CACHE[key] = by_datasheet
    return by_datasheet


def catalogue_faction_datasheet_index():
    """Return {catalogue_model_id: {bsdata_faction_id: bsdata_datasheet_id}} for every
    model release whose resolution (or raw links) covers more than one faction.

    Used by the collection API to surface minis in cross-faction views — e.g. a mini
    stored under the CSM Plague Marines datasheet should also appear when browsing Death
    Guard because the model catalogue links that physical kit to both datasheets.
    """
    from data_store import get_store
    store = get_store()

    key = ("catalogue_faction_ds_index", _mtime_key(MANUAL_PATH, RESOLUTIONS_PATH))
    if key in _CACHE:
        return _CACHE[key]

    data = _load_json(MANUAL_PATH, {"model_releases": []})
    resolutions = _resolution_map()
    index = {}

    for r in data.get("model_releases", []):
        cid = r.get("id")
        if not cid:
            continue
        resolution = resolutions.get(cid, {})
        action = resolution.get("action", "")
        if action in {"exclude", "mark_accessory", "mark_box_product", "no_current_datasheet"}:
            continue
        if action in {"link_datasheet", "link_multiple_datasheets"}:
            link_ids = resolution.get("datasheet_ids", [])
        else:
            link_ids = [lnk["datasheet_id"] for lnk in r.get("datasheet_links", [])
                        if lnk.get("datasheet_id")]

        fac_map = {}
        for did in link_ids:
            ds = store.ds_by_id.get(did)
            if ds:
                fac_map[ds["faction_id"]] = ds["id"]

        if fac_map:
            index[cid] = fac_map

    _CACHE[key] = index
    return index


def _safe_catalogue_path(catalogue_model_id, ext):
    """Return the resolved path for a catalogue model image, or None if outside the cache dir."""
    os.makedirs(CATALOGUE_IMAGE_DIR, exist_ok=True)
    fname = catalogue_model_id + ext
    path = os.path.abspath(os.path.join(CATALOGUE_IMAGE_DIR, fname))
    root = os.path.abspath(CATALOGUE_IMAGE_DIR)
    if not path.startswith(root + os.sep) and path != root:
        return None
    return path


def save_catalogue_model_image(catalogue_model_id, blob, ext):
    """Save a user-provided image for a catalogue model. Returns (local_path, error)."""
    path = _safe_catalogue_path(catalogue_model_id, ext)
    if not path:
        return None, "Invalid catalogue model ID."
    _clear_catalogue_model_image_files(catalogue_model_id)
    local = "cache/images/catalogue/" + catalogue_model_id + ext
    with open(path, "wb") as fh:
        fh.write(blob)
    doc = _load_json(IMAGES_PATH, {"images": []})
    rows = [row for row in doc.get("images", [])
            if row.get("catalogue_model_id") != catalogue_model_id]
    rows.append({
        "catalogue_model_id": catalogue_model_id,
        "local_path": local,
        "source": "user",
        "caption": "",
    })
    rows.sort(key=lambda row: row.get("catalogue_model_id", ""))
    doc["images"] = rows
    _write_json(IMAGES_PATH, doc)
    _CACHE.clear()
    return local, None


def _clear_catalogue_model_image_files(catalogue_model_id):
    """Remove any {catalogue_model_id}.{ext} files in the catalogue image dir."""
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = _safe_catalogue_path(catalogue_model_id, ext)
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def clear_catalogue_model_image(catalogue_model_id):
    """Remove the user-set image for a catalogue model."""
    _clear_catalogue_model_image_files(catalogue_model_id)
    doc = _load_json(IMAGES_PATH, {"images": []})
    rows = [row for row in doc.get("images", [])
            if row.get("catalogue_model_id") != catalogue_model_id]
    doc["images"] = rows
    _write_json(IMAGES_PATH, doc)
    _CACHE.clear()


def save_resolution(catalogue_model_id, payload):
    allowed = {
        "link_datasheet",
        "link_multiple_datasheets",
        "no_current_datasheet",
        "mark_accessory",
        "mark_box_product",
        "exclude",
        "add_alias",
        "defer",
    }
    action = str(payload.get("action") or "defer")
    if action not in allowed:
        return None, "Unknown resolution action."

    datasheet_ids = payload.get("datasheet_ids") or []
    if isinstance(datasheet_ids, str):
        datasheet_ids = [v.strip() for v in datasheet_ids.split(",") if v.strip()]
    datasheet_ids = [str(v).strip() for v in datasheet_ids if str(v).strip()][:20]

    resolution = {
        "catalogue_model_id": catalogue_model_id,
        "action": action,
        "catalogue_type": str(payload.get("catalogue_type") or "").strip(),
        "datasheet_ids": datasheet_ids,
        "notes": str(payload.get("notes") or "").strip()[:1000],
        "updated_at": time.time(),
    }

    doc = _resolution_document()
    rows = [r for r in doc.get("resolutions", [])
            if r.get("catalogue_model_id") != catalogue_model_id]
    rows.append(resolution)
    rows.sort(key=lambda r: r.get("catalogue_model_id", ""))
    doc["resolutions"] = rows
    _write_json(RESOLUTIONS_PATH, doc)
    _CACHE.clear()
    return resolution, None


def _next_md_id(existing_ids):
    """Return the next available MD-##### ID."""
    pattern = re.compile(r'^MD-(\d{5,})$')
    highest = 50000
    for eid in existing_ids:
        m = pattern.match(str(eid))
        if m:
            highest = max(highest, int(m.group(1)))
    return f"MD-{highest + 1:05d}"


def add_manual_model(payload):
    """Append a new model release to model_catalogue_manual.json. Returns (record, error)."""
    name = str(payload.get("name") or "").strip()
    if not name:
        return None, "Name is required."

    faction_label = str(payload.get("faction_label") or "").strip()
    faction_id = str(payload.get("faction_id") or "").strip()
    if faction_id:
        from data_store import get_store

        faction = get_store().faction_by_id.get(faction_id)
        faction_label = faction.get("name", faction_id) if faction else (faction_label or faction_id)
    release_date = str(payload.get("release_date") or "").strip()
    release_year = None
    if release_date:
        if not re.match(r'^\d{4}(-\d{2})?$', release_date):
            return None, "Release date must be YYYY or YYYY-MM."
        try:
            release_year = int(release_date[:4])
        except ValueError:
            pass

    material = str(payload.get("material") or "Plastic").strip()
    note = str(payload.get("note") or "").strip()[:500]
    status = str(payload.get("status") or "current_or_unknown").strip()
    if status not in ("current_or_unknown", "discontinued"):
        status = "current_or_unknown"

    doc = _load_json(MANUAL_PATH, {"schema_version": 1, "notes": "", "model_releases": []})
    existing_ids = {r.get("id") for r in doc.get("model_releases", [])}
    cid = _next_md_id(existing_ids)

    record = {
        "id": cid,
        "name": name,
        "faction_label": faction_label,
        "faction_id": faction_id,
        "release_date": release_date,
        "release_year": release_year,
        "material": material,
        "status": status,
        "note": note,
        "flags": [],
        "datasheet_links": [],
        "source": {"workbook": "manual", "sheet": faction_label or faction_id, "row": 0},
    }

    doc.setdefault("model_releases", []).append(record)
    _write_json(MANUAL_PATH, doc)
    _CACHE.clear()
    return record, None


def duplicate_manual_model(catalogue_model_id, new_name):
    """Duplicate a catalogue entry with a new name. Returns (record, error)."""
    new_name = str(new_name or "").strip()
    if not new_name:
        return None, "Name is required."

    doc = _load_json(MANUAL_PATH, {"schema_version": 1, "notes": "", "model_releases": []})
    releases = doc.get("model_releases", [])
    original = next((r for r in releases if r.get("id") == catalogue_model_id), None)
    if not original:
        return None, "Model not found in the catalogue."

    import copy
    import time as _time
    new_record = copy.deepcopy(original)
    new_record["name"] = new_name

    existing_ids = {r.get("id") for r in releases}
    cid = _next_md_id(existing_ids)
    new_record["id"] = cid

    doc["model_releases"].append(new_record)
    _write_json(MANUAL_PATH, doc)
    _CACHE.clear()
    return new_record, None


def delete_manual_model(catalogue_model_id):
    """Remove a model from model_catalogue_manual.json. Returns (True, None) or (False, error)."""
    doc = _load_json(MANUAL_PATH, {"schema_version": 1, "notes": "", "model_releases": []})
    before = len(doc.get("model_releases", []))
    doc["model_releases"] = [r for r in doc.get("model_releases", []) if r.get("id") != catalogue_model_id]
    if len(doc["model_releases"]) == before:
        return False, "Model not found in the catalogue."
    _write_json(MANUAL_PATH, doc)
    _CACHE.clear()
    return True, None


def save_field_overrides(catalogue_model_id, overrides):
    """Save editable field overrides directly into the catalogue file."""
    allowed = {'name', 'release_date', 'release_year', 'material', 'status', 'note', 'flags',
               'faction_id', 'faction_label'}
    overrides = {k: v for k, v in overrides.items() if k in allowed}

    doc = _load_json(MANUAL_PATH, {"schema_version": 1, "notes": "", "model_releases": []})
    records = doc.get("model_releases", [])
    for i, r in enumerate(records):
        if r.get("id") == catalogue_model_id:
            for field, value in overrides.items():
                r[field] = value
            records[i] = r
            doc["model_releases"] = records
            _write_json(MANUAL_PATH, doc)
            _CACHE.clear()
            return r, None
    return None, "Model not found."
