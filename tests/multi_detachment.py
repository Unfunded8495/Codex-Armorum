"""Multi-detachment (Detachment Points) round-trip tests.

Exercises the P0 slice: an army unlocks several detachments by spending its
battle-size Detachment Points, each contributing its own enhancements/rules/
stratagems. In-process Flask client against an isolated DB copy. Self-cleaning.

Run: python tests/multi_detachment.py
"""
import sys
import _harness as H
from _harness import Reporter

import army
from eligibility import eligible_enhancements
S = H.store()
C = H.client()


def dets_for(fid):
    """[(id, name, cost)] of normal detachments for a faction, cheapest first."""
    items = H.json_of(C.get(f"/api/factions/{fid}/detachments")) or []
    out = [(d["id"], d.get("name", ""), d.get("points_cost", 0)) for d in items]
    return sorted(out, key=lambda x: x[2])


def create(fid, battle_size="Strike Force", detachment_ids=None):
    body = {"name": "__mdet__", "faction_id": fid, "battle_size": battle_size}
    if detachment_ids is not None:
        body["detachment_ids"] = detachment_ids
    resp = C.post("/api/armies", json=body)
    return H.army_id_from(H.json_of(resp)), resp


def get_army(aid):
    return H.json_of(C.get(f"/api/armies/{aid}")) or {}


def update(aid, **body):
    return C.post(f"/api/armies/{aid}", json=body)


def run():
    r = Reporter("multi-detachment")
    created = []
    try:
        fid = H.fid("Ultramarines")
        dts = dets_for(fid)
        ones = [d for d in dts if d[2] == 1]              # cost-1 detachments
        if len(ones) < 3:
            r.skip("multi-detachment", "need >=3 cost-1 detachments to test")
            return r.summary()
        a, b, cc = ones[0][0], ones[1][0], ones[2][0]
        twos = [d for d in dts if d[2] == 2]

        # --- 1) Create with two detachments (2 of 3 DP) ----------------------
        aid, cresp = create(fid, "Strike Force", [a, b])
        r.check("create with 2 detachments returns 200", aid is not None,
                f"status {cresp.status_code}")
        if not aid:
            return r.summary()
        created.append(aid)
        army0 = get_army(aid)
        r.check("GET returns both detachment_ids in order",
                army0.get("detachment_ids") == [a, b], f"{army0.get('detachment_ids')}")
        r.check("detachment_points_used = 2", army0.get("detachment_points_used") == 2,
                f"{army0.get('detachment_points_used')}")
        r.check("detachments payload has 2 chips", len(army0.get("detachments") or []) == 2)
        r.check("validation reports detachment_points_ok",
                any(v.get("code") == "detachment_points_ok" for v in army0.get("validation", [])))

        # --- 2) Over-budget create is rejected -------------------------------
        if twos:
            over = [twos[0][0], a, b]  # 2 + 1 + 1 = 4 > 3
            _, oresp = create(fid, "Strike Force", over)
            r.check("create over the DP budget is rejected (400)", oresp.status_code == 400,
                    f"status {oresp.status_code}")
        else:
            r.skip("over-budget create", "no cost-2 detachment to overflow with")

        # --- 3) Add a third (fills 3/3), then duplicate is de-duped ----------
        u3 = update(aid, detachment_ids=[a, b, cc])
        j3 = H.json_of(u3) or {}
        r.check("add a third cost-1 detachment fills 3/3 DP",
                j3.get("ok") and j3.get("detachment_points_used") == 3,
                f"{j3.get('detachment_points_used')}")
        u_dup = update(aid, detachment_ids=[a, a, b])
        jd = H.json_of(u_dup) or {}
        r.check("duplicate detachment ids are de-duped", jd.get("detachment_ids") == [a, b],
                f"{jd.get('detachment_ids')}")

        # --- 4) Auto-trim on a battle-size downgrade -------------------------
        update(aid, detachment_ids=[a, b, cc])            # back to 3/3 at Strike Force
        u_down = update(aid, battle_size="Incursion")     # budget drops to 2
        jdown = H.json_of(u_down) or {}
        ids_after = jdown.get("detachment_ids") or []
        r.check("downgrade trims the set to fit the smaller DP budget",
                army.detachment_set_cost(ids_after) <= 2 and len(ids_after) < 3,
                f"ids={ids_after} cost={army.detachment_set_cost(ids_after)}")

        # --- 5) Enhancement pool is the union of selected detachments -------
        # Find a Character eligible for enhancements in TWO budget-fitting
        # detachments, so the union is strictly larger than either alone -- the
        # real test of the union behaviour. (Chapter characters live in the parent
        # pool, so use the picker's selectable set, not _datasheet_in_faction.)
        sel_chars = [u["id"] for u in S.selectable_units_for_army(fid)
                     if S.ds_by_id.get(u["id"], {}).get("role") == "Character"]
        costby = {d[0]: d[2] for d in dts}
        pick = None
        for cid in sel_chars:
            elig = [d[0] for d in dts if eligible_enhancements(cid, d[0])]
            for i in range(len(elig)):
                for j in range(i + 1, len(elig)):
                    if costby[elig[i]] + costby[elig[j]] <= 3:
                        pick = (cid, elig[i], elig[j])
                        break
                if pick:
                    break
            if pick:
                break
        if pick:
            cid, da, db_ = pick
            aid2, _ = create(fid, "Strike Force", [da, db_])
            created.append(aid2)
            au = H.json_of(C.post(f"/api/armies/{aid2}/units", json={"datasheet_id": cid}))
            auid = (au or {}).get("unit", {}).get("id")
            ea = {str(e["id"]) for e in eligible_enhancements(cid, da)}
            want = ea | {str(e["id"]) for e in eligible_enhancements(cid, db_)}
            got = {str(e["id"]) for e in (H.json_of(C.get(f"/api/army-units/{auid}/enhancements")) or [])}
            r.check("unit enhancement pool == union of both detachments' eligible sets",
                    got == want, f"missing={want - got} extra={got - want}")
            r.check("union pool is strictly larger than a single detachment alone",
                    len(want) > len(ea), f"union={len(want)} single={len(ea)}")
            # Assigning an enhancement that only exists in the second detachment
            # succeeds (proves it resolves against the union, not detachment[0]).
            only_b = sorted(want - ea)
            if only_b and auid:
                up = C.post(f"/api/army-units/{auid}", json={"enhancement_id": only_b[0]})
                r.check("a second-detachment enhancement is assignable",
                        (H.json_of(up) or {}).get("ok") is True, f"status {up.status_code}")
        else:
            r.skip("enhancement union", "no character eligible in two budget-fitting detachments")

        # --- 6) Export / import preserves the detachment set ----------------
        aid3, _ = create(fid, "Strike Force", [a, b])
        created.append(aid3)
        j = H.json_of(C.get(f"/api/armies/{aid3}/export?fmt=json"))
        r.check("roster export carries detachment_ids", j.get("detachment_ids") == [a, b],
                f"{j.get('detachment_ids')}")
        imp = H.json_of(C.post("/api/armies/import", json=j))
        bid = H.army_id_from(imp)
        if bid:
            created.append(bid)
            r.check("imported army restores the detachment set",
                    get_army(bid).get("detachment_ids") == [a, b])
        else:
            r.check("import succeeded", False, "no id returned")
    finally:
        for aid in created:
            C.delete(f"/api/armies/{aid}")
        H.drop_isolated_db()
    return r.summary()


if __name__ == "__main__":
    sys.exit(run())
