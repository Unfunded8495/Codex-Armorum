"""No-network harness for the w40k leader-name resolver.

Verifies:
  1. NFKD-normalised lookup resolves the Ûthar mismatch (the only natural
     unresolved case in `data_version: 886`).
  2. A leader entry whose name has no match in the store renders as plain text
     (id=None) rather than being silently dropped.
  3. Astorath -> Death Company Marines with Jump Packs resolves and renders as
     a link.
"""
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    from data_store import get_store, _nfkd
    store = get_store()

    # 1. NFKD: confirm the resolver casefolds + decomposes apostrophes etc.
    assert_true(_nfkd("Ûthar the Destined") == _nfkd("Uthar the Destined"),
                "NFKD should fold combining marks so Ûthar matches Uthar")

    # 2. Unresolved name renders as plain text. Build a fake _leads_names entry
    #    that cannot resolve, run the resolver, and check the resulting entry
    #    has id=None and keeps the raw name.
    fake_uuid = "test-fabricated-leader"
    fake_leader = {
        "id": fake_uuid,
        "name": "Fabricated Leader",
        "faction_id": next(f["id"] for f in store.factions
                           if f["name"] == "Adeptus Astartes"),
        "_leads_names": ["Definitely Not A Real Unit XYZ"],
        "_led_by_names": [],
    }
    store.datasheets.append(fake_leader)
    store.ds_by_id[fake_uuid] = fake_leader
    try:
        store._resolve_leaders()
        leads = store.leads.get(fake_uuid, [])
        assert_true(len(leads) == 1,
                    f"Unresolved name should still produce one entry, got {leads!r}")
        assert_true(leads[0]["id"] is None,
                    f"Unresolved name should have id=None, got {leads[0]!r}")
        assert_true(leads[0]["name"] == "Definitely Not A Real Unit XYZ",
                    f"Raw name preserved, got {leads[0]['name']!r}")
    finally:
        store.datasheets.pop()
        store.ds_by_id.pop(fake_uuid, None)
        store._resolve_leaders()  # rebuild clean state

    # 3. Astorath -> Death Company Marines with Jump Packs.
    astorath = next((u for u in store.datasheets if u["name"] == "Astorath"), None)
    assert_true(astorath is not None, "Astorath should be in the store")
    leads = store.leads.get(astorath["id"], [])
    jump = next((L for L in leads
                 if L["name"] == "Death Company Marines with Jump Packs"), None)
    assert_true(jump is not None and jump["id"],
                f"Astorath should lead Death Company Marines with Jump Packs "
                f"as a resolved link, got {leads!r}")

    print(f"OK: NFKD, unresolved fallback, Astorath link. "
          f"({len(store.datasheets)} datasheets in store)")


if __name__ == "__main__":
    main()
