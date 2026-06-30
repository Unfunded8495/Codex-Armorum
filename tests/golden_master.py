"""Golden master -- per-faction army snapshots.

Builds one small army per buildable faction through the real API, captures the
resolved output (units with points/role/loadout, total, validation codes), and
diffs it against a checked-in snapshot. Because the engine is deterministic, any
diff is either an intended change you re-bless with --build, or a regression.

  python tests/golden_master.py --build    # (re)generate snapshots
  python tests/golden_master.py            # verify against snapshots

Snapshots live in tests/golden/<faction>.json and are meant to be committed.
"""
import sys
import os
import json
import _harness as H
from _harness import Reporter

import army
S = H.store()
C = H.client()
GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

VOLATILE = {"id", "auid", "army_list_id", "created_at", "updated_at", "sort_order", "rowid"}


def gnorm(o):
    if isinstance(o, dict):
        return {k: gnorm(v) for k, v in sorted(o.items()) if k not in VOLATILE}
    if isinstance(o, list):
        return [gnorm(v) for v in o]
    return o


def buildable_factions():
    out = []
    for f in S.factions:
        fid = f["id"] if isinstance(f, dict) else f
        rec = S.faction_by_id.get(fid, {})
        if rec.get("unit_count") and S.selectable_units_for_army(fid):
            out.append((rec.get("name"), fid))
    return sorted(out)


def first_detachment(fid):
    items = H.json_of(C.get(f"/api/factions/{fid}/detachments")) or []
    if isinstance(items, dict):
        items = items.get("detachments") or items.get("items") or []
    for d in items:
        if isinstance(d, dict) and d.get("id") and not d.get("is_combat_patrol"):
            return d["id"]
    return ""


def build_army_snapshot(name, fid):
    """A small, deterministic army: first 3 picker units at default size."""
    body = {"name": "__golden__", "faction_id": fid,
            "detachment_id": first_detachment(fid), "battle_size": "Strike Force"}
    resp = C.post("/api/armies", json=body)
    if resp.status_code != 200:
        body["detachment_id"] = ""
        resp = C.post("/api/armies", json=body)
    aid = H.army_id_from(H.json_of(resp))
    if not aid:
        return None, None
    picks = [u["id"] for u in S.selectable_units_for_army(fid)][:3]
    for did in picks:
        C.post(f"/api/armies/{aid}/units", json={"datasheet_id": did})
    full = H.json_of(C.get(f"/api/armies/{aid}"))
    C.delete(f"/api/armies/{aid}")
    if not full:
        return None, None
    snap = {
        "faction": full.get("faction_name"),
        "detachment": full.get("detachment_name"),
        "battle_size": full.get("battle_size"),
        "total_points": full.get("total_points"),
        "units": [{"name": u.get("name"), "datasheet_id": u.get("datasheet_id"),
                   "squad_size": u.get("squad_size"), "points": u.get("points"),
                   "role": u.get("role"), "loadout_summary": u.get("loadout_summary")}
                  for u in full.get("units", [])],
        "validation": sorted(v.get("code") for v in full.get("validation", []) if isinstance(v, dict)),
    }
    return aid, gnorm(snap)


def run():
    build = "--build" in sys.argv
    r = Reporter("golden master (build)" if build else "golden master (verify)")
    os.makedirs(GOLD, exist_ok=True)
    facs = buildable_factions()

    if build:
        n = 0
        for name, fid in facs:
            _, snap = build_army_snapshot(name, fid)
            if snap is None:
                r.check(f"build snapshot: {name}", False, "army build failed")
                continue
            with open(os.path.join(GOLD, f"{fid}.json"), "w") as fh:
                json.dump(snap, fh, indent=2, sort_keys=True)
            n += 1
        H.drop_isolated_db()
        print(f"\nwrote {n} snapshots to {GOLD}")
        return r.summary()

    existing = [f for f in os.listdir(GOLD) if f.endswith(".json")] if os.path.isdir(GOLD) else []
    if not existing:
        print("--   no golden snapshots found; run:  python tests/golden_master.py --build")
        H.drop_isolated_db()
        return 0  # not a failure: nothing to verify yet
    for name, fid in facs:
        path = os.path.join(GOLD, f"{fid}.json")
        if not os.path.exists(path):
            r.skip(f"golden: {name}", "no snapshot (run --build)")
            continue
        with open(path) as fh:
            want = json.load(fh)
        _, got = build_army_snapshot(name, fid)
        r.check(f"golden: {name} resolves identically to snapshot", got == gnorm(want),
                "resolved output drifted; re-bless with --build if intended")
    H.drop_isolated_db()
    return r.summary()


if __name__ == "__main__":
    sys.exit(run())
