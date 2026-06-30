"""Fuzz -- random armies stress the whole stack.

Builds many random armies through the API and asserts the invariants that must
hold for ANY input: no 500s, validation is deterministic for identical input,
points are non-negative, and (if export exists) the round trip is idempotent.
Combinations are where parity bugs hide; this is the cheap net for them.

Deterministic by default (fixed seed) so failures reproduce.

  python tests/fuzz_armies.py [iterations] [seed]
"""
import sys
import random
import _harness as H
from _harness import Reporter

import army
S = H.store()
C = H.client()

SIZES = ["Incursion", "Strike Force", "Onslaught", "Custom"]


def first_detachment(fid):
    items = H.json_of(C.get(f"/api/factions/{fid}/detachments")) or []
    if isinstance(items, dict):
        items = items.get("detachments") or items.get("items") or []
    for d in items:
        if isinstance(d, dict) and d.get("id") and not d.get("is_combat_patrol"):
            return d["id"]
    return ""


def buildable():
    return [(S.faction_by_id[f["id"] if isinstance(f, dict) else f].get("name"),
             f["id"] if isinstance(f, dict) else f)
            for f in S.factions
            if S.faction_by_id.get(f["id"] if isinstance(f, dict) else f, {}).get("unit_count")
            and S.selectable_units_for_army(f["id"] if isinstance(f, dict) else f)]


def run():
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    rng = random.Random(seed)
    r = Reporter(f"fuzz ({iters} armies, seed {seed})")
    facs = buildable()
    has_export = False
    created = []
    server_errors, nondet, negative, roundtrip_bad = [], [], [], []

    try:
        for i in range(iters):
            name, fid = rng.choice(facs)
            size = rng.choice(SIZES)
            body = {"name": f"__fuzz_{i}__", "faction_id": fid,
                    "detachment_id": first_detachment(fid), "battle_size": size}
            resp = C.post("/api/armies", json=body)
            if resp.status_code >= 500:
                server_errors.append(("create", name, size, resp.status_code)); continue
            if resp.status_code != 200:
                body["detachment_id"] = ""
                resp = C.post("/api/armies", json=body)
            aid = H.army_id_from(H.json_of(resp))
            if not aid:
                continue
            created.append(aid)

            picks = [u["id"] for u in S.selectable_units_for_army(fid)]
            rng.shuffle(picks)
            for did in picks[:rng.randint(1, 6)]:
                bounds = army._squad_bounds(did)
                ss = rng.randint(bounds["min"], bounds["max"])
                ar = C.post(f"/api/armies/{aid}/units", json={"datasheet_id": did, "squad_size": ss})
                if ar.status_code >= 500:
                    server_errors.append(("add", name, did, ar.status_code))

            a1 = H.json_of(C.get(f"/api/armies/{aid}"))
            a2 = H.json_of(C.get(f"/api/armies/{aid}"))
            if a1 is None or a2 is None:
                server_errors.append(("get", name, aid, "no json")); continue
            v1 = sorted(json_dump(v) for v in a1.get("validation", []))
            v2 = sorted(json_dump(v) for v in a2.get("validation", []))
            if v1 != v2:
                nondet.append((name, aid))
            if (a1.get("total_points") or 0) < 0:
                negative.append((name, a1.get("total_points")))

            ex = C.get(f"/api/armies/{aid}/export?fmt=json")
            if ex.status_code == 200:
                has_export = True
                j1 = H.json_of(ex)
                imp = C.post("/api/armies/import", json=j1)
                bid = H.army_id_from(H.json_of(imp))
                if bid:
                    created.append(bid)
                    j2 = H.json_of(C.get(f"/api/armies/{bid}/export?fmt=json"))
                    if _strip(j1) != _strip(j2):
                        roundtrip_bad.append((name, aid))

        r.check("fuzz: no endpoint returned a 5xx for any random army",
                not server_errors, f"{len(server_errors)} e.g. {server_errors[:3]}")
        r.check("fuzz: validation is deterministic across repeated GETs",
                not nondet, f"{len(nondet)} nondeterministic e.g. {nondet[:3]}")
        r.check("fuzz: total points are never negative",
                not negative, f"{len(negative)} e.g. {negative[:3]}")
        if has_export:
            r.check("fuzz: export/import is idempotent for random armies",
                    not roundtrip_bad, f"{len(roundtrip_bad)} e.g. {roundtrip_bad[:3]}")
        else:
            r.skip("fuzz: round-trip idempotence", "export route absent (pre-Phase 6)")
    finally:
        for aid in created:
            C.delete(f"/api/armies/{aid}")
        H.drop_isolated_db()
    return r.summary()


def json_dump(v):
    import json
    return json.dumps(v, sort_keys=True, default=str)


_VOL = {"id", "auid", "army_list_id", "name", "created_at", "updated_at", "sort_order", "rowid"}


def _strip(o):
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in sorted(o.items()) if k not in _VOL}
    if isinstance(o, list):
        return [_strip(v) for v in o]
    return o


if __name__ == "__main__":
    sys.exit(run())
