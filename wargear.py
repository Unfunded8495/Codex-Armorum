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
from itertools import combinations, combinations_with_replacement
from math import comb

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
        choice_sets = []
        for ch in am.get("choices") or []:
            cs = []
            for it in ch.get("items") or []:
                if it.get("item"):
                    items.add(it["item"])
                    cs.append((it["item"], max(1, _int(it.get("count", 1)))))
            if cs:
                choice_sets.append(tuple(cs))
        # ``choice_sets`` keeps the per-choice structure: a choice granting two
        # items ("hyperphase sword and dispersion shield") is ONE pick, not two.
        res.append({"miniature": am.get("miniature"), "items": items,
                    "choice_sets": tuple(choice_sets)})
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


_BULLET_SPLIT = re.compile(r"[◦•]")


def _bullet_bundles(instr, items):
    """Parse an instruction's '◦' bullet list against the group's item names.
    Returns ``(bundles, singles)``: bundles are bullets granting SEVERAL of the
    group's items at once ("1 plasma pistol and 1 Astartes chainsword" is ONE
    option) as ordered ``[(item, count), ...]`` lists; singles maps each item
    name appearing alone in some bullet to its quantity there ("2 inferno
    pistols" is ONE option granting 2 copies; conflicting quantities across
    bullets fall back to 1). Conservative: an item only counts when the bullet
    names it with a leading quantity."""
    parts = _BULLET_SPLIT.split(instr or "")
    if len(parts) < 2:
        # No bullet list: an inline "…can be replaced with 1 kombi-weapon and
        # 1 close combat weapon." is ONE pick granting both items. Parse only
        # the text after the phrase so the *displaced* weapons named before it
        # can't be mistaken for granted ones.
        m = re.search(r"can be replaced with\b(.*)", instr or "",
                      re.IGNORECASE | re.DOTALL)
        if not m:
            return [], {}
        parts = ["", m.group(1)]
    names = {i["item"] for i in items}
    bundles, singles = [], {}
    for seg in parts[1:]:
        seg_l = " " + seg.lower()
        found = {}
        for nm in names:
            m = re.search(r"(\d+)\s+" + re.escape(nm.lower()) + r"s?\b", seg_l)
            if m:
                found[nm] = (m.start(), max(1, _int(m.group(1))))
        for nm in list(found):   # "power fist" inside "relic power fist" etc.
            if any(nm != o and nm.lower() in o.lower() for o in found):
                del found[nm]
        if len(found) == 1:
            nm, (_pos, q) = next(iter(found.items()))
            singles[nm] = q if singles.get(nm, q) == q else 1
        elif len(found) > 1 and " and " in seg_l:
            bundles.append([(nm, q) for nm, (pos, q) in
                            sorted(found.items(), key=lambda kv: kv[1][0])])
    return bundles, singles


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
    if "can be replaced with" in t:
        # Single-alternative swaps ("The Boss Nob's big choppa can be replaced
        # with 1 power klaw") are replace_one with one option: mutually
        # exclusive with the default they displace, not an additive extra.
        # ("cannot be replaced" never contains this phrase, so additive
        # equip-notes stay `choice`.)
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
    the pool weapon. ``linked_default_qty`` maps a linked key to the number of
    pool weapons ONE replacement displaces when that is more than 1 (Seraphim
    trade BOTH their bolt pistols per pick); keys absent from the map displace 1.
    ``option_qty`` is the grant-side mirror: it maps a group item's key to the
    number of copies ONE pick carries when that is more than 1 (a Seraphim pick
    grants 2 inferno pistols) -- the selection still stores picks.
    Empty for the 8 no-options units."""
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
                           "linked_default_keys": (), "linked_default_qty": {},
                           "option_qty": {}})
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
    # (case-insensitive, modulo a leading quantity and a plural "s"), and that
    # default key must not be managed by a weapon array (the array passes
    # re-derive such keys after the replace_one exclusion runs, which would
    # undo the clear -- e.g. Krieg Combat Engineers' Watchmaster, whose
    # autopistol is also an "any number of models" array pool weapon).
    # A compound name ("big choppa and slugga", "bolt pistol, boltgun and
    # close combat weapon") displaces SEVERAL defaults at once; linked only
    # when every part resolves, else left unlinked like any ambiguous case.
    array_owned = {m["key"] for sp in specs for m in sp["members"]}
    array_owned |= _multi_item_keys(did)
    for grp in groups:
        if grp["type"] != "replace_one" or grp["linked_default_keys"]:
            continue
        m = re.search(r"[’']s\s+(.+?)\s+can be replaced", grp["instruction"] or "",
                      re.IGNORECASE)
        if not m:
            continue
        names = [nm.strip() for part in m.group(1).split(" and ")
                 for nm in part.split(",") if nm.strip()]
        link_keys = []
        for nm in names:
            nm_l = re.sub(r"^\d+\s+", "", nm.lower())
            key = next((k for (mn, item), k in default_keys.items()
                        if mn == grp["miniature"]
                        and (item.lower() == nm_l or item.lower() + "s" == nm_l)),
                       None)
            if key is None or key in array_owned or key in link_keys:
                link_keys = None
                break
            link_keys.append(key)
        if link_keys:
            grp["linked_default_keys"] = tuple(link_keys)

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

    # limited_per_n → default cross-reference (no weapon array): a capped
    # "…can each replace their sonic blaster with 1 blastmaster" group on a
    # unit with no replace_any array still displaces a Default-group weapon
    # (Noise Marines: 5 sonic blasters + 2 blastmasters is one weapon too
    # many per carrier). choose_from lists the full mutually-exclusive choice
    # set including the default, so recover the displaced key(s) per
    # miniature the group spans. Unlike the replace_one pass's flat leftover,
    # the displaced set must be bundle-aware: an entry's choices often carry
    # common riders in EVERY bundle (Heavy Intercessors: bolt pistol + close
    # combat weapon ride in both the heavy-bolt-rifle bundle and the
    # heavy-weapon bundles), and those are kept, not displaced. Displaced =
    # items of the bundles NOT offering a group item, minus items of the
    # bundles that do. Guards: exactly one overlapping entry, not already
    # claimed by a replace_one group, every displaced item a confirmed
    # Default-group item, and no linked key owned by a weapon array (its
    # settlement would re-derive the decrement away). Genuinely additive
    # extras (a Chaos Icon) displace nothing and stay unlinked.
    # validate_selection's linked-card pass then consumes each displaced
    # weapon per replacement taken -- times its bundle count, carried in
    # ``linked_default_qty`` (Seraphim: "their 2 bolt pistols" is a count-2
    # displaced bundle, so ONE pick consumes BOTH pistols).
    for grp in groups:
        if grp["type"] != "limited_per_n" or grp["linked_default_keys"]:
            continue
        minis = {i["miniature"] for i in grp["items"]}
        names = {i["item"] for i in grp["items"]}
        link_keys, link_qty = [], {}
        for mini in minis:
            matches = [c for c in cfs
                       if (c.get("miniature") == mini or c.get("miniature") is None)
                       and (_flat_items(c.get("choices")) & names)]
            if len(matches) != 1 or id(matches[0]) in entry_owners:
                link_keys = None
                break
            kept, dfl, dfl_qty = set(), set(), {}
            for b in matches[0].get("choices") or []:
                bundle = [i for i in (b if isinstance(b, list) else [])
                          if isinstance(i, dict) and i.get("item")]
                items_b = {i["item"] for i in bundle}
                if items_b & names:
                    kept.update(items_b)
                else:
                    dfl.update(items_b)
                    for i in bundle:
                        q = max(1, _int(i.get("count", 1)))
                        dfl_qty[i["item"]] = max(dfl_qty.get(i["item"], 1), q)
            displaced = dfl - kept - names
            keys = [default_keys[(mini, nm)] for nm in displaced
                    if (mini, nm) in default_keys]
            if not displaced or len(keys) != len(displaced):
                link_keys = None
                break
            link_keys += keys
            for nm in displaced:
                if dfl_qty.get(nm, 1) > 1:
                    link_qty[default_keys[(mini, nm)]] = dfl_qty[nm]
        if link_keys and not (set(link_keys) & array_owned):
            grp["linked_default_keys"] = tuple(link_keys)
            grp["linked_default_qty"] = link_qty

    # ---- multi-item option bundles ---------------------------------------
    # A bullet like "1 plasma pistol and 1 Astartes chainsword" is ONE option
    # granting both weapons; the flat options list models it as two independent
    # items, which double-counts the cap, eats two pool weapons per pick, and
    # makes replace_one radios strip a legally-chosen pair to one weapon.
    # ``option_bundles`` carries the true grouping: {label, keys{key: qty},
    # anchors(keys unique to the bundle, qty 1 -- the pick counters)}.
    # Sources: instruction bullets for limited_per_n / replace_one; the
    # structured all_model choice_sets for all_model. Conservative guards --
    # an ambiguous parse keeps today's flat behaviour.
    for grp in groups:
        if grp["type"] == "limited_per_n" and grp["duplicate_limit"] is None and \
                re.search(r"duplicates are not allowed", grp["instruction"] or "",
                          re.IGNORECASE):
            grp["duplicate_limit"] = 1   # stated in the rule text, absent in the data
        if grp["type"] not in ("limited_per_n", "replace_one", "all_model"):
            continue
        if grp["type"] == "all_model":
            gitems = {i["item"] for i in grp["items"]}
            am = next((a for a in allmodel
                       if (a["miniature"] == grp["miniature"] or a["miniature"] is None)
                       and (gitems & a["items"])), None)
            raw = [list(cs) for cs in (am["choice_sets"] if am else ()) if len(cs) > 1]
            singles = {}
        else:
            raw, singles = _bullet_bundles(grp["instruction"], grp["items"])
        if any(nm in singles for b in raw for nm, _q in b):
            continue   # an item both standalone and bundled -- ambiguous
        by_name = {}
        for it in grp["items"]:
            by_name.setdefault(it["item"], []).append(it)
        # A single-item bullet with a quantity ("2 inferno pistols") is ONE
        # pick granting that many copies. The selection keeps storing picks
        # (caps and pool consumption count picks); ``option_qty`` records the
        # per-pick copy count so the display passes can report carried copies.
        grp["option_qty"] = {by_name[nm][0]["key"]: q for nm, q in singles.items()
                             if q > 1 and nm in by_name and len(by_name[nm]) == 1}
        if not raw:
            continue
        if not all(nm in by_name and len(by_name[nm]) == 1 for b in raw for nm, _q in b):
            continue   # same item on several miniatures in one group
        if any(len({by_name[nm][0]["miniature"] for nm, _q in b}) != 1 for b in raw):
            continue   # a bundle must equip ONE model type
        bundles = []
        for b in raw:
            keys = {by_name[nm][0]["key"]: q for nm, q in b}
            label = " + ".join(("%d× %s" % (q, nm)) if q > 1 else nm for nm, q in b)
            bundles.append({"label": label, "keys": keys})
        usage = {}
        for bd in bundles:
            for k in bd["keys"]:
                usage[k] = usage.get(k, 0) + 1
        key_order = [i["key"] for i in grp["items"]]
        # First anchor = the pick's representative (it alone consumes the
        # displaced pool weapon), so prefer one that is NOT itself a weapon-
        # array member -- an array-owned representative would be skipped by
        # the pool-settlement pass and the pick would consume nothing.
        member_canon = {m["key"] for sp in specs for m in sp["members"]}
        item_of = {i["key"]: i for i in grp["items"]}
        def _is_member(k):
            it = item_of[k]
            return canon.get((it["miniature"], it["item"]), k) in member_canon
        for bd in bundles:
            bd["anchors"] = tuple(sorted(
                (k for k, q in bd["keys"].items() if usage[k] == 1 and q == 1),
                key=lambda k: (_is_member(k), key_order.index(k))))
        if grp["type"] == "limited_per_n" and any(not bd["anchors"] for bd in bundles):
            continue   # cross-product bullets (pistol × melee) -- keep flat UI
        grp["option_bundles"] = tuple(bundles)

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
                pool_keys = {m["key"] for m in s["members"] if m["is_pool"]}
                minis = []
                for mm in (md["miniatures"] if md else []):
                    if mm not in md["per_mini"]:
                        continue
                    pm = md["per_mini"][mm]
                    # ``pool_uses`` = the pool-weapon share of each bundle's
                    # key_counts. The client compares the pool count the raw
                    # ``@b`` picks imply against the settled selection to see
                    # how many models a linked capped card has consumed (the
                    # server decrements the pool weapon during settlement, but
                    # the ``@b`` picks themselves stay on the default bundle).
                    bundles = [{"idx": j, "label": b["label"], "points": b["points"],
                                "pool_uses": {k: c for k, c in b["key_counts"].items()
                                              if k in pool_keys},
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
    (option-key counts, synthetic ``@b|…`` bundle picks, and ``@on|…``
    placement hints -- which model of a miniature carries an additive item)."""
    sel = default_selection(did, squad_size)
    if overrides:
        for k, v in overrides.items():
            if k in sel or k.startswith("@on|"):
                sel[k] = _int(v)
    return sel


def overrides_of(did, squad_size, selection):
    """Sparse diff of a full selection from the default — what we persist. Item
    counts derived from bundle picks are skipped (the ``@b|…`` picks carry them).
    ``@on|…`` placement hints default to 0, so any set hint is an override."""
    default = default_selection(did, squad_size)
    derived = _multi_item_keys(did)
    return {k: _int(v) for k, v in (selection or {}).items()
            if (k.startswith("@on|") and _int(v))
            or (k not in derived and k in default and _int(v) != default[k])}


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


@lru_cache(maxsize=4096)
def _cluster_legal_sets(did):
    """Per ``choose_from`` cluster: ``(miniature, item names, legal states)``,
    where a legal state is a frozenset of (item, count) pairs. The official
    app's semantics: a loadout picks exactly ``limit`` choice bundles; the
    explicit EMPTY bundle may fill any number of slots (an empty slot is not a
    "duplicate weapon"), non-empty bundles repeat only when allow_duplicates.
    Clusters whose items a weapon array manages are excluded -- the array
    passes balance those against the mount count and the cluster ``limit`` is
    not the mount count (see the array notes below). Two self-calibration
    guards keep the gate honest against export quirks: a cluster the pristine
    default loadout itself fails is dropped (its model disagrees with the
    exported defaults -- Tactical Squad's counts, Soul Grinder's omitted
    mandatory pick), and clusters sharing an item name on the same miniature
    are all dropped (unit-wide counts can't be attributed to one of them --
    Gladiator Valiant lists Multi-melta both fixed and optional)."""
    array_items = {(m["miniature"], m["item"])
                   for s in _array_specs(did) for m in s["members"]}
    # Pristine state from the Default-group option rows -- the SAME source the
    # gate counts at runtime, so "a fresh unit never flags" holds by
    # construction (default_loadout is empty for some sheets, e.g. Serberys
    # Sulphurhounds, and can disagree with the option rows).
    ddef = {}
    for o, _k in _keyed_options(did):
        if _is_default_group(o.get("group")) and _int(o.get("default_value")) > 0:
            k = (o.get("miniature"), o.get("item"))
            ddef[k] = ddef.get(k, 0) + _int(o.get("default_value"))
    out = []
    for cf in _wl(did).get("choose_from") or []:
        if cf.get("alternate"):
            continue   # semantics unverified in this data; never guess a warning
        mini = cf.get("miniature")
        bundles, has_empty = [], False
        for b in cf.get("choices") or []:
            c = {}
            for it in b:
                c[it["item"]] = c.get(it["item"], 0) + _int(it.get("count"))
            if c:
                bundles.append(c)
            else:
                has_empty = True
        if not bundles:
            continue
        items = frozenset(nm for c in bundles for nm in c)
        if any((mini, nm) in array_items for nm in items):
            continue
        limit = max(1, _int(cf.get("limit")) or 1)
        pick = combinations_with_replacement if cf.get("allow_duplicates") \
            else combinations
        est = (comb(len(bundles) + limit - 1, limit) if cf.get("allow_duplicates")
               else comb(len(bundles), limit)) * (limit + 1 if has_empty else 1)
        if est > 20000:
            continue   # combinatorial guard; no such cluster in data_version 886
        legal = set()
        for k in ([limit] if not has_empty else range(limit + 1)):
            for combo in pick(range(len(bundles)), k):
                s = {}
                for i in combo:
                    for nm, q in bundles[i].items():
                        s[nm] = s.get(nm, 0) + q
                legal.add(frozenset(s.items()))
        if not legal:
            continue
        dstate = frozenset((nm, ddef[(mini, nm)]) for nm in items
                           if ddef.get((mini, nm), 0) > 0)
        if dstate and dstate not in legal:
            continue
        out.append((mini, items, frozenset(legal)))
    # Same-miniature name overlap: keep only unambiguous clusters.
    usage = {}
    for mini, items, _ in out:
        for nm in items:
            usage[(mini, nm)] = usage.get((mini, nm), 0) + 1
    return tuple((mini, items, legal) for mini, items, legal in out
                 if all(usage[(mini, nm)] == 1 for nm in items))


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
        if k in default or k.startswith("@on|"):
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
    # Keys belonging to a multi-item option bundle: their counts ride with the
    # bundle's pick (set together, priced together) and must never be folded
    # into a weapon array's mount tally -- the bundled chainsword is part of
    # the capped pick, not an extra mount swap.
    bundle_member_keys = {k for g in schema if g.get("option_bundles")
                          for bd in g["option_bundles"] for k in bd["keys"]}
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

    # Two replace_one groups can displace the SAME default (Boyz' Boss Nob:
    # "big choppa → power klaw" and "big choppa and slugga → kombi-weapon...").
    # A group with no active pick restores its linked defaults below -- but it
    # must not resurrect one that a sibling group's active pick displaces.
    # Activeness per group is stable across the loop (healing keeps a group's
    # winning pick), so the set can be computed up front.
    displaced_by_pick = set()
    for grp in schema:
        if grp["type"] == "replace_one" and \
                any(_int(sel.get(i["key"])) > 0 for i in grp["items"]):
            displaced_by_pick.update(grp.get("linked_default_keys") or ())
    claimed_links = set()   # linked keys an already-applied pick displaces
    # Stale-default detection must see the selection as it ARRIVED: a sibling
    # group sharing the link zeroes the default before the picking group's
    # turn, which would hide the auto-correction from the violation report.
    sel_in = dict(sel)

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
            # baseline. Alternatives themselves group into PICK UNITS: a
            # multi-item bundle ("1 lascannon and 1 twin heavy bolter") is one
            # choice whose keys stay active together.
            own_keys = [i["key"] for i in items]
            bundles = grp.get("option_bundles") or ()
            bundled_keys = {k for bd in bundles for k in bd["keys"]}
            units_ = [dict(bd["keys"]) for bd in bundles] \
                + [{k: 1} for k in own_keys if k not in bundled_keys]
            linked = list(grp.get("linked_default_keys") or ())
            active = [u for u in units_ if any(_int(sel.get(k)) > 0 for k in u)]
            default_active = any(_int(sel_in.get(k)) > 0 for k in linked)
            # a fully-active bundle beats a unit that's only active via a key
            # it shares with the winner (partial overlap after a patch)
            active.sort(key=lambda u: -sum(1 for k in u if _int(sel.get(k)) > 0))
            distinct = []
            for u in active:
                act = {k for k in u if _int(sel.get(k)) > 0}
                if not any(act <= set(v) for v in distinct):
                    distinct.append(u)
            if distinct and (set(linked) & claimed_links):
                # A sibling group's pick already consumed one of the defaults
                # this swap replaces (Boss Nob: power klaw and the kombi bundle
                # both take the big choppa) -- first group in schema order
                # wins, this pick is dropped and its uncontested defaults come
                # back.
                flag("%s: default already replaced by another option" % instr)
                for k in own_keys:
                    sel[k] = 0
                for k in linked:
                    if k not in claimed_links:
                        sel[k] = default.get(k, 0)
                        displaced_by_pick.discard(k)  # nothing displaces it now
                continue
            if len(distinct) > 1 or (distinct and default_active):
                flag("%s: choose only one" % instr)
            if distinct:
                chosen = distinct[0]
                for k in own_keys:
                    sel[k] = chosen.get(k, 0)
                for k in linked:
                    sel[k] = 0
                claimed_links.update(linked)
            else:
                for k in own_keys:
                    sel[k] = 0
                for k in linked:
                    sel[k] = 0 if k in displaced_by_pick else default.get(k, 0)
        elif t == "limited_per_n":
            if grp["instruction"] in rel_spec:
                continue  # settled against its weapon array below (cap + pool)
            cap = limited_cap(grp["limits"], squad_size)
            dup = grp["duplicate_limit"]
            clamped = False
            # Pick units in item order: a multi-item bundle ("plasma pistol AND
            # chainsword") is ONE pick counted by its anchor keys; shared
            # partner keys (Boyz' close combat weapon riding with either heavy
            # pick) are derived afterwards, never counted or clamped directly.
            bundles = grp.get("option_bundles") or ()
            bundled_keys = {k for bd in bundles for k in bd["keys"]}
            units_, seen_b = [], set()
            for i in items:
                k = i["key"]
                if k in bundled_keys:
                    bd = next(b for b in bundles if k in b["keys"])
                    if id(bd) not in seen_b and k in bd["anchors"]:
                        seen_b.add(id(bd))
                        units_.append(("bundle", bd))
                else:
                    units_.append(("item", k))
            running = 0
            for kind, ref in units_:
                if kind == "bundle":
                    v = max(_int(sel.get(a)) for a in ref["anchors"])
                else:
                    v = _int(sel.get(ref))
                if dup is not None and v > dup:
                    v = dup
                    clamped = True
                if running + v > cap:
                    v = max(0, cap - running)
                    clamped = True
                if kind == "bundle":
                    for a in ref["anchors"]:
                        sel[a] = v   # anchors move in lockstep (one pick)
                else:
                    sel[ref] = v
                running += v
            # Derive partner keys from the bundle picks they belong to.
            partner = {}
            for bd in bundles:
                n = _int(sel.get(bd["anchors"][0]))
                for k, q in bd["keys"].items():
                    if k not in bd["anchors"]:
                        partner[k] = partner.get(k, 0) + n * q
            for k, v in partner.items():
                if _int(sel.get(k)) > v:
                    clamped = True   # a partner count with no matching pick
                sel[k] = v
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

    # all_model: each unit-wide choice equips every model with exactly one
    # CHOICE -- which may grant several items at once ("hyperphase sword and
    # dispersion shield" is one loadout, both carried). The alternatives live
    # in different option groups, so link them by key.
    item_keys = _item_keys(did)
    for am in _all_model_index(did):
        keys = [k for it in am["items"] for k in item_keys.get((am["miniature"], it), [])]
        if not keys:
            continue
        # {key: qty} per choice; falls back to one single-key choice per item
        # when the structured choice_sets are missing.
        choice_units = []
        for cs in am.get("choice_sets") or ():
            u = {}
            for it, q in cs:
                ks = item_keys.get((am["miniature"], it), [])
                if ks:
                    u[ks[0]] = q
            if u:
                choice_units.append(u)
        if not choice_units:
            choice_units = [{k: 1} for k in keys]
        mc = counts.get(am["miniature"], 0)
        active = [u for u in choice_units
                  if any(_int(sel.get(k)) > 0 and default.get(k, 0) == 0 for k in u)]
        active.sort(key=lambda u: -sum(1 for k in u if _int(sel.get(k)) > 0))
        distinct = []
        for u in active:
            act = {k for k in u if _int(sel.get(k)) > 0}
            if not any(act <= set(v) for v in distinct):
                distinct.append(u)
        if len(distinct) > 1:
            flag("Unit weapon: choose only one")
        chosen = distinct[0] if distinct else next(
            (u for u in choice_units if all(default.get(k, 0) > 0 for k in u)),
            choice_units[0])
        for k in keys:
            sel[k] = mc * chosen[k] if k in chosen else 0

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
            # fold any stray counts onto each item's canonical key (bundle
            # member keys excluded -- their counts belong to a capped pick,
            # not to this array's mounts)
            for m in mems:
                for k in item_keys.get((m["miniature"], m["item"]), []):
                    if k != m["key"] and k not in bundle_member_keys and _int(sel.get(k)):
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
        # Multi-item bundles are ONE pick: only the bundle's representative
        # anchor consumes budget/pool; its partner keys ride along at
        # ``extra × qty`` (the chainsword granted with the plasma pistol is
        # part of the same replacement, not a second one).
        def _resolve(it):
            """(write_key, base, dx, stepper_count, ck) for a card item,
            folding legacy stray keys; None when the array alone owns it."""
            gk = it["key"]
            M = it["miniature"]
            ck = canon.get((M, it["item"]), gk)
            c = ctx.get(M)
            array_owned = c is not None and ck in c["item_keys"]
            if (array_owned or ck in settled_keys) and gk == ck:
                return None  # nothing but the array / an earlier card sets it
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
            return key, base, dx, st, ck

        for grp in relevant:
            cap = limited_cap(grp["limits"], squad_size)
            dup = grp["duplicate_limit"]
            capped = grp["instruction"] in flagged
            short = False
            budget = cap - picks_using(ext_keys_of(grp))
            bundles_g = grp.get("option_bundles") or ()
            rep_of = {bd["anchors"][0]: bd for bd in bundles_g}
            riders = {k for bd in bundles_g for k in bd["keys"]
                      if k != bd["anchors"][0]}
            item_of_g = {i["key"]: i for i in grp["items"]}
            rider_add = {}   # rider key -> Σ extra × qty over its bundles
            for it in grp["items"]:
                gk = it["key"]
                M = it["miniature"]
                if gk in settled_keys or gk in riders:
                    continue  # riders are written once, after all reps below
                r = _resolve(it)
                if r is None:
                    continue
                key, base, dx, st, ck = r
                extra_want = max(0, st - dx)
                extra = min(extra_want, max(0, budget))
                if dup is not None:
                    extra = min(extra, max(0, dup - dx))
                if extra < extra_want:
                    capped = True
                c = ctx.get(M)
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
                bd = rep_of.get(gk)
                if bd:
                    for pk, q in bd["keys"].items():
                        if pk != gk:
                            rider_add[pk] = rider_add.get(pk, 0) + extra * q
            # riders (shared partners like Boyz' close combat weapon) sum the
            # contributions of every bundle that grants them
            for pk, add in rider_add.items():
                it2 = item_of_g[pk]
                r2 = _resolve(it2)
                if r2 is None:
                    # The array owns the rider's (canonical) key outright, so
                    # its derived @b share is already written -- but the card's
                    # replacement grants the rider ON TOP of that share (Krieg
                    # Combat Engineers: the flamer pick's close combat weapon
                    # is also an array bundle member).
                    ck2 = canon.get((it2["miniature"], it2["item"]), pk)
                    c2 = ctx.get(it2["miniature"])
                    if add > 0 and c2 is not None and ck2 in c2["item_keys"]:
                        sel[ck2] = _int(sel.get(ck2)) + add
                    settled_keys.add(pk)
                    continue
                key2, base2, dx2, st2, _ck2 = r2
                if st2 > dx2 + add:
                    capped = True   # a rider count with no matching pick is trimmed
                sel[key2] = base2 + dx2 + add
            if capped:
                flag("%s: max %d at this size" % (clip(grp["instruction"]), cap))
            if short:
                flag("%s: more replacements than weapons to replace"
                     % clip(grp["instruction"], 40))

    # linked limited_per_n cards with no multi-item array to settle against
    # (mounts-mode / single-item specs): every replacement taken on the card
    # still consumes each displaced pool weapon of its own miniature -- times
    # its linked_default_qty when a pick trades several copies (a Seraphim
    # pick eats BOTH bolt pistols) -- trimming the card when the pool runs
    # out. Items the array already balances as members are excluded.
    member_keys = {m["key"] for s in specs for m in s["members"]}
    # Plain Default pool keys (not managed by any weapon array) are re-anchored
    # to their squad-scaled default before consumption: the decrement below
    # persists via overrides, so consuming from the *current* value would eat
    # another pool weapon on every re-validation (5 sonic blasters -> 4 -> 3
    # across edits). Array-managed pools skip this (the array pass just
    # re-derived them from slot counts); keys an active replace_one pick
    # displaced stay displaced.
    for grp in linked_groups:
        if grp["instruction"] in rel_spec:
            continue
        for pk in grp["linked_default_keys"]:
            if pk not in member_keys and pk not in claimed_links:
                sel[pk] = _int(default.get(pk, 0))
    for grp in linked_groups:
        if grp["instruction"] in rel_spec:
            continue
        # A multi-item bundle is ONE pick: only its first anchor consumes a
        # pool weapon; the other member keys ride along (skipped here).
        ride_along = set()
        for bd in (grp.get("option_bundles") or ()):
            rep = bd["anchors"][0]
            ride_along |= {k for k in bd["keys"] if k != rep}
        short = False
        for it in grp["items"]:
            gk = it["key"]
            if gk in ride_along:
                settled_keys.add(gk)
                continue
            ck = canon.get((it["miniature"], it["item"]), gk)
            if gk in member_keys or ck in member_keys or gk in settled_keys:
                continue
            settled_keys.add(gk)
            n = max(0, _int(sel.get(gk)))
            pool = [k for k in grp["linked_default_keys"]
                    if k.split("|", 1)[0] == it["miniature"]]
            if not pool or not n:
                continue
            qty = grp.get("linked_default_qty") or {}
            rows = min(n, min(max(0, _int(sel.get(pk))) // qty.get(pk, 1)
                              for pk in pool))
            for pk in pool:
                sel[pk] = _int(sel.get(pk)) - rows * qty.get(pk, 1)
            if rows < n:
                sel[gk] = rows  # not enough pool weapons left to replace
                bd = next((b for b in (grp.get("option_bundles") or ())
                           if b["anchors"][0] == gk), None)
                if bd:   # a trimmed bundle pick scales its partners with it
                    for k2, q2 in bd["keys"].items():
                        if k2 != gk:
                            sel[k2] = rows * q2
                short = True
        if short:
            flag("%s: more replacements than weapons to replace"
                 % clip(grp["instruction"], 40))

    # Placement hints for items no longer selected are stale -- zero them so
    # they neither persist in the overrides nor steer a future re-add.
    for k in [k for k in sel if k.startswith("@on|")]:
        base = k[4:].rsplit("|", 1)[0]
        if _int(sel.get(base)) <= 0:
            sel[k] = 0

    # Final legality gate against the official app's exhaustive legal option
    # sets (choose_from). The passes above heal group STRUCTURE (exclusivity,
    # caps, pools), but conditional rules ("If this model is equipped with...",
    # "For each X this model is equipped with...") exist only in that combo
    # list, so a structurally-valid selection can still be an illegal loadout.
    # Warn-only: there is no single nearest legal state to auto-correct
    # toward. Single-model contingents only (squad-scaled cluster semantics
    # are not modelled here), and an all-default empty pick is never flagged
    # (a unit whose mandatory choice the exported default loadout omits would
    # otherwise nag from birth). A pick's count multiplies by its option_qty
    # grant ("2 lascannons" is one pick carrying two).
    clusters = _cluster_legal_sets(did)
    if clusters:
        grant = {k: q for g in schema
                 for k, q in (g.get("option_qty") or {}).items()}
        icounts = {}
        for o, key in _keyed_options(did):
            n = _int(sel.get(key)) * grant.get(key, 1)
            if n > 0:
                mi = (o.get("miniature"), o.get("item"))
                icounts[mi] = icounts.get(mi, 0) + n
        for mini, items, legal in clusters:
            if counts.get(mini) != 1:
                continue
            state = frozenset((nm, icounts[(mini, nm)]) for nm in items
                              if icounts.get((mini, nm), 0) > 0)
            if state and state not in legal:
                got = " + ".join(("%d× %s" % (q, nm)) if q > 1 else nm
                                 for nm, q in sorted(state))
                flag("Illegal loadout: %s is not one of this model's legal "
                     "weapon combinations" % clip(got, 90))

    return {"selection": sel,
            "overrides": overrides_of(did, squad_size, sel),
            "violations": violations,
            "points_delta": points_delta(did, squad_size, sel),
            "loadout_summary": resolved_loadout(did, squad_size, sel),
            "loadout_setups": loadout_setups(did, squad_size, sel)}


def _touched_items(did):
    """``{(miniature, item)}`` some option can change: offered by a non-default
    group, displaced via ``linked_default_keys``, or managed by a weapon array.
    Everything else in the Default group is *fixed* -- the model always carries
    it no matter what the user picks."""
    key_item = {key: (o.get("miniature") or "", o.get("item") or "")
                for o, key in _keyed_options(did)}
    touched = set()
    for g in wargear_schema(did):
        if g["type"] == "default":
            continue
        for i in (g.get("items") or []):
            touched.add((i.get("miniature") or "", i.get("item") or ""))
        for k in (g.get("linked_default_keys") or ()):
            if k in key_item:
                touched.add(key_item[k])
    for s in _array_specs(did):
        for m in s["members"]:
            touched.add((m["miniature"] or "", m["item"] or ""))
    return touched


def loadout_setups(did, squad_size, selection):
    """Structured per-model view of a resolved selection for the UI's "Current
    loadout" block: ``{"setups": [{miniature, count, items}, ...],
    "fixed": [{miniature, items}, ...], "kits": {miniature: [{item: qty}, ...]}}``
    -- ``kits`` lists each model's changeable kit by model index, for the
    placement tick-list UI.

    ``setups`` groups a miniature's models by identical *changeable* kit ("5×
    Legionary — Boltgun", "1× Legionary — Plasma gun"), reconstructed by
    seeding every model with its default kit (per-model ``@b`` bundle picks
    where a models-mode array applies), then reconciling against the final
    counts: an item short of its seeded count frees that many models, and the
    surplus items (replacements / additive extras) land on freed models first.
    ``fixed`` holds the items no option can ever change, reported once per
    miniature instead of on every line. A miniature whose attribution can't be
    reconciled cleanly falls back to a single aggregate row."""
    sel = selection or {}
    key_item = {key: (o.get("miniature") or "", o.get("item") or "")
                for o, key in _keyed_options(did)}
    touched = _touched_items(did)
    mcounts = _miniature_counts(did, squad_size)
    default_sel = default_selection(did, squad_size)

    # ``@on|<item key>|<model idx>`` placement hints: the user picked WHICH
    # model of the miniature carries an additive item (a Chaos Icon). They
    # steer attribution below; counts/legality never depend on them.
    hints = {}   # (miniature, item) -> [model indexes]
    for k, v in sel.items():
        if k.startswith("@on|") and _int(v) > 0:
            base, _, idx = k[4:].rpartition("|")
            mi = key_item.get(base)
            if mi and idx.isdigit():
                hints.setdefault(mi, []).append(int(idx))

    # Final + default counts per (miniature, item); stable item order per mini.
    # Minis ordered smallest contingent first (leader before troops, matching
    # the roster row's composition line). A qty pick (``option_qty``) counts
    # its carried copies, not its pick count.
    grant = {k: q for g in wargear_schema(did)
             for k, q in (g.get("option_qty") or {}).items()}
    final, ddef, item_order = {}, {}, {}
    mini_order = sorted(mcounts, key=lambda M: mcounts.get(M, 0))
    for o, key in _keyed_options(did):
        M = o.get("miniature") or ""
        it = o.get("item") or ""
        if M not in mini_order:
            mini_order.append(M)
        rank = item_order.setdefault(M, {})
        if it not in rank:
            rank[it] = len(rank)
        c = _int(sel.get(key, 0)) * grant.get(key, 1)
        if c > 0:
            final.setdefault(M, {})
            final[M][it] = final[M].get(it, 0) + c
        if _is_default_group(o.get("group")):
            d = _int(default_sel.get(key, 0))
            if d > 0:
                ddef.setdefault(M, {})
                ddef[M][it] = ddef[M].get(it, 0) + d

    multi = _multi_meta(did)
    # Items that REPLACE something (their group displaces a default / is a
    # swap) take a freed model during reconciliation; additive extras (a Chaos
    # Icon "can be equipped with") ride on an armed model instead -- otherwise
    # the icon eats the freed slot and a weaponless "Legionary — Chaos Icon"
    # row appears while the flamer lands on the wrong model.
    displacing = set()
    for g in wargear_schema(did):
        if g["type"] in ("default", "array"):
            continue
        if g.get("linked_default_keys") or g["type"] in ("replace_one", "all_model") \
                or re.search(r"replac", g.get("instruction") or "", re.IGNORECASE):
            for i in (g.get("items") or []):
                displacing.add((i.get("miniature") or "", i.get("item") or ""))
    # Multi-item option bundles: a pick grants ALL its items to one model, so
    # place them on the same freed model during reconciliation below.
    bundle_units = {}   # miniature -> [({item: qty}, picks), ...]
    for g in wargear_schema(did):
        for bd in (g.get("option_bundles") or ()):
            ks = bd["keys"]
            M0 = key_item.get(next(iter(ks)), ("", ""))[0]
            if bd.get("anchors"):
                nb = min(_int(sel.get(a)) for a in bd["anchors"])
            else:
                nb = min(_int(sel.get(k)) // q for k, q in ks.items())
            if nb > 0:
                bundle_units.setdefault(M0, []).append(
                    ({key_item[k][1]: q for k, q in ks.items()}, nb))
    # A qty pick (``option_qty``) likewise lands ALL its copies on one model
    # (a Seraphim pick = 2 inferno pistols on that Seraphim).
    for g in wargear_schema(did):
        for k, q in (g.get("option_qty") or {}).items():
            picks = _int(sel.get(k))
            if picks > 0 and k in key_item:
                M0, it0 = key_item[k]
                bundle_units.setdefault(M0, []).append(({it0: q}, picks))
    # Per-pick displaced copies: a pick that trades SEVERAL copies of one
    # default (``linked_default_qty``, Seraphim: both bolt pistols) strips
    # them from the same model during reconciliation below.
    chunk = {}
    for g in wargear_schema(did):
        for pk, q in (g.get("linked_default_qty") or {}).items():
            if q > 1 and pk in key_item:
                chunk[key_item[pk]] = max(chunk.get(key_item[pk], 1), q)
    setups, fixed, all_kits = [], [], {}
    fmt = lambda it, c: ("%d× %s" % (c, it)) if c > 1 else it

    for M in mini_order:
        counts = final.get(M)
        if not counts:
            continue
        n = mcounts.get(M, 0)
        rank = item_order.get(M, {})
        ordered = sorted(counts, key=lambda it: rank.get(it, 999))

        # Split fixed (untouchable, evenly carried) from variable items.
        fx, var = [], {}
        for it in ordered:
            c = counts[it]
            if (M, it) not in touched and n and c % n == 0:
                fx.append(fmt(it, c // n))
            else:
                var[it] = c
        if fx:
            fixed.append({"miniature": M, "items": fx})
        if not var:
            continue
        if n <= 1:
            setups.append({"miniature": M, "count": max(n, 1),
                           "items": [fmt(it, c) for it, c in var.items()]})
            all_kits[M] = [dict(var)]
            continue

        # Seed every model with its default variable kit...
        kits = [dict() for _ in range(n)]
        for it, c in (ddef.get(M) or {}).items():
            if it not in var and counts.get(it, 0) == c and (M, it) not in touched:
                continue  # fixed, already reported
            per, rem = divmod(c, n)
            for i in range(n):
                q = per + (1 if i < rem else 0)
                if q:
                    kits[i][it] = q
        # ...overridden by the model's actual bundle pick where a models-mode
        # array applies (the only genuinely per-model data in a selection).
        for spec_idx, md in multi.items():
            pm = md["per_mini"].get(M)
            if not pm:
                continue
            domain = {key_item[k][1] for k in pm["item_keys"] if k in key_item}
            for i in range(n):
                b = _int(sel.get(_bundle_key(spec_idx, M, i), pm["default_idx"]))
                if not (0 <= b < len(pm["bundles"])):
                    b = pm["default_idx"]
                for it in domain:
                    kits[i].pop(it, None)
                for k, c in pm["bundles"][b]["key_counts"].items():
                    it = key_item.get(k, ("", ""))[1]
                    kits[i][it] = kits[i].get(it, 0) + c

        # Reconcile seeded kits against the final counts: an item seeded above
        # its final count frees that many models; surplus items (replacements,
        # additive extras) land on freed models first, then untouched ones.
        recon = {}
        for kit in kits:
            for it, c in kit.items():
                recon[it] = recon.get(it, 0) + c
        freed, ok = [], True   # kit indices awaiting a replacement item
        for it in ordered:            # removals: seeded > final
            need = recon.get(it, 0) - var.get(it, 0)
            # whole-pick chunks first: a pick trading SEVERAL copies of the
            # same default takes them all off one model; leftovers (a mix of
            # causes) fall through to the per-copy loop below
            cq = chunk.get((M, it), 0)
            while cq > 1 and need >= cq:
                i = next((j for j in sorted(range(n), key=lambda j: j not in freed)
                          if kits[j].get(it, 0) >= cq), None)
                if i is None:
                    break
                kits[i][it] -= cq
                if not kits[i][it]:
                    del kits[i][it]
                if i not in freed:
                    freed.append(i)
                need -= cq
            # prefer already-freed kits: a pick that displaces TWO defaults
            # ("choppa and slugga") strips both from the same model
            for i in sorted(range(n), key=lambda i: i not in freed):
                if need <= 0:
                    break
                if kits[i].get(it, 0) > 0:
                    kits[i][it] -= 1
                    if not kits[i][it]:
                        del kits[i][it]
                    if i not in freed:
                        freed.append(i)
                    need -= 1
            if need > 0:
                ok = False
                break
        if ok:
            need = {it: var.get(it, 0) - recon.get(it, 0) for it in ordered}
            rr = [0]

            def take_slot():
                if freed:
                    return freed.pop(0)
                i = rr[0] % n          # no freed model left: round-robin
                rr[0] += 1
                return i

            # bundle picks first: all of a pick's items land on ONE model
            for bitems, nb in bundle_units.get(M, []):
                place = min([nb] + [need.get(it, 0) // q for it, q in bitems.items()])
                for _ in range(max(0, place)):
                    i = take_slot()
                    for it, q in bitems.items():
                        kits[i][it] = kits[i].get(it, 0) + q
                        need[it] = need.get(it, 0) - q
            # additions: final > seeded. Replacements first (they pair with the
            # models their removals freed), additive extras after (round-robin
            # onto armed models once the freed slots are spent). A placement
            # hint pins an addition to the model the user actually ticked.
            for it in sorted(ordered, key=lambda it: (M, it) not in displacing):
                for i in sorted(hints.get((M, it), [])):
                    if need.get(it, 0) <= 0:
                        break
                    if 0 <= i < n:
                        kits[i][it] = kits[i].get(it, 0) + 1
                        need[it] -= 1
                while need.get(it, 0) > 0:
                    i = take_slot()
                    kits[i][it] = kits[i].get(it, 0) + 1
                    need[it] -= 1
        if not ok:
            # Attribution failed -- one honest aggregate row beats a wrong split.
            setups.append({"miniature": M, "count": n,
                           "items": [fmt(it, c) for it, c in var.items()]})
            continue

        # Per-model kits, indexable by the model index ``@on`` hints use --
        # the UI's placement tick-list is built from these.
        all_kits[M] = [dict(kit) for kit in kits]

        # Group models with identical kits, largest group first.
        grouped, order = {}, []
        for kit in kits:
            sig = tuple(sorted(kit.items()))
            if sig not in grouped:
                grouped[sig] = 0
                order.append(sig)
            grouped[sig] += 1
        for sig in sorted(order, key=lambda s: -grouped[s]):
            setups.append({"miniature": M, "count": grouped[sig],
                           "items": [fmt(it, c) for it, c in
                                     sorted(sig, key=lambda p: rank.get(p[0], 999))]})

    return {"setups": setups, "fixed": fixed, "kits": all_kits}


def resolved_loadout(did, squad_size, selection):
    """Human-readable per-miniature summary of the selected items (count > 0).
    A pick granting several copies (``option_qty``) reports the copies carried,
    not the pick count (2 Seraphim picks = 4 inferno pistols)."""
    selection = selection or {}
    grant = {k: q for g in wargear_schema(did)
             for k, q in (g.get("option_qty") or {}).items()}
    by_mini, order = {}, []
    for o, key in _keyed_options(did):
        count = _int(selection.get(key, 0)) * grant.get(key, 1)
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
