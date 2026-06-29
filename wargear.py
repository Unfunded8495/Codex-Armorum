"""Wargear / loadout engine.

Turns the structured ``store.wargear_loadout[did]`` into a render schema, a
default loadout, a sparse-override persistence model, points, a resolved summary,
and a legality validator.

A selection is ``{option_key: value}`` (0/1 for a checkbox, a count for a
stepper). Option keys are ``miniature|group_index|item|slot_index`` — slot_index
is the 0-based occurrence of that triple in the options list, which resolves the
24 duplicate triples in the data. We persist only the **sparse diff from the
default** so squad-size changes re-scale bulk weapons while explicit choices are
preserved.
"""
from functools import lru_cache

import army
from data_store import get_store
from utils import _int

DEFAULT_GROUP = "Default Wargear"


def _is_default_group(name):
    """True for the base-loadout group, tolerating the data's "Default Wargesr"
    typo (Commissar Graves) by matching the "Default Warge…" prefix."""
    return (name or "").strip().lower().startswith("default warge")


def _wl(did):
    return get_store().wargear_loadout.get(did) or {}


@lru_cache(maxsize=4096)
def _keyed_options(did):
    """``((option_dict, key), ...)`` for the unit's options, stable keys, cached."""
    opts = _wl(did).get("options") or []
    group_index = {}
    for o in opts:
        g = o.get("group")
        if g not in group_index:
            group_index[g] = len(group_index)
    seen = {}
    out = []
    for o in opts:
        gi = group_index[o.get("group")]
        triple = (o.get("miniature"), gi, o.get("item"))
        slot = seen.get(triple, 0)
        seen[triple] = slot + 1
        key = "%s|%d|%s|%d" % (o.get("miniature") or "", gi, o.get("item") or "", slot)
        out.append((o, key))
    return tuple(out)


def _flat_items(choices):
    """Set of item names across a ``[[{item,count}…]…]`` choices structure."""
    out = set()
    for bundle in choices or []:
        for it in (bundle if isinstance(bundle, list) else []):
            if isinstance(it, dict) and it.get("item"):
                out.add(it["item"])
    return out


@lru_cache(maxsize=4096)
def _limited_index(did):
    res = []
    for lc in _wl(did).get("limited_choices") or []:
        limits = lc.get("limits") or []
        dup = next((l.get("duplicate_limit") for l in limits
                    if l.get("duplicate_limit") is not None), None)
        res.append({"miniature": lc.get("miniature"),
                    "items": _flat_items(lc.get("choices")),
                    "limits": limits, "duplicate_limit": dup})
    return tuple(res)


@lru_cache(maxsize=4096)
def _all_model_index(did):
    res = []
    for am in _wl(did).get("all_model_choices") or []:
        items = set()
        for ch in am.get("choices") or []:
            for it in ch.get("items") or []:
                if it.get("item"):
                    items.add(it["item"])
        res.append({"miniature": am.get("miniature"), "items": items})
    return tuple(res)


@lru_cache(maxsize=4096)
def _item_keys(did):
    """``{(miniature, item): [key, …]}`` for linking constraint items to options."""
    out = {}
    for o, key in _keyed_options(did):
        out.setdefault((o.get("miniature"), o.get("item")), []).append(key)
    return out


@lru_cache(maxsize=4096)
def _canonical_keys(did):
    """``{(miniature, item): key}`` — the Default-group key when the item has one
    there, else the first option key. Collapses items that appear in several groups
    (e.g. Havoc autocannon in both the Default and the replace group) onto one
    count-holder so the array layer never double-counts them."""
    default_key, first_key = {}, {}
    for o, key in _keyed_options(did):
        mi = (o.get("miniature"), o.get("item"))
        first_key.setdefault(mi, key)
        if _is_default_group(o.get("group")):
            default_key.setdefault(mi, key)
    return {mi: default_key.get(mi, first_key[mi]) for mi in first_key}


@lru_cache(maxsize=4096)
def _array_specs(did):
    """Weapon-array specs — one per ``replace_any`` ("Any number of…") group that
    draws from a Default-group **pool** weapon. Each spec:
    ``{instruction, single_item, miniatures, bundles, members}`` where ``members`` is
    a tuple of ``{miniature, item, key (canonical), points, is_pool}`` covering the
    pool weapon(s) and the alternative(s). ``slot_count`` is derived at validate time
    from the (squad-scaled) default counts of the pool members, so an array's counts
    must sum to the number of weapon mounts. Groups with no pool are *additive* and
    excluded (the 19 "equipped with X" extras keep their stepper behaviour)."""
    keyed = _keyed_options(did)
    canon = _canonical_keys(did)
    default_items, item_points = {}, {}
    for o, key in keyed:
        mi = (o.get("miniature"), o.get("item"))
        item_points.setdefault(mi, _int(o.get("points")))
        if _is_default_group(o.get("group")) and _int(o.get("default_value")) > 0:
            default_items[mi] = _int(o.get("default_value"))
    groups, order = {}, []
    for o, key in keyed:
        g = o.get("group")
        if _is_default_group(g):
            continue
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append((o, key))
    choose_from = _wl(did).get("choose_from") or []
    specs = []
    for g in order:
        if _instruction_type(g) != "replace_any":
            continue
        opts = groups[g]
        minis = {o.get("miniature") for o, _ in opts}
        alt_items = {o.get("item") for o, _ in opts}
        cf = next((c for c in choose_from
                   if c.get("miniature") in minis
                   and (_flat_items(c.get("choices")) & alt_items)), None)
        if not cf:
            continue
        cf_items = _flat_items(cf.get("choices"))
        bundles = cf.get("choices") or []
        single_item = all(len(b) <= 1 for b in bundles)
        members, seen = [], set()
        for (mini, item), dv in default_items.items():
            if item in cf_items and mini in minis:
                mi = (mini, item)
                members.append({"miniature": mini, "item": item, "key": canon[mi],
                                "points": item_points.get(mi, 0), "is_pool": True})
                seen.add(mi)
        if not members:
            continue  # additive — no pool to draw from
        for o, key in opts:
            mi = (o.get("miniature"), o.get("item"))
            if mi in seen:
                continue
            seen.add(mi)
            members.append({"miniature": mi[0], "item": mi[1], "key": canon[mi],
                            "points": item_points.get(mi, 0), "is_pool": False})
        specs.append({"instruction": g, "single_item": single_item,
                      "miniatures": tuple(minis), "bundles": bundles,
                      "members": tuple(members)})
    return tuple(specs)


@lru_cache(maxsize=4096)
def _multi_meta(did):
    """Per-model bundle metadata for the *multi-item* array specs (each model picks
    a whole loadout, e.g. Carnifex "cannon + talons"). Keyed by the spec's index in
    ``_array_specs``: ``{spec_idx: {miniatures, per_mini: {M: {bundles, default_idx,
    item_keys}}}}``. A bundle is ``{key_counts (canonical→count), points, label}``.
    Per-model picks persist as synthetic ``@b|<spec>|<mini>|<model>`` keys holding a
    bundle index; the item counts are *derived* from those picks in
    ``validate_selection`` so points/summary stay on the normal option keys."""
    specs = _array_specs(did)
    if not any(not s["single_item"] for s in specs):
        return {}
    canon = _canonical_keys(did)
    dv_of, pts_of = {}, {}
    for o, key in _keyed_options(did):
        mi = (o.get("miniature"), o.get("item"))
        pts_of.setdefault(mi, _int(o.get("points")))
        if _is_default_group(o.get("group")):
            dv_of[mi] = _int(o.get("default_value"))
    nbase = _miniature_counts(did, army._squad_bounds(did)["default"])
    meta, claimed = {}, set()
    for i, s in enumerate(specs):
        if s["single_item"]:
            continue
        minis = []
        for m in s["members"]:
            if m["miniature"] not in minis:
                minis.append(m["miniature"])
        per_mini = {}
        for M in minis:
            m_keys = {m["key"] for m in s["members"] if m["miniature"] == M}
            if m_keys & claimed:
                continue  # another group already owns these weapons (e.g. Carnifex)
            claimed |= m_keys
            nb = nbase.get(M, 0) or 1
            pm_default = {}
            for m in s["members"]:
                if m["is_pool"] and m["miniature"] == M:
                    per = dv_of.get((M, m["item"]), 0) // nb
                    if per:
                        pm_default[m["key"]] = per
            bundles = []
            for b in s["bundles"]:
                kc, pts, labels, ok = {}, 0, [], True
                for it in b:
                    mi = (M, it["item"])
                    if mi not in canon:
                        ok = False
                        break
                    c = _int(it.get("count", 1))
                    kc[canon[mi]] = kc.get(canon[mi], 0) + c
                    pts += pts_of.get(mi, 0) * c
                    labels.append(("%d %s" % (c, it["item"])) if c > 1 else it["item"])
                if ok and kc:
                    bundles.append({"key_counts": kc, "points": pts,
                                    "label": " + ".join(labels)})
            if not bundles:
                claimed -= m_keys  # nothing renderable for M — release its weapons
                continue
            default_idx = next((j for j, bd in enumerate(bundles)
                                if bd["key_counts"] == pm_default), 0)
            per_mini[M] = {"bundles": bundles, "default_idx": default_idx,
                           "item_keys": sorted({m["key"] for m in s["members"]
                                                if m["miniature"] == M})}
        if per_mini:
            meta[i] = {"miniatures": [m for m in minis if m in per_mini],
                       "per_mini": per_mini}
    return meta


@lru_cache(maxsize=4096)
def _multi_item_keys(did):
    """All canonical item keys whose count is *derived* from per-model bundle picks
    (so ``overrides_of`` persists the bundle picks, not these recomputed counts)."""
    out = set()
    for md in _multi_meta(did).values():
        for pm in md["per_mini"].values():
            out.update(pm["item_keys"])
    return out


def _bundle_key(spec_idx, miniature, model_idx):
    return "@b|%d|%s|%d" % (spec_idx, miniature or "", model_idx)


def _instruction_type(instruction):
    t = (instruction or "").lower()
    if _is_default_group(instruction):
        return "default"
    if "for every" in t:
        return "limited_per_n"
    if "all models in this unit" in t or "every model in this unit" in t:
        return "all_model"
    if "any number of" in t:
        return "replace_any"
    if "one of the following" in t:
        return "replace_one"
    return "choice"


@lru_cache(maxsize=4096)
def wargear_schema(did):
    """Ordered render groups. Each: ``{instruction, type, miniature, items, limits,
    duplicate_limit}`` where ``type`` ∈ {default, replace_one, limited_per_n,
    all_model, replace_any, choice}. ``replace_one``/``all_model`` items are
    promoted to ``input_type: radio``. Empty for the 8 no-options units."""
    keyed = _keyed_options(did)
    limited = _limited_index(did)
    allmodel = _all_model_index(did)
    groups, index = [], {}
    for o, key in keyed:
        g = o.get("group")
        if g not in index:
            index[g] = len(groups)
            groups.append({"instruction": g, "type": None, "miniature": o.get("miniature"),
                           "items": [], "limits": None, "duplicate_limit": None})
        groups[index[g]]["items"].append({
            "key": key, "item": o.get("item"), "miniature": o.get("miniature"),
            "input_type": o.get("input_type"), "points": _int(o.get("points")),
            "default_value": _int(o.get("default_value")),
        })
    for grp in groups:
        items = {i["item"] for i in grp["items"]}
        mini = grp["miniature"]
        if _is_default_group(grp["instruction"]):
            grp["type"] = "default"
            continue
        lc = next((l for l in limited
                   if (l["miniature"] == mini or l["miniature"] is None) and (items & l["items"])), None)
        am = next((a for a in allmodel
                   if (a["miniature"] == mini or a["miniature"] is None) and (items & a["items"])), None)
        if lc:
            grp["type"] = "limited_per_n"
            grp["limits"] = lc["limits"]
            grp["duplicate_limit"] = lc["duplicate_limit"]
        elif am:
            grp["type"] = "all_model"
        else:
            grp["type"] = _instruction_type(grp["instruction"])
        if grp["type"] in ("replace_one", "all_model"):
            for i in grp["items"]:
                i["input_type"] = "radio"

    # Weapon arrays: ``replace_any`` groups with a pool become an ``array`` group.
    # Single-item bundles → mode "mounts" (per-mount weapon selects/steppers).
    # Multi-item bundles → mode "models" (each model picks a whole loadout). The pool
    # weapons are managed in the array, so suppress them from the read-only Default.
    specs = _array_specs(did)
    spec_by_instr = {s["instruction"]: (idx, s) for idx, s in enumerate(specs)}
    meta = _multi_meta(did)
    suppressed = {(m["miniature"], m["item"])
                  for s in specs for m in s["members"] if m["is_pool"]}
    out = []
    for grp in groups:
        entry = spec_by_instr.get(grp["instruction"])
        if entry and not _is_default_group(grp["instruction"]):
            idx, s = entry
            if s["single_item"]:
                per, order = {}, []
                for m in s["members"]:
                    mm = m["miniature"]
                    if mm not in per:
                        per[mm] = []
                        order.append(mm)
                    per[mm].append({"item": m["item"], "key": m["key"],
                                    "points": m["points"], "is_pool": m["is_pool"]})
                out.append({"instruction": grp["instruction"], "type": "array", "mode": "mounts",
                            "miniatures": order,
                            "minis": [{"miniature": mm, "options": per[mm]} for mm in order]})
            else:
                md = meta.get(idx)
                minis = [{"miniature": mm,
                          "bundles": [{"idx": j, "label": b["label"], "points": b["points"]}
                                      for j, b in enumerate(md["per_mini"][mm]["bundles"])]}
                         for mm in (md["miniatures"] if md else []) if mm in md["per_mini"]]
                if minis:  # skip groups whose weapons another picker already owns
                    out.append({"instruction": grp["instruction"], "type": "array",
                                "mode": "models", "spec_idx": idx, "minis": minis})
        elif _is_default_group(grp["instruction"]):
            grp["items"] = [i for i in grp["items"]
                            if (i["miniature"], i["item"]) not in suppressed]
            out.append(grp)
        else:
            out.append(grp)
    return out


def _miniature_counts(did, squad_size):
    return {m["model"]: m["count"]
            for m in army._composition_breakdown(did, squad_size)}


def default_selection(did, squad_size):
    """Default loadout ``{key: value}``. Default-Wargear stepper counts scale with
    the model count of their miniature; everything else uses ``default_value``."""
    bounds = army._squad_bounds(did)
    base = _miniature_counts(did, bounds["default"])
    current = _miniature_counts(did, squad_size)
    selection = {}
    for o, key in _keyed_options(did):
        dv = _int(o.get("default_value"))
        if (o.get("input_type") == "stepper" and _is_default_group(o.get("group"))
                and o.get("miniature")):
            bc = base.get(o["miniature"], 0)
            cc = current.get(o["miniature"], 0)
            selection[key] = (dv * cc // bc) if bc else dv
        else:
            selection[key] = dv
    # Per-model bundle picks for multi-item arrays default to each model's default
    # loadout (a synthetic ``@b|spec|mini|model`` key holding a bundle index).
    for i, md in _multi_meta(did).items():
        for M, pm in md["per_mini"].items():
            for model_idx in range(current.get(M, 0)):
                selection[_bundle_key(i, M, model_idx)] = pm["default_idx"]
    return selection


def apply_overrides(did, squad_size, overrides):
    """Full selection = default loadout overlaid with the sparse user overrides
    (option-key counts *and* synthetic ``@b|…`` bundle picks)."""
    sel = default_selection(did, squad_size)
    if overrides:
        for k, v in overrides.items():
            if k in sel:
                sel[k] = _int(v)
    return sel


def overrides_of(did, squad_size, selection):
    """Sparse diff of a full selection from the default — what we persist. Item
    counts derived from bundle picks are skipped (the ``@b|…`` picks carry them)."""
    default = default_selection(did, squad_size)
    derived = _multi_item_keys(did)
    return {k: _int(v) for k, v in (selection or {}).items()
            if k not in derived and k in default and _int(v) != default[k]}


def points_delta(did, squad_size, selection):
    """Points of a selection relative to the default loadout (default → 0)."""
    default = default_selection(did, squad_size)
    delta = 0
    for o, key in _keyed_options(did):
        pts = _int(o.get("points"))
        if pts:
            delta += (_int(selection.get(key, default[key])) - default[key]) * pts
    return delta


def limited_cap(limits, squad_size):
    """Threshold lookup: the ``max_choices`` of the highest ``per_models`` that is
    ``<= squad_size`` (0 if none). Handles non-monotonic tables (Blightlord)."""
    applicable = [l for l in (limits or []) if (l.get("per_models") or 0) <= squad_size]
    if not applicable:
        return 0
    best = max(applicable, key=lambda l: l.get("per_models") or 0)
    return _int(best.get("max_choices"))


def validate_selection(did, squad_size, selection):
    """Enforce legality, returning ``{selection, overrides, violations,
    points_delta, loadout_summary}``. Illegal selections are auto-corrected toward
    the nearest legal state and each correction is recorded as a violation.

    Enforced: stepper bounds, ``replace_one``/``all_model`` mutual exclusion,
    ``limited_per_n`` threshold caps + ``duplicate_limit``."""
    schema = wargear_schema(did)
    default = default_selection(did, squad_size)
    sel = dict(default)
    for k, v in (selection or {}).items():
        if k in default:
            sel[k] = _int(v)
    counts = _miniature_counts(did, squad_size)
    violations = []

    def flag(msg):
        violations.append({"level": "warn", "code": "wargear_illegal", "message": msg})

    for grp in schema:
        if grp["type"] == "array":
            continue  # balanced unit-wide below, against its spec
        items = grp["items"]
        t = grp["type"]
        instr = (grp["instruction"] or "")[:48]
        if t == "replace_one":
            chosen = [i for i in items if _int(sel.get(i["key"])) > 0]
            if len(chosen) > 1:
                for i in chosen[1:]:
                    sel[i["key"]] = 0
                flag("%s: choose only one" % instr)
            for i in items:
                if _int(sel.get(i["key"])) > 1:
                    sel[i["key"]] = 1
        elif t == "limited_per_n":
            cap = limited_cap(grp["limits"], squad_size)
            dup = grp["duplicate_limit"]
            clamped = False
            for i in items:
                v = _int(sel.get(i["key"]))
                if dup is not None and v > dup:
                    sel[i["key"]] = v = dup
                    clamped = True
            running = 0
            for i in items:
                v = _int(sel.get(i["key"]))
                if running + v > cap:
                    sel[i["key"]] = max(0, cap - running)
                    clamped = True
                running += _int(sel.get(i["key"]))
            if clamped:
                flag("%s: max %d at this size" % (instr, cap))
        else:  # default / replace_any / choice — bound *additive* steppers only
            for i in items:
                if (i["input_type"] == "stepper" and i["miniature"] and t != "default"
                        and i["default_value"] == 0):
                    mc = counts.get(i["miniature"], 0) or squad_size
                    if _int(sel.get(i["key"])) > mc:
                        sel[i["key"]] = mc
                        flag("%s: at most %d" % (instr, mc))

    # all_model: each unit-wide choice equips exactly one weapon on every model
    # (the alternatives live in different option groups, so link them by key).
    item_keys = _item_keys(did)
    for am in _all_model_index(did):
        keys = [k for it in am["items"] for k in item_keys.get((am["miniature"], it), [])]
        if not keys:
            continue
        mc = counts.get(am["miniature"], 0)
        active = [k for k in keys if _int(sel.get(k)) > 0 and default.get(k, 0) == 0]
        if len(active) > 1:
            flag("Unit weapon: choose only one")
        chosen = active[0] if active else next((k for k in keys if default.get(k, 0) > 0), keys[0])
        for k in keys:
            sel[k] = mc if k == chosen else 0

    # weapon arrays: per miniature, the counts over a spec's members must sum to the
    # number of weapon mounts (Σ pool defaults). The choose_from `limit` is *not*
    # enforced here — "Any number of…" lets every model deviate. The editor posts the
    # full balanced state, so this is a no-op for valid edits; it re-derives the pool
    # on squad-size changes and trims over-cap alternatives defensively.
    for spec in _array_specs(did):
        if not spec["single_item"]:
            continue
        by_mini = {}
        for m in spec["members"]:
            by_mini.setdefault(m["miniature"], []).append(m)
        for mini, mems in by_mini.items():
            # fold any stray counts onto each item's canonical key
            for m in mems:
                for k in item_keys.get((m["miniature"], m["item"]), []):
                    if k != m["key"] and _int(sel.get(k)):
                        sel[m["key"]] = _int(sel.get(m["key"])) + _int(sel.get(k))
                        sel[k] = 0
            for m in mems:
                if _int(sel.get(m["key"])) < 0:
                    sel[m["key"]] = 0
            pool = [m for m in mems if m["is_pool"]]
            alts = [m for m in mems if not m["is_pool"]]
            slot_count = sum(_int(default.get(m["key"], 0)) for m in pool)
            total = sum(_int(sel.get(m["key"])) for m in mems)
            if total == slot_count:
                continue  # valid distribution — leave the user's choices intact
            over = total > slot_count   # illegal input; underfill = squad-grow (silent)
            alt_sum = sum(_int(sel.get(m["key"])) for m in alts)
            if alt_sum > slot_count:  # too many alternatives — trim from the end
                excess = alt_sum - slot_count
                for m in reversed(alts):
                    take = min(_int(sel.get(m["key"])), excess)
                    sel[m["key"]] -= take
                    excess -= take
                    if excess <= 0:
                        break
                alt_sum = slot_count
            # fill the remaining mounts with the pool weapon(s), by default share
            remaining = slot_count - alt_sum
            assigned = 0
            for idx, m in enumerate(pool):
                val = (remaining - assigned) if idx == len(pool) - 1 \
                    else max(0, min(remaining - assigned, _int(default.get(m["key"], 0))))
                sel[m["key"]] = val
                assigned += val
            if over:
                flag("%s: up to %d weapon%s"
                     % ((spec["instruction"] or "")[:40], slot_count,
                        "" if slot_count == 1 else "s"))

    # multi-item arrays: each model picks a whole loadout (a bundle index in an
    # ``@b|…`` key). Clamp the index, then derive the item counts from the picks.
    for i, md in _multi_meta(did).items():
        for M, pm in md["per_mini"].items():
            bundles = pm["bundles"]
            nb = len(bundles)
            for k in pm["item_keys"]:
                sel[k] = 0
            for model_idx in range(counts.get(M, 0)):
                bk = _bundle_key(i, M, model_idx)
                bidx = _int(sel.get(bk, pm["default_idx"]))
                if bidx < 0 or bidx >= nb:
                    bidx = pm["default_idx"]
                sel[bk] = bidx
                for k, c in bundles[bidx]["key_counts"].items():
                    sel[k] = _int(sel.get(k)) + c

    return {"selection": sel,
            "overrides": overrides_of(did, squad_size, sel),
            "violations": violations,
            "points_delta": points_delta(did, squad_size, sel),
            "loadout_summary": resolved_loadout(did, squad_size, sel)}


def resolved_loadout(did, squad_size, selection):
    """Human-readable per-miniature summary of the selected items (count > 0)."""
    selection = selection or {}
    by_mini, order = {}, []
    for o, key in _keyed_options(did):
        count = _int(selection.get(key, 0))
        if count <= 0:
            continue
        mini = o.get("miniature") or ""
        if mini not in by_mini:
            by_mini[mini] = {}
            order.append(mini)
        item = o.get("item") or ""
        by_mini[mini][item] = by_mini[mini].get(item, 0) + count
    parts = []
    for mini in order:
        text = ", ".join(("%d %s" % (c, it)) if c > 1 else it
                         for it, c in by_mini[mini].items())
        parts.append(("%s — %s" % (mini, text)) if mini else text)
    return " · ".join(parts)
