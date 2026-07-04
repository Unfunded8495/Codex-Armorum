"""Compare two w40k.db exports: what changed between app data versions.

The decision-support half of the data-update runbook
(CODEX_ARMORUM_DATA_UPDATE.md). Point it at the current db and a freshly
exported staging db *before* swapping the new file in, and it answers "what
did this update actually change?":

  python scripts/compare_w40k_db.py data/w40k/w40k.db <staging>/w40k.db
  python scripts/compare_w40k_db.py OLD NEW --full        # no list truncation

Reports, in order:

  meta            data_version bump
  schema          tables and columns added/removed (FTS internals ignored)
  row counts      per-table deltas
  factions        added / removed / renamed
  datasheets      added / removed / renamed / points changed / Legends flips
                  / rules-content changed (models, weapons, abilities,
                  wargear loadout, leader data - hashed per datasheet)
  detachments     added / removed / DP cost changed
  enhancements    added / removed / points changed
  stratagems      added / removed / CP changed
  battle sizes    any limit change
  keywords        keyword + wargear-ability names added/removed; changed
                  wargear-ability rules text (=> sync static/weapon_keywords.json)
  core rules      sections added/removed, sections whose block text changed,
                  FAQ count (=> data/rules/ source markdown may need a refresh)

Purely informational: read-only on both files, always exits 0 unless a file
is unreadable. Tolerates schema drift - a table or column missing on either
side is reported under `schema` and skipped in the content diff, so an old
pre-enforcement db compares cleanly against a current export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys

LIST_LIMIT = 20  # truncate long lists unless --full

# sqlite housekeeping + FTS shadow tables: never content-diffed
def _is_internal(name: str) -> bool:
    return name == "sqlite_sequence" or "_fts" in name


def connect_ro(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    return con


def tables(con) -> set[str]:
    return {r["name"] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'") if not _is_internal(r["name"])}


def columns(con, table: str) -> list[str]:
    return [r["name"] for r in con.execute(f"PRAGMA table_info('{table}')")]


def count(con, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]


def norm_json(text):
    """Canonicalise a JSON text column so formatting differences don't diff."""
    if text is None:
        return None
    try:
        return json.dumps(json.loads(text), sort_keys=True)
    except (TypeError, ValueError):
        return text


def rows_map(con, table: str, cols: list[str], key="id") -> dict:
    sel = ", ".join(f'"{c}"' for c in cols)
    return {r[key]: r for r in con.execute(f'SELECT "{key}", {sel} FROM "{table}"')}


# ---------------------------------------------------------------- printing

_section_open = False


def section(title: str):
    global _section_open
    print(f"\n== {title} " + "=" * max(0, 60 - len(title)))
    _section_open = False


def item(line: str):
    global _section_open
    _section_open = True
    print("  " + line)


def listing(label: str, names, full: bool):
    names = sorted(names)
    if not names:
        return
    item(f"{label} ({len(names)}):")
    shown = names if full else names[:LIST_LIMIT]
    for n in shown:
        print(f"      {n}")
    if len(names) > len(shown):
        print(f"      ... and {len(names) - len(shown)} more (--full to list all)")


def nothing():
    if not _section_open:
        print("  (no differences)")


# ---------------------------------------------------------------- helpers

def meta_version(con) -> str:
    try:
        r = con.execute("SELECT value FROM meta WHERE key='data_version'").fetchone()
        return r[0] if r else "?"
    except sqlite3.OperationalError:
        return "?"


def faction_names(con) -> dict:
    """datasheet_id -> first faction display name, for labelling datasheets."""
    out = {}
    try:
        q = """SELECT df.datasheet_id AS did,
                      COALESCE(f.display_name, f.name) AS fname
               FROM datasheet_faction df JOIN faction f ON f.id = df.faction_id
               ORDER BY fname"""
        for r in con.execute(q):
            out.setdefault(r["did"], r["fname"])
    except sqlite3.OperationalError:
        pass
    return out


def child_hashes(con, table: str, cols: list[str], parent_col: str) -> dict:
    """parent_id -> stable hash of all child rows (order-independent)."""
    out: dict[str, list] = {}
    sel = ", ".join(f'"{c}"' for c in cols)
    for r in con.execute(f'SELECT "{parent_col}", {sel} FROM "{table}"'):
        blob = "\x1f".join("" if r[c] is None else str(r[c]) for c in cols)
        out.setdefault(r[parent_col], []).append(blob)
    return {k: hashlib.md5("\x1e".join(sorted(v)).encode()).hexdigest()
            for k, v in out.items()}


def weapon_hashes(con, wcols, pcols) -> dict:
    """datasheet_id -> hash over weapons + their profiles."""
    profs: dict[str, list] = {}
    psel = ", ".join(f'"{c}"' for c in pcols)
    for r in con.execute(f'SELECT weapon_id, {psel} FROM weapon_profile'):
        profs.setdefault(r["weapon_id"], []).append(
            "\x1f".join("" if r[c] is None else str(r[c]) for c in pcols))
    out: dict[str, list] = {}
    wsel = ", ".join(f'"{c}"' for c in wcols)
    for r in con.execute(f'SELECT id, datasheet_id, {wsel} FROM weapon'):
        blob = "\x1f".join("" if r[c] is None else str(r[c]) for c in wcols)
        blob += "\x1d" + "\x1e".join(sorted(profs.get(r["id"], [])))
        out.setdefault(r["datasheet_id"], []).append(blob)
    return {k: hashlib.md5("\x1e".join(sorted(v)).encode()).hexdigest()
            for k, v in out.items()}


# ---------------------------------------------------------------- sections

def diff_schema(old, new, full):
    section("schema")
    t_old, t_new = tables(old), tables(new)
    listing("tables added", t_new - t_old, full)
    listing("tables removed", t_old - t_new, full)
    shared = sorted(t_old & t_new)
    for t in shared:
        c_old, c_new = set(columns(old, t)), set(columns(new, t))
        for c in sorted(c_new - c_old):
            item(f"column added:   {t}.{c}")
        for c in sorted(c_old - c_new):
            item(f"column removed: {t}.{c}")
    nothing()
    return shared


def diff_counts(old, new, shared, full):
    section("row counts")
    changed = []
    for t in shared:
        a, b = count(old, t), count(new, t)
        if a != b:
            changed.append(f"{t}: {a} -> {b} ({b - a:+d})")
    for line in (changed if full else changed[:LIST_LIMIT]):
        item(line)
    if not full and len(changed) > LIST_LIMIT:
        item(f"... and {len(changed) - LIST_LIMIT} more (--full)")
    nothing()


def diff_named(old, new, shared, table, label, extra_cols, full,
               fmt=lambda r: r["name"]):
    """Generic id-keyed diff: added / removed / renamed / listed field changes."""
    section(label)
    if table not in shared:
        item(f"table '{table}' not present in both files - skipped")
        return {}, {}
    cols = ["name"] + [c for c in extra_cols
                       if c in columns(old, table) and c in columns(new, table)]
    o, n = rows_map(old, table, cols), rows_map(new, table, cols)
    listing("added", [fmt(n[i]) for i in n.keys() - o.keys()], full)
    listing("removed", [fmt(o[i]) for i in o.keys() - n.keys()], full)
    renamed = [f'{o[i]["name"]} -> {n[i]["name"]}'
               for i in o.keys() & n.keys() if o[i]["name"] != n[i]["name"]]
    listing("renamed", renamed, full)
    return o, n


def diff_datasheets(old, new, shared, full):
    ds_facs_new = faction_names(new)
    ds_facs_old = faction_names(old)

    def tag(row, facs):
        return f'{row["name"]}  [{facs.get(row["id"], "?")}]'

    points_cols = ["points", "points_steps", "default_points"]
    content_cols = [c for c in (
        "unit_composition_text", "keywords", "conditional_keywords",
        "wargear_loadout", "leads_units", "can_be_led_by", "damage_brackets",
        "leader_groups", "base_size", "max_model_count", "is_legends")
        if c in columns(old, "datasheet") and c in columns(new, "datasheet")]
    o, n = rows_map(old, "datasheet", ["name"] + points_cols + content_cols,), \
           rows_map(new, "datasheet", ["name"] + points_cols + content_cols,)

    section("datasheets")
    listing("added", [tag(n[i], ds_facs_new) for i in n.keys() - o.keys()], full)
    listing("removed", [tag(o[i], ds_facs_old) for i in o.keys() - n.keys()], full)
    both = o.keys() & n.keys()
    listing("renamed", [f'{o[i]["name"]} -> {n[i]["name"]}'
                        for i in both if o[i]["name"] != n[i]["name"]], full)

    pts, legends = [], []
    for i in both:
        a, b = o[i], n[i]
        if any(norm_json(a[c]) != norm_json(b[c]) for c in points_cols):
            da, db = a["default_points"], b["default_points"]
            detail = f"{da} -> {db} pts" if da != db else "points tiers changed"
            pts.append(f'{tag(b, ds_facs_new)}  {detail}')
        if "is_legends" in content_cols and a["is_legends"] != b["is_legends"]:
            legends.append(f'{tag(b, ds_facs_new)}  legends: '
                           f'{a["is_legends"]} -> {b["is_legends"]}')
    listing("points changed", pts, full)
    listing("Legends flag changed", legends, full)

    # content hash: datasheet scalar fields + child tables
    def content_map(con, rows):
        child_specs = [("model", "datasheet_id"), ("ability", "datasheet_id"),
                       ("extra_rule", "datasheet_id")]
        hashes = {}
        for t, pc in child_specs:
            if t in tables(con):
                cc = [c for c in columns(con, t) if c not in ("id", pc)]
                hashes[t] = child_hashes(con, t, cc, pc)
        wh = {}
        if "weapon" in tables(con) and "weapon_profile" in tables(con):
            wcols = [c for c in columns(con, "weapon") if c not in ("id", "datasheet_id")]
            pcols = [c for c in columns(con, "weapon_profile") if c not in ("id", "weapon_id")]
            wh = weapon_hashes(con, wcols, pcols)
        out = {}
        for i, r in rows.items():
            scal = "\x1f".join(str(norm_json(r[c])) for c in content_cols
                               if c != "is_legends")
            kids = "\x1f".join(hashes.get(t, {}).get(i, "") for t, _ in child_specs)
            out[i] = hashlib.md5(f"{scal}\x1d{kids}\x1d{wh.get(i, '')}".encode()).hexdigest()
        return out

    co, cn = content_map(old, o), content_map(new, n)
    changed = [tag(n[i], ds_facs_new) for i in both if co.get(i) != cn.get(i)]
    listing("rules content changed (stats/weapons/abilities/wargear/leaders)",
            changed, full)
    nothing()


def diff_battle_sizes(old, new, shared):
    section("battle sizes")
    if "battle_size" not in shared:
        item("table 'battle_size' not present in both files - skipped")
        return
    cols = [c for c in columns(new, "battle_size") if c != "name"]
    o = rows_map(old, "battle_size", cols, key="name")
    n = rows_map(new, "battle_size", cols, key="name")
    for name in sorted(o.keys() | n.keys()):
        if name not in o:
            item(f"added: {name}")
        elif name not in n:
            item(f"removed: {name}")
        else:
            for c in cols:
                if o[name][c] != n[name][c]:
                    item(f"{name}.{c}: {o[name][c]} -> {n[name][c]}")
    nothing()


def diff_keywords(old, new, shared, full):
    section("keywords & weapon abilities")
    if "keyword" in shared:
        o = {r["name"] for r in old.execute("SELECT name FROM keyword")}
        n = {r["name"] for r in new.execute("SELECT name FROM keyword")}
        listing("keywords added", n - o, full)
        listing("keywords removed", o - n, full)
    if "wargear_ability" in shared:
        o = rows_map(old, "wargear_ability", ["rules"], key="name")
        n = rows_map(new, "wargear_ability", ["rules"], key="name")
        listing("weapon abilities added", n.keys() - o.keys(), full)
        listing("weapon abilities removed", o.keys() - n.keys(), full)
        changed = [k for k in o.keys() & n.keys() if o[k]["rules"] != n[k]["rules"]]
        listing("weapon-ability rules text changed", changed, full)
        if (n.keys() - o.keys()) or changed:
            item(">> sync static/weapon_keywords.json (tooltip glossary) with these")
    nothing()


def diff_core_rules(old, new, shared, full):
    section("core rules & FAQs")
    if "rule_section" in shared and "rule_block" in shared:
        o = rows_map(old, "rule_section", ["title"])
        n = rows_map(new, "rule_section", ["title"])
        listing("sections added", [n[i]["title"] for i in n.keys() - o.keys()], full)
        listing("sections removed", [o[i]["title"] for i in o.keys() - n.keys()], full)
        bcols = [c for c in ("type", "title", "content_text", "image_url")
                 if c in columns(old, "rule_block") and c in columns(new, "rule_block")]
        ho = child_hashes(old, "rule_block", bcols, "section_id")
        hn = child_hashes(new, "rule_block", bcols, "section_id")
        changed = [n[i]["title"] for i in o.keys() & n.keys()
                   if ho.get(i) != hn.get(i)]
        listing("sections whose text changed", changed, full)
        if changed:
            item(">> the /rules page source (data/rules/wh40k_core_rules_combined.md)")
            item("   is hand-merged from this text - review + scripts/build_rules.py")
    if "faq" in shared:
        a, b = count(old, "faq"), count(new, "faq")
        if a != b:
            item(f"FAQ entries: {a} -> {b} ({b - a:+d})")
    nothing()


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Diff two w40k.db exports (old vs new app data version).")
    ap.add_argument("old", help="Current / previous w40k.db")
    ap.add_argument("new", help="Freshly exported w40k.db (staging)")
    ap.add_argument("--full", action="store_true",
                    help="List every changed record (no truncation)")
    args = ap.parse_args(argv)

    try:
        old, new = connect_ro(args.old), connect_ro(args.new)
        tables(old), tables(new)  # force open errors early
    except sqlite3.Error as exc:
        print(f"ERROR: cannot open database: {exc}", file=sys.stderr)
        return 1

    print(f"old: {args.old}  (data_version {meta_version(old)})")
    print(f"new: {args.new}  (data_version {meta_version(new)})")

    shared = diff_schema(old, new, args.full)
    diff_counts(old, new, shared, args.full)
    diff_named(old, new, shared, "faction", "factions", [], args.full)
    nothing()
    diff_datasheets(old, new, shared, args.full)

    do, dn = diff_named(old, new, shared, "detachment", "detachments",
                        ["detachment_points_cost"], args.full)
    dp = [f'{dn[i]["name"]}: {do[i]["detachment_points_cost"]} -> '
          f'{dn[i]["detachment_points_cost"]} DP'
          for i in do.keys() & dn.keys()
          if "detachment_points_cost" in do[i].keys()
          and do[i]["detachment_points_cost"] != dn[i]["detachment_points_cost"]]
    listing("DP cost changed", dp, args.full)
    nothing()

    eo, en = diff_named(old, new, shared, "enhancement", "enhancements",
                        ["points"], args.full)
    ep = [f'{en[i]["name"]}: {eo[i]["points"]} -> {en[i]["points"]} pts'
          for i in eo.keys() & en.keys()
          if "points" in eo[i].keys() and eo[i]["points"] != en[i]["points"]]
    listing("points changed", ep, args.full)
    nothing()

    so, sn = diff_named(old, new, shared, "stratagem", "stratagems",
                        ["cp_cost"], args.full)
    sp = [f'{sn[i]["name"]}: {so[i]["cp_cost"]} -> {sn[i]["cp_cost"]} CP'
          for i in so.keys() & sn.keys()
          if "cp_cost" in so[i].keys() and so[i]["cp_cost"] != sn[i]["cp_cost"]]
    listing("CP cost changed", sp, args.full)
    nothing()

    diff_battle_sizes(old, new, shared)
    diff_keywords(old, new, shared, args.full)
    diff_core_rules(old, new, shared, args.full)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
