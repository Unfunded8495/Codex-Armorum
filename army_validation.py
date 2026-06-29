"""Army roster legality engine.

Returns structured validation rows the army builder renders. Each row is
``{"level": "ok"|"warn"|"err"|"info", "code": str, "message": str}``. The
renderer keys off ``level`` only, so later phases add new ``code`` values
(duplicate-unit, detachment-cap, allies) without touching the frontend.

Phase 1 codes: points_over / points_ok, enhancement_over / enhancement_ok,
no_detachment, under_assigned, over_assigned, wishlist_units.
"""
from army import _army_unit_row, battle_size_caps, duplicate_cap
from data_store import get_store


def _unit_rows(c, aid):
    rows = c.execute(
        "SELECT * FROM army_units WHERE army_list_id=? ORDER BY sort_order, rowid",
        (aid,)).fetchall()
    return [_army_unit_row(c, u) for u in rows]


def _total_points(units):
    return sum((u.get("points") or 0) + (u.get("enhancement_cost") or 0)
               for u in units)


def _rows(army, units, store):
    caps = battle_size_caps(army["battle_size"])
    rows = []
    total = _total_points(units)

    # Points vs limit. For named sizes the cap is derived; for Custom it is the
    # stored free-form value. Only enforce when there is a positive cap.
    limit = caps["points_limit"]
    if limit is None:
        limit = army["points_limit"]
    if limit and limit > 0:
        if total > limit:
            rows.append({"level": "err", "code": "points_over",
                         "message": f"{total - limit} pts over limit"})
        else:
            rows.append({"level": "ok", "code": "points_ok",
                         "message": "Within points limit"})

    # Enhancement count vs the battle-size cap (skipped for Custom / null cap).
    enh_limit = caps["enhancement_limit"]
    if enh_limit is not None:
        enh_count = sum(1 for u in units if u.get("enhancement_id"))
        if enh_count > enh_limit:
            rows.append({"level": "err", "code": "enhancement_over",
                         "message": f"{enh_count} enhancements - limit is {enh_limit}"})
        elif enh_count:
            rows.append({"level": "ok", "code": "enhancement_ok",
                         "message": f"{enh_count} of {enh_limit} enhancements"})

    # Detachment chosen?
    if not (army["detachment_id"] or ""):
        rows.append({"level": "info", "code": "no_detachment",
                     "message": "No detachment selected"})

    # Ownership rows (carried over from the old client-side checks).
    for u in units:
        owned = u.get("owned_count") or 0
        assigned = u.get("assigned_count") or 0
        squad = u.get("squad_size") or 0
        if assigned > squad:
            rows.append({"level": "err", "code": "over_assigned",
                         "message": f"{u['name']}: {assigned - squad} too many assigned"})
        elif owned > 0 and assigned < squad:
            short = squad - assigned
            rows.append({"level": "warn", "code": "under_assigned",
                         "message": f"{u['name']}: assign {short} more "
                                    f"model{'' if short == 1 else 's'}"})
    wishlist = sum(1 for u in units if (u.get("owned_count") or 0) == 0)
    if wishlist:
        rows.append({"level": "info", "code": "wishlist_units",
                     "message": f"{wishlist} unit{'' if wishlist == 1 else 's'} "
                                f"not yet owned (wishlist)"})

    # Wargear legality (auto-correct heals on write, so this normally stays clean).
    for u in units:
        for v in (u.get("wargear_violations") or []):
            rows.append({"level": v.get("level", "warn"), "code": "wargear_illegal",
                         "message": f"{u['name']}: {v.get('message', '')}"})

    # Enhancement eligibility + uniqueness, and the single-Warlord rule (Phase 4).
    from eligibility import enhancement_eligible
    dtid = army["detachment_id"] or ""
    by_enh = {}
    for u in units:
        eid = str(u.get("enhancement_id") or "")
        if not eid:
            continue
        by_enh.setdefault(eid, []).append(u)
        ds = store.ds_by_id.get(u.get("datasheet_id"), {})
        e = next((x for x in store.enhancements_by_detachment.get(dtid, [])
                  if str(x.get("id")) == eid), None)
        if e and not enhancement_eligible(set(ds.get("_keywords") or []), ds.get("role"),
                                          e.get("eligibility_struct") or {}, ds.get("name")):
            rows.append({"level": "err", "code": "enhancement_ineligible",
                         "message": f"{u['name']}: not eligible for "
                                    f"{u.get('enhancement_name') or 'that enhancement'}"})
    for eid, us in by_enh.items():
        if len(us) > 1:
            rows.append({"level": "err", "code": "enhancement_duplicate",
                         "message": f"{us[0].get('enhancement_name') or 'Enhancement'} "
                                    f"taken by {len(us)} units - each is unique"})

    warlords = [u for u in units if u.get("is_warlord")]
    if len(warlords) > 1:
        rows.append({"level": "err", "code": "warlord_multiple",
                     "message": f"{len(warlords)} Warlords - choose exactly one"})
    elif not warlords and any(u.get("is_character") for u in units):
        rows.append({"level": "warn", "code": "warlord_missing",
                     "message": "No Warlord selected"})

    # Leader attachment legality (Phase 4b) — defensive; the save path enforces it.
    by_id = {u["id"]: u for u in units}
    for u in units:
        att = u.get("attached_to") or ""
        if not att:
            continue
        tgt = by_id.get(att)
        leads = {t["id"] for t in store.leads.get(u.get("datasheet_id"), [])}
        if not tgt or tgt.get("datasheet_id") not in leads:
            rows.append({"level": "err", "code": "illegal_attachment",
                         "message": f"{u['name']}: invalid leader attachment"})

    # Duplicate-datasheet limit (Phase 5a): Rule of N, Battleline/Transport x2,
    # Epic Heroes 1. Custom / Combat Patrol have no cap (Epic Heroes still 1).
    bs = army["battle_size"] or ""
    counts, flagged = {}, set()
    for u in units:
        counts[u.get("datasheet_id")] = counts.get(u.get("datasheet_id"), 0) + 1
    for u in units:
        did = u.get("datasheet_id")
        if did in flagged:
            continue
        cap = duplicate_cap(bs, did)
        if cap is not None and counts[did] > cap:
            flagged.add(did)
            at = f" at {bs}" if bs and bs != "Custom" else ""
            rows.append({"level": "err", "code": "duplicate_over",
                         "message": f"{counts[did]}x {u['name']}, max {cap}{at}"})

    # Detachment excludes (Phase 5a): excludes_datasheets holds datasheet NAMES.
    det = store.detachment_by_id.get(army["detachment_id"] or "")
    excludes = set(det.get("excludes_datasheets") or []) if det else set()
    for u in units:
        if u["name"] in excludes:
            rows.append({"level": "err", "code": "detachment_excluded",
                         "message": f"{u['name']} is excluded by this detachment"})

    # Allied factions (Phase 5b): per ally config, a points budget and the keyword
    # caps, both at the army's battle size. Custom has no limits -> unlimited.
    if bs and bs != "Custom":
        afid = army["faction_id"]
        by_cfg = {}
        for u in units:
            if not u.get("is_ally"):
                continue
            cfg = store.ally_config_for(afid, u.get("datasheet_id"))
            if cfg:
                by_cfg.setdefault(cfg["id"], (cfg, []))[1].append(u)
        for cfg, aus in by_cfg.values():
            label = " / ".join(cfg["ally_faction_names"]) or "Allies"
            lim = next((p.get("points") for p in cfg["points_limits"]
                        if p.get("battle_size") == bs), None)
            if lim is not None:
                spent = sum((u.get("points") or 0) + (u.get("enhancement_cost") or 0) for u in aus)
                if spent > lim:
                    rows.append({"level": "err", "code": "allies_points_over",
                                 "message": f"{label} allies {spent} pts, max {lim}"})
            for kl in cfg["keyword_limits"]:
                if kl.get("battle_size") not in (None, bs):
                    continue
                kword, kcap = kl.get("keyword"), kl.get("limit")
                if not kword or kcap is None:
                    continue
                n = sum(1 for u in aus
                        if kword in set(store.ds_by_id.get(u.get("datasheet_id"), {}).get("_keywords") or []))
                if n > kcap:
                    rows.append({"level": "err", "code": "allies_keyword_over",
                                 "message": f"{label} allies: {n}x {kword}, max {kcap}"})
    return rows


def validate_army(c, aid, store=None):
    """Return the list of validation rows for army ``aid`` (empty if missing)."""
    store = store or get_store()
    army = c.execute("SELECT * FROM army_lists WHERE id=?", (aid,)).fetchone()
    if not army:
        return []
    return _rows(army, _unit_rows(c, aid), store)


def validation_payload(c, aid, store=None, units=None):
    """``{"total_points", "validation"}`` for army ``aid``.

    Pass pre-built ``units`` (``_army_unit_row`` dicts) to avoid rebuilding them
    when the caller already has the list (e.g. ``api_get_army``).
    """
    store = store or get_store()
    army = c.execute("SELECT * FROM army_lists WHERE id=?", (aid,)).fetchone()
    if not army:
        return {"total_points": 0, "validation": []}
    if units is None:
        units = _unit_rows(c, aid)
    return {"total_points": _total_points(units),
            "validation": _rows(army, units, store)}
