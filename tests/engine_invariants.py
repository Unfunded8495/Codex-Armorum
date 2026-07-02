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
            # each kept replacement must displace its pool weapon(s) one-for-one:
            # every pool key of the item's miniature drops by exactly `got` or
            # not at all ("choppa AND slugga" rows drop together; a power fist
            # leaves the combi-bolter alone), and something must drop unless the
            # data offers the item *alongside* the full pool row (an additive
            # extra like a Regimental Standard displaces nothing).
            it0 = grp["items"][0]
            ck0 = canon.get((it0["miniature"], it0["item"]), k0)
            pks = [pk for pk in grp["linked_default_keys"]
                   if pk.split("|", 1)[0] == it0["miniature"]]
            deltas = [_int(default.get(pk)) - _int(final.get(pk)) for pk in pks]
            additive = any(ck0 in b["key_counts"] and set(pks) <= set(b["key_counts"])
                           for md in wargear._multi_meta(did).values()
                           for pm in [md["per_mini"].get(it0["miniature"])] if pm
                           for b in pm["bundles"])
            ok_deltas = all(d in (0, got) for d in deltas)
            if additive:
                ok_deltas = ok_deltas and all(d == 0 for d in deltas)
            else:
                ok_deltas = ok_deltas and (not pks or got in deltas or got == 0)
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
    r.check("wargear: a limited_per_n replacement displaces its array-pool weapon one-for-one",
            not pool_bad, f"{len(pool_bad)} unbalanced e.g. {pool_bad[:3]}")
    r.check(f"wargear: over-cap @b bundle picks are clamped to the limited cap ({bundle_checked} spec×card pairs)",
            bundle_checked > 0 and not bundle_kept, f"{len(bundle_kept)} over cap e.g. {bundle_kept[:3]}")
    r.check("wargear: over-cap @b correction is recorded as a violation",
            not bundle_silent, f"{len(bundle_silent)} silent e.g. {bundle_silent[:3]}")
    r.check("wargear: limited×array corrections converge (re-validation is legal and stable)",
            not unconverged, f"{len(unconverged)} unstable e.g. {unconverged[:3]}")

    # 5) Enhancement eligibility: classify every enhancement without error; no Epic
    #    Hero ever passes; every datasheet-specific group resolves to a real name.
    names = set(v["name"] for v in s.ds_by_id.values())
    elig_err, epic_pass, ds_unresolved = [], [], []
    seen = 0
    char_kw = {"Character"}
    epic_kw = {"Character", "Epic Hero"}
    for dtid, enhs in s.enhancements_by_detachment.items():
        for e in enhs:
            seen += 1
            struct = e.get("eligibility_struct") or {}
            try:
                eligibility.enhancement_eligible(char_kw, "Character", struct)
                if eligibility.enhancement_eligible(epic_kw, "Epic Hero", struct):
                    epic_pass.append(e.get("name"))
            except Exception as ex:
                elig_err.append((e.get("name"), repr(ex)))
            for grp in struct.get("required_groups", []):
                d = grp.get("datasheet")
                if d and d not in names:
                    ds_unresolved.append((e.get("name"), d))
    r.check(f"eligibility: all {seen} enhancements classify without exception",
            not elig_err, f"{len(elig_err)} errored e.g. {elig_err[:2]}")
    r.check("eligibility: no Epic Hero passes any enhancement (core rule)",
            not epic_pass, f"{len(epic_pass)} admitted e.g. {epic_pass[:3]}")
    r.check("eligibility: every datasheet-specific group resolves to a real datasheet name",
            not ds_unresolved, f"{len(ds_unresolved)} unresolved e.g. {ds_unresolved[:3]}")

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
