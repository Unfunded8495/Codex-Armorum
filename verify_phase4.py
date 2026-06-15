"""Phase 4 standalone verification: new data_store loads from SQLite catalogue."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_store import get_store

print("Loading store...")
store = get_store()

print(f"  factions:   {len(store.factions)}")
print(f"  datasheets: {len(store.datasheets)}")
print(f"  ds_by_id:   {len(store.ds_by_id)}")
print(f"  cost:       {len(store.cost)}")
print()

# Faction list
fl = store.faction_list()
print(f"faction_list() -> {len(fl)} factions")
for f in fl[:5]:
    print(f"  {f['id']}  {f['name']}  ({f['unit_count']} units)")
print()

# Check a keyword-mapped faction
am_fac = next((f for f in fl if "Astra Militarum" in f["name"] and "Library" not in f["name"]), None)
if am_fac:
    print(f"Astra Militarum faction: {am_fac}")
    am_units = store.units_for_faction(am_fac["id"])
    print(f"  units_for_faction -> {len(am_units)} units")
    print(f"  first 3: {[u['name'] for u in am_units[:3]]}")
else:
    print("WARNING: Astra Militarum faction not found")
print()

# Find Space Marines faction
sm_fac = next((f for f in fl if "Space Marines" in f["name"] and "Blood" not in f["name"]
               and "Dark" not in f["name"] and "Space Wolves" not in f["name"]
               and "Black" not in f["name"] and "Adeptus Astartes -" not in f["name"]), None)
if sm_fac:
    print(f"Space Marines faction: {sm_fac['name']} (id={sm_fac['id']})")
    sm_units = store.units_for_faction(sm_fac["id"])
    print(f"  units_for_faction -> {len(sm_units)} units")
    intercessor = next((u for u in sm_units if "Intercessor" in u["name"]), None)
    if intercessor:
        print(f"  Found: {intercessor['name']} (id={intercessor['id']}, pts={intercessor['points']})")
        detail = store.unit_detail(intercessor["id"])
        print(f"  unit_detail keys: {list(detail.keys())}")
        print(f"  Ranged weapons: {len(detail['ranged'])}")
        print(f"  Melee weapons:  {len(detail['melee'])}")
        print(f"  faction_id:     {detail['faction_id']}")
        print(f"  keywords:       {detail['keywords'][:5]}")
        print(f"  faction_kws:    {detail['faction_keywords'][:3]}")
        if detail["ranged"]:
            w = detail["ranged"][0]
            print(f"  First ranged:   {w['name']}  A={w['A']} BS_WS={w['BS_WS']} S={w['S']} AP={w['AP']} D={w['D']}")
    else:
        print("  WARNING: Intercessor Squad not found")
else:
    print("WARNING: Space Marines faction not found")
print()

# Check owned_totals dependency: store.ds_by_id keyed by GUID-style IDs
sample_ids = list(store.ds_by_id.keys())[:3]
print(f"Sample ds_by_id keys (should be GUIDs): {sample_ids}")
print()

print("Phase 4 standalone verification PASSED" if len(fl) > 20 else "WARNING: few factions")
