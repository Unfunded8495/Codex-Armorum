"""Enhancement eligibility — which Characters may bear a given Enhancement.

An Enhancement's ``eligibility_struct`` is ``{required_groups, excluded_keywords}``.
A bearer is eligible when it:

* has the ``Character`` keyword,
* is **not** an Epic Hero — a core-rules restriction that is *not* encoded in the
  struct (so matching alone would wrongly admit e.g. Belisarius Cawl),
* matches **at least one** ``required_group``, and
* carries **none** of ``excluded_keywords``.

A ``required_group`` matches when every one of its ``keywords`` is on the unit, every
``faction_keywords`` entry is present as ``"Faction: <name>"`` (datasheets store the
prefixed form; the struct holds the bare name), and its ``datasheet`` — a **name
string**, not a UUID — equals the unit's name when set.
"""
from data_store import get_store


def enhancement_eligible(unit_keywords, role, struct, unit_name=None):
    """True if a unit with these keywords / role / name may take the enhancement."""
    kw = unit_keywords if isinstance(unit_keywords, set) else set(unit_keywords or [])
    if "Character" not in kw or role == "Epic Hero":
        return False
    struct = struct or {}
    if any(x in kw for x in (struct.get("excluded_keywords") or [])):
        return False
    groups = struct.get("required_groups") or []
    if not groups:
        return True  # the lone enhancement with no required group: any character
    for g in groups:
        if any(n not in kw for n in (g.get("keywords") or [])):
            continue
        if any(("Faction: " + fk) not in kw for fk in (g.get("faction_keywords") or [])):
            continue
        ds = g.get("datasheet")
        if ds and ds != (unit_name or ""):
            continue  # a datasheet-specific group only matches the named sheet
        return True
    return False


def eligible_enhancements(did, detachment_id):
    """The enhancements of ``detachment_id`` that the datasheet ``did`` may bear."""
    store = get_store()
    unit = store.ds_by_id.get(did) or {}
    kw = set(unit.get("_keywords") or [])
    role = unit.get("role") or ""
    name = unit.get("name") or ""
    return [e for e in store.enhancements_by_detachment.get(detachment_id, [])
            if enhancement_eligible(kw, role, e.get("eligibility_struct") or {}, name)]
