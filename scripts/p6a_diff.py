import sys, sqlite3, hashlib

OLD = sys.argv[1] if len(sys.argv) > 1 else "/tmp/w40k.pre6a.db"
NEW = sys.argv[2] if len(sys.argv) > 2 else "data/w40k/w40k.db"

NEW_TABLES = {"mission_pack", "mission_deployment", "mission_layout",
              "mission_preset", "mission_twist"}
NEW_TABLE_COUNTS = {"mission_pack": 2, "mission_deployment": 9, "mission_layout": 46,
                    "mission_preset": 48, "mission_twist": 6}
WIDENED = {"mission_primary", "mission_secondary"}
WIDENED_ADDED = {"id", "mission_pack_id"}

def conn(p):
    c = sqlite3.connect(p); c.row_factory = sqlite3.Row; return c

old, new = conn(OLD), conn(NEW)
fail = 0
def check(label, cond):
    global fail
    print(f"{'ok ' if cond else 'XX '} {label}")
    fail += 0 if cond else 1

def tables(c):
    return {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
def create_sql(c, t):
    r = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
    return (r["sql"] or "") if r else ""
def cols(c, t):
    return [r["name"] for r in c.execute(f"PRAGMA table_info('{t}')")]
def count(c, t):
    return c.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
def content_hash(c, t):
    rows = c.execute(f"SELECT * FROM '{t}'").fetchall()
    ser = sorted("\x1f".join("" if v is None else str(v) for v in tuple(r)) for r in rows)
    return hashlib.md5("\x1e".join(ser).encode()).hexdigest()
def is_fts_virtual(c, t):
    return "fts5" in create_sql(c, t).lower()

old_t, new_t = tables(old), tables(new)
fts_virtual = {t for t in old_t if is_fts_virtual(old, t)}

# table-set: nothing removed, exactly the 5 new tables added
check("no pre-existing table removed", not (old_t - new_t))
check(f"exactly the 5 new mission tables added (got {sorted(new_t - old_t)})",
      (new_t - old_t) == NEW_TABLES)

# per pre-existing table
for t in sorted(old_t):
    if "fts" in t.lower() and t not in fts_virtual:
        continue  # FTS shadow table: internal, covered via the virtual table
    if t in fts_virtual:
        check(f"{t}: FTS schema + logical content identical",
              create_sql(old, t) == create_sql(new, t) and content_hash(old, t) == content_hash(new, t))
        continue
    if t == "stratagem":
        o = {r["id"]: tuple(r) for r in old.execute("SELECT * FROM stratagem")}
        n = {r["id"]: tuple(r) for r in new.execute("SELECT * FROM stratagem")}
        check("stratagem: schema identical", create_sql(old, t) == create_sql(new, t))
        check(f"stratagem: old has 1421 rows at ids 1-1421 (got {len(o)})",
              set(o) == set(range(1, 1422)))
        extra = sorted(set(n) - set(o))
        check(f"stratagem: exactly 11 core appended at ids 1422-1432 (got {extra})",
              extra == list(range(1422, 1433)))
        check("stratagem: existing 1421 rows unchanged by content",
              all(n.get(i) == o[i] for i in o))
        di = cols(new, "stratagem").index("detachment_id")
        new_rows = {r["id"]: r for r in new.execute("SELECT * FROM stratagem")}
        check("stratagem: the 11 core rows have detachment_id NULL",
              all(new_rows[i]["detachment_id"] is None for i in extra))
        continue
    if t == "sqlite_sequence":
        # The only expected change: the stratagem AUTOINCREMENT counter advances
        # 1421 -> 1432 because the 11 core rows were appended (this is exactly what
        # makes their ids 1422-1432). Every other counter must be unchanged.
        so = {r["name"]: r["seq"] for r in old.execute("SELECT name, seq FROM sqlite_sequence")}
        sn = {r["name"]: r["seq"] for r in new.execute("SELECT name, seq FROM sqlite_sequence")}
        diffs = {k for k in set(so) | set(sn) if so.get(k) != sn.get(k)}
        check(f"sqlite_sequence: only the stratagem counter changed (got {sorted(diffs)})",
              diffs == {"stratagem"})
        check(f"sqlite_sequence: stratagem counter 1421 -> 1432 (got {so.get('stratagem')} -> {sn.get('stratagem')})",
              so.get("stratagem") == 1421 and sn.get("stratagem") == 1432)
        continue
    if t in WIDENED:
        oc, nc = cols(old, t), cols(new, t)
        added = set(nc) - set(oc)
        check(f"{t}: exactly id + mission_pack_id added (got {sorted(added)})", added == WIDENED_ADDED)
        check(f"{t}: no original column dropped/renamed", set(oc) <= set(nc))
        check(f"{t}: row count unchanged ({count(old, t)})", count(old, t) == count(new, t))
        proj = ",".join(f'"{c}"' for c in oc)
        o_seq = [tuple(r) for r in old.execute(f"SELECT {proj} FROM '{t}' ORDER BY rowid")]
        n_seq = [tuple(r) for r in new.execute(f"SELECT {proj} FROM '{t}' ORDER BY rowid")]
        check(f"{t}: original columns unchanged row-for-row", o_seq == n_seq)
        nulls = new.execute(f"SELECT COUNT(*) FROM '{t}' WHERE id IS NULL OR mission_pack_id IS NULL").fetchone()[0]
        check(f"{t}: id + mission_pack_id populated on every row", nulls == 0)
        continue
    # normal pre-existing table: fully unchanged
    same = create_sql(old, t) == create_sql(new, t) and count(old, t) == count(new, t) and content_hash(old, t) == content_hash(new, t)
    check(f"{t}: unchanged (schema + {count(old, t)} rows + content)", same)

# the 5 new tables: present + expected counts
for t, want in NEW_TABLE_COUNTS.items():
    got = count(new, t) if t in new_t else -1
    check(f"{t}: present with {want} rows (got {got})", got == want)

# data_version unchanged
def dv(c):
    r = c.execute("SELECT value FROM meta WHERE key='data_version'").fetchone()
    return r[0] if r else None
check(f"meta.data_version == 886 in both (old={dv(old)}, new={dv(new)})", str(dv(old)) == "886" and str(dv(new)) == "886")

print("\nALL PASS" if not fail else f"\n{fail} FAILED")
sys.exit(1 if fail else 0)
