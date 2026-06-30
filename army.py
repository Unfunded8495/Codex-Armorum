"""Army builder helpers: points calculation, enhancements, unit row assembly."""
import json

from data_store import foc_category, get_store, ROLE_ORDER
from utils import _int, _as_int


def _tier_span(tier):
    """(lo, hi) total model count for a composition tier (summed across model
    lines)."""
    models = tier.get("models") or []
    return (sum(_int(m.get("min")) for m in models),
            sum(_int(m.get("max")) for m in models))


def _squad_bounds(did):
    """{min, max, default} model counts for a unit, from its composition tiers.
    Default mirrors the official app: the first ``is_default`` tier's max size.
    A unit with no tiers (rare) locks to a single model."""
    tiers = get_store().composition_tiers.get(did) or []
    spans = [(lo, hi) for lo, hi in (_tier_span(t) for t in tiers) if hi > 0]
    if not spans:
        return {"min": 1, "max": 1, "default": 1}
    lo = max(1, min(s[0] for s in spans))
    hi = max(s[1] for s in spans)
    default = None
    for t in tiers:
        if t.get("is_default"):
            d_hi = _tier_span(t)[1]
            if d_hi > 0:
                default = d_hi
                break
    if default is None:
        default = lo
    return {"min": lo, "max": hi, "default": max(lo, min(default, hi))}


def _tier_for_size(tiers, size):
    """The tier that prices ``size``: the first ``is_default`` covering tier,
    else the first covering tier in stored order. Reproduces the exporter's
    ``default_points`` resolution and disambiguates points-history duplicates."""
    covering = [t for t in tiers if _tier_span(t)[0] <= size <= _tier_span(t)[1]]
    if not covering:
        return None
    return next((t for t in covering if t.get("is_default")), covering[0])


def _points_for(did, squad_size):
    """Points for a unit at ``squad_size`` from the covering composition tier
    (flat per bracket). Falls back to ``default_points`` then 0 for the rare
    unit with no tiers."""
    store = get_store()
    tiers = store.composition_tiers.get(did) or []
    if not tiers:
        return _int(store.ds_by_id.get(did, {}).get("default_points"))
    bounds = _squad_bounds(did)
    size = max(bounds["min"], min(_as_int(squad_size, bounds["default"]), bounds["max"]))
    tier = _tier_for_size(tiers, size)
    if tier is None:
        spans = sorted(((_tier_span(t), t) for t in tiers), key=lambda x: x[0][0])
        tier = spans[0][1] if size < spans[0][0][0] else spans[-1][1]
    return _int(tier.get("points"))


def _composition_breakdown(did, squad_size):
    """``[{model, count}]`` at ``squad_size``: fixed models at their min, the
    single variable model absorbs the remainder. Tiers with >1 variable model
    (rare, all non-default) show each at its min, since the split is ambiguous."""
    tiers = get_store().composition_tiers.get(did) or []
    if not tiers:
        return []
    bounds = _squad_bounds(did)
    size = max(bounds["min"], min(_as_int(squad_size, bounds["default"]), bounds["max"]))
    tier = _tier_for_size(tiers, size) or tiers[0]
    models = tier.get("models") or []
    single_var = sum(1 for m in models if _int(m.get("max")) > _int(m.get("min"))) == 1
    remainder = max(0, size - sum(_int(m.get("min")) for m in models)) if single_var else 0
    out = []
    for m in models:
        lo, hi = _int(m.get("min")), _int(m.get("max"))
        count = min(hi, lo + remainder) if (single_var and hi > lo) else lo
        out.append({"model": m.get("model") or "", "count": count})
    return out


def _normalise_squad_size(did, value, default=None):
    bounds = _squad_bounds(did)
    if default is None:
        default = bounds["default"]
    return min(_as_int(value, default, minimum=bounds["min"]), bounds["max"])


def _enhancement_for(eid, detachment_id=None):
    store = get_store()
    if not eid:
        return None
    # w40k.db enhancement ids are integers, but the API/DB round-trips them as
    # strings (army_units.enhancement_id is TEXT). Compare as strings so a
    # posted "91" still matches the stored int 91.
    eid_s = str(eid)
    if detachment_id:
        for e in store.enhancements_by_detachment.get(detachment_id, []):
            if str(e.get("id")) == eid_s:
                return e
        return None
    for enhs in store.enhancements_by_detachment.values():
        for e in enhs:
            if str(e.get("id")) == eid_s:
                return e
    return None


def _enhancement_cost(eid, detachment_id=None):
    e = _enhancement_for(eid, detachment_id)
    return _int(e.get("cost", 0)) if e else 0


# ---- multi-detachment (Detachment Points) ---------------------------------
# An army unlocks one or more detachments by spending its battle-size Detachment
# Points; each contributes its own rules / enhancements / stratagems additively.
# The ordered set lives in army_lists.detachment_ids (JSON array); the legacy
# scalar detachment_id is mirrored to the first id for back-compat.

def parse_detachment_ids(row):
    """Ordered list of selected detachment ids for an ``army_lists`` row (or a
    plain mapping). Reads the JSON-array ``detachment_ids``; falls back to the
    legacy scalar ``detachment_id`` for un-migrated rows / v1 roster imports."""
    keys = row.keys() if hasattr(row, "keys") else row
    raw = (row["detachment_ids"] if "detachment_ids" in keys else "") or ""
    if raw:
        try:
            ids = json.loads(raw)
            if isinstance(ids, list):
                return [str(x) for x in ids if x]
        except (TypeError, ValueError):
            pass
    legacy = (row["detachment_id"] if "detachment_id" in keys else "") or ""
    return [legacy] if legacy else []


def detachment_set_cost(ids):
    """Total Detachment Points spent by the selected detachment ids."""
    store = get_store()
    return sum(_int(store.detachment_by_id.get(d, {}).get("points_cost")) for d in ids)


def _enhancement_for_ids(eid, dt_ids):
    """Resolve enhancement ``eid`` within the union of the given detachments'
    pools (enhancement ids are globally unique, but restricting to the selected
    set means an enhancement from a de-selected detachment stops resolving)."""
    if not eid:
        return None
    store = get_store()
    eid_s = str(eid)
    for d in dt_ids:
        for e in store.enhancements_by_detachment.get(d, []):
            if str(e.get("id")) == eid_s:
                return e
    return None


def clear_orphaned_enhancements(c, aid, dt_ids):
    """Clear any unit enhancement that no longer resolves within the army's
    selected detachments (e.g. after a detachment is de-selected). Returns the
    number of units cleared. Replaces the old blunt "clear all on any change"."""
    rows = c.execute(
        "SELECT id, enhancement_id FROM army_units WHERE army_list_id=? AND enhancement_id!=''",
        (aid,)).fetchall()
    cleared = 0
    for r in rows:
        if _enhancement_for_ids(r["enhancement_id"], dt_ids) is None:
            c.execute("UPDATE army_units SET enhancement_id='' WHERE id=?", (r["id"],))
            cleared += 1
    return cleared


def _valid_detachment_for_faction(fid, dtid):
    store = get_store()
    if not dtid:
        return True
    # Picker parity: accept exactly the detachments the picker offers for this
    # faction (membership via detachments_for_faction - own set or the parent's),
    # minus Combat Patrol, mirroring api_faction_detachments so the guard and the
    # picker agree by construction. The leaf-wins primary faction_id is NOT a
    # reliable membership test for multi-faction generic detachments - e.g. a
    # generic Space Marines detachment's primary is a chapter, not Adeptus
    # Astartes, so the old `det_fac == fid` check rejected Gladius for an
    # Adeptus Astartes army even though the picker offered it.
    offered = {d["id"] for d in store.detachments_for_faction(fid)
               if not d.get("is_combat_patrol")}
    return dtid in offered


def battle_size_caps(name):
    """Caps for a battle size name, or all-None for Custom/unknown (no limits
    enforced). Used by the army API and the validation engine."""
    bs = get_store().battle_size_by_name.get(name or "")
    if not bs:
        return {"points_limit": None, "enhancement_limit": None,
                "duplicate_unit_limit": None, "detachment_points_limit": None}
    return {
        "points_limit": bs["points_limit"],
        "enhancement_limit": bs["enhancement_limit"],
        # Surface the authoritative base (DUP_BASE) so the value shown matches what
        # duplicate_cap enforces — the v886 data has a stale Onslaught=3.
        "duplicate_unit_limit": DUP_BASE.get(name, bs["duplicate_unit_limit"]),
        "detachment_points_limit": bs["detachment_points_limit"],
    }


# Authoritative per-datasheet duplicate limits (Rule of N). v886 data has a stale
# Onslaught=3; the correct base is 4. Battleline / Dedicated Transport double these;
# Epic Heroes are always 1.
DUP_BASE = {"Incursion": 2, "Strike Force": 3, "Onslaught": 4}


def duplicate_cap(battle_size, did):
    """Max copies of datasheet ``did`` at ``battle_size``. Epic Heroes → 1 at any
    size (unique). Otherwise the per-size base from ``DUP_BASE`` (``None`` for Custom
    / Combat Patrol → no Rule-of-N), **doubled for Battleline / Dedicated Transport**
    (via ``foc_category()``, the same Force-Org bucket the roster's section
    headers use, so the two never disagree)."""
    ds = get_store().ds_by_id.get(did, {})
    if ds.get("role") == "Epic Hero":
        return 1
    base = DUP_BASE.get(battle_size)  # None for Custom / Combat Patrol
    if base is None:
        return None
    if foc_category(ds) in ("Battleline", "Dedicated Transports"):
        return base * 2
    return base


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
    bounds = _squad_bounds(did)
    squad_size = _normalise_squad_size(did, au["squad_size"])
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

    base_pts = _points_for(did, squad_size)

    # ---- wargear loadout: reconcile the stored selection to the current squad
    # size, price the delta, and persist it. The denormalized wargear_points lets
    # api_list_armies add it without importing the wargear engine. (Local import
    # avoids an army<->wargear module cycle.) ----
    import json
    import wargear
    _keys = au.keys()
    try:
        _overrides = json.loads(au["loadout"]) if ("loadout" in _keys and au["loadout"]) else {}
    except (TypeError, ValueError):
        _overrides = {}
    _wg = wargear.validate_selection(did, squad_size,
                                     wargear.apply_overrides(did, squad_size, _overrides))
    loadout = _wg["selection"]
    wargear_pts = _wg["points_delta"]
    wargear_violations = _wg["violations"]
    loadout_summary = _wg["loadout_summary"]
    # Persist the normalized sparse overrides ("" when default) + points delta.
    _loadout_json = json.dumps(_wg["overrides"], separators=(",", ":")) if _wg["overrides"] else ""
    _prev_loadout = (au["loadout"] if "loadout" in _keys else "") or ""
    _prev_wgpts = (au["wargear_points"] if "wargear_points" in _keys else 0) or 0
    if _loadout_json != _prev_loadout or wargear_pts != _prev_wgpts:
        c.execute("UPDATE army_units SET loadout=?, wargear_points=? WHERE id=?",
                  (_loadout_json, wargear_pts, au["id"]))
    pts = base_pts + wargear_pts

    army_row = c.execute(
        "SELECT faction_id, detachment_id, detachment_ids FROM army_lists WHERE id=?",
        (au["army_list_id"],)).fetchone()
    army_fid = (army_row["faction_id"] if army_row else "") or ""
    army_dtids = parse_detachment_ids(army_row) if army_row else []

    enh_name = ""
    enh_cost = 0
    if enhancement_id:
        e = _enhancement_for_ids(enhancement_id, army_dtids)
        if e:
            enh_name = e.get("name", "")
            enh_cost = _int(e.get("cost", 0))

    # Character / Warlord facts (enhancements + warlord are CHARACTER-only; Epic
    # Heroes can never take an Enhancement). Leader-attachment fields land in 4b.
    keywords = set(ds.get("_keywords") or [])
    is_character = "Character" in keywords
    is_epic_hero = ds.get("role") == "Epic Hero"
    _keys = au.keys()
    is_warlord = bool(au["is_warlord"]) if "is_warlord" in _keys else False
    attached_to = (au["attached_to"] if "attached_to" in _keys else "") or ""

    # Allied unit (Phase 5b): tagged when NOT native to the army faction but allowed
    # via an ally config (native-first). Allied units can't take Enhancements unless
    # their config's can_take_enhancements.
    ally_cfg = None if _datasheet_in_faction(did, army_fid) else store.ally_config_for(army_fid, did)
    is_ally = ally_cfg is not None
    ally_faction = " / ".join(ally_cfg["ally_faction_names"]) if ally_cfg else ""

    # ---- Leader attachment (Phase 4b). A leader (datasheet in store.leads) can
    # attach to an in-army Bodyguard it may lead, capped at one leader per bodyguard.
    leads_targets = {t["id"] for t in store.leads.get(did, [])}
    attach_targets = []
    attached_leader_name = ""
    siblings = c.execute(
        "SELECT id, datasheet_id, attached_to FROM army_units WHERE army_list_id=? AND id!=?",
        (au["army_list_id"], au["id"])).fetchall()
    if leads_targets:  # this unit is a leader → list bodyguards it can still join
        taken = {s["attached_to"] for s in siblings if s["attached_to"]}
        for sib in siblings:
            sdid = store.ds_by_id.get(sib["datasheet_id"], {}).get("id") or sib["datasheet_id"]
            if sdid in leads_targets and (sib["id"] not in taken or sib["id"] == attached_to):
                attach_targets.append({"id": sib["id"],
                                       "name": store.ds_by_id.get(sdid, {}).get("name", "")})
    for sib in siblings:  # is a leader attached to THIS unit (bodyguard)?
        if sib["attached_to"] == au["id"]:
            attached_leader_name = store.ds_by_id.get(sib["datasheet_id"], {}).get("name", "")
            break

    return {
        "id": au["id"],
        "datasheet_id": did,
        "name": ds.get("name", ""),
        "role": ds.get("role", ""),
        "foc_category": foc_category(ds),
        "squad_size": squad_size,
        "squad_min": bounds["min"],
        "squad_max": bounds["max"],
        "composition": _composition_breakdown(did, squad_size),
        "assigned_count": assigned,
        "owned_count": owned,
        "available_count": available,
        "points": pts,
        "wargear_points": wargear_pts,
        "loadout": loadout,
        "loadout_summary": loadout_summary,
        "wargear_schema": wargear.wargear_schema(did),
        "wargear_violations": wargear_violations,
        "enhancement_id": enhancement_id,
        "enhancement_name": enh_name,
        "enhancement_cost": enh_cost,
        "is_character": is_character,
        "is_epic_hero": is_epic_hero,
        "can_have_enhancement": is_character and not is_epic_hero
                                and (not is_ally or bool(ally_cfg and ally_cfg["can_take_enhancements"])),
        "is_warlord": is_warlord,
        "is_ally": is_ally,
        "ally_faction": ally_faction,
        "attached_to": attached_to,
        "attach_targets": attach_targets,
        "attached_leader_name": attached_leader_name,
        "notes": au["notes"] or "",
        "sort_order": au["sort_order"],
    }


# ---- roster export / import (Phase 6e) -----------------------------------

def roster_json(c, aid):
    """Re-importable structured roster. Leader attachments are stored as indices
    into the units array because army-unit ids are regenerated on import."""
    army = c.execute("SELECT * FROM army_lists WHERE id=?", (aid,)).fetchone()
    if not army:
        return None
    rows = c.execute(
        "SELECT * FROM army_units WHERE army_list_id=? ORDER BY sort_order, rowid",
        (aid,)).fetchall()
    idx = {r["id"]: i for i, r in enumerate(rows)}
    dt_ids = parse_detachment_ids(army)
    return {
        "format": "codex-armorum-roster",
        "version": 2,
        "name": army["name"],
        "faction_id": army["faction_id"],
        "battle_size": army["battle_size"] or "",
        "points_limit": army["points_limit"],
        # v2 carries the full ordered detachment set; detachment_id (first id)
        # is kept so a v1 importer still restores the primary detachment.
        "detachment_ids": dt_ids,
        "detachment_id": dt_ids[0] if dt_ids else "",
        "units": [{
            "datasheet_id": r["datasheet_id"],
            "squad_size": r["squad_size"],
            "loadout": json.loads(r["loadout"] or "{}"),
            "enhancement_id": r["enhancement_id"] or "",
            "is_warlord": bool(r["is_warlord"]),
            "attached_to_index": idx.get(r["attached_to"]) if r["attached_to"] else None,
        } for r in rows],
    }


def _roster_unit_lines(u, leader):
    sz = (" x%d" % u["squad_size"]) if u["squad_size"] > 1 else ""
    star = " [Warlord]" if u["is_warlord"] else ""
    ally = (" [Ally: %s]" % u["ally_faction"]) if u.get("is_ally") and u.get("ally_faction") else ""
    out = ["  %s%s - %d pts%s%s" % (u["name"], sz, u["points"], star, ally)]
    if u.get("enhancement_name"):
        out.append("    Enhancement: %s" % u["enhancement_name"])
    if u.get("loadout_summary"):
        out.append("    %s" % u["loadout_summary"])
    if leader:
        lstar = " [Warlord]" if leader["is_warlord"] else ""
        out.append("    + %s - %d pts%s" % (leader["name"], leader["points"], lstar))
        if leader.get("enhancement_name"):
            out.append("      Enhancement: %s" % leader["enhancement_name"])
        if leader.get("loadout_summary"):
            out.append("      %s" % leader["loadout_summary"])
    return out


def roster_text(c, aid):
    """Human-readable roster: faction, detachment, points, then units by role
    with wargear, enhancements, warlord and attached leaders."""
    army = c.execute("SELECT * FROM army_lists WHERE id=?", (aid,)).fetchone()
    if not army:
        return ""
    rows = c.execute(
        "SELECT * FROM army_units WHERE army_list_id=? ORDER BY sort_order, rowid",
        (aid,)).fetchall()
    units = [_army_unit_row(c, r) for r in rows]
    store = get_store()
    fac = store.faction_by_id.get(army["faction_id"], {})
    det_names = [store.detachment_by_id.get(d, {}).get("name", "")
                 for d in parse_detachment_ids(army)]
    det_names = [n for n in det_names if n]
    total = sum(u["points"] for u in units)
    bs = army["battle_size"] or "Custom"
    sub = fac.get("display_name") or fac.get("name", "") or army["faction_id"]
    if det_names:
        sub += " - " + ", ".join(det_names)
    lines = ["%s (%s) - %d/%s pts" % (army["name"], bs, total, army["points_limit"]), sub]
    leader_for = {u["attached_to"]: u for u in units if u["attached_to"]}
    standalone = [u for u in units if not u["attached_to"]]
    by_role = {}
    for u in standalone:
        by_role.setdefault(u["role"] or "Other", []).append(u)
    order = [r for r in ROLE_ORDER if r in by_role] + \
            [r for r in by_role if r not in ROLE_ORDER]
    for role in order:
        lines.append("")
        lines.append(role.upper())
        for u in by_role[role]:
            lines += _roster_unit_lines(u, leader_for.get(u["id"]))
    return "\n".join(lines)
