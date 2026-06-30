import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, sqlite3
from data_store import get_store

s = get_store()
fail = 0
def check(label, cond):
    global fail
    print(f"{'ok ' if cond else 'XX '} {label}")
    fail += 0 if cond else 1

# Core stratagems surfaced
check(f"len(store.core_stratagems) == 11 (got {len(s.core_stratagems)})", len(s.core_stratagems) == 11)

# Army rule, faction-resolved (parent-aware)
FAC = {v["name"]: k for k, v in s.faction_by_id.items()}
def rule_names(fid):
    rules = s.army_rules_for(fid)
    out = []
    for r in rules:
        out.append(r.get("name") if isinstance(r, dict) else getattr(r, "name", r))
    return out
check("army_rules_for(Adeptus Astartes) includes 'Oath of Moment'",
      "Oath of Moment" in rule_names(FAC["Adeptus Astartes"]))
check("army_rules_for(Ultramarines) includes 'Oath of Moment' (parent-aware ok either way)",
      "Oath of Moment" in rule_names(FAC["Ultramarines"]))

# Missions exclude the Combat Patrol pack
missions = s.missions() if callable(getattr(s, "missions", None)) else s.missions
blob = json.dumps(missions, default=str)
check("store.missions excludes the 'Combat Patrol' pack", "Combat Patrol" not in blob)
check("store.missions includes the 'Chapter Approved 2026-2027' pack", "Chapter Approved 2026-2027" in blob)

# Exported mission tables: pack-tagging produces the right per-pack counts
db = sqlite3.connect("data/w40k/w40k.db"); db.row_factory = sqlite3.Row
def packcol(t):
    c = [r["name"] for r in db.execute(f"PRAGMA table_info('{t}')")]
    return "pack_id" if "pack_id" in c else "mission_pack_id"
def pack_id(name):
    r = db.execute("SELECT id FROM mission_pack WHERE name=?", (name,)).fetchone()
    return r["id"] if r else None
ca = pack_id("Chapter Approved 2026-2027")
cp = pack_id("Combat Patrol")
check("both packs present in mission_pack", ca is not None and cp is not None)
def n(t, pid):
    return db.execute(f"SELECT COUNT(*) FROM '{t}' WHERE {packcol(t)}=?", (pid,)).fetchone()[0]
def total(t):
    return db.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
# CA-only (what the UI shows)
for t, want in [("mission_primary", 25), ("mission_secondary", 18), ("mission_deployment", 6),
                ("mission_layout", 45), ("mission_preset", 45), ("mission_twist", 6)]:
    got = n(t, ca)
    check(f"{t}: Chapter-Approved count == {want} (got {got})", got == want)
# totals across both packs
for t, want in [("mission_primary", 49), ("mission_secondary", 18), ("mission_deployment", 9),
                ("mission_layout", 46), ("mission_preset", 48), ("mission_twist", 6)]:
    got = total(t)
    check(f"{t}: total across both packs == {want} (got {got})", got == want)

print("\nALL PASS" if not fail else f"\n{fail} FAILED")
sys.exit(1 if fail else 0)
