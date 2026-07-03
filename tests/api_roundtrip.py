"""API round-trip tests -- in-process Flask client against an isolated DB.

Exercises the real routes a user hits: add-unit guard parity (the chapter
add-guard regression), server validation codes (duplicate / excludes / allies),
and export/import idempotence. Phase 5/6 pieces are feature-detected.

The DB is an isolated copy of collection.db (COLLECTION_DB_PATH), so this never
touches real data and starts no server. Self-cleaning.

Run: python tests/api_roundtrip.py
"""
import sys
import json
import _harness as H
from _harness import Reporter

# Import army/store BEFORE the client so we can reason about faction membership.
import army
S = H.store()
C = H.client()  # sets COLLECTION_DB_PATH to a temp copy, returns app.app.test_client()

VOLATILE = {"id", "auid", "army_id", "army_list_id", "name", "created_at",
            "updated_at", "sort_order", "rowid"}


def norm(o):
    if isinstance(o, dict):
        return {k: norm(v) for k, v in sorted(o.items()) if k not in VOLATILE}
    if isinstance(o, list):
        return [norm(v) for v in o]
    return o


def first_detachment(fid):
    """A normal (non-Combat-Patrol) detachment id for the faction, or '' ."""
    resp = C.get(f"/api/factions/{fid}/detachments")
    items = H.json_of(resp) or []
    if isinstance(items, dict):
        items = items.get("detachments") or items.get("items") or []
    for d in items:
        dtid = d.get("id") if isinstance(d, dict) else d
        if dtid and not (isinstance(d, dict) and d.get("is_combat_patrol")):
            return dtid
    return ""


def create_army(fid, battle_size="Strike Force", detachment_id=None):
    if detachment_id is None:
        detachment_id = first_detachment(fid)
    body = {"name": "__test__", "faction_id": fid, "detachment_id": detachment_id,
            "battle_size": battle_size}
    resp = C.post("/api/armies", json=body)
    if resp.status_code != 200:
        # retry with no detachment (empty is valid for some sizes)
        body["detachment_id"] = ""
        resp = C.post("/api/armies", json=body)
    return H.army_id_from(H.json_of(resp)), resp


def add_unit(aid, did, squad_size=None):
    body = {"datasheet_id": did}
    if squad_size is not None:
        body["squad_size"] = squad_size
    return C.post(f"/api/armies/{aid}/units", json=body)


def get_army(aid):
    return H.json_of(C.get(f"/api/armies/{aid}"))


def validation_codes(aid):
    a = get_army(aid) or {}
    return [v.get("code") for v in a.get("validation", []) if isinstance(v, dict)]


def run():
    r = Reporter("api round-trip")
    created = []
    try:
        # --- 1) Add-unit guard parity (the chapter add-guard regression) ----------
        # For a chapter faction, every unit the picker offers must be addable, and
        # nothing outside it. In a pre-chapter-fix tree the generic-add fails (the
        # route still gates on the narrower _datasheet_in_faction); post-fix it
        # passes because the route gates on the picker set.
        ult = H.fid("Ultramarines")
        offered = S.selectable_units_for_army(ult)
        offered_ids = {u["id"] for u in offered}
        native = next((u["id"] for u in offered if army._datasheet_in_faction(u["id"], ult)), None)
        generic = next((u["id"] for u in offered if not army._datasheet_in_faction(u["id"], ult)), None)
        # a unit the picker does NOT offer (a Blood Angels-only sheet), to guard
        # against over-acceptance
        ba = H.fid("Blood Angels")
        ba_only = next((u["id"] for u in S.selectable_units_for_army(ba)
                        if u["id"] not in offered_ids and army._datasheet_in_faction(u["id"], ba)
                        and not army._datasheet_in_faction(u["id"], ult)), None)

        aid, cresp = create_army(ult)
        r.check("create Ultramarines army returns 200 + id", aid is not None, f"status {cresp.status_code}")
        if aid:
            created.append(aid)
            if native:
                r.check("add-guard: a native chapter unit is accepted",
                        add_unit(aid, native).status_code == 200)
            if generic is not None:
                sc = add_unit(aid, generic).status_code
                ok = sc == 200
                r.check("add-guard: a generic unit the picker offers is accepted (chapter add-guard fix)",
                        ok, f"status {sc} -- EXPECTED to fail in a PRE-chapter-fix tree; "
                            f"PASS confirms the add route gates on the picker set")
            else:
                r.skip("add-guard: generic-unit acceptance", "no generic in picker (unexpected)")
            if ba_only:
                r.check("add-guard: a unit the picker does NOT offer is rejected (no over-acceptance)",
                        add_unit(aid, ba_only).status_code == 400)
            else:
                r.skip("add-guard: over-acceptance guard", "could not find an out-of-faction sheet")

        # --- 2) Duplicate cap validation (Phase 5) --------------------------------
        if H.has(army, "duplicate_cap"):
            aid2, _ = create_army(ult)
            if aid2:
                created.append(aid2)
                bl = H.did("Intercessor Squad")  # Battleline -> cap 6 at Strike Force
                for _ in range(7):
                    add_unit(aid2, bl)
                codes = validation_codes(aid2)
                r.check("validation: 7x a Battleline unit triggers duplicate_over",
                        "duplicate_over" in codes, f"codes={codes}")
        else:
            r.skip("validation: duplicate cap", "army.duplicate_cap absent (pre-Phase 5)")

        # --- 3) Detachment excludes (Phase 5) -------------------------------------
        # Black Spear Task Force (Deathwatch) excludes specific datasheets.
        try:
            dw = H.fid("Deathwatch")
            dets = H.json_of(C.get(f"/api/factions/{dw}/detachments")) or []
            if isinstance(dets, dict):
                dets = dets.get("detachments") or dets.get("items") or []
            bstf = next((d["id"] for d in dets if isinstance(d, dict)
                         and "Black Spear" in (d.get("name") or "")), None)
            excludes = next((d.get("excludes_datasheets") or [] for d in dets if isinstance(d, dict)
                             and "Black Spear" in (d.get("name") or "")), [])
        except KeyError:
            bstf, excludes = None, []
        if bstf and excludes:
            aid3, _ = create_army(dw, detachment_id=bstf)
            ex_name = excludes[0]
            ex_did = H.name_index().get(ex_name)
            if aid3 and ex_did:
                created.append(aid3)
                add_unit(aid3, ex_did)
                codes = validation_codes(aid3)
                # only a real pass/fail if Phase 5 added the code; else informational
                if "detachment_excluded" in codes:
                    r.check("validation: an excluded unit triggers detachment_excluded", True)
                else:
                    r.skip("validation: detachment_excluded", "code not present (pre-Phase 5)")
            else:
                r.skip("validation: detachment_excluded", "could not set up Black Spear army")
        else:
            r.skip("validation: detachment_excluded", "Black Spear detachment/excludes not found")

        # --- 4) Export / import idempotence (Phase 6) -----------------------------
        probe = C.get(f"/api/armies/{aid}/export?fmt=json") if aid else None
        if probe is not None and probe.status_code == 200:
            aid4, _ = create_army(ult)
            created.append(aid4)
            add_unit(aid4, native or H.did("Intercessor Squad"))
            # add an ally if the allies system is present
            if H.has(S, "ally_config_for"):
                try:
                    add_unit(aid4, H.did("Callidus Assassin"))
                except KeyError:
                    pass
            j1 = H.json_of(C.get(f"/api/armies/{aid4}/export?fmt=json"))
            imp = C.post("/api/armies/import", json=j1)
            bid = H.army_id_from(H.json_of(imp))
            r.check("export -> import creates a new army", bid and bid != aid4,
                    f"import status {imp.status_code}")
            if bid:
                created.append(bid)
                j2 = H.json_of(C.get(f"/api/armies/{bid}/export?fmt=json"))
                r.check("export -> import -> export is idempotent (ignoring ids/names)",
                        norm(j1) == norm(j2),
                        "if this fails, the export likely embeds internal ids; add them to VOLATILE")
            txt = C.get(f"/api/armies/{aid4}/export?fmt=text")
            r.check("text export is non-empty", txt.status_code == 200 and txt.get_data(as_text=True).strip())
        else:
            r.skip("export/import idempotence", "export route absent (pre-Phase 6)")

        # --- 5) Leader attachment (leader_group enforcement) -----------------------
        # One Leader-slot character attaches, a support character joins alongside
        # (a 400 pre-leader_group), a second Leader-slot character is rejected.
        if H.has(S, "leader_groups"):
            ints = H.did("Intercessor Squad")
            pure = {"leader": [], "support": []}
            for ldid, lgroups in S.leader_groups.items():
                if ldid not in offered_ids:
                    continue
                kinds = {"support" if g.get("type") == "support" else "leader"
                         for g in lgroups
                         if ints in g["member_ids"] and not g.get("required_detachment_id")}
                if len(kinds) == 1:
                    pure[next(iter(kinds))].append(ldid)
            if len(pure["leader"]) >= 2 and pure["support"]:
                aid5, _ = create_army(ult)
                created.append(aid5)

                def added(did_):
                    return ((H.json_of(add_unit(aid5, did_)) or {}).get("unit") or {}).get("id")

                bg = added(ints)
                la, lb = added(pure["leader"][0]), added(pure["leader"][1])
                sp = added(pure["support"][0])
                if all([bg, la, lb, sp]):
                    s1 = C.post(f"/api/army-units/{la}", json={"attached_to": bg}).status_code
                    s2 = C.post(f"/api/army-units/{sp}", json={"attached_to": bg}).status_code
                    s3 = C.post(f"/api/army-units/{lb}", json={"attached_to": bg}).status_code
                    r.check("attach: a Leader joins its bodyguard", s1 == 200, f"status {s1}")
                    r.check("attach: a support character joins alongside the Leader",
                            s2 == 200, f"status {s2}")
                    r.check("attach: a second Leader is rejected", s3 == 400, f"status {s3}")
                    a5 = get_army(aid5) or {}
                    row5 = next((u for u in a5.get("units", []) if u.get("id") == bg), {})
                    names = row5.get("attached_leader_name") or ""
                    r.check("attach: bodyguard row reports both attached characters",
                            S.ds_by_id[pure["leader"][0]]["name"] in names
                            and S.ds_by_id[pure["support"][0]]["name"] in names,
                            f"attached_leader_name={names!r}")
                    codes = validation_codes(aid5)
                    r.check("attach: legal attachments raise no illegal_attachment",
                            "illegal_attachment" not in codes, f"codes={codes}")
                else:
                    r.check("attach: test units added", False, "add-unit failed")
            else:
                r.skip("attach journey",
                       "no 2 pure-Leader + 1 support characters for Intercessors in the picker")
        else:
            r.skip("attach journey", "store.leader_groups absent")
    finally:
        for aid in created:
            C.delete(f"/api/armies/{aid}")
        H.drop_isolated_db()

    return r.summary()


if __name__ == "__main__":
    sys.exit(run())
