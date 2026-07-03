"""Enhancement eligibility — which units may bear a given Enhancement.

``enhancement_eligible`` takes the store's enhancement dict, which carries both
the structured ``eligibility_struct`` (``{required_groups, excluded_keywords}``)
and the per-enhancement rule flags exported from the official app. A bearer is
eligible when it:

* is not on a datasheet whose models bar Enhancements outright
  (``store.enhancement_excluded_ds``, e.g. Ogryn Bodyguard),
* has the ``Character`` keyword — waived when the enhancement is flagged
  ``non_character_eligible`` (e.g. Combat Patrol squad upgrades),
* is **not** an Epic Hero — a core-rules restriction that is *not* encoded in
  the struct (so matching alone would wrongly admit e.g. Belisarius Cawl) —
  waived when the enhancement is flagged ``epic_hero_eligible``,
* matches **at least one** ``required_group``, and
* carries **none** of ``excluded_keywords``.

A ``required_group`` matches when every one of its ``keywords`` is on the unit,
every ``faction_keywords`` entry is present as ``"Faction: <name>"`` (datasheets
store the prefixed form; the struct holds the bare name), and its ``datasheet``
— a **name string**, not a UUID — equals the unit's name when set.
"""
from data_store import get_store


def enhancement_eligible(unit_keywords, role, enh, unit_name=None, datasheet_id=None):
    """True if a unit with these keywords / role / name may take ``enh``.

    ``enh`` is the store's enhancement dict (rule flags + eligibility_struct).
    ``datasheet_id`` enables the model-level Enhancement ban when supplied.
    """
    kw = unit_keywords if isinstance(unit_keywords, set) else set(unit_keywords or [])
    enh = enh or {}
    if datasheet_id and datasheet_id in get_store().enhancement_excluded_ds:
        return False
    if "Character" not in kw and not enh.get("non_character_eligible"):
        return False
    if role == "Epic Hero" and not enh.get("epic_hero_eligible"):
        return False
    struct = enh.get("eligibility_struct") or {}
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
    canonical = unit.get("id") or did
    return [e for e in store.enhancements_by_detachment.get(detachment_id, [])
            if enhancement_eligible(kw, role, e, name, canonical)]
