"""Cross-check OUR app's derived points against the ListForge reference dump.

ListForge (io.codeseed.list_forge) is a third-party 40k list builder whose data
is the SAME official app database we already export: its dump reports
`data_version 886`, identical to our `data/w40k/w40k.db`. So this is not an
independent data source. It is an independent *transform* of the same raw source,
which makes it a good check on OUR derivation logic: same input, two
implementations, diff the outputs. Any mismatch is a bug on one side, not a fact
about 40k.

It runs two checks, each reported independently:

Phase 1 - points:
  base points    our unit_detail(did)["costs"]        vs dump unit_composition.points
  step surcharge our unit_detail(did)["points_steps"] vs dump datasheet_points_step

Phase 2 - reachable wargear items (per datasheet):
  our exported wargear_loadout (every "item" it names) vs the official wargear
  graph (base_miniature_loadout + wargear_option_group/wargear_option + the
  loadout / limited / all-model choice sets). Items we surface that the official
  graph never allows are candidate ILLEGAL loadouts; official items we never
  surface are candidate UNREACHABLE loadouts. This is item-set granularity, an
  independent check on our EXPORTER; full pick/limit legality is covered by the
  app's own tests/wargear_reachability.py (see docs/WARGEAR_REACHABILITY_PLAN.md).

Both sides join on the datasheet UUID (multi-miniature units resolve each
miniature back to its datasheet). The dump is camelCase (`datasheetId`,
`stepAt`, `stepPoints`); our export is snake_case.

Usage:
  python scripts/validate_against_listforge.py
  python scripts/validate_against_listforge.py --full        # no list truncation
  python scripts/validate_against_listforge.py --strict      # exit 1 if any mismatch

Reference snapshot: scripts/data/listforge_dump_886.json (git-ignored, ~28 MB).
It is a one-time capture; the tool never touches the network. To refresh it later
(only when the app data version bumps), fetch the presigned URL the public API
hands out, no credentials required:

  curl -s https://list-forge.fly.dev/api/reference/dump40k        # returns {"url": ...}
  curl -o scripts/data/listforge_dump_886.json "<that url>"       # valid ~5 min

Read-only on both sides. Exits 0 (informational) unless a file is unreadable, or
--strict is set and mismatches were found.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_DUMP = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "listforge_dump_886.json")

# Canonical UUID: our datasheet ids. Non-UUID store keys (e.g. the synthetic
# `cat:<id>` datasheet-less entries) have no counterpart in the official dump and
# are counted separately rather than reported as spurious "only ours" misses.
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

LIST_LIMIT = 25  # truncate long lists unless --full


def _int(v):
    """Coerce to int, or None if it is not a whole number. None-safe."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _norm_name(s):
    """Fold a wargear item name for tolerant set comparison: trim, casefold,
    and unify curly apostrophes with straight ones (both sides render the same
    official names, but quote style can drift)."""
    if not s:
        return ""
    return s.strip().casefold().replace("’", "'").replace("‘", "'")


# ---------------------------------------------------------------- printing

_section_open = False


def section(title):
    global _section_open
    print(f"\n== {title} " + "=" * max(0, 60 - len(title)))
    _section_open = False


def item(line):
    global _section_open
    _section_open = True
    print("  " + line)


def listing(label, lines, full):
    lines = list(lines)
    if not lines:
        return
    item(f"{label} ({len(lines)}):")
    shown = lines if full else lines[:LIST_LIMIT]
    for n in shown:
        print(f"      {n}")
    if len(lines) > len(shown):
        print(f"      ... and {len(lines) - len(shown)} more (--full to list all)")


def nothing():
    if not _section_open:
        print("  (no differences)")


# ---------------------------------------------------------------- load sides

def load_dump(path):
    """Return (meta, names, base, steps, items) from the ListForge reference dump.

    names  datasheet UUID -> English name (for labelling)
    base   datasheet UUID -> sorted list of int points per unit_composition tier
    steps  datasheet UUID -> set of (step_at, step_points) tuples
    items  datasheet UUID -> {normalized item name: display name} reachable
    """
    with io.open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    data = d.get("data", {})
    meta = d.get("metadata", {})

    names = {}
    for r in data.get("datasheet", []):
        loc = (r.get("localisations") or {}).get("en") or {}
        names[r["id"]] = loc.get("name") or r["id"]

    base = {}
    for r in data.get("unit_composition", []):
        did = r.get("datasheetId")
        if did is None:
            continue
        pts = _int(r.get("points"))
        if pts is not None:
            base.setdefault(did, []).append(pts)
    for did in base:
        base[did].sort()

    steps = {}
    for r in data.get("datasheet_points_step", []):
        did = r.get("datasheetId")
        if did is None:
            continue
        steps.setdefault(did, set()).add(
            (_int(r.get("stepAt")), _int(r.get("stepPoints"))))

    return meta, names, base, steps, dump_loadout_items(data)


def dump_loadout_items(data):
    """datasheet UUID -> {normalized item name: display name} for every wargear
    item the official graph makes reachable: the base loadout, the option groups,
    and the loadout / limited / all-model choice sets. Rows keyed by miniature
    resolve to their datasheet via the miniature table."""
    item_name = {r["id"]: ((r.get("localisations") or {}).get("en") or {}).get("name")
                 for r in data.get("wargear_item", [])}
    opt_item = {r["id"]: r.get("wargearItemId")
                for r in data.get("wargear_option", [])}
    mini_ds = {r["id"]: r.get("datasheetId") for r in data.get("miniature", [])}

    def did_of(row):
        return row.get("datasheetId") or mini_ds.get(row.get("miniatureId"))

    out = {}

    def add(did, name):
        if did and name:
            out.setdefault(did, {})[_norm_name(name)] = name

    # base loadout: base_miniature_loadout -> *_wargear_option -> option -> item
    bml_did = {r["id"]: did_of(r) for r in data.get("base_miniature_loadout", [])}
    for r in data.get("base_miniature_loadout_wargear_option", []):
        add(bml_did.get(r.get("baseMiniatureLoadoutId")),
            item_name.get(opt_item.get(r.get("wargearOptionId"))))

    # option groups: wargear_option_group -> wargear_option -> item
    grp_did = {r["id"]: did_of(r) for r in data.get("wargear_option_group", [])}
    for r in data.get("wargear_option", []):
        add(grp_did.get(r.get("wargearOptionGroupId")),
            item_name.get(r.get("wargearItemId")))

    # choice sets: <set> -> <choice> -> <choice_wargear_item> -> item
    def choice_source(set_tbl, set_fk, choice_tbl, choice_fk, item_tbl):
        set_did = {r["id"]: did_of(r) for r in data.get(set_tbl, [])}
        choice_did = {r["id"]: set_did.get(r.get(set_fk))
                      for r in data.get(choice_tbl, [])}
        for r in data.get(item_tbl, []):
            add(choice_did.get(r.get(choice_fk)),
                item_name.get(r.get("wargearItemId")))

    choice_source("loadout_choice_set", "loadoutChoiceSetId",
                  "loadout_choice", "loadoutChoiceId",
                  "loadout_choice_wargear_item")
    choice_source("limited_wargear_choice_set", "limitedWargearChoiceSetId",
                  "limited_wargear_choice", "limitedWargearChoiceId",
                  "limited_wargear_choice_wargear_item")
    choice_source("all_model_wargear_choice_set", "allModelWargearChoiceSetId",
                  "all_model_wargear_choice", "allModelWargearChoiceId",
                  "all_model_wargear_choice_wargear_item")
    return out


def load_ours(store):
    """Return (names, base, steps, non_uuid) as our app derives them.

    Keyed by every UUID datasheet in the store; base/steps use the exact shape
    unit_detail() exposes to the SPA, so this checks real app output. non_uuid
    collects any non-UUID store keys (e.g. synthetic cat: entries) that have no
    counterpart in the official dump.
    """
    names, base, steps, non_uuid = {}, {}, {}, []
    for did in store.ds_by_id:
        if not UUID_RE.match(str(did)):
            non_uuid.append(did)
            continue
        det = store.unit_detail(did)
        if not det:
            continue
        names[did] = det.get("name") or did
        base[did] = sorted(
            p for p in (_int(c.get("cost")) for c in det.get("costs", []))
            if p is not None)
        steps[did] = set(
            (_int(s.get("step_at")), _int(s.get("step_points")))
            for s in (det.get("points_steps") or []))
    return names, base, steps, non_uuid


def _walk_items(obj, out):
    """Collect every value stored under an "item" key into out (norm -> display).
    Walks the whole wargear_loadout blob so default_loadout, options and the
    choose_from bundles are all covered."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "item" and isinstance(v, str):
                out[_norm_name(v)] = v
            else:
                _walk_items(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _walk_items(x, out)


def our_loadout_items(store):
    """datasheet UUID -> {normalized item name: display name} our exported
    wargear_loadout makes reachable."""
    out = {}
    for did, blob in getattr(store, "wargear_loadout", {}).items():
        if not UUID_RE.match(str(did)):
            continue
        names = {}
        _walk_items(blob, names)
        out[did] = names
    return out


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Cross-check our derived points against the ListForge dump.")
    ap.add_argument("--dump", default=DEFAULT_DUMP,
                    help="Path to the ListForge reference dump JSON.")
    ap.add_argument("--full", action="store_true",
                    help="List every mismatch (no truncation).")
    ap.add_argument("--strict", action="store_true",
                    help="Exit 1 if any mismatch is found.")
    args = ap.parse_args(argv)

    # Force UTF-8 output: datasheet names carry non-cp1252 characters (e.g.
    # 'Ûthar the Destined') and the default Windows console encoding would crash.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if not os.path.exists(args.dump):
        print(f"ERROR: reference dump not found: {args.dump}", file=sys.stderr)
        print("       See this script's docstring for the one-line refresh command.",
              file=sys.stderr)
        return 2

    try:
        meta, dump_names, dump_base, dump_steps, dump_wg = load_dump(args.dump)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot read dump: {exc}", file=sys.stderr)
        return 2

    import sqlite3
    from data_store import W40K_DB_PATH, get_store
    store = get_store()

    our_names, our_base, our_steps, non_uuid = load_ours(store)
    our_wg = our_loadout_items(store)

    dv_dump = meta.get("data_version", "?")
    dv_ours = "?"
    try:
        con = sqlite3.connect(f"file:{W40K_DB_PATH}?mode=ro&immutable=1", uri=True)
        row = con.execute("SELECT value FROM meta WHERE key='data_version'").fetchone()
        con.close()
        if row:
            dv_ours = row[0]
    except sqlite3.Error:
        pass
    print(f"ours:      data/w40k/w40k.db  (data_version {dv_ours})")
    print(f"reference: {args.dump}  (data_version {dv_dump})")
    print(f"datasheets: ours {len(our_base)} UUID "
          f"({len(non_uuid)} non-UUID skipped) | reference {len(dump_names)}")
    if str(dv_dump) != str(dv_ours):
        print("  NOTE: data versions differ - mismatches below may be version drift,")
        print("        not derivation bugs. Refresh the dump to the same version.")

    our_ids = set(our_base)
    dump_ids = set(dump_names)
    shared = our_ids & dump_ids

    def our_tag(did):
        return f'{our_names.get(did, did)}  [{did[:8]}]'

    def dump_tag(did):
        return f'{dump_names.get(did, did)}  [{did[:8]}]'

    # ---- coverage: datasheets present on only one side ----
    section("datasheet coverage")
    listing("only in our store (UUID, missing from reference)",
            sorted(our_tag(i) for i in our_ids - dump_ids), args.full)
    listing("only in reference (we do not surface these)",
            sorted(dump_tag(i) for i in dump_ids - our_ids), args.full)
    nothing()

    # ---- base points per composition tier ----
    section("base points (per unit_composition tier)")
    base_bad = []
    for did in shared:
        if our_base[did] != dump_base.get(did, []):
            base_bad.append(
                f'{our_tag(did)}  ours={our_base[did]}  ref={dump_base.get(did, [])}')
    listing("base points differ", sorted(base_bad), args.full)
    nothing()

    # ---- per-selection surcharge steps ----
    section("points steps (per-selection surcharge)")
    step_bad = []
    for did in shared:
        if our_steps.get(did, set()) != dump_steps.get(did, set()):
            o = sorted(our_steps.get(did, set()))
            r = sorted(dump_steps.get(did, set()))
            step_bad.append(f'{our_tag(did)}  ours={o}  ref={r}')
    listing("points steps differ", sorted(step_bad), args.full)
    nothing()

    # ---- reachable wargear items ----
    section("wargear reachable items (per datasheet)")
    illegal, missing = [], []  # items we over-offer / official items we drop
    for did in shared:
        o, r = our_wg.get(did, {}), dump_wg.get(did, {})
        extra = sorted(o[k] for k in o.keys() - r.keys())
        absent = sorted(r[k] for k in r.keys() - o.keys())
        if extra:
            illegal.append(f'{our_tag(did)}: {", ".join(extra)}')
        if absent:
            missing.append(f'{our_tag(did)}: {", ".join(absent)}')
    listing("offer items NOT in the official graph (candidate illegal)",
            sorted(illegal), args.full)
    listing("missing official items (candidate unreachable)",
            sorted(missing), args.full)
    nothing()

    # ---- summary ----
    section("summary")
    only_ours = len(our_ids - dump_ids)
    only_dump = len(dump_ids - our_ids)
    item(f"shared datasheets checked: {len(shared)}")
    item(f"coverage gaps:  {only_ours} ours-only, {only_dump} reference-only")
    item(f"base points mismatches:      {len(base_bad)}")
    item(f"points step mismatches:      {len(step_bad)}")
    item(f"wargear over-offer sheets:   {len(illegal)} (candidate illegal)")
    item(f"wargear missing-item sheets: {len(missing)} (candidate unreachable)")
    total = len(base_bad) + len(step_bad) + len(illegal) + len(missing)
    print()

    if args.strict and (total or only_ours or only_dump):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
