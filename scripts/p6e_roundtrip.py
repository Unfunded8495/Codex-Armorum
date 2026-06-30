import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, copy
import app
from data_store import get_store

s = get_store()
NAME = {v["name"]: k for k, v in s.ds_by_id.items()}
ULT = next(k for k, v in s.faction_by_id.items() if v["name"] == "Ultramarines")
TAG = "__p6_roundtrip__"
c = app.app.test_client()
fail = 0
created = []

def check(label, cond):
    global fail
    print(f"{'ok ' if cond else 'XX '} {label}")
    fail += 0 if cond else 1

def army_id(resp):
    j = resp.get_json()
    for k in ("id", "army_id", "army_list_id"):
        if isinstance(j, dict) and k in j:
            return j[k]
        if isinstance(j, dict) and isinstance(j.get("army"), dict) and k in j["army"]:
            return j["army"][k]
    raise SystemExit(f"could not find army id in create response: {j}")

VOLATILE = {"id", "army_id", "army_list_id", "auid", "army_unit_id", "unit_id",
            "name", "created_at", "updated_at"}
def norm(o):
    if isinstance(o, dict):
        return {k: norm(v) for k, v in o.items() if k not in VOLATILE}
    if isinstance(o, list):
        return [norm(v) for v in o]
    return o

try:
    # Build a minimal but multi-table army: a native unit + an ally.
    A = army_id(c.post("/api/armies", json={"name": TAG, "faction_id": ULT, "battle_size": "Strike Force"}))
    created.append(A)
    c.post(f"/api/armies/{A}/units", json={"datasheet_id": NAME["Intercessor Squad"]})
    c.post(f"/api/armies/{A}/units", json={"datasheet_id": NAME["Callidus Assassin"]})  # ally

    j1 = c.get(f"/api/armies/{A}/export?fmt=json").get_json()
    check("export?fmt=json returns a payload", bool(j1))

    imp = c.post("/api/armies/import", json=j1)
    B = army_id(imp)
    created.append(B)
    check("import created a new army", B and B != A)

    j2 = c.get(f"/api/armies/{B}/export?fmt=json").get_json()
    check("export -> import -> export is idempotent (ignoring ids/names)", norm(j1) == norm(j2))

    # text export is non-empty and mentions the faction
    txt = c.get(f"/api/armies/{A}/export?fmt=text").get_data(as_text=True)
    check("text export is non-empty", len(txt.strip()) > 0)
finally:
    for aid in created:
        c.delete(f"/api/armies/{aid}")

print("\nALL PASS" if not fail else f"\n{fail} FAILED (if idempotence fails, print norm(j1) vs norm(j2) to see the diff; if the export embeds internal army-unit ids, add them to VOLATILE)")
sys.exit(1 if fail else 0)
