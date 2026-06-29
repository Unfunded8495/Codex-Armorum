import os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import db
from data_store import get_store
from army import duplicate_cap
from army_validation import validate_army

store = get_store()
NAME_TO_ID = {v["name"]: k for k, v in store.ds_by_id.items()}
FAC = {v["name"]: k for k, v in store.faction_by_id.items()}
DET = {d["name"]: i for i, d in store.detachment_by_id.items()}
TAG = "__p5_selftest__"
fail = 0

def need(d, key, label):
    if key not in d:
        sys.exit(f"FAIL: {label} not found: {key!r}")
    return d[key]

def did(name): return need(NAME_TO_ID, name, "datasheet")

def codes(rows): return [r["code"] for r in rows]

def make_army(faction, battle_size, detachment="", points_limit=2000):
    aid = uuid.uuid4().hex
    with db() as c:
        c.execute(
            "INSERT INTO army_lists(id,name,faction_id,detachment_id,points_limit,battle_size,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (aid, TAG, need(FAC, faction, "faction"),
             DET.get(detachment, ""), points_limit, battle_size, time.time()))
    return aid

def add(aid, name, n=1):
    with db() as c:
        for i in range(n):
            c.execute(
                "INSERT INTO army_units(id,army_list_id,datasheet_id,squad_size,sort_order)"
                " VALUES(?,?,?,?,?)",
                (uuid.uuid4().hex, aid, did(name), 1, i))

def drop():
    with db() as c:
        for r in c.execute("SELECT id FROM army_lists WHERE name=?", (TAG,)).fetchall():
            c.execute("DELETE FROM army_units WHERE army_list_id=?", (r["id"],))
            c.execute("DELETE FROM army_lists WHERE id=?", (r["id"],))

def check(label, cond):
    global fail
    print(f"{'ok ' if cond else 'XX '} {label}")
    fail += 0 if cond else 1

try:
    drop()

    # --- duplicate_cap pure-function table (section 1) ---
    table = {
        "Intercessor Squad": {"Incursion": 4, "Strike Force": 6, "Onslaught": 8, "Custom": None},
        "Hellblaster Squad": {"Incursion": 2, "Strike Force": 3, "Onslaught": 4, "Custom": None},
        "Roboute Guilliman": {"Incursion": 1, "Strike Force": 1, "Onslaught": 1, "Custom": 1},
    }
    for unit, sizes in table.items():
        for size, want in sizes.items():
            got = duplicate_cap(size, did(unit))
            check(f"duplicate_cap({size!r}, {unit!r}) = {got} (want {want})", got == want)

    # --- duplicate_over: 7x Battleline at Strike Force (cap 6) over, 6x not ---
    a = make_army("Ultramarines", "Strike Force")
    add(a, "Intercessor Squad", 7)
    with db() as c:
        cc = codes(validate_army(c, a))
    check("7x Intercessor Squad @Strike Force -> duplicate_over present", "duplicate_over" in cc)
    drop()

    a = make_army("Ultramarines", "Strike Force")
    add(a, "Intercessor Squad", 6)
    with db() as c:
        cc = codes(validate_army(c, a))
    check("6x Intercessor Squad @Strike Force -> no duplicate_over", "duplicate_over" not in cc)
    drop()

    # --- duplicate_over: 4x plain at Strike Force (cap 3) over; 4x OK at Onslaught (cap 4) ---
    a = make_army("Ultramarines", "Strike Force")
    add(a, "Hellblaster Squad", 4)
    with db() as c:
        cc = codes(validate_army(c, a))
    check("4x Hellblaster Squad @Strike Force -> duplicate_over present", "duplicate_over" in cc)
    drop()

    a = make_army("Ultramarines", "Onslaught")
    add(a, "Hellblaster Squad", 4)
    with db() as c:
        cc = codes(validate_army(c, a))
    check("4x Hellblaster Squad @Onslaught -> no duplicate_over", "duplicate_over" not in cc)
    drop()

    # --- Epic Hero capped at 1 even on Custom ---
    a = make_army("Ultramarines", "Custom")
    add(a, "Roboute Guilliman", 2)
    with db() as c:
        cc = codes(validate_army(c, a))
    check("2x Roboute Guilliman @Custom -> duplicate_over present (cap 1)", "duplicate_over" in cc)
    drop()

    # --- detachment_excluded: Black Spear Task Force forbids Deathwatch Kill Team ---
    a = make_army("Deathwatch", "Strike Force", detachment="Black Spear Task Force")
    add(a, "Deathwatch Kill Team", 1)
    with db() as c:
        cc = codes(validate_army(c, a))
    check("Black Spear + Deathwatch Kill Team -> detachment_excluded present", "detachment_excluded" in cc)
    drop()

    # --- control: no detachment -> no exclusion row for the same unit ---
    a = make_army("Deathwatch", "Strike Force")
    add(a, "Deathwatch Kill Team", 1)
    with db() as c:
        cc = codes(validate_army(c, a))
    check("No detachment + Deathwatch Kill Team -> no detachment_excluded", "detachment_excluded" not in cc)
    drop()

finally:
    drop()

print("ALL PASS" if not fail else f"{fail} FAILED")
sys.exit(1 if fail else 0)
