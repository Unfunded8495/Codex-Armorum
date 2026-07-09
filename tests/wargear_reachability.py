"""Phase 0 of docs/WARGEAR_REACHABILITY_PLAN.md - the reachability oracle.

Enumerate every UI-reachable wargear selection (at default squad size) for each
auditable datasheet, run each through ``wargear.validate_selection``, and:

  (a) HARD-FAIL if any reachable-but-illegal end state is not flagged with the
      "Illegal loadout" warning. The legality gate must be complete: anything the
      UI lets you build that is not a legal weapon combination has to warn.
  (b) Track the legal-but-unreachable combinations against a shrink-only baseline
      (data/wargear_reachability_baseline.json) - the loadouts the official app
      allows that our UI cannot build. New ones fail; fewer ones pass and should
      be re-blessed with --update-baseline as reachability phases land.

"Auditable" = a datasheet with at least one surviving choose_from cluster
(``wargear._cluster_legal_sets``) whose miniature is a single-model contingent at
default size. That is the only shape where the legality gate can fire (it skips
multi-model contingents) and where the cluster oracle is unambiguous. Every other
datasheet is counted and reported as not-audited, never silently dropped.

UI reachability is replicated from static/js/army-detail.js renderGroupHtml: each
control's posted patch (radio rows incl. keep-default, limited_per_n steppers and
bundle steppers under the cap, checkboxes, additive steppers) is enumerated. Only
the groups whose items touch a cluster are varied - the rest stay at their default
- which bounds the product. Every product element is a real sequence of clicks, so
canonicalising it through validate_selection yields exactly the reachable end
states. Datasheets whose product exceeds ENUM_CAP are recorded as not-audited.

Usage:
  python tests/wargear_reachability.py                    # verify vs baseline
  python tests/wargear_reachability.py --update-baseline  # re-bless the baseline
  python tests/wargear_reachability.py --debug "Ravager"  # dump one datasheet
"""
import itertools
import json
import math
import os
import sys

from _harness import Reporter, store, _safe_print

import army
import wargear

BASELINE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "wargear_reachability_baseline.json")

# Max reachable-state product per datasheet. Above this we record not-audited
# rather than enumerate (kept well above every auditable sheet in data_version
# 886; oversized sheets are reported, not silently skipped).
ENUM_CAP = 6000


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _got(state):
    """Render a frozenset of (item, count) the way the legality gate does, so we
    can confirm a specific illegal combo was the one warned about."""
    return " + ".join(("%d× %s" % (q, nm)) if q > 1 else nm
                      for nm, q in sorted(state))


def _clip(text, n=90):
    """Replica of wargear.validate_selection's inner clip() (word-boundary
    truncation) so we can reconstruct the exact warning message it emits."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(" ,;:")
    return (cut or text[:n]) + "..."


def _illegal_msg(state):
    """The exact "Illegal loadout" message the gate flags for this combo. Matching
    on this (not on loose name containment) is robust to the gate's 90-char clip
    and to multi-cluster sheets where several combos can be flagged at once."""
    return ("Illegal loadout: %s is not one of this model's legal "
            "weapon combinations" % _clip(_got(state), 90))


# ------------------------------------------------------------- reachable patches

def _rival_keys(schema, group):
    """Other replace_one/all_model groups that displace the same default key(s);
    clicking one zeroes the rivals' keys (army-detail.js renderGroupHtml)."""
    linked = set(group.get("linked_default_keys") or ())
    if not linked:
        return []
    out = []
    for o in schema:
        if o is group:
            continue
        if (o.get("type") in ("replace_one", "all_model")
                and set(o.get("linked_default_keys") or ()) & linked):
            out.extend(i["key"] for i in o.get("items", []))
    return out


def _radio_patches(schema, group, comp, size):
    """One patch per radio row: keep-default, each bundle, each single item. Each
    zeroes the group's own keys + linked defaults + rival keys before setting its
    own, mirroring setWargearRadio."""
    def per_model(key):
        if group.get("type") != "all_model":
            return 1
        it = next((i for i in group["items"] if i["key"] == key), None)
        return comp.get(it.get("miniature"), size) if it else size

    keys = ([i["key"] for i in group["items"]]
            + list(group.get("linked_default_keys") or ())
            + _rival_keys(schema, group))
    zero = {k: 0 for k in keys}
    bundles = group.get("option_bundles") or ()
    bkeys = {k for b in bundles for k in b["keys"]}

    # keep-default = the user leaves this group untouched, so NO patch is posted
    # (an empty dict). Only an active radio click zeroes the group's keys/linked/
    # rivals and then sets its own (setWargearRadio). Posting zeros for an
    # untouched group would wrongly wipe unrelated defaults it shares no link with.
    patches = [{}]
    for b in bundles:
        patches.append(dict(zero, **{k: q * per_model(k)
                                     for k, q in b["keys"].items()}))
    for i in group["items"]:
        if i["key"] not in bkeys:
            patches.append(dict(zero, **{i["key"]: per_model(i["key"])}))
    return patches


def _limited_patches(group, size):
    """Joint stepper states for a limited_per_n group: each pick unit (bundle via
    its anchor, or a plain item) runs 0..maxPer with the total <= cap."""
    cap = wargear.limited_cap(group.get("limits") or [], size)
    if cap <= 0:
        return [{}]
    dup = group.get("duplicate_limit")
    max_per = min(cap, dup) if dup is not None else cap
    bundles = group.get("option_bundles") or ()
    bkeys = {k for b in bundles for k in b["keys"]}
    slots = [("bundle", b["anchors"][0]) for b in bundles if b.get("anchors")]
    slots += [("item", i["key"]) for i in group["items"] if i["key"] not in bkeys]

    patches = []

    def rec(idx, remaining, acc):
        if idx == len(slots):
            patches.append(dict(acc))
            return
        _, key = slots[idx]
        for n in range(0, min(max_per, remaining) + 1):
            if n:
                acc[key] = n
            rec(idx + 1, remaining - n, acc)
            if n:
                del acc[key]

    rec(0, cap, {})
    return patches


def _choice_patches(group, comp, size):
    """Joint states for a plain choice group: checkbox items 0/1, additive
    steppers 0..model-count."""
    ranges = []
    for i in group["items"]:
        if i.get("input_type") == "checkbox":
            ranges.append((i["key"], (0, 1)))
        else:
            mc = comp.get(i.get("miniature"), size)
            ranges.append((i["key"], tuple(range(0, mc + 1))))
    patches = [{}]
    for key, vals in ranges:
        patches = [dict(p, **({key: v} if v else {}))
                   for p in patches for v in vals]
    return patches


def _touches(group, items_by_mini):
    """True if any of the group's items is a cluster item on its miniature."""
    for i in group.get("items", []):
        if i.get("item") in items_by_mini.get(i.get("miniature"), ()):
            return True
    return False


# ------------------------------------------------------------- per-datasheet audit

def _combo(sel, mini, items, grant, keyed):
    """Item-count state for one cluster miniature from a resolved selection,
    exactly as the legality gate computes it (counts x option_qty grant)."""
    icounts = {}
    for o, key in keyed:
        if o.get("miniature") != mini or o.get("item") not in items:
            continue
        n = _int(sel.get(key)) * grant.get(key, 1)
        if n > 0:
            icounts[o["item"]] = icounts.get(o["item"], 0) + n
    return frozenset(icounts.items())


def audit_datasheet(did):
    """Return a dict describing one datasheet's reachability, or {'skip': reason}.

    On success: {'name', 'clusters': [{'mini','unreachable':[got,...],
    'illegal_unwarned':[got,...]}], 'audited': True}.
    """
    name = store().ds_by_id.get(did, {}).get("name", did)
    clusters = wargear._cluster_legal_sets(did)
    if not clusters:
        return {"skip": "no cluster"}

    size = army._squad_bounds(did)["default"]
    comp = wargear._miniature_counts(did, size)
    schema = wargear.wargear_schema(did)
    keyed = wargear._keyed_options(did)
    grant = {k: q for g in schema
             for k, q in (g.get("option_qty") or {}).items()}

    # Which cluster miniatures are single-model (the auditable ones).
    single = [(mini, items, legal) for mini, items, legal in clusters
              if comp.get(mini) == 1]
    if not single:
        return {"skip": "clusters are multi-model only"}

    items_by_mini = {}
    for mini, items, _ in single:
        items_by_mini.setdefault(mini, set()).update(items)

    # Groups that can change a cluster's item counts; everything else stays default.
    relevant = [g for g in schema
                if g.get("type") != "default" and _touches(g, items_by_mini)]
    for g in relevant:
        if g.get("type") == "array":
            return {"skip": "array-managed cluster group"}

    patch_lists = []
    for g in relevant:
        t = g.get("type")
        if t in ("replace_one", "all_model"):
            patch_lists.append(_radio_patches(schema, g, comp, size))
        elif t == "limited_per_n":
            patch_lists.append(_limited_patches(g, size))
        else:
            patch_lists.append(_choice_patches(g, comp, size))

    product = math.prod(len(pl) for pl in patch_lists) if patch_lists else 1
    if product > ENUM_CAP:
        return {"skip": "state product %d > cap %d" % (product, ENUM_CAP)}

    reached = [set() for _ in single]
    unwarned = [set() for _ in single]

    for combo_patches in itertools.product(*patch_lists) if patch_lists else [()]:
        merged = {}
        for p in combo_patches:
            merged.update(p)
        res = wargear.validate_selection(did, size, merged)
        sel = res["selection"]
        messages = {v["message"] for v in res["violations"]}
        for idx, (mini, items, legal) in enumerate(single):
            state = _combo(sel, mini, items, grant, keyed)
            if not state:
                continue
            reached[idx].add(state)
            # (a): an illegal reachable state must carry the gate's exact
            # "Illegal loadout" warning for this specific combo.
            if state not in legal and _illegal_msg(state) not in messages:
                unwarned[idx].add(state)

    out_clusters = []
    for idx, (mini, items, legal) in enumerate(single):
        # Empty state is always reachable and never flagged; exclude it.
        unreachable = [s for s in legal if s and s not in reached[idx]]
        out_clusters.append({
            "mini": mini,
            "unreachable": sorted(_got(s) for s in unreachable),
            "illegal_unwarned": sorted(_got(s) for s in unwarned[idx]),
        })
    return {"name": name, "clusters": out_clusters, "audited": True}


# ------------------------------------------------------------- baseline i/o

def _load_baseline():
    try:
        with open(BASELINE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_baseline(payload):
    tmp = BASELINE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, BASELINE_PATH)


def _unreachable_set(datasheets):
    """Flatten to a set of 'did::got' keys for shrink-only comparison."""
    out = set()
    for did, rec in datasheets.items():
        for got in rec.get("unreachable", []):
            out.add(f"{did}::{got}")
    return out


# ------------------------------------------------------------- run

def _collect():
    s = store()
    datasheets, not_audited, illegal_unwarned = {}, {}, []
    audited = 0
    for did in list(s.ds_by_id.keys()):
        try:
            res = audit_datasheet(did)
        except Exception as exc:  # a broken sheet should surface, not abort the run
            not_audited[did] = "error: %r" % (exc,)
            continue
        if "skip" in res:
            # Only record sheets that had clusters but were not auditable; a
            # plain "no cluster" sheet is not in scope and not worth listing.
            if res["skip"] != "no cluster":
                not_audited[did] = res["skip"]
            continue
        audited += 1
        unreachable = sorted(
            g for c in res["clusters"] for g in c["unreachable"])
        if unreachable:
            datasheets[did] = {"name": res["name"], "unreachable": unreachable}
        for c in res["clusters"]:
            for got in c["illegal_unwarned"]:
                illegal_unwarned.append("%s: %s" % (res["name"], got))
    return audited, datasheets, not_audited, illegal_unwarned


def run(update_baseline=False):
    r = Reporter("wargear reachability")
    audited, datasheets, not_audited, illegal_unwarned = _collect()

    print("  audited %d single-model cluster datasheets; "
          "%d not audited; %d have unreachable legal loadouts"
          % (audited, len(not_audited), len(datasheets)))

    if update_baseline:
        payload = {
            "note": ("Legal-but-unreachable wargear loadouts per datasheet at "
                     "default squad size. Shrink-only: run --update-baseline "
                     "after a reachability phase lands. See "
                     "docs/WARGEAR_REACHABILITY_PLAN.md."),
            "audited_count": audited,
            "datasheets": dict(sorted(datasheets.items())),
        }
        _write_baseline(payload)
        total = sum(len(v["unreachable"]) for v in datasheets.values())
        print("  wrote baseline -> %s (%d sheets, %d unreachable loadouts)"
              % (BASELINE_PATH, len(datasheets), total))
        return 0

    # (a) HARD-FAIL invariant: no reachable-illegal end state may go unwarned.
    r.check("no unwarned reachable-illegal loadout on any auditable datasheet",
            not illegal_unwarned,
            "%d unwarned e.g. %s" % (len(illegal_unwarned), illegal_unwarned[:3]))

    # (b) shrink-only baseline of legal-but-unreachable loadouts.
    baseline = _load_baseline()
    if baseline is None:
        r.skip("legal-but-unreachable vs baseline",
               "no baseline yet; run --update-baseline")
    else:
        current = _unreachable_set(datasheets)
        base = _unreachable_set(baseline.get("datasheets", {}))
        regressions = sorted(current - base)
        fixed = base - current
        r.check("no NEW legal-but-unreachable loadouts vs baseline",
                not regressions,
                "%d new e.g. %s" % (len(regressions), regressions[:3]))
        if fixed:
            r.skip("baseline improved",
                   "%d loadouts now reachable; re-bless with --update-baseline"
                   % len(fixed))

    return r.summary()


def _debug(term):
    idx = {v["name"]: k for k, v in store().ds_by_id.items()}
    did = idx.get(term) or (term if term in store().ds_by_id else None)
    if not did:
        matches = [n for n in idx if term.lower() in n.lower()]
        if len(matches) == 1:
            did = idx[matches[0]]
        else:
            print("no unique datasheet for %r; candidates: %s"
                  % (term, matches[:10]))
            return 1
    res = audit_datasheet(did)
    _safe_print("%s  [%s]" % (store().ds_by_id[did]["name"], did))
    _safe_print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if "--debug" in sys.argv:
        i = sys.argv.index("--debug")
        sys.exit(_debug(sys.argv[i + 1]))
    sys.exit(run(update_baseline="--update-baseline" in sys.argv))
