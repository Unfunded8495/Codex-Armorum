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


def eligible_tiers(did, fid=None, dt_ids=None):
    """Composition tiers offered to an army. A tier can be gated to a roster
    faction (e.g. the 80-pt Assault Intercessor tier is Blood Angels only) or
    to a detachment (e.g. the 380-pt C'tan tiers of Pantheon of Woe). Gated
    tiers that match the context REPLACE the ungated list — the data mirrors
    every gated set span-for-span against the ungated one, so e.g. a Blood
    Angels army prices Outriders entirely off the Blood Angels tiers while an
    Ultramarines army never sees them. With no context at all (both ``fid``
    and ``dt_ids`` None) every tier is returned — the legacy behaviour for
    callers without an army, e.g. the wargear engine's default counts."""
    store = get_store()
    tiers = store.composition_tiers.get(did) or []
    if fid is None and dt_ids is None:
        return tiers
    matching_gated, ungated = [], []
    for t in tiers:
        req_fac = t.get("required_faction_keyword_ids")
        req_det = t.get("required_detachment_ids")
        if not req_fac and not req_det:
            ungated.append(t)
            continue
        fac_ok = not req_fac or (fid and any(
            fid == r or store.faction_parent(fid) == r for r in req_fac))
        det_ok = not req_det or (dt_ids and any(d in req_det for d in dt_ids))
        if fac_ok and det_ok:
            matching_gated.append(t)
    return matching_gated or ungated or tiers


def _squad_bounds(did, fid=None, dt_ids=None):
    """{min, max, default} model counts for a unit, from its composition tiers.
    Default mirrors the official app: the first ``is_default`` tier's max size.
    A unit with no tiers (rare) locks to a single model."""
    tiers = eligible_tiers(did, fid, dt_ids)
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


def _points_for(did, squad_size, fid=None, dt_ids=None):
    """Points for a unit at ``squad_size`` from the covering composition tier
    (flat per bracket), honouring faction/detachment tier gates when the army
    context is given. Falls back to ``default_points`` then 0 for the rare
    unit with no tiers."""
    store = get_store()
    tiers = eligible_tiers(did, fid, dt_ids)
    if not tiers:
        return _int(store.ds_by_id.get(did, {}).get("default_points"))
    bounds = _squad_bounds(did, fid, dt_ids)
    size = max(bounds["min"], min(_as_int(squad_size, bounds["default"]), bounds["max"]))
    tier = _tier_for_size(tiers, size)
    if tier is None:
        spans = sorted(((_tier_span(t), t) for t in tiers), key=lambda x: x[0][0])
        tier = spans[0][1] if size < spans[0][0][0] else spans[-1][1]
    return _int(tier.get("points"))


def points_step(did):
    """The duplicate-selection surcharge for a datasheet ("After the Nth
    selection of this unit, additional selections each cost +X pts"), as
    ``{"step_at": N+1, "step_points": X}``, or None. w40k.db carries at most
    one step per datasheet."""
    steps = get_store().ds_by_id.get(did, {}).get("_points_steps") or []
    return steps[0] if steps else None


def points_step_surcharge(did, count):
    """Total surcharge for ``count`` selections of ``did`` in one army: every
    selection from ordinal ``step_at`` onward pays ``step_points`` on top of
    its tier price."""
    step = points_step(did)
    if not step or count < _int(step.get("step_at")):
        return 0
    return _int(step.get("step_points")) * (count - (_int(step.get("step_at")) - 1))


def _composition_breakdown(did, squad_size, fid=None, dt_ids=None):
    """``[{model, count}]`` at ``squad_size``: fixed models at their min, the
    single variable model absorbs the remainder. Tiers with >1 variable model
    (rare, all non-default) show each at its min, since the split is ambiguous."""
    tiers = eligible_tiers(did, fid, dt_ids)
    if not tiers:
        return []
    bounds = _squad_bounds(did, fid, dt_ids)
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


def _normalise_squad_size(did, value, default=None, fid=None, dt_ids=None):
    bounds = _squad_bounds(did, fid, dt_ids)
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


# ---- leader attachment (leader_group enforcement) ---------------------------
# Legality comes from store.leader_groups (the official app's structured
# leader-attachment groups), not the flat leads/led_by name lists: a group can
# be gated to a detachment, demand every unit in the attached party share a
# keyword, and is typed - a 'leader' group fills the bodyguard's single Leader
# slot while 'support' (Lieutenants, Dialogus, ...) attaches alongside it.

# The five Chaos mark keywords used by requires_all_units_keyword gates (the
# only values in v886 data). A mark is chosen at army-building time in the
# official app and isn't modelled here, so a unit with no static mark keyword
# counts as able to take the required one; a unit statically marked otherwise
# (e.g. a Khorne unit against a Nurgle gate) can never match.
MARK_KEYWORDS = frozenset(
    {"Chaos Undivided", "Khorne", "Nurgle", "Tzeentch", "Slaanesh"})


def _rk(row, key):
    """Tolerant field access for sqlite3.Row / dict army-unit rows."""
    try:
        return row[key] or ""
    except (KeyError, IndexError):
        return ""


def leader_groups_for(did, enhancement_id, dt_ids, ignore_detachments=False):
    """Effective leader-attachment groups for a unit in an army context: the
    datasheet's groups filtered by the army's selected detachments, plus any
    granted by the unit's enhancement (grants_leader_attachment - resolved
    within the selected detachments, so a grant from a de-selected detachment
    stops applying together with its enhancement)."""
    store = get_store()
    out = []
    for g in store.leader_groups.get(did, []):
        if not ignore_detachments:
            req = g.get("required_detachment_id")
            exc = g.get("excluded_detachment_id")
            if req and req not in dt_ids:
                continue
            if exc and exc in dt_ids:
                continue
        out.append(g)
    e = _enhancement_for_ids(enhancement_id, dt_ids)
    if e:
        out += e.get("leader_grants") or []
    return out


def _satisfies_party_keyword(did, kw):
    """Unit ``did`` passes a requires_all_units_keyword gate for ``kw``."""
    kws = set(get_store().ds_by_id.get(did, {}).get("_keywords") or [])
    if kw in kws:
        return True
    if kw in MARK_KEYWORDS:
        return not (kws & MARK_KEYWORDS)
    return False


def _attach_kinds(groups, target_did, party_dids):
    """Which bodyguard slots ({'leader', 'support'}) ``groups`` allow against
    bodyguard ``target_did``. ``party_dids`` are the datasheets of the full
    prospective party (bodyguard + every attached character) for the
    requires_all_units_keyword gate."""
    kinds = set()
    for g in groups:
        if target_did not in g["member_ids"]:
            continue
        kw = g.get("requires_all_units_keyword")
        if kw and not all(_satisfies_party_keyword(d, kw) for d in party_dids):
            continue
        kinds.add("support" if g.get("type") == "support" else "leader")
    return kinds


def attach_check(dt_ids, rows, leader, target):
    """``None`` when ``leader`` may attach to ``target``, else a user-facing
    reason. ``rows`` are the army's unit rows (mappings with id, datasheet_id,
    enhancement_id, attached_to), including ``leader`` and ``target``. A
    'support' match always admits; a 'leader' match needs the bodyguard's
    single Leader slot free - attached characters that could sit in a support
    slot don't occupy it."""
    store = get_store()

    def canon(d):
        return store.ds_by_id.get(d, {}).get("id") or d

    lid, tid = _rk(leader, "id"), _rk(target, "id")
    ldid = canon(_rk(leader, "datasheet_id"))
    tdid = canon(_rk(target, "datasheet_id"))
    if _rk(target, "attached_to"):
        return "that unit is itself attached to another unit"
    others = [r for r in rows
              if _rk(r, "attached_to") == tid and _rk(r, "id") != lid]
    party = [tdid] + [canon(_rk(r, "datasheet_id")) for r in others] + [ldid]
    lenh = _rk(leader, "enhancement_id")
    kinds = _attach_kinds(leader_groups_for(ldid, lenh, dt_ids), tdid, party)
    if "support" in kinds:
        return None
    if "leader" in kinds:
        for r in others:
            okinds = _attach_kinds(
                leader_groups_for(canon(_rk(r, "datasheet_id")),
                                  _rk(r, "enhancement_id"), dt_ids),
                tdid, party)
            if "support" not in okinds:
                return "that unit already has a Leader"
        return None
    # Nothing matched - say why.
    raw = leader_groups_for(ldid, lenh, dt_ids, ignore_detachments=True)
    if not any(tdid in g["member_ids"] for g in raw):
        return "this leader cannot join that unit"
    if _attach_kinds(raw, tdid, party):
        return "not available with this army's detachment(s)"
    return "every unit in the attached party must share a required keyword"


def _army_unit_row(c, au):
    store = get_store()
    did = au["datasheet_id"]
    ds = store.ds_by_id.get(did, {})
    # Normalize to the canonical Wahapedia datasheet id on access
    canonical_did = ds.get("id") or did
    if canonical_did != did:
        c.execute("UPDATE army_units SET datasheet_id=? WHERE id=?", (canonical_did, au["id"]))
        did = canonical_did

    # Army context up front: faction + selected detachments gate which
    # composition tiers (sizes and prices) this unit is offered.
    army_row = c.execute(
        "SELECT faction_id, detachment_id, detachment_ids FROM army_lists WHERE id=?",
        (au["army_list_id"],)).fetchone()
    army_fid = (army_row["faction_id"] if army_row else "") or ""
    army_dtids = parse_detachment_ids(army_row) if army_row else []

    bounds = _squad_bounds(did, army_fid, army_dtids)
    squad_size = _normalise_squad_size(did, au["squad_size"], fid=army_fid, dt_ids=army_dtids)
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

    base_pts = _points_for(did, squad_size, army_fid, army_dtids)

    # Duplicate-selection surcharge: this row's ordinal among the army's
    # selections of the same datasheet, in roster order (sort_order, rowid --
    # the same order api_get_army lists rows). From ordinal step_at onward each
    # selection pays step_points on top of its tier price, mirroring the
    # official app's "After the Nth selection..." unit-composition note.
    step = points_step(did)
    step_pts = 0
    if step:
        earlier = c.execute(
            "SELECT COUNT(*) n FROM army_units WHERE army_list_id=? AND datasheet_id=?"
            " AND (COALESCE(sort_order,0) < COALESCE(?,0)"
            "      OR (COALESCE(sort_order,0) = COALESCE(?,0)"
            "          AND rowid < (SELECT rowid FROM army_units WHERE id=?)))",
            (au["army_list_id"], did, au["sort_order"], au["sort_order"],
             au["id"])).fetchone()["n"]
        if earlier + 1 >= _int(step.get("step_at")):
            step_pts = _int(step.get("step_points"))

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
    loadout_setups = _wg["loadout_setups"]
    # Persist the normalized sparse overrides ("" when default) + points delta.
    _loadout_json = json.dumps(_wg["overrides"], separators=(",", ":")) if _wg["overrides"] else ""
    _prev_loadout = (au["loadout"] if "loadout" in _keys else "") or ""
    _prev_wgpts = (au["wargear_points"] if "wargear_points" in _keys else 0) or 0
    if _loadout_json != _prev_loadout or wargear_pts != _prev_wgpts:
        c.execute("UPDATE army_units SET loadout=?, wargear_points=? WHERE id=?",
                  (_loadout_json, wargear_pts, au["id"]))
    pts = base_pts + wargear_pts + step_pts

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
    ally_faction = " / ".join(ally_cfg.get("ally_faction_display_names")
                              or ally_cfg["ally_faction_names"]) if ally_cfg else ""

    # ---- Leader attachment: legality from the structured leader_group data
    # (detachment gates, leader vs support slots, party keyword matching,
    # enhancement-granted targets) via attach_check.
    attach_targets = []
    siblings = c.execute(
        "SELECT id, datasheet_id, enhancement_id, attached_to FROM army_units "
        "WHERE army_list_id=? AND id!=?",
        (au["army_list_id"], au["id"])).fetchall()
    self_row = {"id": au["id"], "datasheet_id": did,
                "enhancement_id": enhancement_id, "attached_to": attached_to}
    all_rows = [self_row] + list(siblings)
    if leader_groups_for(did, enhancement_id, army_dtids):
        for sib in siblings:
            if sib["attached_to"]:
                continue  # an attached character is not a bodyguard candidate
            if (sib["id"] == attached_to
                    or attach_check(army_dtids, all_rows, self_row, sib) is None):
                sdid = store.ds_by_id.get(sib["datasheet_id"], {}).get("id") or sib["datasheet_id"]
                attach_targets.append({"id": sib["id"],
                                       "name": store.ds_by_id.get(sdid, {}).get("name", "")})
    # Characters attached to THIS unit (bodyguard) - a Leader plus any number
    # of support characters, so this can be several names.
    attached_leader_name = ", ".join(
        n for n in (store.ds_by_id.get(s["datasheet_id"], {}).get("name", "")
                    for s in siblings if s["attached_to"] == au["id"]) if n)

    return {
        "id": au["id"],
        "datasheet_id": did,
        "name": ds.get("name", ""),
        "role": ds.get("role", ""),
        "foc_category": foc_category(ds),
        "squad_size": squad_size,
        "squad_min": bounds["min"],
        "squad_max": bounds["max"],
        "composition": _composition_breakdown(did, squad_size, army_fid, army_dtids),
        "assigned_count": assigned,
        "owned_count": owned,
        "available_count": available,
        "points": pts,
        "wargear_points": wargear_pts,
        "points_step": step,
        "points_step_added": step_pts,
        "loadout": loadout,
        "loadout_summary": loadout_summary,
        "loadout_setups": loadout_setups,
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


def _roster_unit_lines(u, leaders):
    sz = (" x%d" % u["squad_size"]) if u["squad_size"] > 1 else ""
    star = " [Warlord]" if u["is_warlord"] else ""
    ally = (" [Ally: %s]" % u["ally_faction"]) if u.get("is_ally") and u.get("ally_faction") else ""
    out = ["  %s%s - %d pts%s%s" % (u["name"], sz, u["points"], star, ally)]
    if u.get("enhancement_name"):
        out.append("    Enhancement: %s" % u["enhancement_name"])
    if u.get("loadout_summary"):
        out.append("    %s" % u["loadout_summary"])
    for leader in leaders or []:
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
    leaders_for = {}
    for u in units:
        if u["attached_to"]:
            leaders_for.setdefault(u["attached_to"], []).append(u)
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
            lines += _roster_unit_lines(u, leaders_for.get(u["id"]))
    return "\n".join(lines)
