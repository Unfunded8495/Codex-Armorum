"""Single registry of every place an external rules id is stored.

Why this exists
---------------
The model catalogue joins to ``data/w40k/w40k.db`` by an opaque id copied *by
value* into many denormalised places: eight-plus collection.db columns and the
nested id lists inside three JSON files. Each migration script used to hand-list
those locations, so locations got forgotten - ``model_catalogue_resolutions.json``
was skipped on the w40k migration and needed a whole follow-up, and
``photos.datasheet_id`` was never rewritten at all.

This module declares the locations once. Migrations and the catalogue verifier
(``scripts/find_datasheet_gaps.py``) both import :data:`LOCATIONS` and iterate it,
so adding a new id-bearing column is a single new entry here and the verifier
covers it automatically.

Metadata drives policy, it is not just an inventory:

``id_type``    routes validation. ``cat:<MD>`` / ``MD-#####`` values validate
               against the manual catalogue; UUIDs validate against w40k.db.
               (This is what retires the ``cat:MD-50979`` false positive: a
               ``cat:`` value living in a ``datasheet_uuid`` column is classified
               by *value shape*, not by the column's declared type.)
``authority``  ``user_data`` rows must migrate (loss = data loss) and are what the
               zero-tolerance dangling check (check A) gates on. ``derived`` rows
               are rebuilt from rules data on app start (the ``arsenal_*`` tables
               via ``arsenal_store.sync_datasheets``, and the vestigial
               ``photos.datasheet_id``); the gate skips them.
``nullable``   whether an unresolved id may be nulled in place. ``False`` for PK /
               NOT NULL columns, where the only alternative to quarantine is
               deleting the row.

This module imports nothing from the app (no ``data_store`` / ``catalogue_review``)
so any script can import it without dragging in the Flask/render chain.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")

# ---------------------------------------------------------------------------
# id_type tags
DATASHEET_UUID = "datasheet_uuid"
FACTION_UUID = "faction_uuid"
DETACHMENT_UUID = "detachment_uuid"
WEAPON_UUID = "weapon_uuid"
CATALOGUE_MODEL_ID = "catalogue_model_id"

# authority tags
USER_DATA = "user_data"   # must migrate; the dangling gate checks these
DERIVED = "derived"       # rebuilt on app start; the gate skips these

# ---------------------------------------------------------------------------
# id-shape predicates. The verifier routes a value to the right authority by
# its shape first, falling back to the location's declared id_type.

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_MD_RE = re.compile(r"^MD-\d{5,}$")
CAT_PREFIX = "cat:"


def is_uuid(value) -> bool:
    return bool(value) and bool(_UUID_RE.match(str(value)))


def is_cat_id(value) -> bool:
    """A synthetic datasheet-less key, e.g. ``cat:MD-50979``."""
    return bool(value) and str(value).startswith(CAT_PREFIX)


def is_md_id(value) -> bool:
    """A bare manual-catalogue model id, e.g. ``MD-50979``."""
    return bool(value) and bool(_MD_RE.match(str(value)))


def cat_to_md(value) -> str:
    """``cat:MD-50979`` -> ``MD-50979``; a bare ``MD-...`` passes through."""
    s = str(value)
    return s[len(CAT_PREFIX):] if s.startswith(CAT_PREFIX) else s


# Intentional sentinels that are NOT dangling references. ``"unresolved"`` is the
# placeholder the catalogue's faction re-resolve writes for a link-less row it
# could not place (see catalogue_review.py); the gate must not flag it.
FACTION_SENTINELS = frozenset({"unresolved"})


def is_faction_sentinel(value) -> bool:
    return str(value).strip().lower() in FACTION_SENTINELS


# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SqliteLocation:
    table: str
    column: str
    id_type: str
    authority: str
    nullable: bool
    db: str = "collection"
    kind: str = "sqlite"

    @property
    def label(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass(frozen=True)
class JsonLocation:
    filename: str          # relative to data/
    accessor: tuple        # traversal steps; "[]" expands a list
    id_type: str
    authority: str
    nullable: bool
    kind: str = "json"

    @property
    def path(self) -> str:
        return os.path.join(DATA_DIR, self.filename)

    @property
    def label(self) -> str:
        return f"{self.filename}:{'.'.join(self.accessor)}"


# ---------------------------------------------------------------------------
# The inventory. Order is documentation: user-data datasheet refs first (what
# the gate cares about), then faction/detachment/catalogue refs, then derived.

LOCATIONS: tuple = (
    # -- collection.db: datasheet UUID, user data -----------------------------
    SqliteLocation("minis", "datasheet_id", DATASHEET_UUID, USER_DATA, nullable=False),
    SqliteLocation("minis", "unit_bsdata_id", DATASHEET_UUID, USER_DATA, nullable=True),
    SqliteLocation("unit_wip", "datasheet_id", DATASHEET_UUID, USER_DATA, nullable=False),  # PK
    SqliteLocation("unit_wip_photos", "datasheet_id", DATASHEET_UUID, USER_DATA, nullable=False),
    SqliteLocation("custom_box_set_contents", "datasheet_id", DATASHEET_UUID, USER_DATA, nullable=False),
    SqliteLocation("army_units", "datasheet_id", DATASHEET_UUID, USER_DATA, nullable=False),
    SqliteLocation("army_units", "unit_bsdata_id", DATASHEET_UUID, USER_DATA, nullable=True),

    # -- collection.db: faction UUID, user data -------------------------------
    SqliteLocation("favourite_factions", "faction_id", FACTION_UUID, USER_DATA, nullable=False),  # PK
    SqliteLocation("custom_box_sets", "faction_id", FACTION_UUID, USER_DATA, nullable=True),
    SqliteLocation("army_lists", "faction_id", FACTION_UUID, USER_DATA, nullable=False),

    # -- collection.db: detachment UUID (0 rows today; no validator yet) -------
    SqliteLocation("army_lists", "detachment_id", DETACHMENT_UUID, USER_DATA, nullable=True),

    # -- collection.db: catalogue-internal model id (referential only) --------
    SqliteLocation("minis", "catalogue_model_id", CATALOGUE_MODEL_ID, USER_DATA, nullable=True),
    SqliteLocation("custom_box_set_contents", "catalogue_model_id", CATALOGUE_MODEL_ID, USER_DATA, nullable=True),

    # -- collection.db: derived (rebuilt on app start; gate skips) -------------
    # photos.datasheet_id is write-only (every read is WHERE mini_id=?) and is
    # being retired; see scripts/remediate_dangling_refs.py.
    SqliteLocation("photos", "datasheet_id", DATASHEET_UUID, DERIVED, nullable=False),
    SqliteLocation("arsenal_weapon_datasheet", "datasheet_id", DATASHEET_UUID, DERIVED, nullable=True),
    SqliteLocation("arsenal_weapon_datasheet", "unit_bsdata_id", DATASHEET_UUID, DERIVED, nullable=True),
    SqliteLocation("arsenal_weapon", "weapon_bsdata_id", WEAPON_UUID, DERIVED, nullable=True),

    # -- model_catalogue_manual.json ------------------------------------------
    JsonLocation("model_catalogue_manual.json",
                 ("model_releases", "[]", "datasheet_links", "[]", "datasheet_id"),
                 DATASHEET_UUID, USER_DATA, nullable=True),
    JsonLocation("model_catalogue_manual.json",
                 ("model_releases", "[]", "datasheet_links", "[]", "faction_id"),
                 FACTION_UUID, USER_DATA, nullable=True),
    JsonLocation("model_catalogue_manual.json",
                 ("model_releases", "[]", "faction_id"),
                 FACTION_UUID, USER_DATA, nullable=True),

    # -- model_catalogue_resolutions.json -------------------------------------
    JsonLocation("model_catalogue_resolutions.json",
                 ("resolutions", "[]", "datasheet_ids", "[]"),
                 DATASHEET_UUID, USER_DATA, nullable=True),
    JsonLocation("model_catalogue_resolutions.json",
                 ("resolutions", "[]", "catalogue_model_id"),
                 CATALOGUE_MODEL_ID, USER_DATA, nullable=True),

    # -- model_catalogue_images.json ------------------------------------------
    JsonLocation("model_catalogue_images.json",
                 ("images", "[]", "catalogue_model_id"),
                 CATALOGUE_MODEL_ID, USER_DATA, nullable=True),
)


def sqlite_locations(*, authority=None, id_type=None):
    for loc in LOCATIONS:
        if loc.kind != "sqlite":
            continue
        if authority is not None and loc.authority != authority:
            continue
        if id_type is not None and loc.id_type != id_type:
            continue
        yield loc


def json_locations(*, authority=None, id_type=None):
    for loc in LOCATIONS:
        if loc.kind != "json":
            continue
        if authority is not None and loc.authority != authority:
            continue
        if id_type is not None and loc.id_type != id_type:
            continue
        yield loc


# ---------------------------------------------------------------------------
def walk_json(node, accessor):
    """Yield ``(container, key, value)`` for every leaf the accessor reaches.

    ``key`` is a dict key (str) or a list index (int); assigning
    ``container[key] = new`` mutates ``node`` in place, so the same accessor
    serves both the read-only verifier and a rewriting migration.

    ``"[]"`` in the accessor expands the current node as a list. An accessor
    ending in ``"[]"`` yields the list's scalar elements (e.g. the
    ``datasheet_ids`` list), with ``container`` being the list and ``key`` the
    index. Missing keys are skipped silently so a partially-shaped document does
    not raise.
    """
    if not accessor:
        return
    step, rest = accessor[0], accessor[1:]
    if step == "[]":
        if isinstance(node, list):
            for i, item in enumerate(node):
                if rest:
                    yield from walk_json(item, rest)
                else:
                    yield node, i, item
    else:
        if isinstance(node, dict) and step in node:
            child = node[step]
            if rest:
                yield from walk_json(child, rest)
            else:
                yield node, step, child
