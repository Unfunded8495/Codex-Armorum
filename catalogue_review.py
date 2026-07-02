"""Helpers for reviewing imported model catalogue rows.

Leaf-vs-parent faction seam (read before editing the army_ids / source_faction
construction): every catalogue record's stored faction_id and every nested
datasheet_links[].faction_id is a leaf-level w40k.db UUID (Blood Angels, not
Adeptus Astartes), set by scripts/reresolve_catalogue_faction.py per the
leaf-wins primary the data store computes. The catalogue scoping layer
deliberately collapses those leaves to their parent at render time
(store.faction_parent), so a Blood Angels datasheet groups under the Adeptus
Astartes army tile even though its stored ids point at the chapter. Two
pieces hold that contract together and must move in lockstep if either is
changed: the per-link collapse inside the datasheet loop in
catalogue_payload, and the source_faction collapse a few lines below it. If
a future change starts surfacing chapter-level groups in the catalogue, both
sites need to relax together or the army_ids union and the displayed
faction_id will disagree.
"""
import json
import os
import re
import time

import catalogue_links as cl
import factions_theme as ft


BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
MANUAL_PATH = os.environ.get(
    "MANUAL_JSON_PATH", os.path.join(DATA_DIR, "model_catalogue_manual.json"))
RESOLUTIONS_PATH = os.path.join(DATA_DIR, "model_catalogue_resolutions.json")
IMAGES_PATH = os.path.join(DATA_DIR, "model_catalogue_images.json")
CATALOGUE_IMAGE_DIR = os.path.join(BASE, "cache", "images", "catalogue")

_CACHE = {}


# ---------------------------------------------------------------------------
# Faction-label canonicalisation
#
# After the w40k.db faction re-resolve (scripts/reresolve_catalogue_faction.py),
# every record's faction_label is the bare w40k.db faction.name (or "Unresolved"
# for the placeholder bucket). Legacy "Xenos - " / "Imperium - " / "Chaos - "
# grouping prefixes are no longer stored. The aliases table is intentionally
# left empty: re-adding prefix variants here would undo the rewrite by
# re-prefixing bare labels at display time. Grouped display, if wanted, is a
# render-time concern keyed on the faction's parent in w40k.db, not on a
# baked-in label string.
FACTION_LABEL_ALIASES = {}


def canonical_faction_label(label):
    """Trim a stored faction_label. The aliases table is empty post-reresolve;
    bare labels pass straight through. Kept as a function so the API edit path
    has a single canonicalisation seam if a future drift needs handling."""
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
    from data_store import get_store
    store = get_store()

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
        if cl.is_render_excluded(resolution):
            continue
        link_ids = cl.effective_link_ids(record, resolution)

        links = []
        linked_factions = set()
        for did in link_ids:
            ds = datasheets.get(did)
            if not ds:
                continue
            # Collapse chapter datasheets back to the parent faction (e.g. a
            # Blood Angels datasheet groups under Adeptus Astartes). Chapters
            # are first-class factions for browsing and favourites, but the
            # catalogue grouping and search scope deliberately stay at the
            # parent level so the purchase browser is unchanged by the split.
            fac = store.faction_parent(ds.get("faction_id", ""))
            linked_factions.add(fac)
            links.append({
                "datasheet_id": did,
                "datasheet_name": ds.get("name", ""),
                "faction_id": fac,
                "role": ds.get("role", ""),
            })

        # Faction authority is single-source: w40k.db via the linked
        # datasheets when present, else the stored faction_id. We do NOT
        # union the stored id with the datasheet-derived ids, because that
        # was the path that doubled the Ork bucket pre-reresolve when the
        # stored legacy code and the UUID disagreed. After the reresolve
        # the stored faction_id is the majority-pick leaf-level UUID (or
        # the "unresolved" sentinel for link-less rows that the code map
        # could not place); faction_parent collapses leaf chapter UUIDs
        # back to the parent so the catalogue scoping stays at top-level
        # factions (a Blood Angels datasheet groups under Adeptus Astartes
        # in the army filter), matching the per-link parent-collapse
        # already applied in the loop above.
        raw_top = record.get("faction_id", "") or ""
        if linked_factions:
            army_ids = set(linked_factions)
            source_faction = store.faction_parent(raw_top) if raw_top else ""
        else:
            source_faction = store.faction_parent(raw_top) if raw_top else ""
            army_ids = {source_faction} if source_faction else set()
        army_ids.discard("")
        for fid in army_ids:
            factions.setdefault(fid, {"id": fid, "name": fid, "count": 0})
            factions[fid]["count"] += 1

        fo = resolution.get("field_overrides", {})
        faction_label = canonical_faction_label(record.get("faction_label", ""))
        # Display label: swap to the faction's common_name when one exists so
        # the seven renamed factions read by their familiar name (Adeptus
        # Astartes -> Space Marines etc.). The canonical faction_label above
        # stays untouched - it remains the catalogue's grouping/join key.
        faction_label_display = _faction_card_display_name(faction_label) if faction_label else ""
        items.append({
            "id": cid,
            "name": fo.get("name") or resolution.get("name_override") or record.get("name", ""),
            "faction_label": faction_label,
            "faction_label_display": faction_label_display or faction_label,
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

    for fid, faction in factions.items():
        fac_row = store.faction_by_id.get(fid, {})
        name = fac_row.get("name", faction["name"])
        # Theming and the icon resolver stay keyed on the canonical name;
        # display_name is the user-facing label (common_name when set).
        primary, accent, _ = ft.theme_for(name)
        faction["name"] = name
        faction["display_name"] = fac_row.get("display_name") or name
        faction["parent_display_name"] = fac_row.get("parent_display_name") or ""
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


# ---------------------------------------------------------------------------
# Faction cards for the History view
#
# Cards are grouped by canonical faction_label (how a person thinks of a faction),
# NOT faction_id: a single Wahapedia faction code is shared by every Space Marine
# chapter and by all the Aeldari branches, so grouping by id would collapse them
# into one card.
STATIC_IMAGE_DIR = os.path.join(BASE, "static", "images")

# Faction labels whose photographic card image does not match the default slug.
# Held explicitly so the mapping is auditable rather than guessed (see
# MODEL_PAGE_BRIEF.md). Keyed by the prefix-stripped display name.
FACTION_CARD_IMAGE_ALIASES = {
    "Tau Empire": "t_au_empire.jpg",       # catalogue drops the apostrophe; file slugged from "T'au Empire"
    "T'au Empire": "t_au_empire.jpg",
    "Craftworlds": "aeldari.jpg",          # Aeldari subfaction, no own card image
    "Harlequins": "aeldari.jpg",
    "Ynnari": "aeldari.jpg",
    "Inquisition": "imperial_agents.jpg",  # Imperial Agents grouping, no own card image
    "Imperial Assassins": "imperial_agents.jpg",
    "Supplement Marines": "space_marines.jpg",  # generic Space Marine bucket
}

# Labels theme_for() does not key on directly. Each maps onto the colours of the
# parent faction the card already borrows its image from, so a subfaction card never
# falls back to the grey placeholder theme.
FACTION_CARD_THEME_ALIASES = {
    "Tau Empire": "T'au Empire",        # catalogue drops the apostrophe theme_for keys on
    "Craftworlds": "Aeldari",
    "Harlequins": "Aeldari",
    "Imperial Agents": "Agents of the Imperium",
    "Inquisition": "Agents of the Imperium",
    "Imperial Assassins": "Agents of the Imperium",
}


def _faction_card_display_name(label):
    """User-facing tile name for a canonical faction_label.

    Strips any legacy alignment prefix ("Imperium - ..."), then applies the
    w40k.db common_name swap (Adeptus Astartes -> Space Marines, Heretic
    Astartes -> Chaos Space Marines, etc.) so the seven renamed factions read
    by their familiar name. Theme lookups keep using the canonical name a few
    lines below so the colour treatment is unchanged."""
    stripped = label.rsplit(" - ", 1)[-1].strip()
    from data_store import get_store
    fac = next((f for f in get_store().factions if f["name"] == stripped), None)
    if fac and fac.get("display_name"):
        return fac["display_name"]
    return stripped


def _faction_card_image_url(display_name, label):
    """Resolve the card image to a known-good /static/images URL, or None.

    Order: exact slug file, then the explicit alias table, else None (the client
    falls back to the tinted faction glyph so no card renders blank)."""
    slug = re.sub(r"[^a-z0-9_-]+", "_", display_name.lower()).strip("_")
    exact = f"{slug}.jpg"
    if os.path.exists(os.path.join(STATIC_IMAGE_DIR, exact)):
        return f"/static/images/{exact}"
    alias = (FACTION_CARD_IMAGE_ALIASES.get(display_name)
             or FACTION_CARD_IMAGE_ALIASES.get(label))
    if alias and os.path.exists(os.path.join(STATIC_IMAGE_DIR, alias)):
        return f"/static/images/{alias}"
    return None


def faction_cards():
    """Return one card per canonical faction_label, sorted by model count desc.

    Each card: faction_label (canonical, the join key for the drill-in), display_name,
    count, year_min/year_max, primary/accent/glyph from the faction theme, and a
    server-resolved photographic image_url. Test Faction is excluded entirely."""
    key = ("faction_cards", _mtime_key(MANUAL_PATH, RESOLUTIONS_PATH))
    if key in _CACHE:
        return _CACHE[key]

    payload = catalogue_payload()
    groups = {}
    for item in payload.get("items", []):
        label = item.get("faction_label", "")
        if not label or label == "Test Faction":
            continue
        g = groups.get(label)
        if g is None:
            g = groups[label] = {"label": label, "count": 0, "years": []}
        g["count"] += 1
        year = item.get("release_year")
        if isinstance(year, int):
            g["years"].append(year)

    cards = []
    for label, g in groups.items():
        display = _faction_card_display_name(label)
        # Theming stays keyed on the canonical label so the colour scheme is
        # unchanged for the seven factions whose display name now reads as
        # their common name (Adeptus Astartes -> Space Marines, Adeptus
        # Titanicus -> Titan Legions, etc.).
        canonical_key = label.rsplit(" - ", 1)[-1].strip()
        theme_key = FACTION_CARD_THEME_ALIASES.get(canonical_key, canonical_key)
        primary, accent, glyph = ft.theme_for(theme_key)
        years = g["years"]
        cards.append({
            "faction_label": label,
            "display_name": display,
            "count": g["count"],
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "primary": primary,
            "accent": accent,
            "glyph": glyph,
            "initial": (display[:1] or "?").upper(),
            "image_url": _faction_card_image_url(display, label),
        })

    cards.sort(key=lambda c: (-c["count"], c["display_name"]))
    _CACHE[key] = cards
    return cards


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
        if cl.is_render_excluded(resolution):
            continue
        link_ids = cl.effective_link_ids(r, resolution)
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

    _CACHE[key] = by_datasheet
    return by_datasheet


def catalogue_faction_datasheet_index():
    """Return {catalogue_model_id: {faction_id: datasheet_id}} for every
    model release whose resolution (or raw links) covers more than one faction.

    Used by the collection API to surface minis in cross-faction views - e.g. a mini
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
        if cl.is_render_excluded(resolution):
            continue
        # no_current_datasheet yields [] here, so fac_map stays empty and the
        # record contributes no entry - same outcome as the old explicit skip.
        link_ids = cl.effective_link_ids(r, resolution)

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
