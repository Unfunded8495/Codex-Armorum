"""Army roster legality engine.

Returns structured validation rows the army builder renders. Each row is
``{"level": "ok"|"warn"|"err"|"info", "code": str, "message": str}``. The
renderer keys off ``level`` only, so later phases add new ``code`` values
(duplicate-unit, detachment-cap, allies) without touching the frontend.
Unit-scoped rows also carry ``auid`` (the army_units id) so the UI can jump
to the offending unit.

Phase 1 codes: points_over / points_ok, enhancement_over / enhancement_ok,
no_detachment, wishlist_units.
"""
from army import (_army_unit_row, attach_check, battle_size_caps,
                  duplicate_cap, parse_detachment_ids, detachment_set_cost)
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
    dt_ids = parse_detachment_ids(army)
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
    # counts_toward_limit=False enhancements (e.g. Canoptek Court cryptek
    # upgrades) are free with respect to the cap; unknown ids count.
    enh_limit = caps["enhancement_limit"]
    if enh_limit is not None:
        enh_count = sum(
            1 for u in units if u.get("enhancement_id")
            and store.enhancement_by_id.get(str(u["enhancement_id"]),
                                            {}).get("counts_toward_limit", True))
        if enh_count > enh_limit:
            rows.append({"level": "err", "code": "enhancement_over",
                         "message": f"{enh_count} enhancements - limit is {enh_limit}"})
        elif enh_count:
            rows.append({"level": "ok", "code": "enhancement_ok",
                         "message": f"{enh_count} of {enh_limit} enhancements"})

    # Detachment(s) chosen, and Detachment Points within the battle-size budget.
    # Each detachment costs 1-3 DP; their sum must not exceed the size's DP cap
    # (null for Custom -> no DP limit, any number of detachments allowed).
    dp_budget = caps["detachment_points_limit"]
    if not dt_ids:
        rows.append({"level": "info", "code": "no_detachment",
                     "message": "No detachment selected"})
    elif dp_budget is not None:
        dp_used = detachment_set_cost(dt_ids)
        if dp_used > dp_budget:
            rows.append({"level": "err", "code": "detachment_points_over",
                         "message": f"{dp_used} DP used - limit is {dp_budget}"})
        elif len(dt_ids) > 1:
            rows.append({"level": "ok", "code": "detachment_points_ok",
                         "message": f"{dp_used} of {dp_budget} Detachment Points"})

    # Ownership is informational only -- lists are not managed against the
    # collection (no per-list model assignment), so the only row is a passive
    # count of units not owned at all.
    wishlist = sum(1 for u in units if (u.get("owned_count") or 0) == 0)
    if wishlist:
        rows.append({"level": "info", "code": "wishlist_units",
                     "message": f"{wishlist} unit{'' if wishlist == 1 else 's'} "
                                f"not yet owned (wishlist)"})

    # Wargear legality (auto-correct heals on write, so this normally stays clean).
    for u in units:
        for v in (u.get("wargear_violations") or []):
            rows.append({"level": v.get("level", "warn"), "code": "wargear_illegal",
                         "auid": u["id"],
                         "message": f"{u['name']}: {v.get('message', '')}"})

    # Enhancement eligibility + take limits, and the single-Warlord rule (Phase 4).
    from eligibility import enhancement_eligible
    # Enhancements come from the union of every selected detachment's pool.
    enh_pool = [e for d in dt_ids for e in store.enhancements_by_detachment.get(d, [])]
    by_enh = {}
    for u in units:
        eid = str(u.get("enhancement_id") or "")
        if not eid:
            continue
        by_enh.setdefault(eid, []).append(u)
        ds = store.ds_by_id.get(u.get("datasheet_id"), {})
        e = next((x for x in enh_pool if str(x.get("id")) == eid), None)
        if e and not enhancement_eligible(set(ds.get("_keywords") or []), ds.get("role"),
                                          e, ds.get("name"),
                                          ds.get("id") or u.get("datasheet_id")):
            rows.append({"level": "err", "code": "enhancement_ineligible",
                         "auid": u["id"],
                         "message": f"{u['name']}: not eligible for "
                                    f"{u.get('enhancement_name') or 'that enhancement'}"})
    # Most enhancements are unique; some Upgrade-type ones allow take_limit copies.
    for eid, us in by_enh.items():
        cap = (store.enhancement_by_id.get(eid) or {}).get("take_limit") or 1
        if len(us) > cap:
            nm = us[0].get("enhancement_name") or "Enhancement"
            why = "each is unique" if cap == 1 else f"max {cap} per army"
            rows.append({"level": "err", "code": "enhancement_duplicate",
                         "message": f"{nm} taken by {len(us)} units - {why}"})

    warlords = [u for u in units if u.get("is_warlord")]
    for u in warlords:
        e = store.enhancement_by_id.get(str(u.get("enhancement_id") or ""))
        if e and e.get("cannot_be_warlord"):
            rows.append({"level": "err", "code": "warlord_enhancement",
                         "auid": u["id"],
                         "message": f"{u['name']}: the bearer of {e['name']} "
                                    f"cannot be the Warlord"})
    if len(warlords) > 1:
        rows.append({"level": "err", "code": "warlord_multiple",
                     "message": f"{len(warlords)} Warlords - choose exactly one"})
    elif not warlords and any(u.get("is_character") for u in units):
        rows.append({"level": "warn", "code": "warlord_missing",
                     "message": "No Warlord selected"})

    # Leader attachment legality — leader_group conditions (detachment gates,
    # leader vs support slots, mark-keyword parties, enhancement grants).
    # Defensive; the save path enforces the same via attach_check, but a
    # roster can go stale under it (detachment de-selected, enhancement
    # cleared, or rows written by an older build).
    by_id = {u["id"]: u for u in units}
    for u in units:
        att = u.get("attached_to") or ""
        if not att:
            continue
        tgt = by_id.get(att)
        if not tgt:
            rows.append({"level": "err", "code": "illegal_attachment",
                         "auid": u["id"],
                         "message": f"{u['name']}: invalid leader attachment"})
            continue
        why = attach_check(dt_ids, units, u, tgt)
        if why:
            rows.append({"level": "err", "code": "illegal_attachment",
                         "auid": u["id"],
                         "message": f"{u['name']}: {why}"})

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
            rows.append({"level": "err", "code": "duplicate_over", "auid": u["id"],
                         "message": f"{counts[did]}x {u['name']}, max {cap}{at}"})

    # Faction membership: a unit must be one the picker would offer this army
    # (own units + parent generics, explicit exclusions vetoing — e.g.
    # Librarians are barred from Black Templars) or be admitted by an ally
    # config. The add-guard enforces the same set on write; this row catches
    # rosters built before an exclusion existed.
    afid_m = army["faction_id"]
    offerable = {x["id"] for x in store.selectable_units_for_army(afid_m)}
    for u in units:
        did = u.get("datasheet_id")
        if did not in offerable and not store.ally_config_for(afid_m, did):
            rows.append({"level": "err", "code": "faction_excluded", "auid": u["id"],
                         "message": f"{u['name']} is not available to this faction"})

    # Detachment excludes (Phase 5a): excludes_datasheets holds datasheet NAMES.
    # Union the excludes of every selected detachment.
    excludes = set()
    for d in dt_ids:
        det = store.detachment_by_id.get(d)
        if det:
            excludes.update(det.get("excludes_datasheets") or [])
    for u in units:
        if u["name"] in excludes:
            rows.append({"level": "err", "code": "detachment_excluded",
                         "message": f"{u['name']} is excluded by a selected detachment"})

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
