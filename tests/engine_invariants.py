"""Engine invariants -- exhaustive, data-derived, no server.

Sweeps the whole catalogue rather than sampling: every datasheet for points and
loadout fidelity, every faction for picker well-formedness, every enhancement for
eligibility. Phase 5/6 checks (duplicate_cap, allies, army rules, core
stratagems, missions) are feature-detected and skipped if absent.

Run: python tests/engine_invariants.py
"""
import sys
from _harness import Reporter, store, has, name_index

import army
import wargear
import eligibility


def _int(v, d=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def run():
    r = Reporter("engine invariants")
    s = store()
    dsids = list(s.ds_by_id.keys())

    # 1) Points fidelity: tier-priced default-size points == stored default_points.
    pts_bad = []
    for did in dsids:
        ds = s.ds_by_id[did]
        if did not in s.composition_tiers:
            continue  # no tiers -> _points_for falls back to default_points trivially
        default_size = army._squad_bounds(did)["default"]
        got = army._points_for(did, default_size)
        want = _int(ds.get("default_points"))
        if want and got != want:
            pts_bad.append((ds.get("name"), got, want))
    r.check(f"points: default-size price == default_points for all {len(dsids)} datasheets",
            not pts_bad, f"{len(pts_bad)} mismatch e.g. {pts_bad[:3]}")

    # 1b) Duplicate-selection surcharge shape: army.points_step and the UI note
    #     (pointsStepNote in datasheet.js) both read only steps[0], so a future
    #     data_version shipping >1 step per datasheet would silently underprice
    #     repeat selections and render an incomplete note. Fail loudly so the
    #     data-update runbook catches it as "fix code, not data".
    step_multi, step_bad, stepped = [], [], 0
    for did in dsids:
        steps = s.ds_by_id[did].get("_points_steps") or []
        if steps:
            stepped += 1
        if len(steps) > 1:
            step_multi.append(s.ds_by_id[did].get("name"))
        for st in steps:
            if _int(st.get("step_at")) < 2 or _int(st.get("step_points")) <= 0:
                step_bad.append((s.ds_by_id[did].get("name"), st))
    r.check(f"points: at most one points_step per datasheet ({stepped} stepped datasheets)",
            stepped > 0 and not step_multi,
            f"{len(step_multi)} multi-step e.g. {step_multi[:3]}" if step_multi
            else "no stepped datasheets - population vanished?")
    r.check("points: every points_step has step_at >= 2 and step_points > 0",
            not step_bad, f"{len(step_bad)} malformed e.g. {step_bad[:3]}")

    # 2+3+4) One wargear pass: default loadout is legal, prices at delta 0, and
    #        every weapon-array balances to its slot_count.
    delta_bad, illegal, array_units, array_bad, errored = [], [], 0, [], []
    for did in dsids:
        try:
            size = army._squad_bounds(did)["default"]
            sel = wargear.default_selection(did, size)
            res = wargear.validate_selection(did, size, sel)
        except Exception as e:  # an engine exception is always a failure
            errored.append((s.ds_by_id[did].get("name"), repr(e)))
            continue
        if res.get("points_delta", 0) != 0:
            delta_bad.append((s.ds_by_id[did].get("name"), res["points_delta"]))
        if res.get("violations"):
            illegal.append((s.ds_by_id[did].get("name"), res["violations"][:1]))
        schema = wargear.wargear_schema(did)
        specs = [g for g in schema if g.get("type") == "array"]
        if specs:
            array_units += 1
            # Array balance (sum of slot counts == slot_count) is enforced inside
            # validate_selection; a violation on the default selection means the
            # default did not balance.
            if res.get("violations"):
                array_bad.append(s.ds_by_id[did].get("name"))

    r.check(f"wargear: default_selection + validate_selection run for all {len(dsids)} without exception",
            not errored, f"{len(errored)} errored e.g. {errored[:2]}")
    r.check("wargear: default loadout prices at points_delta == 0 for every unit",
            not delta_bad, f"{len(delta_bad)} nonzero e.g. {delta_bad[:3]}")
    r.check("wargear: default loadout is legal (no violations) for every unit",
            not illegal, f"{len(illegal)} illegal e.g. {illegal[:3]}")
    r.check(f"wargear: weapon-array units detected and balance at default ({array_units} array units)",
            array_units > 0 and not array_bad,
            f"{len(array_bad)} unbalanced e.g. {array_bad[:3]}" if array_bad else "no array units found")

    # 4b) replace_one cross-group correctness: picking an alternative must clear
    #     the Default-group item(s) it displaces. Regression guard for a bug where
    #     a client patch that sets only the alternative key (never touching the
    #     pre-swap default key, which lives in a separate schema group) left both
    #     nonzero in the persisted loadout, silently and without a violation --
    #     validate_selection's replace_one handling only looked within its own
    #     group's items, never across to the Default group. Simulates that exact
    #     incomplete patch for every linked replace_one group in the catalogue.
    swap_bad, swap_unflagged, swap_checked = [], [], 0
    for did in dsids:
        size = army._squad_bounds(did)["default"]
        for grp in wargear.wargear_schema(did):
            if grp.get("type") != "replace_one" or not grp.get("linked_default_keys"):
                continue
            swap_checked += 1
            sel = dict(wargear.default_selection(did, size))
            alt_key = grp["items"][0]["key"]
            sel[alt_key] = 1  # the alternative, picked without clearing the displaced default
            res = wargear.validate_selection(did, size, sel)
            final = res["selection"]
            if _int(final.get(alt_key)) > 0 and any(_int(final.get(k)) > 0 for k in grp["linked_default_keys"]):
                swap_bad.append((s.ds_by_id[did].get("name"), grp["instruction"][:48]))
            elif not res["violations"]:
                swap_unflagged.append((s.ds_by_id[did].get("name"), grp["instruction"][:48]))
    r.check(f"wargear: replace_one swap clears its displaced default item ({swap_checked} linked groups)",
            swap_checked > 0 and not swap_bad, f"{len(swap_bad)} still conflicting e.g. {swap_bad[:3]}")
    r.check("wargear: replace_one auto-correction of a stale default is recorded as a violation",
            not swap_unflagged, f"{len(swap_unflagged)} silent e.g. {swap_unflagged[:3]}")

    # 4c) limited_per_n × weapon-array cross-governance: a capped "…can be
    #     replaced" card whose weapons displace an array's pool weapon (linked
    #     via linked_default_keys, e.g. Legionaries' "For every 5 models…"
    #     heavy-weapon card vs. the "Any number…" boltgun array). Regression
    #     guard, mirroring 4b, for an order-of-operations bug: the multi-item
    #     array pass re-derived those weapon counts from @b bundle picks *after*
    #     the limited_per_n clamp had run, so an over-cap count survived
    #     validation (flagged at best, silent via the @b path) and app.py
    #     persisted it; and a capped replacement never decremented the pool
    #     weapon it displaces, persisting 9 boltguns + 2 plasma guns on 9 mounts.
    over_kept, over_silent, pool_bad, unconverged, lim_checked = [], [], [], [], 0
    bundle_kept, bundle_silent, bundle_checked = [], [], 0
    for did in dsids:
        schema = wargear.wargear_schema(did)
        linked = [g for g in schema if g.get("type") == "limited_per_n"
                  and g.get("linked_default_keys")]
        if not linked:
            continue
        size = army._squad_bounds(did)["max"]
        nm = s.ds_by_id[did].get("name")
        derived_keys = wargear._multi_item_keys(did)
        canon = wargear._canonical_keys(did)
        default = wargear.default_selection(did, size)
        for grp in linked:
            cap = wargear.limited_cap(grp["limits"], size)
            if cap <= 0:
                continue
            k0 = grp["items"][0]["key"]
            if k0 in derived_keys:
                continue  # array-owned key; the card's stepper never sets it
            lim_checked += 1
            sel = dict(default)
            sel[k0] = cap + 2  # over the cap, straight on the card's stepper
            res = wargear.validate_selection(did, size, sel)
            final = res["selection"]
            got = _int(final.get(k0))
            if got > cap:
                over_kept.append((nm, grp["instruction"][:48]))
            elif not res["violations"]:
                over_silent.append((nm, grp["instruction"][:48]))
            # each kept replacement must displace its pool weapon(s) in full:
            # every pool key of the item's miniature drops by exactly `got`
            # times its linked_default_qty (one pick can trade several copies,
            # e.g. a Seraphim gives up BOTH bolt pistols) or not at all
            # ("choppa AND slugga" rows drop together; a power fist leaves the
            # combi-bolter alone), and something must drop unless the data
            # offers the item *alongside* the full pool row (an additive extra
            # like a Regimental Standard displaces nothing).
            it0 = grp["items"][0]
            ck0 = canon.get((it0["miniature"], it0["item"]), k0)
            qty = grp.get("linked_default_qty") or {}
            pks = [pk for pk in grp["linked_default_keys"]
                   if pk.split("|", 1)[0] == it0["miniature"]]
            want = [got * qty.get(pk, 1) for pk in pks]
            deltas = [_int(default.get(pk)) - _int(final.get(pk)) for pk in pks]
            additive = any(ck0 in b["key_counts"] and set(pks) <= set(b["key_counts"])
                           for md in wargear._multi_meta(did).values()
                           for pm in [md["per_mini"].get(it0["miniature"])] if pm
                           for b in pm["bundles"])
            ok_deltas = all(d in (0, w) for d, w in zip(deltas, want))
            if additive:
                ok_deltas = ok_deltas and all(d == 0 for d in deltas)
            else:
                ok_deltas = ok_deltas and (not pks or got == 0 or
                                           any(d == w for d, w in zip(deltas, want)))
            if not ok_deltas:
                pool_bad.append((nm, grp["instruction"][:48], deltas, got))
            # corrections converge: the corrected state is legal and stable
            res2 = wargear.validate_selection(did, size, final)
            if res2["violations"] or res2["selection"] != final:
                unconverged.append((nm, grp["instruction"][:48], res2["violations"][:1]))
        # the @b path: over-cap counts set via per-model bundle picks alone
        # (the path that skipped the clamp entirely -- zero violations)
        mcounts = wargear._miniature_counts(did, size)
        for spec_idx, md in wargear._multi_meta(did).items():
            for M, pm in md["per_mini"].items():
                n = mcounts.get(M, 0)
                item_keys = set(pm["item_keys"])
                for grp in linked:
                    cap = wargear.limited_cap(grp["limits"], size)
                    if cap <= 0 or cap >= n:
                        continue  # no over-cap state reachable via n picks
                    ckeys = {canon.get((it["miniature"], it["item"]))
                             for it in grp["items"]} - item_keys
                    tgt = next(((j, k) for j, b in enumerate(pm["bundles"])
                                for k in b["key_counts"] if k in ckeys), None)
                    if not tgt:
                        continue
                    j, k = tgt
                    bundle_checked += 1
                    sel = dict(default)
                    for mi_ in range(n):
                        sel[wargear._bundle_key(spec_idx, M, mi_)] = j
                    res = wargear.validate_selection(did, size, sel)
                    final = res["selection"]
                    if _int(final.get(k)) > cap:
                        bundle_kept.append((nm, grp["instruction"][:48]))
                    elif not res["violations"]:
                        bundle_silent.append((nm, grp["instruction"][:48]))
                    res2 = wargear.validate_selection(did, size, final)
                    if res2["violations"] or res2["selection"] != final:
                        unconverged.append((nm, grp["instruction"][:48], res2["violations"][:1]))
    r.check(f"wargear: limited_per_n cap holds against its linked weapon-array ({lim_checked} linked cards)",
            lim_checked > 0 and not over_kept, f"{len(over_kept)} over cap e.g. {over_kept[:3]}")
    r.check("wargear: over-cap limited_per_n correction is recorded as a violation",
            not over_silent, f"{len(over_silent)} silent e.g. {over_silent[:3]}")
    r.check("wargear: a limited_per_n replacement displaces its pool weapon(s) in full",
            not pool_bad, f"{len(pool_bad)} unbalanced e.g. {pool_bad[:3]}")
    r.check(f"wargear: over-cap @b bundle picks are clamped to the limited cap ({bundle_checked} spec×card pairs)",
            bundle_checked > 0 and not bundle_kept, f"{len(bundle_kept)} over cap e.g. {bundle_kept[:3]}")
    r.check("wargear: over-cap @b correction is recorded as a violation",
            not bundle_silent, f"{len(bundle_silent)} silent e.g. {bundle_silent[:3]}")
    r.check("wargear: limited×array corrections converge (re-validation is legal and stable)",
            not unconverged, f"{len(unconverged)} unstable e.g. {unconverged[:3]}")

    # 4d) Multi-item option bundles ("1 plasma pistol and 1 Astartes chainsword"
    #     is ONE option): a bundle pick posted the way the UI posts it must
    #     survive validation intact and legally. limited_per_n: anchors set to 1
    #     -> every member key >= its qty, no violations, and the pick counts
    #     once against the cap. replace_one/all_model: the group zeroed + the
    #     bundle's keys set -> all keys stay active, no "choose only one".
    lb_bad, rb_bad, lb_n, rb_n = [], [], 0, 0
    for did in dsids:
        schema = wargear.wargear_schema(did)
        if not any(g.get("option_bundles") for g in schema):
            continue
        size = army._squad_bounds(did)["default"]
        nm = s.ds_by_id[did].get("name")
        mcs = wargear._miniature_counts(did, size)
        for g in schema:
            for bd in (g.get("option_bundles") or ()):
                if g["type"] == "limited_per_n":
                    if wargear.limited_cap(g["limits"], size) < 1:
                        continue
                    lb_n += 1
                    sel = dict(wargear.default_selection(did, size))
                    for a in bd["anchors"]:
                        sel[a] = 1
                    res = wargear.validate_selection(did, size, sel)
                    f = res["selection"]
                    if (any(_int(f.get(k)) < q for k, q in bd["keys"].items())
                            or res["violations"]):
                        lb_bad.append((nm, bd["label"], res["violations"][:1]))
                else:  # replace_one / all_model
                    rb_n += 1
                    mc = (mcs.get(g.get("miniature"), 0) or size) \
                        if g["type"] == "all_model" else 1
                    sel = dict(wargear.default_selection(did, size))
                    for i in g["items"]:
                        sel[i["key"]] = 0
                    for k in (g.get("linked_default_keys") or ()):
                        sel[k] = 0
                    for k, q in bd["keys"].items():
                        sel[k] = q * mc
                    res = wargear.validate_selection(did, size, sel)
                    f = res["selection"]
                    if (any(_int(f.get(k)) <= 0 for k in bd["keys"])
                            or any("choose only one" in (v.get("message") or "")
                                   for v in res["violations"])):
                        rb_bad.append((nm, bd["label"], res["violations"][:1]))
    r.check(f"wargear: limited_per_n bundle picks are one legal pick ({lb_n} bundles)",
            lb_n > 0 and not lb_bad, f"{len(lb_bad)} bad e.g. {lb_bad[:3]}")
    r.check(f"wargear: replace_one/all_model bundle picks keep every member ({rb_n} bundles)",
            rb_n > 0 and not rb_bad, f"{len(rb_bad)} bad e.g. {rb_bad[:3]}")

    # 5) Enhancement eligibility: classify every enhancement without error; the
    #    Epic Hero and Character gates hold exactly per the exported rule flags
    #    (epic_hero_eligible / non_character_eligible waive them for a handful);
    #    every datasheet-specific group resolves to a real name. Bearers are
    #    given the first required group's own keywords so the gate under test -
    #    not an unmatched group - is what decides.
    names = set(v["name"] for v in s.ds_by_id.values())
    elig_err, epic_bad, nonchar_bad, ds_unresolved = [], [], [], []
    seen = epic_ok = nonchar_ok = 0
    for dtid, enhs in s.enhancements_by_detachment.items():
        for e in enhs:
            seen += 1
            struct = e.get("eligibility_struct") or {}
            g = (struct.get("required_groups") or [{}])[0]
            base = set(g.get("keywords") or []) \
                | {"Faction: " + fk for fk in (g.get("faction_keywords") or [])}
            nm = g.get("datasheet") or ""
            try:
                eligibility.enhancement_eligible(base | {"Character"}, "Character", e, nm)
                epic = eligibility.enhancement_eligible(
                    base | {"Character", "Epic Hero"}, "Epic Hero", e, nm)
                nonchar = eligibility.enhancement_eligible(base - {"Character"}, "", e, nm)
            except Exception as ex:
                elig_err.append((e.get("name"), repr(ex)))
                continue
            if epic and not e.get("epic_hero_eligible"):
                epic_bad.append(e.get("name"))
            epic_ok += 1 if (epic and e.get("epic_hero_eligible")) else 0
            if nonchar and not e.get("non_character_eligible"):
                nonchar_bad.append(e.get("name"))
            nonchar_ok += 1 if (nonchar and e.get("non_character_eligible")) else 0
            for grp in struct.get("required_groups", []):
                d = grp.get("datasheet")
                if d and d not in names:
                    ds_unresolved.append((e.get("name"), d))
    r.check(f"eligibility: all {seen} enhancements classify without exception",
            not elig_err, f"{len(elig_err)} errored e.g. {elig_err[:2]}")
    r.check("eligibility: an Epic Hero passes only epic_hero_eligible enhancements",
            not epic_bad, f"{len(epic_bad)} admitted e.g. {epic_bad[:3]}")
    r.check(f"eligibility: epic_hero_eligible enhancements admit an Epic Hero ({epic_ok})",
            epic_ok > 0, "none admitted - flag loaded but inert?")
    r.check("eligibility: a non-Character passes only non_character_eligible enhancements",
            not nonchar_bad, f"{len(nonchar_bad)} admitted e.g. {nonchar_bad[:3]}")
    r.check(f"eligibility: non_character_eligible enhancements admit a non-Character ({nonchar_ok})",
            nonchar_ok > 0, "none admitted - flag loaded but inert?")
    r.check("eligibility: every datasheet-specific group resolves to a real datasheet name",
            not ds_unresolved, f"{len(ds_unresolved)} unresolved e.g. {ds_unresolved[:3]}")

    # 5b) Model-level Enhancement bans (excluded_from_enhancements): every banned
    #     datasheet resolves, and is blocked from every enhancement in the game
    #     even with its real (Character) keywords.
    excl = getattr(s, "enhancement_excluded_ds", set())
    excl_missing = [d for d in excl if d not in s.ds_by_id]
    excl_pass = []
    for did in excl:
        u = s.ds_by_id.get(did) or {}
        kw, role, nm = set(u.get("_keywords") or []), u.get("role") or "", u.get("name") or ""
        for enhs in s.enhancements_by_detachment.values():
            for e in enhs:
                if eligibility.enhancement_eligible(kw, role, e, nm, did):
                    excl_pass.append((nm, e.get("name")))
    r.check(f"eligibility: model-level Enhancement bans loaded and resolve ({len(excl)} datasheets)",
            len(excl) > 0 and not excl_missing,
            f"missing {excl_missing}" if excl_missing else "no banned datasheets loaded")
    r.check("eligibility: a banned datasheet is blocked from every enhancement",
            not excl_pass, f"{len(excl_pass)} admitted e.g. {excl_pass[:3]}")

    # 5c) Enhancement rule flags: take_limit is a positive int everywhere, the
    #     multi-take / cap-free / warlord-barred populations exist, and the
    #     enhancement_by_id index holds the same dict objects the pools do (the
    #     validators key off it by str(id)).
    flag_bad, unindexed = [], []
    multi = free = cbw = 0
    for dtid, enhs in s.enhancements_by_detachment.items():
        for e in enhs:
            tl = e.get("take_limit")
            if not isinstance(tl, int) or tl < 1:
                flag_bad.append((e.get("name"), "take_limit", tl))
            elif tl > 1:
                multi += 1
            free += 0 if e.get("counts_toward_limit", True) else 1
            cbw += 1 if e.get("cannot_be_warlord") else 0
            if s.enhancement_by_id.get(str(e.get("id"))) is not e:
                unindexed.append(e.get("name"))
    r.check(f"flags: take_limit positive everywhere; multi-take ({multi}), cap-free ({free}) "
            f"and cannot_be_warlord ({cbw}) populations all present",
            not flag_bad and multi > 0 and free > 0 and cbw > 0,
            f"bad {flag_bad[:3]}" if flag_bad else f"multi={multi} free={free} cbw={cbw}")
    r.check("flags: enhancement_by_id indexes every enhancement (same object as the pool)",
            not unindexed, f"{len(unindexed)} unindexed e.g. {unindexed[:3]}")

    # 5d) Leader-attachment groups (leader_group): loaded and resolved, at
    #     parity with the flat leads name lists, and the attach engine honours
    #     Leader/support slots, detachment gates and mark-keyword parties.
    if has(s, "leader_groups") and has(army, "attach_check"):
        n_groups = sum(len(v) for v in s.leader_groups.values())
        member_bad, pop = [], {"support": 0, "det_gated": 0, "kw_gated": 0, "kw_members": 0}
        for ldid, lgroups in s.leader_groups.items():
            for g in lgroups:
                if g.get("type") == "support":
                    pop["support"] += 1
                if g.get("required_detachment_id") or g.get("excluded_detachment_id"):
                    pop["det_gated"] += 1
                if g.get("requires_all_units_keyword"):
                    pop["kw_gated"] += 1
                if not g["member_ids"]:
                    pop["kw_members"] += 1  # a group with no resolved members is inert
                for m in g["member_ids"]:
                    if m not in s.ds_by_id:
                        member_bad.append((s.ds_by_id[ldid].get("name"), m))
        r.check(f"leaders: leader_group loaded ({len(s.leader_groups)} leaders, {n_groups} groups); "
                f"support ({pop['support']}), detachment-gated ({pop['det_gated']}) and "
                f"keyword-gated ({pop['kw_gated']}) populations all present",
                n_groups > 0 and pop["support"] > 0 and pop["det_gated"] > 0 and pop["kw_gated"] > 0,
                f"populations {pop}")
        r.check("leaders: every group's membership resolves to loaded datasheets (none inert)",
                not member_bad and pop["kw_members"] == 0,
                f"{len(member_bad)} bad, {pop['kw_members']} empty e.g. {member_bad[:3]}")

        # Parity: every target the flat leads_units list names is reachable
        # through some leader_group (ignoring gates) - enforcement never bars a
        # pairing the display layer advertises outright. By NAME: the flat
        # resolver fans a shared name out to every datasheet carrying it (two
        # Sternguard Veteran Squads exist), while leader_group pins the one
        # the official app means.
        parity_bad = []
        for ldid, targets in s.leads.items():
            union_names = set()
            for g in s.leader_groups.get(ldid, []):
                union_names |= {s.ds_by_id[m]["name"] for m in g["member_ids"]}
            for t in targets:
                if t.get("id") and t.get("name") not in union_names:
                    parity_bad.append((s.ds_by_id[ldid].get("name"), t.get("name")))
        r.check("leaders: every resolved leads_units target name appears in some leader_group",
                not parity_bad, f"{len(parity_bad)} missing e.g. {parity_bad[:3]}")

        # Behaviour: one Leader-slot character + any support alongside; a second
        # Leader-slot character is blocked. Case found from the data (a bodyguard
        # with >=2 pure-leader leaders and >=1 pure-support leader, no gates).
        by_target = {}
        for ldid, lgroups in s.leader_groups.items():
            for g in lgroups:
                if (g.get("required_detachment_id") or g.get("excluded_detachment_id")
                        or g.get("requires_all_units_keyword")):
                    continue
                for m in g["member_ids"]:
                    d = by_target.setdefault(m, {"leader": set(), "support": set()})
                    d["support" if g.get("type") == "support" else "leader"].add(ldid)
        case = next(((t, d) for t, d in by_target.items()
                     if len(d["leader"] - d["support"]) >= 2 and (d["support"] - d["leader"])), None)
        if case:
            t, d = case
            la, lb = sorted(d["leader"] - d["support"])[:2]
            sp = sorted(d["support"] - d["leader"])[0]
            mk = lambda i, dd, a="": {"id": i, "datasheet_id": dd, "enhancement_id": "", "attached_to": a}
            rows_ = [mk("bg", t), mk("la", la), mk("lb", lb), mk("sp", sp)]
            ok_leader = army.attach_check([], rows_, rows_[1], rows_[0]) is None
            rows_[1]["attached_to"] = "bg"
            ok_support = army.attach_check([], rows_, rows_[3], rows_[0]) is None
            rows_[3]["attached_to"] = "bg"
            second_blocked = army.attach_check([], rows_, rows_[2], rows_[0]) is not None
            r.check("leaders: attach engine admits Leader + support and blocks a second Leader "
                    f"({s.ds_by_id[t].get('name')}: {s.ds_by_id[la].get('name')} + {s.ds_by_id[sp].get('name')})",
                    ok_leader and ok_support and second_blocked,
                    f"leader={ok_leader} support={ok_support} second_blocked={second_blocked}")
        else:
            r.check("leaders: found a bodyguard with both Leader and support leaders", False,
                    "no ungated leader+support case in data (population vanished?)")

        # Behaviour: the detachment/mark pattern the data actually uses (CSM) -
        # a base group carries excluded_detachment X and no keyword gate, its
        # twins carry required_detachment X plus one mark each. Outside X the
        # pairing is mark-free; inside X the party must share one mark.
        marked = {}
        for k in army.MARK_KEYWORDS:
            marked[k] = next((dd for dd, u in s.ds_by_id.items()
                              if k in set(u.get("_keywords") or [])), None)
        k1, k2 = marked.get("Khorne"), marked.get("Nurgle")
        combo = None
        for ldid, lgroups in s.leader_groups.items():
            for g in lgroups:
                exc_id = g.get("excluded_detachment_id")
                if not exc_id or g.get("requires_all_units_keyword"):
                    continue
                twins = [x for x in lgroups
                         if x.get("required_detachment_id") == exc_id
                         and x.get("requires_all_units_keyword")
                         and x["member_ids"] & g["member_ids"]]
                if not twins:
                    continue
                shared = twins[0]["member_ids"] & g["member_ids"]
                # pick a member no third, unconditional group also covers, so
                # the in-detachment mark gate is the only path
                for m in sorted(shared):
                    if not any(m in x["member_ids"] for x in lgroups
                               if x is not g and x not in twins
                               and not x.get("required_detachment_id")):
                        combo = (ldid, m, exc_id)
                        break
                if combo:
                    break
            if combo:
                break
        if combo and k1 and k2:
            ldid, m, x = combo
            mixed = [m, ldid, k1, k2]
            out_kinds = army._attach_kinds(army.leader_groups_for(ldid, "", []), m, mixed)
            in_unmarked = army._attach_kinds(army.leader_groups_for(ldid, "", [x]), m, [m, ldid])
            in_mixed = army._attach_kinds(army.leader_groups_for(ldid, "", [x]), m, mixed)
            r.check("leaders: mark gate off outside its detachment, enforced inside "
                    f"({s.ds_by_id[ldid].get('name')} -> {s.ds_by_id[m].get('name')})",
                    bool(out_kinds) and bool(in_unmarked) and not in_mixed,
                    f"outside={out_kinds} in_unmarked={in_unmarked} in_mixed={in_mixed}")
        else:
            r.check("leaders: found an excluded-base + mark-twin detachment pattern",
                    False, f"combo={combo} k1={bool(k1)} k2={bool(k2)}")

        # Enhancement grants (grants_leader_attachment): loaded, members resolve,
        # and a grant gives its bearer attach targets through leader_groups_for.
        grant_bad, grant_n = [], 0
        granting = None
        for e in s.enhancement_by_id.values():
            for g in e.get("leader_grants") or []:
                grant_n += 1
                granting = granting or e
                for m in g["member_ids"]:
                    if m not in s.ds_by_id:
                        grant_bad.append((e.get("name"), m))
        r.check(f"leaders: enhancement grants_leader_attachment loaded ({grant_n} groups) and members resolve",
                grant_n > 0 and not grant_bad, f"{len(grant_bad)} bad e.g. {grant_bad[:3]}")
        if granting:
            gs_ = army.leader_groups_for("no-such-datasheet", str(granting["id"]),
                                         [granting["detachment_id"]])
            r.check(f"leaders: an enhancement grant adds attach targets for its bearer ({granting['name']})",
                    any(g["member_ids"] for g in gs_), "grant did not surface via leader_groups_for")
    else:
        r.skip("leaders: leader_group sweep", "store.leader_groups/army.attach_check absent")

    # 6) Picker well-formedness: everything the picker offers is a real datasheet,
    #    and every faction the data says has native units (unit_count > 0) offers a
    #    non-empty picker. Grouping factions (unit_count == 0, e.g. Aeldari) hold no
    #    units of their own and are exempt. Also reports the picker-vs-membership
    #    gap the chapter add-guard fix closes.
    picker_bad, empty_buildable, empty_grouping, gap = [], [], [], {}
    for f in s.factions:
        fid_ = f["id"] if isinstance(f, dict) else f
        frec = s.faction_by_id.get(fid_, {})
        try:
            offered = s.selectable_units_for_army(fid_)
        except Exception as e:
            picker_bad.append((fid_, repr(e)))
            continue
        ids = [u["id"] for u in offered]
        if not ids:
            (empty_buildable if frec.get("unit_count") else empty_grouping).append(frec.get("name"))
        for uid in ids:
            if uid not in s.ds_by_id:
                picker_bad.append((fid_, uid))
        rejected = [uid for uid in ids if not army._datasheet_in_faction(uid, fid_)]
        if rejected:
            gap[fid_] = len(rejected)
    r.check("picker: every offered unit is a real datasheet",
            not picker_bad, f"{len(picker_bad)} bad e.g. {picker_bad[:2]}")
    r.check("picker: every faction with native units (unit_count > 0) has a non-empty picker",
            not empty_buildable, f"empty: {empty_buildable}")
    if empty_grouping:
        print(f"     note: {len(empty_grouping)} grouping faction(s) empty by design "
              f"(unit_count == 0): {empty_grouping}")
    # This is reported, not asserted: post-fix the add route gates on the picker
    # set, so the membership helper may legitimately still differ. The API-level
    # parity test (api_roundtrip.py) is the real pass/fail for the add-guard.
    if gap:
        total = sum(gap.values())
        print(f"     note: {len(gap)} factions offer {total} units the bare "
              f"_datasheet_in_faction check rejects (chapter add-guard territory; "
              f"verified at the API level in api_roundtrip.py)")

    # 7) Phase 5: duplicate_cap defined and sane for every (battle size, datasheet).
    if has(army, "duplicate_cap"):
        sizes = ["Incursion", "Strike Force", "Onslaught", "Custom"]
        cap_err = []
        for did in dsids:
            for bs in sizes:
                try:
                    c = army.duplicate_cap(bs, did)
                except Exception as e:
                    cap_err.append((s.ds_by_id[did].get("name"), bs, repr(e)))
                    continue
                if c is not None and (not isinstance(c, int) or c < 1):
                    cap_err.append((s.ds_by_id[did].get("name"), bs, c))
        r.check("caps: duplicate_cap returns a positive int or None for every (size, datasheet)",
                not cap_err, f"{len(cap_err)} bad e.g. {cap_err[:3]}")
        # Epic Hero -> 1 at every size
        epic = [did for did, d in s.ds_by_id.items() if d.get("role") == "Epic Hero"]
        epic_bad = [s.ds_by_id[d].get("name") for d in epic[:200]
                    if any(army.duplicate_cap(bs, d) != 1 for bs in sizes)]
        r.check("caps: every Epic Hero has duplicate_cap == 1 at every size",
                not epic_bad, f"{len(epic_bad)} e.g. {epic_bad[:3]}")
    else:
        r.skip("caps: duplicate_cap sweep", "army.duplicate_cap absent (pre-Phase 5)")

    # 8) Phase 5: allies surfaced and well-formed.
    if has(s, "allied_by_host") and has(s, "ally_config_for"):
        bad = []
        for host, configs in s.allied_by_host.items():
            if host not in s.faction_by_id:
                bad.append(("unknown host", host))
            for cfg in configs:
                for aid in (cfg.get("datasheet_ids") or cfg.get("datasheets") or []):
                    if aid not in s.ds_by_id:
                        bad.append((host, aid))
        r.check("allies: every host is a real faction and every allied datasheet id resolves",
                not bad, f"{len(bad)} bad e.g. {bad[:3]}")
    else:
        r.skip("allies: allied_by_host sweep", "store.allied_by_host/ally_config_for absent (pre-Phase 5)")

    # 9) Phase 6: army rules resolve, core stratagems == 11, missions exclude CP.
    if has(s, "army_rules_for"):
        aa = next((f["id"] if isinstance(f, dict) else f for f in s.factions
                   if s.faction_by_id.get((f["id"] if isinstance(f, dict) else f), {}).get("name") == "Adeptus Astartes"), None)
        if aa:
            rules = s.army_rules_for(aa)
            nms = [x.get("name") if isinstance(x, dict) else getattr(x, "name", x) for x in rules]
            r.check("reference: army_rules_for(Adeptus Astartes) includes 'Oath of Moment'",
                    "Oath of Moment" in nms, f"got {nms}")
    else:
        r.skip("reference: army rules", "store.army_rules_for absent (pre-Phase 6)")
    if has(s, "core_stratagems"):
        r.check("reference: 11 core stratagems surfaced", len(s.core_stratagems) == 11,
                f"got {len(s.core_stratagems)}")
    else:
        r.skip("reference: core stratagems", "store.core_stratagems absent (pre-Phase 6)")
    if has(s, "missions"):
        m = s.missions() if callable(getattr(s, "missions")) else s.missions
        import json
        blob = json.dumps(m, default=str)
        r.check("reference: missions exclude the Combat Patrol pack", "Combat Patrol" not in blob)
    else:
        r.skip("reference: missions", "store.missions absent (pre-Phase 6)")

    return r.summary()


if __name__ == "__main__":
    sys.exit(run())
