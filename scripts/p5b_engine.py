import os, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import db
from data_store import get_store
from army_validation import validate_army

store = get_store()
NAME_TO_ID = {v["name"]: k for k, v in store.ds_by_id.items()}
FAC = {v["name"]: k for k, v in store.faction_by_id.items()}
TAG = "__p5_selftest__"
fail = 0

def need(d, key, label):
    if key not in d:
        sys.exit(f"FAIL: {label} not found: {key!r}")
    return d[key]

def did(name): return need(NAME_TO_ID, name, "datasheet")

def codes(rows): return [r["code"] for r in rows]

def check(label, cond):
    global fail
    print(f"{'ok ' if cond else 'XX '} {label}")
    fail += 0 if cond else 1

def make_army(faction, battle_size, detachment="", points_limit=2000):
    aid = uuid.uuid4().hex
    with db() as c:
        c.execute(
            "INSERT INTO army_lists(id,name,faction_id,detachment_id,points_limit,battle_size,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (aid, TAG, need(FAC, faction, "faction"), detachment, points_limit, battle_size, time.time()))
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

ult = need(FAC, "Ultramarines", "faction")
gsc = need(FAC, "Genestealer Cults", "faction")

try:
    drop()

    # --- store.allied_by_host present and keyed by faction id ---
    ab = getattr(store, "allied_by_host", None)
    check("store.allied_by_host present and non-empty", isinstance(ab, dict) and len(ab) >= 1)

    # --- Ultramarines allies = Agents / Imperial Knights / Adeptus Titanicus ---
    allies = set()
    for cfg in store.allied_configs(ult):
        for nm in cfg.get("ally_faction_names", []):
            allies.add(nm)
    want = {"Agents of the Imperium", "Imperial Knights", "Adeptus Titanicus"}
    check(f"Ultramarines allies superset of {sorted(want)} (got {sorted(allies)})", want.issubset(allies))
    check("Ultramarines allies exclude Astra Militarum", "Astra Militarum" not in allies)

    # --- ally_config_for: allowed ally yes, native unit no ---
    check("ally_config_for(Ultramarines, Callidus Assassin) is not None",
          store.ally_config_for(ult, did("Callidus Assassin")) is not None)
    check("ally_config_for(Ultramarines, Intercessor Squad) is None (native, not ally)",
          store.ally_config_for(ult, did("Intercessor Squad")) is None)
    check("ally_config_for(Genestealer Cults, Baneblade) is not None",
          store.ally_config_for(gsc, did("Baneblade")) is not None)

    # --- allies_keyword_over: Ultramarines @Incursion + 2 Agents Characters (cap 1) ---
    a = make_army("Ultramarines", "Incursion")
    add(a, "Callidus Assassin", 1)
    add(a, "Vindicare Assassin", 1)
    with db() as c:
        cc = codes(validate_army(c, a))
    check("2 Agents Characters @Incursion -> allies_keyword_over present", "allies_keyword_over" in cc)
    check("Agents config has no points limit -> no allies_points_over", "allies_points_over" not in cc)
    drop()

    # --- allies_points_over: GSC @Incursion + Baneblade (450) + Shadowsword (410) = 860 > 500 ---
    a = make_army("Genestealer Cults", "Incursion")
    add(a, "Baneblade", 1)
    add(a, "Shadowsword", 1)
    with db() as c:
        cc = codes(validate_army(c, a))
    check("Astra Militarum allies 860 pts @Incursion (cap 500) -> allies_points_over present",
          "allies_points_over" in cc)
    drop()

finally:
    drop()

print("ALL PASS" if not fail else f"{fail} FAILED")
sys.exit(1 if fail else 0)
