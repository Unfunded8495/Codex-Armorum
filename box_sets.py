"""Box set catalogue and purchase tracking logic."""
import json
import os
import re
import time
import uuid

from data_store import get_store
from db import db, _table_exists
from utils import _as_int, _slug

BASE = os.path.dirname(os.path.abspath(__file__))
BOX_SETS_PATH = os.path.join(BASE, "data", "box_sets.json")

_box_cache = {"key": None, "data": []}
_custom_box_cache = {"key": None, "data": []}


def _catalogue_dependency_key():
    paths = [
        os.path.join(BASE, "data", "model_catalogue_manual.json"),
        os.path.join(BASE, "data", "model_catalogue_resolutions.json"),
        os.path.join(BASE, "data", "model_catalogue_images.json"),
    ]
    key = []
    for path in paths:
        try:
            key.append(os.path.getmtime(path))
        except OSError:
            key.append(0)
    return tuple(key)


def _new_catalogue_context():
    return {
        "model_index": None,
        "models_by_datasheet": {},
        "payload_items": None,
        "payload_index": None,
        "name_matches": {},
    }


def _catalogue_model_lookup(catalogue_model_id, ctx=None):
    if not catalogue_model_id:
        return None
    try:
        from catalogue_review import catalogue_model_index
        if ctx is not None:
            if ctx["model_index"] is None:
                ctx["model_index"] = catalogue_model_index()
            return ctx["model_index"].get(catalogue_model_id)
        return catalogue_model_index().get(catalogue_model_id)
    except Exception:
        return None


def _catalogue_models_for_datasheet(datasheet_id, ctx=None):
    try:
        from catalogue_review import catalogue_models_for_datasheet
        if ctx is not None:
            if datasheet_id not in ctx["models_by_datasheet"]:
                ctx["models_by_datasheet"][datasheet_id] = catalogue_models_for_datasheet(datasheet_id)
            return ctx["models_by_datasheet"][datasheet_id]
        return catalogue_models_for_datasheet(datasheet_id)
    except Exception:
        return []


def _catalogue_payload_items(ctx=None):
    try:
        from catalogue_review import catalogue_payload
        if ctx is not None:
            if ctx["payload_items"] is None:
                ctx["payload_items"] = catalogue_payload().get("items", [])
            return ctx["payload_items"]
        return catalogue_payload().get("items", [])
    except Exception:
        return []


# ── Datasheet-less catalogue models ───────────────────────────────────────
# A catalogue model with no Wahapedia datasheet is still trackable: it is keyed
# by the synthetic id "cat:<catalogue_model_id>" wherever a datasheet_id is
# expected (box contents, minis). Everything downstream treats datasheet_id as
# an opaque string, so only the spots that resolve a key to a *real* datasheet
# record need the fallback below.
CAT_PREFIX = "cat:"
_cat_item_index = {"key": None, "data": {}}


def is_catalogue_key(did):
    return isinstance(did, str) and did.startswith(CAT_PREFIX)


def catalogue_model_id_from_key(did):
    return did[len(CAT_PREFIX):] if is_catalogue_key(did) else None


def _catalogue_item_index():
    key = _catalogue_dependency_key()
    if _cat_item_index["key"] != key:
        _cat_item_index["data"] = {it.get("id"): it for it in _catalogue_payload_items()}
        _cat_item_index["key"] = key
    return _cat_item_index["data"]


def catalogue_unit_ref(did, ctx=None):
    """Pseudo-datasheet for a ``cat:<catalogue_model_id>`` key.

    Returns ``{id, catalogue_model_id, name, faction_id (parent-collapsed),
    faction_label, army_ids, catalogue_only: True}`` built from
    ``catalogue_payload()`` items, or ``None`` for a non-cat key or unknown model.
    """
    cid = catalogue_model_id_from_key(did)
    if not cid:
        return None
    if ctx is not None:
        idx = ctx.get("payload_index")
        if idx is None:
            idx = {it.get("id"): it for it in _catalogue_payload_items(ctx)}
            ctx["payload_index"] = idx
        item = idx.get(cid)
    else:
        item = _catalogue_item_index().get(cid)
    if not item:
        return None
    return {
        "id": did,
        "catalogue_model_id": cid,
        "name": item.get("name", ""),
        "faction_id": item.get("faction_id", ""),
        "faction_label": item.get("faction_label", ""),
        "army_ids": item.get("army_ids", []),
        "catalogue_only": True,
    }


def _catalogue_model_in_faction(ref, fid):
    """Parent-aware faction membership check for a datasheet-less model, mirroring
    the catalogue search scoping in ``_catalogue_search_pool``."""
    store = get_store()
    scopes = {fid, store.faction_parent(fid)}
    return bool(scopes & set(ref.get("army_ids") or [])) or ref.get("faction_id") in scopes


def relink_catalogue_minis(catalogue_model_id, datasheet_ids):
    """Re-key a datasheet-less model's tracked data onto real datasheet(s) once a
    datasheet is linked to it, so the collection "updates throughout".

    Single datasheet  → re-key ``cat:`` minis and box-content rows directly.
    Multiple datasheets → the kit is now a multikit choice: rebuild affected box
    rows as a multikit group, and assign existing minis to the first datasheet
    (best-effort) with a note, since a standalone mini carries no box reference to
    rebuild a per-box build choice from. Returns the number of minis migrated.
    """
    store = get_store()
    dids = [d for d in (datasheet_ids or []) if d in store.ds_by_id]
    if not dids:
        return 0
    cat_key = CAT_PREFIX + catalogue_model_id
    with db() as c:
        if not _table_exists(c, "minis"):
            return 0
        if len(dids) == 1:
            did = dids[0]
            new_bid = store.ds_by_id.get(did, {}).get("id") or did
            cur = c.execute(
                "UPDATE minis SET datasheet_id=?, unit_bsdata_id=?, catalogue_model_id=? "
                "WHERE datasheet_id=? OR unit_bsdata_id=?",
                (did, new_bid, catalogue_model_id, cat_key, cat_key),
            )
            migrated = cur.rowcount
            if _table_exists(c, "custom_box_set_contents"):
                c.execute(
                    "UPDATE custom_box_set_contents SET datasheet_id=? WHERE datasheet_id=?",
                    (did, cat_key),
                )
        else:
            migrated = _relink_catalogue_minis_multi(c, catalogue_model_id, cat_key, dids)
    # Box caches embed the old cat: key — force a rebuild on next read.
    _box_cache["key"] = None
    _custom_box_cache["key"] = None
    return migrated


def _relink_catalogue_minis_multi(c, cid, cat_key, dids):
    store = get_store()
    mg = f"relink-{cid}"
    if _table_exists(c, "custom_box_set_contents"):
        rows = c.execute(
            "SELECT rowid, * FROM custom_box_set_contents WHERE datasheet_id=?",
            (cat_key,)).fetchall()
        for row in rows:
            c.execute("DELETE FROM custom_box_set_contents WHERE rowid=?", (row["rowid"],))
            for did in dids:
                c.execute(
                    """INSERT INTO custom_box_set_contents(box_set_id, datasheet_id,
                       catalogue_model_id, datasheet_count, physical_miniatures, notes,
                       sort_order, multikit_group) VALUES(?,?,?,?,?,?,?,?)""",
                    (row["box_set_id"], did, cid, row["datasheet_count"],
                     row["physical_miniatures"], row["notes"], row["sort_order"], mg))
    first = dids[0]
    new_bid = store.ds_by_id.get(first, {}).get("id") or first
    names = ", ".join(store.ds_by_id.get(d, {}).get("name", d) for d in dids)
    note = f"Auto-assigned on relink (buildable as {names})."
    cur = c.execute(
        "UPDATE minis SET datasheet_id=?, unit_bsdata_id=?, catalogue_model_id=?, "
        "notes = CASE WHEN COALESCE(notes,'')='' THEN ? ELSE notes || char(10) || ? END "
        "WHERE datasheet_id=? OR unit_bsdata_id=?",
        (first, new_bid, cid, note, note, cat_key, cat_key))
    return cur.rowcount


def _release_year(value):
    m = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
    return int(m.group(0)) if m else None


def _name_key(value):
    text = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    text = re.sub(r"\b(the|a|an|with|and|of)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _select_model_for_box(models, box_release_date):
    if not models:
        return None
    box_year = _release_year(box_release_date)
    if box_year:
        eligible = [m for m in models if (m.get("release_year") or 0) <= box_year]
        if eligible:
            return max(eligible, key=lambda m: (m.get("release_year") or 0, m.get("name", "")))
    return max(models, key=lambda m: (m.get("release_year") or 0, m.get("name", "")))


def _catalogue_model_by_name(unit_name, faction_id, box_release_date, ctx=None):
    wanted = _name_key(unit_name)
    if not wanted:
        return None, None
    cache_key = (wanted, faction_id or "", box_release_date or "")
    if ctx is not None and cache_key in ctx["name_matches"]:
        return ctx["name_matches"][cache_key]

    candidates = []
    for item in _catalogue_payload_items(ctx):
        army_ids = set(item.get("army_ids") or [])
        if faction_id and army_ids and faction_id not in army_ids and item.get("faction_id") != faction_id:
            continue
        name_key = _name_key(item.get("name", ""))
        note_key = _name_key(item.get("note", ""))
        score = 0
        if wanted == name_key:
            score = 100
        elif name_key.startswith(wanted) or wanted.startswith(name_key):
            score = 90
        elif wanted in name_key or name_key in wanted:
            score = 80
        elif wanted in note_key:
            score = 55
        if score:
            candidates.append((score, item))
    if not candidates:
        if ctx is not None:
            ctx["name_matches"][cache_key] = (None, None)
        return None, None

    best_score = max(score for score, _ in candidates)
    model = _select_model_for_box([item for score, item in candidates if score == best_score], box_release_date)
    result = (model.get("id"), model) if model else (None, None)
    if ctx is not None:
        ctx["name_matches"][cache_key] = result
    return result


def _catalogue_model_for_box_item(datasheet_id, catalogue_model_id, box_release_date,
                                  unit_name="", faction_id="", ctx=None):
    explicit = _catalogue_model_lookup(catalogue_model_id, ctx)
    if explicit:
        return catalogue_model_id, explicit
    models = _catalogue_models_for_datasheet(datasheet_id, ctx)
    model = _select_model_for_box(models, box_release_date)
    if model:
        return model.get("id"), model
    return _catalogue_model_by_name(unit_name, faction_id, box_release_date, ctx)


def _catalogue_model_label(unit_name, catalogue_model):
    if not catalogue_model:
        return ""
    model_name = catalogue_model.get("name") or unit_name
    year = catalogue_model.get("release_year")
    if year:
        if model_name == unit_name:
            return f"{unit_name} ({year} release)"
        return f"{model_name} ({year} release)"
    return model_name if model_name != unit_name else ""


def _normalize_box(box, source="seeded", ctx=None):
    store = get_store()
    ctx = ctx or _new_catalogue_context()
    if not box.get("id") or not isinstance(box.get("contents"), list):
        return None
    contents = []
    for item in box["contents"]:
        did = str(item.get("datasheet_id", ""))
        count = _as_int(item.get("datasheet_count"), 0, minimum=0)
        if count <= 0:
            continue
        if is_catalogue_key(did):
            ref = catalogue_unit_ref(did, ctx)
            if not ref:
                continue
            cat_cid = catalogue_model_id_from_key(did)
            catalogue_model = _catalogue_model_lookup(cat_cid, ctx)
            contents.append({
                "datasheet_id": did,
                "catalogue_model_id": cat_cid,
                "catalogue_model": catalogue_model,
                "catalogue_label": _catalogue_model_label(ref["name"], catalogue_model),
                "name": item.get("name") or ref["name"],
                "faction_id": item.get("faction_id") or ref["faction_id"],
                "datasheet_count": count,
                "physical_miniatures": _as_int(item.get("physical_miniatures"), count, minimum=0),
                "notes": item.get("notes", ""),
                "multikit_group": str(item.get("multikit_group") or "").strip() or None,
            })
            continue
        if did not in store.ds_by_id:
            continue
        ds = store.ds_by_id[did]
        unit_name = item.get("name") or ds.get("name", "")
        faction_id = item.get("faction_id") or ds.get("faction_id", "")
        catalogue_model_id = str(item.get("catalogue_model_id") or "").strip() or None
        catalogue_model_id, catalogue_model = _catalogue_model_for_box_item(
            did, catalogue_model_id, box.get("release_date", ""), unit_name, faction_id, ctx)
        contents.append({
            "datasheet_id": ds["id"],  # canonical Wahapedia id for consistent keys downstream
            "catalogue_model_id": catalogue_model_id,
            "catalogue_model": catalogue_model,
            "catalogue_label": _catalogue_model_label(unit_name, catalogue_model),
            "name": unit_name,
            "faction_id": faction_id,
            "datasheet_count": count,
            "physical_miniatures": _as_int(item.get("physical_miniatures"), count, minimum=0),
            "notes": item.get("notes", ""),
            "multikit_group": str(item.get("multikit_group") or "").strip() or None,
        })
    # Multikit groups share a physical pool — count each group's pool once.
    counted_mk = set()
    total_ds = total_phys = 0
    for i in contents:
        mg = i["multikit_group"]
        if mg:
            if mg not in counted_mk:
                counted_mk.add(mg)
                total_ds += i["datasheet_count"]
                total_phys += i["physical_miniatures"]
        else:
            total_ds += i["datasheet_count"]
            total_phys += i["physical_miniatures"]
    return {
        "id": box["id"],
        "name": box.get("name", box["id"]),
        "faction_id": box.get("faction_id", ""),
        "game_system": box.get("game_system", "Warhammer 40,000"),
        "release_date": box.get("release_date", ""),
        "manufacturer": box.get("manufacturer", ""),
        "status": box.get("status", "seeded"),
        "source": source,
        "editable": True,
        "total_datasheet_models": total_ds,
        "total_physical_miniatures": total_phys,
        "notes": box.get("notes", ""),
        "contents": contents,
        "sources": box.get("sources", []),
        "expected_minis": box.get("expected_minis") or None,
    }


def seeded_box_sets():
    try:
        mtime = os.path.getmtime(BOX_SETS_PATH)
    except OSError:
        return []
    cache_key = (mtime, _catalogue_dependency_key())
    if _box_cache["key"] == cache_key:
        return _box_cache["data"]
    try:
        with open(BOX_SETS_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        raw = {}
    boxes = raw.get("box_sets", [])
    ctx = _new_catalogue_context()
    clean = [b for b in (_normalize_box(box, "seeded", ctx) for box in boxes) if b]
    clean.sort(key=lambda b: b["name"])
    _box_cache["key"] = cache_key
    _box_cache["data"] = clean
    return clean


def custom_box_sets(conn=None):
    store = get_store()
    close = conn is None
    c = conn or db()
    try:
        if not _table_exists(c, "custom_box_sets"):
            return []
        cache_row = c.execute(
            "SELECT COUNT(*) cnt, COALESCE(MAX(updated_at), 0) updated FROM custom_box_sets"
        ).fetchone()
        cache_key = (cache_row["cnt"], cache_row["updated"], _catalogue_dependency_key())
        if _custom_box_cache["key"] == cache_key:
            return _custom_box_cache["data"]
        rows = c.execute("SELECT * FROM custom_box_sets").fetchall()
        boxes = []
        ctx = _new_catalogue_context()
        for r in rows:
            content_rows = c.execute(
                "SELECT * FROM custom_box_set_contents WHERE box_set_id=? ORDER BY sort_order, rowid",
                (r["id"],)).fetchall()
            contents = []
            for cr in content_rows:
                did = cr["datasheet_id"]
                cat_cid = cr["catalogue_model_id"] if "catalogue_model_id" in cr.keys() else None
                if is_catalogue_key(did):
                    ref = catalogue_unit_ref(did, ctx)
                    if not ref:
                        continue
                    name = ref["name"]
                    faction_id = ref["faction_id"]
                    cat_cid = cat_cid or catalogue_model_id_from_key(did)
                else:
                    ds = store.ds_by_id.get(did)
                    if not ds:
                        continue
                    name = ds.get("name", "")
                    faction_id = ds.get("faction_id", "")
                count = _as_int(cr["datasheet_count"], 1, minimum=1)
                contents.append({
                    "datasheet_id": did,
                    "catalogue_model_id": cat_cid,
                    "name": name,
                    "faction_id": faction_id,
                    "datasheet_count": count,
                    "physical_miniatures": _as_int(cr["physical_miniatures"], count, minimum=1),
                    "notes": cr["notes"] or "",
                    "multikit_group": cr["multikit_group"] or None,
                })
            try:
                sources = json.loads(r["sources"] or "[]")
            except ValueError:
                sources = []
            boxes.append(_normalize_box({
                "id": r["id"],
                "name": r["name"],
                "faction_id": r["faction_id"] or "",
                "game_system": r["game_system"] or "Warhammer 40,000",
                "release_date": r["release_date"] or "",
                "manufacturer": r["manufacturer"] or "",
                "status": r["status"] or "manual",
                "notes": r["notes"] or "",
                "contents": contents,
                "sources": sources,
                "expected_minis": r["expected_minis"] if r["expected_minis"] else None,
            }, "local", ctx))
        clean = [b for b in boxes if b]
        _custom_box_cache["key"] = cache_key
        _custom_box_cache["data"] = clean
        return clean
    finally:
        if close:
            c.close()


def box_sets():
    boxes = {b["id"]: b for b in seeded_box_sets()}
    for box in custom_box_sets():
        boxes[box["id"]] = box
    return sorted(boxes.values(), key=lambda b: b["name"])


def box_set_by_id(box_set_id):
    return {b["id"]: b for b in box_sets()}.get(box_set_id)


def bought_info(conn=None, boxes_by_id=None):
    """Return group-aware purchase data.

    Returns a dict with three keys:
      totals    – {did: physical_bought}
                  For multikit members: the shared pool size (same value for all
                  alternatives in the group). For standalone units: quantity × count.
      groups    – {gkey: {"pool": N, "members": [did, ...]}}
                  Each entry is a named physical pool spanning one or more purchases
                  of the same box/group. gkey is "<box_id>::<multikit_group>".
      did_groups – {did: [gkey, ...]}
                  Quick reverse-lookup: which groups does this datasheet belong to?
    """
    boxes = boxes_by_id or {b["id"]: b for b in box_sets()}
    close = conn is None
    c = conn or db()
    try:
        if not _table_exists(c, "purchases"):
            return {"totals": {}, "groups": {}, "did_groups": {}, "standalone": {}}
        rows = c.execute("SELECT box_set_id, quantity FROM purchases").fetchall()
    finally:
        if close:
            c.close()

    totals    = {}
    groups    = {}
    did_groups = {}
    standalone = {}   # {did: qty bought as a dedicated (non-multikit) kit}

    for r in rows:
        box = boxes.get(r["box_set_id"])
        qty = _as_int(r["quantity"], 0, minimum=0)
        if not box or qty <= 0:
            continue

        # First pass: resolve multikit groups defined in this box
        box_mk = {}   # local_group_id -> {physical, members}
        for item in box["contents"]:
            mg = item.get("multikit_group")
            if mg and mg not in box_mk:
                box_mk[mg] = {"physical": item["physical_miniatures"], "members": []}
            if mg:
                box_mk[mg]["members"].append(item["datasheet_id"])

        # Second pass: accumulate totals
        # Use a local set to ensure each group's pool is only incremented once per
        # purchase row — without this, the pool would be added N times for an
        # N-member multikit group, inflating the unlogged count.
        pool_added = set()
        for item in box["contents"]:
            did = item["datasheet_id"]
            mg  = item.get("multikit_group")

            if mg and mg in box_mk:
                pool = qty * box_mk[mg]["physical"]
                gkey = f"{box['id']}::{mg}"

                totals[did] = totals.get(did, 0) + pool

                if gkey not in groups:
                    groups[gkey] = {"pool": 0, "members": list(box_mk[mg]["members"])}
                if gkey not in pool_added:
                    groups[gkey]["pool"] += pool
                    pool_added.add(gkey)

                did_groups.setdefault(did, [])
                if gkey not in did_groups[did]:
                    did_groups[did].append(gkey)
            else:
                amt = qty * item["datasheet_count"]
                totals[did]     = totals.get(did, 0) + amt
                standalone[did] = standalone.get(did, 0) + amt

    return {"totals": totals, "groups": groups, "did_groups": did_groups,
            "standalone": standalone}


def bought_totals(conn=None):
    """Backward-compatible wrapper — returns {did: physical_bought}."""
    return bought_info(conn)["totals"]


def compute_unlogged_map(info, owned):
    """Return {did: unlogged_count} using group-aware logic.

    For standalone units: max(0, bought − owned).
    For multikit units:   max(0, pool − sum(owned for all group members)).
    Each group's unlogged is the same value for all its members.

    Also stores per-group unlogged in info["group_ul"] so that
    dedup_group_total can use the correct per-group value instead of the
    per-DID sum when a unit belongs to more than one multikit group.
    """
    totals     = info["totals"]
    groups     = info["groups"]
    did_groups = info["did_groups"]
    standalone = info.get("standalone", {})

    # A datasheet can be bought both as a dedicated kit (standalone) and as one
    # build option of a shared multikit pool. Attribute owned minis to that
    # datasheet's own dedicated kits first; only the remainder draws down a
    # shared pool. Otherwise a multikit member's owned count would wrongly
    # consume the pool and the dedicated-kit purchases would never be unlogged.
    standalone_ul = {}
    pool_owned = {}   # owned that counts against a shared pool
    for did in set(totals) | set(standalone):
        sa = standalone.get(did, 0)
        own = owned.get(did, 0)
        used = min(own, sa)
        standalone_ul[did] = sa - used
        pool_owned[did] = own - used

    group_ul = {}
    for gkey, g in groups.items():
        consumed = sum(pool_owned.get(m, 0) for m in g["members"])
        group_ul[gkey] = max(0, g["pool"] - consumed)
    info["group_ul"] = group_ul            # expose for dedup_group_total callers
    info["standalone_ul"] = standalone_ul  # expose for dedup_group_total callers

    result = {}
    for did in set(totals) | set(standalone):
        result[did] = (sum(group_ul[gk] for gk in did_groups.get(did, []))
                       + standalone_ul.get(did, 0))
    return result


def dedup_group_total(info, value_by_did):
    """Sum value_by_did, counting each multikit group only once.

    For multikit groups, uses per-group values rather than the per-DID sum so
    that a unit belonging to multiple groups is not counted N times.
    When value_by_did is info["totals"] each group contributes its physical
    pool; otherwise (e.g. ul_map) each group contributes its unlogged count
    stored by compute_unlogged_map in info["group_ul"].
    """
    counted  = set()
    total    = 0
    use_pool = value_by_did is info["totals"]
    group_ul      = info.get("group_ul", {})
    standalone    = info.get("standalone", {})
    standalone_ul = info.get("standalone_ul", {})

    for did, val in value_by_did.items():
        gkeys = info["did_groups"].get(did, [])
        if not gkeys:
            total += val
        else:
            # The dedicated-kit (standalone) portion is per-datasheet, so count it
            # in full; the shared pool is counted once per group.
            total += (standalone if use_pool else standalone_ul).get(did, 0)
            for gk in gkeys:
                if gk not in counted:
                    counted.add(gk)
                    if use_pool:
                        total += info["groups"].get(gk, {}).get("pool", 0)
                    else:
                        total += group_ul.get(gk, 0)
    return total


def purchase_payload(row, boxes_by_id=None):
    box = (boxes_by_id or {}).get(row["box_set_id"]) if boxes_by_id is not None else box_set_by_id(row["box_set_id"])
    qty = _as_int(row["quantity"], 1, minimum=1)
    contents = []
    if box:
        for item in box["contents"]:
            catalogue_model = item.get("catalogue_model") or {}
            contents.append({
                "datasheet_id": item["datasheet_id"],
                "catalogue_model_id": item.get("catalogue_model_id"),
                "catalogue_model": catalogue_model,
                "catalogue_label": item.get("catalogue_label", ""),
                "name": item.get("name", ""),
                "faction_id": item.get("faction_id", ""),
                "datasheet_count": item["datasheet_count"] * qty,
                "per_box_count": item["datasheet_count"],
                "physical_miniatures": item["physical_miniatures"] * qty,
                "release_year": catalogue_model.get("release_year"),
                "multikit_group": item.get("multikit_group"),
            })
    return {
        "id": row["id"],
        "box_set_id": row["box_set_id"],
        "box_name": box["name"] if box else row["box_set_id"],
        "faction_id": box["faction_id"] if box else "",
        "source": box["source"] if box else "",
        "release_date": box["release_date"] if box else "",
        "contents": contents,
        "quantity": qty,
        "notes": row["notes"] or "",
        "bought_at": row["bought_at"],
        "total_datasheet_models": (box["total_datasheet_models"] if box else 0) * qty,
        "total_physical_miniatures": (box["total_physical_miniatures"] if box else 0) * qty,
    }


def _box_slug(name):
    base = _slug(name) or "box-set"
    return base[:80].strip("-") or "box-set"


def _clean_box_payload(data, existing_id=None):
    store = get_store()
    name = str(data.get("name", ""))[:160].strip()
    if not name:
        return None, "Box name is required."
    fid = str(data.get("faction_id", ""))
    if fid and fid not in store.faction_by_id:
        return None, "Unknown faction."
    contents = data.get("contents", [])
    if not isinstance(contents, list) or not contents:
        return None, "Add at least one unit."
    cleaned = []
    seen = {}
    catalogue_cache = {}
    for item in contents:
        did = str(item.get("datasheet_id", ""))
        if is_catalogue_key(did):
            # Datasheet-less catalogue model: validate against the catalogue and
            # take the model id straight from the synthetic key.
            ref = catalogue_unit_ref(did)
            if not ref:
                return None, "Unknown model in box contents."
            if fid and not _catalogue_model_in_faction(ref, fid):
                return None, "One or more units do not belong to the selected army."
            catalogue_model_id = catalogue_model_id_from_key(did)
        else:
            ds = store.ds_by_id.get(did)
            if not ds:
                return None, "Unknown unit in box contents."
            # Parent-aware: an SM-tagged box accepts chapter units (a Blood Angels
            # unit is in SM); a chapter-tagged box accepts that chapter's units.
            if fid and not store.unit_in_faction(did, fid):
                return None, "One or more units do not belong to the selected army."
            catalogue_model_id = str(item.get("catalogue_model_id") or "").strip()[:160] or None
            if catalogue_model_id:
                if did not in catalogue_cache:
                    from catalogue_review import catalogue_models_for_datasheet
                    catalogue_cache[did] = {
                        m["id"] for m in catalogue_models_for_datasheet(did)
                    }
                if catalogue_model_id not in catalogue_cache[did]:
                    catalogue_model_id = None  # stale reference — drop silently
        count    = min(500, _as_int(item.get("datasheet_count"), 1, minimum=1))
        physical = min(500, _as_int(item.get("physical_miniatures"), count, minimum=1))
        notes    = str(item.get("notes", ""))[:300]
        mg       = str(item.get("multikit_group") or "").strip()[:80] or None
        seen_key = (did, catalogue_model_id)
        # Only merge duplicate standalone entries; multikit items always get their own row.
        if not mg and seen_key in seen and not cleaned[seen[seen_key]].get("multikit_group"):
            cleaned[seen[seen_key]]["datasheet_count"]     += count
            cleaned[seen[seen_key]]["physical_miniatures"] += physical
        else:
            if not mg:
                seen[seen_key] = len(cleaned)
            cleaned.append({
                "datasheet_id":     did,
                "catalogue_model_id": catalogue_model_id,
                "datasheet_count":  count,
                "physical_miniatures": physical,
                "notes":            notes,
                "multikit_group":   mg,
            })
    box_id = existing_id or str(data.get("id", "")).strip() or _box_slug(name)
    box_id = re.sub(r"[^a-z0-9_-]+", "-", box_id.lower()).strip("-")[:100] or uuid.uuid4().hex
    return {
        "id": box_id,
        "name": name,
        "faction_id": fid,
        "game_system": str(data.get("game_system", "Warhammer 40,000"))[:80].strip() or "Warhammer 40,000",
        "release_date": str(data.get("release_date", ""))[:40].strip(),
        "manufacturer": str(data.get("manufacturer", "Games Workshop"))[:100].strip() or "Games Workshop",
        "status": str(data.get("status", "manual"))[:40].strip() or "manual",
        "notes": str(data.get("notes", ""))[:2000],
        "sources": data.get("sources", []) if isinstance(data.get("sources", []), list) else [],
        "contents": cleaned,
        "expected_minis": _as_int(data.get("expected_minis"), None) or None,
    }, None


def _unit_search_pool(fid):
    store = get_store()
    if fid:
        # Tree scope: a Space Marines (SM) box must match chapter units too, so
        # an SM scope includes every chapter's units; a chapter scope returns
        # just that chapter's units.
        return store.units_in_faction_tree(fid)
    return [{"id": d["id"], "name": d["name"], "role": d.get("role") or "Other",
             "points": None, "faction_id": d.get("faction_id", "")}
            for d in store.datasheets if not d["virtual_bool"]]


def _catalogue_search_pool(fid):
    from catalogue_review import catalogue_payload
    store = get_store()
    items = catalogue_payload().get("items", [])
    # Parent-aware scope: catalogue army_ids are kept at the parent level (the
    # rollup collapses chapters back to SM in the catalogue), so a chapter scope
    # also matches its parent's catalogue items.
    scopes = {fid, store.faction_parent(fid)} if fid else set()
    pool = []
    for item in items:
        links = item.get("datasheet_links", [])
        if not links:
            continue
        army_ids = set(item.get("army_ids") or [])
        if fid and not (scopes & army_ids) and item.get("faction_id") not in scopes:
            continue
        pool.append({
            "id": item["id"],
            "name": item.get("name", ""),
            "faction_id": item.get("faction_id", ""),
            "datasheet_links": links,
        })
    return pool


def _match_unit_name(text, fid):
    def norm(s):
        s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower())
        s = re.sub(r"\b(grand master of the|with|and|the|a|an)\b", " ", s)
        s = re.sub(r"\bterminators\b", "terminator", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def score_name(wanted, candidate):
        name = norm(candidate)
        if wanted == name:
            return 100
        if wanted in name or name in wanted:
            return 80 + min(len(wanted), len(name)) / max(len(wanted), len(name))
        w_tokens = set(wanted.split())
        n_tokens = set(name.split())
        overlap = len(w_tokens & n_tokens)
        if overlap:
            return overlap / max(len(w_tokens), len(n_tokens)) * 60
        return 0

    wanted = norm(text)
    if not wanted:
        return None, []
    candidates = []
    for u in _catalogue_search_pool(fid):
        names = [u["name"]] + [l.get("datasheet_name", "") for l in u.get("datasheet_links", [])]
        best = max(score_name(wanted, n) for n in names if n)
        if best:
            candidates.append((best, u))
    candidates.sort(key=lambda x: (-x[0], x[1]["name"]))
    if not candidates:
        return None, []
    best_score, best = candidates[0]
    alternatives = [u for score, u in candidates[1:5] if score >= best_score - 10]
    return best, alternatives


def parse_box_text(text, fid):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return {"matches": [], "unresolved": []}
    parts = [p.strip(" ,.;:-") for p in re.split(r"\s+[–—-]\s+|;|\n", text) if p.strip()]
    matches = []
    unresolved = []
    ignored_terms = re.compile(r"\b(watcher in the dark|teleport homers?|tokens?|bases?)\b", re.I)
    for part in parts:
        for m in re.finditer(r"(\d+)\s*x\s+([^,;–—-]+)", part, re.I):
            qty = _as_int(m.group(1), 1, minimum=1)
            name = m.group(2).strip()
            if ignored_terms.search(name):
                continue
            unit, alternatives = _match_unit_name(name, fid)
            if not unit:
                unresolved.append({"text": name, "quantity": qty})
                continue
            links = unit.get("datasheet_links", [])
            primary = links[0] if links else {}
            matches.append({
                "catalogue_model_id": unit["id"],
                "catalogue_label": unit["name"],
                "datasheet_id": primary.get("datasheet_id", ""),
                "name": primary.get("datasheet_name") or unit["name"],
                "faction_id": primary.get("faction_id") or unit.get("faction_id", fid),
                "datasheet_count": qty,
                "physical_miniatures": qty,
                "source_text": name,
                "alternatives": [{
                    "catalogue_model_id": a["id"],
                    "datasheet_id": (a.get("datasheet_links") or [{}])[0].get("datasheet_id", ""),
                    "name": a["name"],
                    "faction_id": a.get("faction_id", fid),
                } for a in alternatives],
            })
    return {"matches": matches, "unresolved": unresolved}


def _save_custom_box(c, box):
    now = time.time()
    exists = c.execute("SELECT id FROM custom_box_sets WHERE id=?", (box["id"],)).fetchone()
    if exists:
        c.execute("""UPDATE custom_box_sets
                     SET name=?, faction_id=?, game_system=?, release_date=?, manufacturer=?,
                         status=?, notes=?, sources=?, expected_minis=?, updated_at=?
                     WHERE id=?""",
                  (box["name"], box["faction_id"], box["game_system"], box["release_date"],
                   box["manufacturer"], box["status"], box["notes"], json.dumps(box["sources"]),
                   box.get("expected_minis"), now, box["id"]))
    else:
        c.execute("""INSERT INTO custom_box_sets(id, name, faction_id, game_system, release_date,
                     manufacturer, status, notes, sources, expected_minis, created_at, updated_at)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (box["id"], box["name"], box["faction_id"], box["game_system"],
                   box["release_date"], box["manufacturer"], box["status"], box["notes"],
                   json.dumps(box["sources"]), box.get("expected_minis"), now, now))
    c.execute("DELETE FROM custom_box_set_contents WHERE box_set_id=?", (box["id"],))
    for idx, item in enumerate(box["contents"]):
        c.execute("""INSERT INTO custom_box_set_contents(box_set_id, datasheet_id, catalogue_model_id,
                     datasheet_count, physical_miniatures, notes, sort_order, multikit_group)
                     VALUES(?,?,?,?,?,?,?,?)""",
                  (box["id"], item["datasheet_id"], item.get("catalogue_model_id"),
                   item["datasheet_count"],
                   item["physical_miniatures"], item["notes"], idx,
                   item.get("multikit_group") or None))
