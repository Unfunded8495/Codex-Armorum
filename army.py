"""Army builder helpers: points calculation, enhancements, unit row assembly."""
import re

from data_store import get_store
from collection import _parse_comp_range
from utils import _int, _as_int


def _points_for(did, squad_size):
    """Find the points tier for the requested squad size.

    Warhammer points are paid by bracket. If a roster somehow asks for an
    in-between size, charge the next bracket up instead of under-pricing it.
    """
    store = get_store()
    costs = store.cost.get(did, [])
    if not costs:
        return 0
    parsed = []
    for c in costs:
        desc = (c.get("description") or "").lower()
        m = re.search(r"(\d+)\s*model", desc)
        if m:
            parsed.append((int(m.group(1)), _int(c.get("cost"))))
    if not parsed:
        return _int(costs[0].get("cost")) if costs else 0
    parsed.sort(key=lambda x: x[0])
    for count, pts in parsed:
        if count == squad_size:
            return pts
    valid = [(cnt, pts) for cnt, pts in parsed if cnt >= squad_size]
    return valid[0][1] if valid else parsed[-1][1]


def _squad_range_for(did):
    comp_range = _parse_comp_range(get_store().composition.get(did, []))
    if not comp_range:
        return {"min": 1, "max": None}
    return {"min": max(1, comp_range.get("min") or 1), "max": comp_range.get("max") or None}


def _normalise_squad_size(did, value, default=1):
    bounds = _squad_range_for(did)
    size = _as_int(value, default, minimum=bounds["min"])
    if bounds["max"]:
        size = min(size, bounds["max"])
    return size


def _enhancement_for(eid, detachment_id=None):
    store = get_store()
    if not eid:
        return None
    if detachment_id:
        for e in store.enhancements_by_detachment.get(detachment_id, []):
            if e.get("id") == eid:
                return e
        return None
    for enhs in store.enhancements_by_detachment.values():
        for e in enhs:
            if e.get("id") == eid:
                return e
    return None


def _enhancement_cost(eid, detachment_id=None):
    e = _enhancement_for(eid, detachment_id)
    return _int(e.get("cost", 0)) if e else 0


def _valid_detachment_for_faction(fid, dtid):
    store = get_store()
    if not dtid:
        return True
    detachment = store.detachment_by_id.get(dtid)
    if not detachment:
        return False
    # A chapter army accepts detachments from its own faction or from the
    # parent faction (so e.g. Blood Angels can field a generic Adeptus
    # Astartes detachment). Codex-divergent chapters get a slightly wider
    # detachment list than strict canon - accepted simplification.
    det_fac = detachment.get("faction_id")
    return det_fac == fid or det_fac == store.faction_parent(fid)


def _datasheet_in_faction(did, fid):
    # Parent-aware: a chapter unit validates as in its own chapter and in the
    # parent faction (a Blood Angels unit is in both Blood Angels and Adeptus
    # Astartes).
    return get_store().unit_in_faction(did, fid)


def _army_unit_row(c, au):
    store = get_store()
    did = au["datasheet_id"]
    ds = store.ds_by_id.get(did, {})
    # Normalize to the canonical Wahapedia datasheet id on access
    canonical_did = ds.get("id") or did
    if canonical_did != did:
        c.execute("UPDATE army_units SET datasheet_id=? WHERE id=?", (canonical_did, au["id"]))
        did = canonical_did
    bounds = _squad_range_for(did)
    squad_size = _normalise_squad_size(did, au["squad_size"], bounds["min"])
    if squad_size != au["squad_size"]:
        c.execute("UPDATE army_units SET squad_size=? WHERE id=?", (squad_size, au["id"]))
    assigned = au["assigned_count"]
    enhancement_id = au["enhancement_id"] or ""

    owned = c.execute(
        "SELECT COUNT(*) cnt FROM minis WHERE unit_bsdata_id=?", (did,)).fetchone()["cnt"]
    other_assigned = c.execute(
        "SELECT COALESCE(SUM(assigned_count),0) tot FROM army_units WHERE datasheet_id=? AND id!=?",
        (did, au["id"])).fetchone()["tot"]
    available = max(0, owned - other_assigned)
    max_current_assignment = min(squad_size, available)
    if assigned > max_current_assignment:
        assigned = max_current_assignment
        c.execute("UPDATE army_units SET assigned_count=? WHERE id=?", (assigned, au["id"]))

    pts = _points_for(did, squad_size)

    enh_name = ""
    enh_cost = 0
    if enhancement_id:
        army = c.execute("SELECT detachment_id FROM army_lists WHERE id=?", (au["army_list_id"],)).fetchone()
        e = _enhancement_for(enhancement_id, (army["detachment_id"] if army else "") or "")
        if e:
            enh_name = e.get("name", "")
            enh_cost = _int(e.get("cost", 0))

    return {
        "id": au["id"],
        "datasheet_id": did,
        "name": ds.get("name", ""),
        "role": ds.get("role", ""),
        "squad_size": squad_size,
        "squad_min": bounds["min"],
        "squad_max": bounds["max"],
        "assigned_count": assigned,
        "owned_count": owned,
        "available_count": available,
        "points": pts,
        "enhancement_id": enhancement_id,
        "enhancement_name": enh_name,
        "enhancement_cost": enh_cost,
        "notes": au["notes"] or "",
        "sort_order": au["sort_order"],
    }
