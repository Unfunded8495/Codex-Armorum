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
import re
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
    duplicate_limit, linked_default_keys}`` where ``type`` ∈ {default, replace_one,
    limited_per_n, all_model, replace_any, choice}. ``replace_one``/``all_model``
    items are promoted to ``input_type: radio``. ``linked_default_keys`` holds the
    Default-group key(s) a ``replace_one``/``all_model`` group displaces when one of
    its alternatives is chosen (see the cross-reference pass below) -- empty when
    that link can't be resolved unambiguously. For ``limited_per_n`` groups it
    instead holds the weapon-array *pool* key(s) the capped replacement displaces
    (see the array cross-reference pass), so taking a replacement can decrement
    the pool weapon. Empty for the 8 no-options units."""
    keyed = _keyed_options(did)
    limited = _limited_index(did)
    allmodel = _all_model_index(did)
    item_keys = _item_keys(did)
    cfs = _wl(did).get("choose_from") or []
    groups, index = [], {}
    for o, key in keyed:
        g = o.get("group")
        if g not in index:
            index[g] = len(groups)
            groups.append({"instruction": g, "type": None, "miniature": o.get("miniature"),
                           "items": [], "limits": None, "duplicate_limit": None,
                           "linked_default_keys": ()})
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
            own = {i["key"] for i in grp["items"]}
            grp["linked_default_keys"] = tuple(k for it in am["items"]
                                               for k in item_keys.get((mini, it), []) if k not in own)
        else:
            grp["type"] = _instruction_type(grp["instruction"])
        if grp["type"] in ("replace_one", "all_model"):
            for i in grp["items"]:
                i["input_type"] = "radio"

    # replace_one cross-reference: a group's instruction text only carries its own
    # alternatives, not the Default-group item it displaces (that lives in a
    # separate group -- e.g. Chaos Lord's "Daemon hammer" vs. its "replaced with one
    # of the following: Accursed weapon / Astartes chainsword" group). ``choose_from``
    # lists the full mutually-exclusive choice set including the default, so use it
    # to recover the displaced key(s) -- but only when the match is unambiguous:
    # exactly one choose_from entry overlaps the group's items, that entry isn't
    # ALSO claimed by some other replace_one group (e.g. a Hive Tyrant's two
    # independently-swappable arms share one combined choose_from entry -- linking
    # both to it would cross-wire each arm's default into the other's), and every
    # leftover item name is a confirmed Default-group item. Ambiguous overlaps and
    # genuinely defaultless slots (e.g. vehicle sponsons with no baseline weapon) are
    # left unlinked and fall back to validate_selection's within-group-only check.
    default_grp = next((g for g in groups if g["type"] == "default"), None)
    default_keys = {(i["miniature"], i["item"]): i["key"]
                     for i in (default_grp["items"] if default_grp else [])
                     if i["default_value"] > 0}
    grp_match, entry_owners = {}, {}
    for grp in groups:
        if grp["type"] != "replace_one":
            continue
        mini = grp["miniature"]
        alt_items = {i["item"] for i in grp["items"]}
        matches = [c for c in cfs if (c.get("miniature") == mini or c.get("miniature") is None)
                   and (_flat_items(c.get("choices")) & alt_items)]
        if len(matches) != 1:
            continue
        grp_match[id(grp)] = matches[0]
        entry_owners.setdefault(id(matches[0]), []).append(grp)
    for grp in groups:
        cf = grp_match.get(id(grp))
        if cf is None or len(entry_owners[id(cf)]) > 1:
            continue
        mini = grp["miniature"]
        alt_items = {i["item"] for i in grp["items"]}
        leftover = _flat_items(cf.get("choices")) - alt_items
        if not leftover:
            continue
        link_keys = [default_keys[(mini, nm)] for nm in leftover if (mini, nm) in default_keys]
        if len(link_keys) == len(leftover):
            grp["linked_default_keys"] = tuple(link_keys)

    # Weapon arrays: ``replace_any`` groups with a pool become an ``array`` group.
    # Single-item bundles → mode "mounts" (per-mount weapon selects/steppers).
    # Multi-item bundles → mode "models" (each model picks a whole loadout). The pool
    # weapons are managed in the array, so suppress them from the read-only Default.
    specs = _array_specs(did)

    # Fallback for the still-unlinked replace_one groups: the instruction
    # itself names the displaced weapon ("The Aspiring Champion's boltgun can
    # be replaced with..."). The choose_from match above goes ambiguous exactly
    # when one miniature has several swap slots with IDENTICAL alternative sets
    # (boltgun-slot and bolt-pistol-slot both offering chainsword/accursed/
    # etc.), but the named weapon disambiguates them for free. Two guards: the
    # name must exactly match a Default-group item of the group's own miniature
    # (case-insensitive), and that default key must not be managed by a weapon
    # array (the array passes re-derive such keys after the replace_one
    # exclusion runs, which would undo the clear -- e.g. Krieg Combat
    # Engineers' Watchmaster, whose autopistol is also an "any number of
    # models" array pool weapon).
    array_owned = {m["key"] for sp in specs for m in sp["members"]}
    array_owned |= _multi_item_keys(did)
    for grp in groups:
        if grp["type"] != "replace_one" or grp["linked_default_keys"]:
            continue
        m = re.search(r"[’']s\s+(.+?)\s+can be replaced", grp["instruction"] or "",
                      re.IGNORECASE)
        if not m:
            continue
        nm = m.group(1).strip().lower()
        key = next((k for (mn, item), k in default_keys.items()
                    if mn == grp["miniature"] and item.lower() == nm), None)
        if key and key not in array_owned:
            grp["linked_default_keys"] = (key,)

    # limited_per_n → array-pool cross-reference: a capped "…boltgun can be
    # replaced with…" group displaces the same pool weapon a replace_any array
    # manages (Legionaries: the "For every 5 models…" heavy-weapon group and the
    # "Any number…" chainsword array both draw on the Default boltgun). Link the
    # group to the spec's pool key(s) so validate_selection can decrement the
    # pool when a capped replacement is taken. Linked only when every item the
    # group offers appears in the spec's choose_from bundles (an additive extra
    # like a Chaos Icon never does) and at least one of them is *not* already a
    # spec member (members are balanced inside the array itself, so an
    # all-members group would be double-counted by the link).
    canon = _canonical_keys(did)
    for grp in groups:
        if grp["type"] != "limited_per_n":
            continue
        # a group's items can span several miniatures (WE Terminators offer the
        # same swap to the Champion and the squad), so link per item-miniature
        minis = {i["miniature"] for i in grp["items"]}
        names = {i["item"] for i in grp["items"]}
        linked = []
        for s in specs:
            if not (minis & set(s["miniatures"])) or not names <= _flat_items(s["bundles"]):
                continue
            member_keys = {m["key"] for m in s["members"]}
            if all(canon.get((i["miniature"], i["item"])) in member_keys
                   for i in grp["items"]):
                continue
            for m in s["members"]:
                if m["is_pool"] and m["miniature"] in minis and m["key"] not in linked:
                    linked.append(m["key"])
        if linked:
            grp["linked_default_keys"] = tuple(linked)

    spec_by_instr = {s["instruction"]: (idx, s) for idx, s in enumerate(specs)}
    meta = _multi_meta(did)
    suppressed = {(m["miniature"], m["item"])
                  for s in specs for m in s["members"] if m["is_pool"]}
    # A "models"-mode bundle option can silently duplicate a weapon that already has
    # its own dedicated card elsewhere (e.g. a squad's per-model boltgun-swap bundle
    # offering "balefire tome" as one of many dropdown choices, when a separate
    # "up to 1 balefire tome in this unit" capped card already governs that exact
    # key). Flag those bundles ``redundant`` rather than dropping them here -- the
    # renderer keeps a model's *current* pick visible even if redundant (dropping it
    # outright would misrender any existing selection made before this de-dup
    # existed), and only hides it as an offer for new picks. The other card stays
    # the one place that controls the key; this just stops the dropdown from
    # pretending to control it too.
    standalone_keys = {i["key"] for grp in groups if grp["type"] != "default"
                        and spec_by_instr.get(grp["instruction"]) is None
                        for i in grp["items"]}
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
                minis = []
                for mm in (md["miniatures"] if md else []):
                    if mm not in md["per_mini"]:
                        continue
                    pm = md["per_mini"][mm]
                    bundles = [{"idx": j, "label": b["label"], "points": b["points"],
                                "redundant": j != pm["default_idx"]
                                             and bool(set(b["key_counts"]) & standalone_keys)}
                               for j, b in enumerate(pm["bundles"])]
                    minis.append({"miniature": mm, "bundles": bundles,
                                  "default_idx": pm["default_idx"]})
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

    Enforced: stepper bounds, ``replace_one``/``all_model`` mutual exclusion
    (including against the Default-group item a chosen alternative displaces, via
    ``linked_default_keys``), ``limited_per_n`` threshold caps + ``duplicate_limit``
    -- re-applied after the weapon-array passes for caps that govern array-bundle
    weapons -- and the pool decrement for ``limited_per_n`` replacements that
    displace a weapon-array pool weapon (a plasma gun taken on the capped card
    consumes one of the boltguns the array manages)."""
    schema = wargear_schema(did)
    default = default_selection(did, squad_size)
    sel = dict(default)
    for k, v in (selection or {}).items():
        if k in default:
            sel[k] = _int(v)
    counts = _miniature_counts(did, squad_size)
    violations = []

    def flag(msg):
        # deduped: the early per-group clamp and the post-array settlement can
        # legitimately correct the same card in one request
        if not any(v["message"] == msg for v in violations):
            violations.append({"level": "warn", "code": "wargear_illegal", "message": msg})

    def clip(text, n=48):
        # Word-boundary truncation for message prefixes -- a hard slice cuts
        # mid-word ("...1 Legionary's b: max 2 at this size").
        text = (text or "").strip()
        if len(text) <= n:
            return text
        cut = text[:n].rsplit(" ", 1)[0].rstrip(" ,;:")
        return (cut or text[:n]) + "..."

    # limited_per_n cards whose weapons a multi-item array's bundles also set
    # (or whose linked pool a multi-item array manages) are settled against that
    # array *after* the ``@b`` derive pass -- clamping them here first would be
    # overwritten by the derive and re-flag on every request. ``rel_spec`` maps
    # each such card to the spec that settles it.
    specs = _array_specs(did)
    canon = _canonical_keys(did)
    meta = _multi_meta(did)
    linked_groups = [g for g in schema
                     if g["type"] == "limited_per_n" and g.get("linked_default_keys")]
    rel_spec = {}
    for i, md in meta.items():
        spec_pool = {m["key"] for m in specs[i]["members"] if m["is_pool"]}
        bundle_keys = set()
        for pm in md["per_mini"].values():
            for b in pm["bundles"]:
                bundle_keys |= set(b["key_counts"])
        for grp in linked_groups:
            if grp["instruction"] in rel_spec:
                continue
            gkeys = {canon.get((it["miniature"], it["item"]), it["key"])
                     for it in grp["items"]}
            if (set(grp["linked_default_keys"]) & spec_pool) or (gkeys & bundle_keys):
                rel_spec[grp["instruction"]] = i

    for grp in schema:
        if grp["type"] == "array":
            continue  # balanced unit-wide below, against its spec
        items = grp["items"]
        t = grp["type"]
        instr = clip(grp["instruction"])
        if t == "replace_one":
            # ``linked`` is the Default-group item(s) this group's alternatives
            # displace (resolved by wargear_schema via choose_from when
            # unambiguous) -- e.g. a Chaos Lord's "Daemon hammer", or a bundled
            # "bolt pistol and boltgun" baseline that several units replace as a
            # pair. Treated as one unit: active alongside one of this group's own
            # alternatives is the conflict this guards (a stale pre-swap default
            # left behind by an incomplete patch); its own members never conflict
            # with *each other* -- they're meant to coexist as the un-replaced
            # baseline.
            own_keys = [i["key"] for i in items]
            linked = list(grp.get("linked_default_keys") or ())
            own_active = [k for k in own_keys if _int(sel.get(k)) > 0]
            default_active = any(_int(sel.get(k)) > 0 for k in linked)
            if len(own_active) > 1 or (own_active and default_active):
                flag("%s: choose only one" % instr)
            if own_active:
                chosen_key = own_active[0]
                for k in own_keys:
                    sel[k] = 1 if k == chosen_key else 0
                for k in linked:
                    sel[k] = 0
            else:
                for k in own_keys:
                    sel[k] = 0
                for k in linked:
                    sel[k] = default.get(k, 0)
        elif t == "limited_per_n":
            if grp["instruction"] in rel_spec:
                continue  # settled against its weapon array below (cap + pool)
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
                     % (clip(spec["instruction"], 40), slot_count,
                        "" if slot_count == 1 else "s"))

    # multi-item arrays: each model picks a whole loadout (a bundle index in an
    # ``@b|…`` key). Clamp the index, then derive the item counts from the picks.
    # Bundle counts land straight on ``sel`` only for the spec's own item_keys;
    # counts a bundle sets on *foreign* keys (weapons owned by a limited_per_n
    # card, e.g. a Legionary's plasma gun) are collected in ``derived`` and
    # reconciled with that card's stepper in the settlement below. Adding them
    # to ``sel`` unconditionally both double-counted the weapon against its own
    # stepper and re-introduced over-cap counts *after* the limited_per_n clamp
    # had already run (the clamp pass sits above the array passes).
    settled_keys = set()
    for i, md in meta.items():
        spec = specs[i]
        ctx = {}
        for M, pm in md["per_mini"].items():
            bundles = pm["bundles"]
            nb = len(bundles)
            item_keys = set(pm["item_keys"])
            for k in item_keys:
                sel[k] = 0
            derived, picks = {}, []
            for model_idx in range(counts.get(M, 0)):
                bk = _bundle_key(i, M, model_idx)
                bidx = _int(sel.get(bk, pm["default_idx"]))
                if bidx < 0 or bidx >= nb:
                    bidx = pm["default_idx"]
                sel[bk] = bidx
                picks.append(bk)
                for k, c in bundles[bidx]["key_counts"].items():
                    derived[k] = derived.get(k, 0) + c
                    if k in item_keys:
                        sel[k] = _int(sel.get(k)) + c
            ctx[M] = {"pm": pm, "bundles": bundles, "item_keys": item_keys,
                      "derived": derived, "picks": picks,
                      "pool_keys": [m["key"] for m in spec["members"]
                                    if m["is_pool"] and m["miniature"] == M]}

        def flip_one(c, keys):
            """Re-point the last model whose bundle sets one of ``keys`` at the
            default bundle (the pool loadout), keeping derived/sel in step."""
            pm, bundles = c["pm"], c["bundles"]
            for bk in reversed(c["picks"]):
                bidx = _int(sel.get(bk))
                if bidx == pm["default_idx"]:
                    continue
                if not (set(bundles[bidx]["key_counts"]) & keys):
                    continue
                for k2, c2 in bundles[bidx]["key_counts"].items():
                    c["derived"][k2] = c["derived"].get(k2, 0) - c2
                    if k2 in c["item_keys"]:
                        sel[k2] = max(0, _int(sel.get(k2)) - c2)
                sel[bk] = pm["default_idx"]
                for k2, c2 in bundles[pm["default_idx"]]["key_counts"].items():
                    c["derived"][k2] = c["derived"].get(k2, 0) + c2
                    if k2 in c["item_keys"]:
                        sel[k2] = _int(sel.get(k2)) + c2
                return True
            return False

        def ext_keys_of(grp):
            """Per-miniature canonical keys of the card's weapons that the array
            doesn't own itself (the ones its bundles set as *foreign* keys)."""
            out = {}
            for it in grp["items"]:
                M = it["miniature"]
                ck = canon.get((M, it["item"]), it["key"])
                if M in ctx and ck not in ctx[M]["item_keys"]:
                    out.setdefault(M, set()).add(ck)
            return out

        def picks_using(ext_by_mini):
            """Models whose current bundle takes one of the card's weapons -- the
            unit the cap counts (a "1 vexilla and 1 misericordia" bundle is one
            replacement, not two)."""
            n = 0
            for M, ks in ext_by_mini.items():
                c = ctx[M]
                for bk in c["picks"]:
                    if set(c["bundles"][_int(sel.get(bk))]["key_counts"]) & ks:
                        n += 1
            return n

        def displaced_pool(c, ck):
            """Pool keys one stepper replacement of ``ck`` takes: those absent
            from the bundle that carries ``ck`` alongside the most pool weapons.
            Additive items (a Regimental Standard rides *with* the lasgun's
            bundle) displace nothing; an item never offered in a bundle is
            assumed to displace the whole pool row."""
            pool = set(c["pool_keys"])
            best = None
            for b in c["bundles"]:
                if ck in b["key_counts"]:
                    kept = pool & set(b["key_counts"])
                    if best is None or len(kept) > len(best):
                        best = kept
            return list(pool - best) if best is not None else list(pool)

        def consume_rows(keys, amount):
            """A replacement takes one of EACH displaced pool weapon ("…autopistol
            and trench club can be replaced…"); returns the shortfall. Nothing to
            displace (an additive item) means no shortfall."""
            if amount <= 0 or not keys:
                return 0
            rows = min(amount, min(max(0, _int(sel.get(k))) for k in keys))
            for k in keys:
                sel[k] = _int(sel.get(k)) - rows
            return amount - rows

        relevant = [g for g in linked_groups if rel_spec.get(g["instruction"]) == i]

        # phase 1 -- flips only: while more models draw on a card's rule than its
        # cap (or an item exceeds duplicate_limit), re-point the excess picks at
        # the default bundle. All flips happen before any card's counts are
        # written, so a later card's flip can't invalidate an earlier card's
        # already-settled state (bundles can span two cards' weapons).
        flagged = set()
        for grp in relevant:
            cap = limited_cap(grp["limits"], squad_size)
            dup = grp["duplicate_limit"]
            ebm = ext_keys_of(grp)
            if picks_using(ebm) > cap:
                flagged.add(grp["instruction"])
                while picks_using(ebm) > cap:
                    for M in reversed(list(ebm)):
                        if flip_one(ctx[M], ebm[M]):
                            break
                    else:
                        break
            if dup is not None:
                for M, ks in ebm.items():
                    for ck in ks:
                        while ctx[M]["derived"].get(ck, 0) > dup:
                            if not flip_one(ctx[M], {ck}):
                                break
                            flagged.add(grp["instruction"])

        # phase 2 -- write each card's counts. A weapon's final count is its
        # derived (@b) share plus whatever the card's stepper asks for beyond it
        # (legacy states persisted both representations of one replacement, so
        # the derived share is never double-added); each stepper-extra unit is
        # one more replaced model, so it consumes the cap budget the picks
        # didn't use and takes the displaced pool weapon(s) off the array.
        for grp in relevant:
            cap = limited_cap(grp["limits"], squad_size)
            dup = grp["duplicate_limit"]
            capped = grp["instruction"] in flagged
            short = False
            budget = cap - picks_using(ext_keys_of(grp))
            for it in grp["items"]:
                gk = it["key"]
                M = it["miniature"]
                ck = canon.get((M, it["item"]), gk)
                c = ctx.get(M)
                if gk in settled_keys:
                    continue
                array_owned = c is not None and ck in c["item_keys"]
                if (array_owned or ck in settled_keys) and gk == ck:
                    continue  # nothing but the array / an earlier card sets it
                if array_owned or ck in settled_keys:
                    key, base, dx = gk, _int(default.get(gk, 0)), 0
                    st = max(0, _int(sel.get(gk)) - base)
                else:
                    key, base = ck, _int(default.get(ck, 0))
                    dx = max(0, (c["derived"].get(ck, 0) if c else 0))
                    st = max(0, _int(sel.get(ck)) - base)
                    if gk != ck:
                        st += max(0, _int(sel.get(gk)))  # fold the card's own key
                        sel[gk] = 0
                    settled_keys.add(ck)
                settled_keys.add(gk)
                extra_want = max(0, st - dx)
                extra = min(extra_want, max(0, budget))
                if dup is not None:
                    extra = min(extra, max(0, dup - dx))
                if extra < extra_want:
                    capped = True
                if c is not None:
                    pool = displaced_pool(c, ck)
                else:  # miniature outside this spec -- use the card's own link
                    pool = [k for k in grp["linked_default_keys"]
                            if k.split("|", 1)[0] == M]
                rem = consume_rows(pool, extra)
                if rem:
                    short = True
                    extra -= rem
                sel[key] = base + dx + extra
                budget -= extra
            if capped:
                flag("%s: max %d at this size" % (clip(grp["instruction"]), cap))
            if short:
                flag("%s: more replacements than weapons to replace"
                     % clip(grp["instruction"], 40))

    # linked limited_per_n cards with no multi-item array to settle against
    # (mounts-mode / single-item specs): every replacement taken on the card
    # still consumes one of each displaced pool weapon of its own miniature,
    # trimming the card when the pool runs out. Items the array already
    # balances as members are excluded.
    member_keys = set()
    for grp in linked_groups:
        if grp["instruction"] in rel_spec:
            continue
        if not member_keys:
            member_keys = {m["key"] for s in specs for m in s["members"]}
        short = False
        for it in grp["items"]:
            gk = it["key"]
            ck = canon.get((it["miniature"], it["item"]), gk)
            if gk in member_keys or ck in member_keys or gk in settled_keys:
                continue
            settled_keys.add(gk)
            n = max(0, _int(sel.get(gk)))
            pool = [k for k in grp["linked_default_keys"]
                    if k.split("|", 1)[0] == it["miniature"]]
            if not pool or not n:
                continue
            rows = min(n, min(max(0, _int(sel.get(pk))) for pk in pool))
            for pk in pool:
                sel[pk] = _int(sel.get(pk)) - rows
            if rows < n:
                sel[gk] = rows  # not enough pool weapons left to replace
                short = True
        if short:
            flag("%s: more replacements than weapons to replace"
                 % clip(grp["instruction"], 40))

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
