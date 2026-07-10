"""Loads unit and faction data from the official 40k app SQLite export.

Authoritative source is `data/w40k/w40k.db` (override with `W40K_DB_PATH`), the
exported rules database from the Warhammer 40,000 mobile app. Opened read-only
and immutable so the file can be refreshed under a running app without journal
mismatch.

The external interface (every public attribute and method) matches the previous
Wahapedia-backed loader so consumers in `app.py`, `army.py`, `collection.py`,
`box_sets.py`, `arsenal_store.py` and the SPA keep working unchanged. Faction
and datasheet ids switch to UUID strings; the column names `bsdata_id` and
`unit_bsdata_id` in user data are kept as a legacy misnomer and now hold those
UUIDs.

Faction membership is many-to-many in the new schema: chapters of the Adeptus
Astartes are their own `faction` rows linked to their generic datasheets through
`datasheet_faction`. Each datasheet is reduced to a single primary faction via
the leaf-wins picker (`_pick_primary_faction`), with `PRIMARY_FACTION_OVERRIDES`
covering the handful of explicit exceptions. The legacy "::"-separated chapter
ids and the load-time chapter rollup are gone - chapters are first-class.
"""
import html as _html
import json
import logging
import os
import re
import sqlite3
import unicodedata
from functools import lru_cache

logger = logging.getLogger(__name__)

# Path to the official 40k app data export. Overridable for dev/CI.
W40K_DB_PATH = os.environ.get(
    "W40K_DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "w40k", "w40k.db"),
)

# Battlefield-role display order used when listing a faction's units. Drawn
# from the `keywords` JSON on each datasheet (first match wins).
ROLE_ORDER = [
    "Epic Hero", "Character", "Battleline", "Infantry", "Mounted",
    "Beast", "Monster", "Vehicle", "Swarm", "Transport",
    "Fortification", "Other", "Unaligned",
]

# Prefix used on each unit dict's `_keywords` for faction keywords (so the
# unit-detail page can split keywords into general / faction buckets). Mirrors
# the prefix the old Wahapedia importer wrote.
FACTION_KW_PREFIX = "Faction: "


def foc_category(ds):
    """Force-Org bucket for the army-builder roster's section headers:
    Characters, Battleline, Dedicated Transports, Other Datasheets. Detected
    via keywords (not `role`, which is single-valued and has no
    Dedicated-Transport entry) -- the same source `duplicate_cap()` and
    `is_character` already use, so the three stay in lockstep."""
    kws = set(ds.get("_keywords") or [])
    if ds.get("role") == "Epic Hero" or "Character" in kws:
        return "Characters"
    if "Dedicated Transport" in kws:
        return "Dedicated Transports"
    if "Battleline" in kws:
        return "Battleline"
    return "Other Datasheets"


def _nfkd(s):
    """NFKD-normalise, strip combining marks, and casefold a string for tolerant
    name lookup. Used for the `leads_units` / `can_be_led_by` name resolution;
    covers the `Ûthar the Destined` mismatch in w40k.db data_version 886
    (NFKD decomposes Û to U + combining circumflex; stripping marks lets it
    match a plain `Uthar`)."""
    if not s:
        return ""
    decomposed = unicodedata.normalize("NFKD", s)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_marks.casefold().strip()


def strip_html(text):
    """Inherited from the previous loader - kept for consumers that still pass
    HTML through. The official app data is plain text, so this is mostly a
    no-op now."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"</li>\s*<li[^>]*>", "; ", text, flags=re.I)
    text = re.sub(r"</?(ul|ol)[^>]*>", " ", text, flags=re.I)
    text = re.sub(r"</?li[^>]*>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([:;,.!?])(?=\S)", r"\1 ", text)
    return text.strip()


# Faction-name -> faction-id overrides for datasheets with no membership in
# datasheet_faction, or where the leaf-wins picker disagrees with intent. Filled
# at load time after the faction table is read (we need the UUID).
_PRIMARY_FACTION_OVERRIDE_RULES = [
    # In data_version 886 this datasheet has zero faction memberships but its
    # keywords place it in Death Guard. No "Unaligned" faction row to fall back
    # on, so an explicit override is the only way to land it in the right place.
    ("Maggot Lords Plague Marines", "Death Guard"),
    # Sir Hekhtur (Codex: Imperial Knights, Epic Hero) also ships with zero
    # datasheet_faction rows in data_version 886 - the same gap ListForge shows -
    # and his keywords carry no faction keyword to fall back on. His publication
    # (Codex: Imperial Knights) and every codex-sibling place him in Imperial
    # Knights, so pin him there explicitly.
    ("Sir Hekhtur", "Imperial Knights"),
]


class DataStore:
    def __init__(self):
        self.factions = []
        self.faction_by_id = {}
        # Map UUID -> parent UUID (None for top-level factions). Read from
        # faction.parent_faction.
        self._faction_parent = {}
        # Map parent UUID -> list of child UUIDs (children of a faction in the
        # tree, e.g. Adeptus Astartes -> [Blood Angels, Dark Angels, ...]).
        self._faction_children = {}

        self.datasheets = []
        self.ds_by_id = {}
        self.ds_by_faction = {}
        # Full membership set per datasheet (UUIDs) for parent-aware queries.
        self._ds_factions = {}
        # Explicit faction exclusions (official-app parity): faction UUID ->
        # {datasheet UUID}. Most rows bar a parent-faction generic from a
        # chapter (e.g. Librarians from Black Templars), which parent-aware
        # membership would otherwise admit.
        self._ds_faction_excluded = {}

        self.cost = {}
        self.composition = {}
        self.wargear_options = {}
        self.loadout = {}
        self.wargear = {}
        # Phase 0: structured army-building data surfaced from w40k.db. These
        # were loaded then discarded; the army builder consumes them directly.
        self.battle_sizes = []          # [{name, points_limit, enhancement_limit, ...}]
        self.battle_size_by_name = {}   # name -> battle size dict (O(1) lookup)
        self.composition_tiers = {}     # did -> [{points, is_default, models:[{model,min,max}]}]
        self.wargear_loadout = {}       # did -> {options, choose_from, limited_choices, all_model_choices, ...}
        self.keywords = {}
        self.detachments_by_faction = {}
        self.detachment_by_id = {}
        # detachment_id -> Force Disposition English name (1:1 read-only label).
        self.disposition_by_detachment = {}
        self.enhancements_by_detachment = {}
        self.enhancement_by_id = {}     # str(enhancement id) -> enhancement dict
        # Datasheets whose model rows bar Enhancements outright (e.g. Ogryn
        # Bodyguard) even though keyword matching alone would admit them.
        self.enhancement_excluded_ds = set()
        # Detachment stratagems (keyed by detachment id) plus the universal Core
        # stratagems (Phase 6 surfaces both to the army-builder panels).
        self.stratagems_by_detachment = {}
        self.core_stratagems = []       # the 11 universal stratagems (detachment_id NULL)
        self.leaders_for = {}
        self.led_by = {}
        self.leads = {}
        # Structured leader-attachment groups (official-app enforcement data):
        # leader datasheet id -> [{type: 'leader'|'support', required/excluded
        # detachment, requires_all_units_keyword, member_ids}]. The flat
        # leads/led_by name lists above stay for datasheet display; army
        # building enforces from these groups.
        self.leader_groups = {}
        self.allied_by_host = {}        # host_faction_id -> [ally config dict] (Phase 5b)
        self.army_rules_by_faction = {} # faction_id -> [{id,name,body_text,body_html}] (Phase 6)
        self.missions = {}              # Phase 6 mission reference (Combat Patrol pack excluded)

        # Retained for back-compat with anything that may still test for it.
        # Chapter rollup is gone - chapters are real factions now.
        self.chapter_faction_ids = set()
        self.chapters_by_parent = {}

        self._load()

    # ---- loading -------------------------------------------------------

    def _connect(self):
        if not os.path.exists(W40K_DB_PATH):
            raise RuntimeError(
                f"Official 40k app data export not found at {W40K_DB_PATH}. "
                "See data/w40k/README.md for the refresh procedure."
            )
        uri = f"file:{W40K_DB_PATH}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _load(self):
        conn = self._connect()
        try:
            self._load_factions(conn)
            self._load_datasheets(conn)
            self._load_detachment_data(conn)
            self._load_leader_groups(conn)
            self._load_battle_sizes(conn)
            self._load_army_rules(conn)
            self._load_missions(conn)
        finally:
            conn.close()

    def _load_battle_sizes(self, conn):
        """Load the three battle sizes (Incursion / Strike Force / Onslaught)
        with their points, enhancement and duplicate-unit limits. These drive
        roster legality in the army builder. Sorted ascending by points."""
        try:
            rows = conn.execute(
                "SELECT name, points_limit, detachment_points_limit, "
                "enhancement_limit, duplicate_unit_limit FROM battle_size"
            ).fetchall()
        except sqlite3.OperationalError:
            return
        self.battle_sizes = sorted(
            ({
                "name": r["name"],
                "points_limit": r["points_limit"],
                "detachment_points_limit": r["detachment_points_limit"],
                "enhancement_limit": r["enhancement_limit"],
                "duplicate_unit_limit": r["duplicate_unit_limit"],
            } for r in rows),
            key=lambda b: b["points_limit"] or 0,
        )
        self.battle_size_by_name = {b["name"]: b for b in self.battle_sizes}

    def _load_army_rules(self, conn):
        """Faction-level army rules (e.g. Oath of Moment). 71 faction-linked
        rules in the export; grouped by faction id for the army-rule panel."""
        try:
            rows = conn.execute(
                "SELECT id, faction_id, name, body_text, body_html "
                "FROM army_rule ORDER BY id").fetchall()
        except sqlite3.OperationalError:
            return
        for r in rows:
            self.army_rules_by_faction.setdefault(r["faction_id"], []).append({
                "id": r["id"], "name": r["name"],
                "body_text": r["body_text"] or "", "body_html": r["body_html"] or ""})

    def army_rules_for(self, fid):
        """A faction's army rules, falling back to the parent faction so a
        chapter (e.g. Ultramarines) inherits its parent's rule (Oath of Moment)."""
        own = self.army_rules_by_faction.get(fid)
        if own:
            return own
        parent = self._faction_parent.get(fid)
        if parent:
            return self.army_rules_by_faction.get(parent, [])
        return []

    def _load_missions(self, conn):
        """Mission reference (Phase 6): packs, primary/secondary missions,
        deployments, layouts, presets, twists. The Combat Patrol pack is
        excluded (matched-play reference only), keyed on its localised name."""
        try:
            packs = [{"id": r["id"], "name": r["name"]} for r in
                     conn.execute("SELECT id, name FROM mission_pack ORDER BY name")]
        except sqlite3.OperationalError:
            return
        cp_ids = {p["id"] for p in packs
                  if (p["name"] or "").strip().lower() == "combat patrol"}

        def rows(table, order="name"):
            return [dict(r) for r in
                    conn.execute("SELECT * FROM %s ORDER BY %s" % (table, order)).fetchall()
                    if r["mission_pack_id"] not in cp_ids]

        def with_objectives(table):
            # `objectives` is a JSON blob of period rows, each carrying its own
            # scoring lines (criteria + victory points); decode it to a list.
            out = rows(table)
            for m in out:
                try:
                    m["objectives"] = json.loads(m.get("objectives") or "[]")
                except (TypeError, ValueError):
                    m["objectives"] = []
            return out

        self.missions = {
            "packs":       [p for p in packs if p["id"] not in cp_ids],
            "primary":     with_objectives("mission_primary"),
            "secondary":   with_objectives("mission_secondary"),
            "deployments": rows("mission_deployment"),
            "layouts":     rows("mission_layout"),
            "presets":     rows("mission_preset"),
            "twists":      rows("mission_twist"),
        }

    def _load_factions(self, conn):
        # `name` is the canonical faction keyword (identity / linking / theming).
        # `common_name` is the app's user-facing label when one exists (e.g.
        # "Space Marines" for "Adeptus Astartes"). `display_name` is
        # common_name when set, else name - always populated, safe to use as a
        # blanket display label.
        rows = conn.execute(
            "SELECT id, name, common_name, parent_faction FROM faction "
            "ORDER BY name"
        ).fetchall()
        self.faction_display_by_name = {}
        for r in rows:
            fid = r["id"]
            self._faction_parent[fid] = r["parent_faction"]
            common = r["common_name"] or None
            faction_dict = {
                "id": fid,
                "name": r["name"],
                "common_name": common,
                "display_name": common or r["name"],
                "parent_display_name": None,
                "unit_count": 0,
            }
            self.factions.append(faction_dict)
            self.faction_by_id[fid] = faction_dict
            self.faction_display_by_name[r["name"]] = common or r["name"]
            self.ds_by_faction[fid] = []
        # Build child index. parent_faction holds the parent NAME in this export
        # - translate to the parent UUID.
        name_to_id = {f["name"]: f["id"] for f in self.factions}
        for fid, parent_name in self._faction_parent.items():
            parent_id = name_to_id.get(parent_name) if parent_name else None
            self._faction_parent[fid] = parent_id
            if parent_id:
                self._faction_children.setdefault(parent_id, []).append(fid)
                self.chapters_by_parent.setdefault(parent_id, []).append(fid)
                self.chapter_faction_ids.add(fid)
                self.faction_by_id[fid]["parent_display_name"] = (
                    self.faction_by_id[parent_id].get("display_name") or ""
                )

    def _load_datasheets(self, conn):
        # ---- per-table queries -------------------------------------------------
        ds_rows = conn.execute("""
            SELECT id, name, lore, is_legends, is_free_from_entitlements,
                   keywords, points, default_points, unit_composition_text,
                   wargear_loadout, leads_units, can_be_led_by, damage_brackets,
                   base_size, points_steps
            FROM datasheet
        """).fetchall()

        # datasheet -> [faction_id, ...]
        ds_factions = {}
        for r in conn.execute(
                "SELECT datasheet_id, faction_id FROM datasheet_faction").fetchall():
            ds_factions.setdefault(r["datasheet_id"], []).append(r["faction_id"])
        self._ds_factions = ds_factions

        # Explicit exclusions (tolerate an older export without the table).
        try:
            for r in conn.execute(
                    "SELECT datasheet_id, faction_id FROM datasheet_faction_excluded").fetchall():
                self._ds_faction_excluded.setdefault(
                    r["faction_id"], set()).add(r["datasheet_id"])
        except sqlite3.OperationalError:
            pass

        # datasheet -> [model row, ...]
        models_by_ds = {}
        for r in conn.execute("""SELECT datasheet_id, name, statline_hidden,
                                        m, t, sv, inv, w, ld, oc, keywords
                                 FROM model""").fetchall():
            models_by_ds.setdefault(r["datasheet_id"], []).append(dict(r))

        # datasheet -> abilities by type ({core, faction, datasheet}).
        abilities_by_ds = {}
        for r in conn.execute("""SELECT datasheet_id, name, type, rules
                                 FROM ability""").fetchall():
            abilities_by_ds.setdefault(r["datasheet_id"], []).append(dict(r))

        # datasheet -> extra_rule rows (Leader, Transport, Support, ...). The
        # transport rule is identified by name LIKE 'Transport%' (no type col).
        extras_by_ds = {}
        for r in conn.execute("""SELECT datasheet_id, name, rules
                                 FROM extra_rule""").fetchall():
            extras_by_ds.setdefault(r["datasheet_id"], []).append(dict(r))

        # datasheet -> wargear abilities (Chaos Icon, Gun Drone, ...). These
        # are weapon rows typed 'wargear' whose rule lives in rule_text; most
        # have no weapon_profile rows, so the profile join below never sees
        # them.
        wargear_ab_by_ds = {}
        for r in conn.execute("""SELECT datasheet_id, name, rule_text
                                 FROM weapon
                                 WHERE wargear_type = 'wargear'""").fetchall():
            wargear_ab_by_ds.setdefault(r["datasheet_id"], []).append(
                {"name": r["name"], "description": r["rule_text"] or ""})

        # datasheet -> weapon profiles. Multi-profile weapons (e.g. Plasma
        # pistol standard/supercharge) carry separate profile rows.
        profiles_by_ds = {}
        for r in conn.execute("""
            SELECT w.datasheet_id, w.name w_name, w.wargear_type, w.rule_text,
                   p.name p_name, p.type, p.range, p.attacks, p.bs, p.ws,
                   p.strength, p.ap, p.damage, p.abilities
            FROM weapon w
            JOIN weapon_profile p ON p.weapon_id = w.id
        """).fetchall():
            profiles_by_ds.setdefault(r["datasheet_id"], []).append(dict(r))

        # ---- primary-faction picker setup -------------------------------------
        override_by_name = {}
        for ds_name, target_faction in _PRIMARY_FACTION_OVERRIDE_RULES:
            target_id = next((f["id"] for f in self.factions
                              if f["name"] == target_faction), None)
            if target_id:
                override_by_name[ds_name] = target_id
            else:
                logger.warning(
                    "PRIMARY_FACTION_OVERRIDES: target faction %r not in "
                    "w40k.db; override for %r ignored", target_faction, ds_name)

        # ---- build unit dicts ---------------------------------------------------
        for ds in ds_rows:
            did = ds["id"]
            name = ds["name"]
            memberships = ds_factions.get(did, [])

            # Pick a primary faction. Override > leaf-wins > first membership >
            # None.
            primary_fid = override_by_name.get(name)
            if not primary_fid:
                primary_fid = self._pick_primary_faction(memberships)
            if not primary_fid:
                logger.warning(
                    "Datasheet %r (%s) has no faction membership and no "
                    "override; skipping.", name, did)
                continue

            try:
                ds_keywords = json.loads(ds["keywords"] or "[]")
            except (TypeError, ValueError):
                ds_keywords = []
            role = next((k for k in ROLE_ORDER if k in ds_keywords), "Other")

            try:
                pts_tiers_raw = json.loads(ds["points"] or "[]")
            except (TypeError, ValueError):
                pts_tiers_raw = []
            points_tiers = self._reshape_points_tiers(pts_tiers_raw)

            try:
                damage_brackets_raw = json.loads(ds["damage_brackets"] or "[]")
            except (TypeError, ValueError):
                damage_brackets_raw = []

            # Duplicate-selection surcharge steps ("After the Nth selection of
            # this unit, additional selections each cost +X pts"). At most one
            # step per datasheet in data_version 886.
            try:
                points_steps = json.loads(ds["points_steps"] or "[]")
            except (TypeError, ValueError):
                points_steps = []

            stats = self._build_stats(models_by_ds.get(did, []))
            transport_text = self._extract_transport(extras_by_ds.get(did, []))
            extra_rules = [
                {"name": r["name"], "rules": r["rules"] or ""}
                for r in extras_by_ds.get(did, [])
            ]
            damaged = self._build_damaged(damage_brackets_raw)
            invuln = self._extract_invuln(models_by_ds.get(did, []))
            ability_groups = self._group_abilities(abilities_by_ds.get(did, []))
            ability_groups["invuln_save"] = invuln
            ability_groups["transport"] = transport_text
            ability_groups["damaged"] = damaged
            ability_groups.setdefault("special", [])
            ability_groups["wargear"] = wargear_ab_by_ds.get(did, [])

            ranged, melee = self._build_weapons(profiles_by_ds.get(did, []))

            faction_keywords = [
                FACTION_KW_PREFIX + self.faction_by_id.get(fid, {}).get("name", "")
                for fid in memberships
                if self.faction_by_id.get(fid)
            ]
            combined_keywords = list(ds_keywords) + faction_keywords

            composition = self._parse_composition(ds["unit_composition_text"], name)
            loadout_sentence = self._extract_loadout_sentence(
                ds["unit_composition_text"])

            try:
                wargear_loadout = json.loads(ds["wargear_loadout"] or "{}")
            except (TypeError, ValueError):
                wargear_loadout = {}

            try:
                leads_units = json.loads(ds["leads_units"] or "[]")
            except (TypeError, ValueError):
                leads_units = []
            try:
                led_by_units = json.loads(ds["can_be_led_by"] or "[]")
            except (TypeError, ValueError):
                led_by_units = []

            unit_dict = {
                "id":            did,
                "bsdata_id":     did,
                "name":          name,
                "faction_id":    primary_fid,
                "role":          role,
                "points":        ds["default_points"],
                "_points_tiers": points_tiers if len(points_tiers) > 1 else None,
                "base_size":     ds["base_size"] or "",
                "_points_steps": points_steps,
                "virtual_bool":  False,
                "is_legends_bool": bool(ds["is_legends"]),
                "legend":        ds["lore"] or "",
                "link":          "",
                "_keywords":     combined_keywords,
                "_stats":        stats,
                "_abilities":    ability_groups,
                "_extra_rules":  extra_rules,
                "_ranged":       ranged,
                "_melee":        melee,
                "_composition":  composition,
                "_comp_tiers":   pts_tiers_raw,
                "_options":      wargear_loadout,
                "_loadout":      loadout_sentence,
                "_leads_names":  leads_units,
                "_led_by_names": led_by_units,
            }
            self.ds_by_id[did] = unit_dict
            self.datasheets.append(unit_dict)

            self.ds_by_faction.setdefault(primary_fid, []).append(unit_dict)
            for fid in memberships:
                self._ds_factions.setdefault(did, [])

        # Recompute unit_count from primary-faction assignments.
        for f in self.factions:
            f["unit_count"] = len(self.ds_by_faction.get(f["id"], []))

        # Build the cost / keywords / composition / wargear side indices that
        # the rest of the app reads.
        for u in self.datasheets:
            tiers = u.get("_points_tiers")
            if tiers:
                self.cost[u["id"]] = tiers
            elif u.get("points") is not None:
                self.cost[u["id"]] = [{"cost": u["points"]}]

            kws = u.get("_keywords", [])
            if kws:
                self.keywords[u["id"]] = kws
            if u.get("_composition"):
                self.composition[u["id"]] = u["_composition"]
            if u.get("_comp_tiers"):
                self.composition_tiers[u["id"]] = u["_comp_tiers"]
            options = u.get("_options") or {}
            if options:
                self.wargear_loadout[u["id"]] = options
            rules_text = options.get("rules_text") if isinstance(options, dict) else None
            if rules_text:
                # Surface rules_text as a list of {description: ...} entries so
                # the existing renderOptions UI (which iterates an array of
                # objects with a description-shaped field) works without change.
                self.wargear_options[u["id"]] = [
                    {"description": line} for line in rules_text if line
                ]
            if u.get("_loadout"):
                self.loadout[u["id"]] = u["_loadout"]
            gear = [{"name": w["name"], "type": "melee"} for w in u["_melee"]]
            gear += [{"name": w["name"], "type": "ranged"} for w in u["_ranged"]]
            if gear:
                self.wargear[u["id"]] = gear

        # ---- leader / led-by resolution ---------------------------------------
        self._resolve_leaders()

    # ---- helpers ------------------------------------------------------------

    def _pick_primary_faction(self, memberships):
        """Leaf-wins picker. Drop any faction that is the parent of another in
        the set. Tiebreak by alphabetical name for determinism. Returns None for
        an empty set."""
        if not memberships:
            return None
        if len(memberships) == 1:
            return memberships[0]
        parents = {self._faction_parent.get(fid) for fid in memberships}
        leaves = [fid for fid in memberships if fid not in parents]
        if not leaves:
            leaves = list(memberships)
        if len(leaves) == 1:
            return leaves[0]
        leaves.sort(key=lambda fid: self.faction_by_id.get(fid, {}).get("name", ""))
        return leaves[0]

    @staticmethod
    def _reshape_points_tiers(raw):
        """Convert the points JSON array to the [{cost, description}] shape
        consumers expect. Description is "{lo}-{hi} models" when a range, or
        "{n} models" when fixed. Per-tier `models` is a list summed across all
        model lines so multi-line compositions price correctly."""
        out = []
        for tier in raw:
            cost = tier.get("points")
            models = tier.get("models") or []
            try:
                lo = sum(int(m.get("min") or 0) for m in models)
                hi = sum(int(m.get("max") or 0) for m in models)
            except (TypeError, ValueError):
                lo = hi = 0
            if hi <= 0:
                desc = ""
            elif lo and lo != hi:
                desc = f"{lo}-{hi} models"
            else:
                desc = f"{hi} model{'s' if hi != 1 else ''}"
            out.append({"cost": cost, "description": desc})
        return out

    @staticmethod
    def _build_stats(model_rows):
        """Return a single dict for single-model units, a list of dicts for
        multi-line units. Mirrors the shape the old Wahapedia importer wrote so
        the SPA's renderDatasheetModels() works unchanged."""
        out = []
        for m in model_rows:
            if m.get("statline_hidden"):
                continue
            d = {"name": m["name"]}
            for k_src, k_dst in (("m", "M"), ("t", "T"), ("sv", "SV"),
                                 ("w", "W"), ("ld", "LD"), ("oc", "OC")):
                v = m.get(k_src)
                if v is not None:
                    d[k_dst] = v
            # `inv` sentinel for "no invulnerable save" is NULL in this export.
            inv = m.get("inv")
            if inv:
                d["INV"] = inv
            out.append(d)
        if len(out) == 1:
            return out[0]
        return out

    @staticmethod
    def _extract_invuln(model_rows):
        invs = {m.get("inv") for m in model_rows if m.get("inv")}
        if not invs:
            return ""
        if len(invs) == 1:
            return next(iter(invs))
        # Mixed invuln saves across models - show the strongest (lowest +).
        def _to_int(v):
            try:
                return int(str(v).rstrip("+"))
            except (TypeError, ValueError):
                return 99
        return min(invs, key=_to_int)

    @staticmethod
    def _extract_transport(extra_rows):
        for r in extra_rows:
            if (r.get("name") or "").lower().startswith("transport"):
                return strip_html(r.get("rules") or "")
        return ""

    @staticmethod
    def _build_damaged(damage_brackets):
        if not damage_brackets:
            return {}
        first = damage_brackets[0] or {}
        name = first.get("name") or ""
        # The wounds threshold is embedded in the name string only
        # ("DAMAGED: 1-4 WOUNDS REMAINING"); the SPA's renderDamaged formats it
        # from `damaged_w` and `damaged_description`. Surface the raw name as
        # the threshold so the existing label keeps reading correctly.
        m = re.search(r"(\d+(?:\s*-\s*\d+)?)\s*WOUND", name)
        threshold = m.group(1).replace(" ", "") if m else ""
        return {"name": name, "threshold": threshold,
                "description": first.get("rules") or ""}

    @staticmethod
    def _group_abilities(ability_rows):
        groups = {"core": [], "faction": [], "datasheet": []}
        for r in ability_rows:
            atype = (r.get("type") or "").lower()
            entry = {"name": r["name"], "description": r.get("rules") or ""}
            if atype in groups:
                groups[atype].append(entry)
            else:
                groups["datasheet"].append(entry)
        return groups

    @staticmethod
    def _build_weapons(profile_rows):
        """Group weapon profiles back under their parent weapon so multi-profile
        weapons render with a single name and sub-profile labels (e.g. Plasma
        pistol -> [standard, supercharge]). Falls back to the profile.name when
        the parent weapon has a single profile and the names match."""
        # Bucket profiles by (weapon_name, type). Two passes so a Plasma pistol
        # with two ranged profiles renders together, while a single-profile
        # weapon renders flat.
        grouped = {}
        order = []
        for p in profile_rows:
            key = (p["w_name"], p["type"])
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(p)

        ranged = []
        melee = []
        for key in order:
            profiles = grouped[key]
            w_name, ptype = key
            bucket = melee if ptype == "melee" else ranged
            for p in profiles:
                try:
                    p_keywords = json.loads(p.get("abilities") or "[]")
                except (TypeError, ValueError):
                    p_keywords = []
                p_name = p.get("p_name") or ""
                # When a weapon has multiple profiles, prefix each with the
                # weapon name so the renderer disambiguates.
                if len(profiles) > 1 and p_name and p_name.lower() != w_name.lower():
                    display = f"{w_name} - {p_name}"
                else:
                    display = w_name
                bucket.append({
                    "name":     display,
                    "range":    p.get("range") or "",
                    "A":        p.get("attacks") or "",
                    "BS_WS":    (p.get("bs") or p.get("ws") or ""),
                    "S":        p.get("strength") or "",
                    "AP":       p.get("ap") or "",
                    "D":        p.get("damage") or "",
                    "keywords": ", ".join(p_keywords),
                    "description": p.get("rule_text") or "",
                })
        return ranged, melee

    @staticmethod
    def _parse_composition(text, ds_name):
        """Parse `unit_composition_text` into [{name, min, max}, ...].

        The body is laid out with U+25A0 bullets followed by markdown-bold
        lines like "**1 Commissar**" or "**3-5 Bladeguard Veterans**". Legends
        and boxed-set rows use plain U+2022 bullets ("• 1 Kasrkin Sergeant
        model") instead; rows with no bullet at all fall back to a single raw
        entry so the UI always renders something."""
        if not text:
            return []
        text = _html.unescape(text)
        # Split on either bullet; first segment is empty if the body starts
        # with one.
        segments = [seg.strip() for seg in re.split(r"[■•]", text) if seg.strip()]
        out = []
        for seg in segments:
            # The line "**This model is equipped with: ..." (or the "Every
            # model" / unbolded variants) follows the composition declaration;
            # drop everything from there onward, then strip markdown bold. The
            # composition declaration itself is always a single line, so keep
            # only the first line of the segment - otherwise trailing prose
            # ("\n\nEvery model is ...") leaks into the regex and the count
            # never matches for multi-line compositions like Tactical Squad.
            head = re.split(r"equipped with", seg, maxsplit=1,
                            flags=re.IGNORECASE)[0]
            head = head.splitlines()[0] if head else ""
            head = re.sub(r"\*\*(.*?)\*\*", r"\1", head)
            head = head.strip().strip("–-").strip()
            # Dash class covers the Unicode hyphens (U+2010/U+2011) some
            # sheets use in ranges like "4‐9 Acolyte Hybrids".
            m = re.match(r"^\s*(\d+)(?:\s*[-‐‑‒–—]\s*(\d+))?\s+(.+?)\s*$", head)
            if not m:
                continue
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else lo
            name = m.group(3)
            # Drop trailing "– EPIC HERO" style epithets and footnote stars
            # ("1-2 Atalan Wolfquads*").
            name = re.split(r"\s+[–-]\s+", name, maxsplit=1)[0].strip().rstrip("*").strip()
            out.append({"name": name, "min": lo, "max": hi})
        if not out:
            # Last-ditch fallback: surface the raw description as a single
            # composition entry. The SPA renders the name verbatim.
            return [{"name": ds_name, "min": 1, "max": 1}]
        return out

    @staticmethod
    def _extract_loadout_sentence(text):
        """Return the loadout prose of unit_composition_text - every
        "**The X is equipped with:** ..." sentence plus any designer's note -
        as HTML, one <br>-separated line each, with markdown bold/italic
        converted. The bolded lead-in is kept: the official app prints these
        lines verbatim under Unit Composition, and a datasheet can carry
        several of them (e.g. Boyz have a Boss Nob clause and an Every Boy
        clause). Composition declarations ("■ **1 Boss Nob**") are dropped
        here; `_parse_composition` owns those."""
        if not text:
            return ""
        kept = []
        for line in _html.unescape(text).replace("\r\n", "\n").splitlines():
            # A leading "* " is a bullet marker (Neurogaunts' note), not an
            # italic opener - italics hug their text ("*This unit...*").
            line = re.sub(r"^\*\s+", "", line.strip())
            if not line:
                continue
            stripped = re.sub(r"\*\*(.*?)\*\*", r"\1", line).strip()
            # Any ■/• line is a composition declaration (verified: none carry
            # loadout prose), as is a bare "N Name" / "N-M Name" line.
            if stripped.startswith(("■", "•")):
                continue
            bare = stripped.lstrip("■•").strip()
            if (re.match(r"^\d+(?:\s*[-‐‑‒–—]\s*\d+)?\s+\S", bare)
                    and "equipped with" not in bare.lower()):
                continue
            # "OR" between alternative composition declarations (Cadian Shock
            # Troops) belongs to the composition block, not the loadout.
            if bare.lower() in ("or", "and"):
                continue
            kept.append(line)
        out = []
        for line in kept:
            h = _html.escape(line, quote=False)
            h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
            h = re.sub(r"\*(.+?)\*", r"<i>\1</i>", h)
            # A few sheets use unbalanced footnote asterisks ("**This unit can
            # only contain 2 Gun Servitors...*"); drop whatever survives the
            # markdown conversion rather than showing markup debris.
            out.append(h.replace("*", ""))
        return "<br>".join(out)

    def _resolve_leaders(self):
        """Resolve `leads_units` and `can_be_led_by` name lists to UUIDs using
        NFKD-normalised, case-insensitive name lookup. Tries the leader's
        faction tree first (primary, parent, parent's other children, own
        children); if that misses, falls back to a global by-name index so
        cross-tree links such as Ynnari characters leading Asuryani units
        resolve. Names that still don't resolve are kept in their string form
        so the unit-detail UI can render them as plain (non-linked) text."""
        # Pre-index ds-by-name within faction trees so each resolver call is
        # O(1) instead of O(N).
        by_tree = {}
        by_name = {}
        for u in self.datasheets:
            n = _nfkd(u["name"])
            by_name.setdefault(n, []).append(u["id"])
            for tree_root in self._faction_tree_roots(u["faction_id"]):
                by_tree.setdefault(tree_root, {}).setdefault(
                    n, []).append(u["id"])

        leaders_for_name = {}
        led_by_id = {}
        leads_id = {}
        unresolved = []

        for u in self.datasheets:
            leader_id = u["id"]
            leader_name = u["name"]
            tree_root = self._tree_root(u["faction_id"])
            tree_index = by_tree.get(tree_root, {})

            resolved_leads = []
            for raw_name in u.get("_leads_names") or []:
                n = _nfkd(raw_name)
                matches = tree_index.get(n) or by_name.get(n, [])
                if matches:
                    for target_id in matches:
                        target = self.ds_by_id.get(target_id)
                        if not target:
                            continue
                        resolved_leads.append(
                            {"id": target_id, "name": target["name"]})
                        leaders_for_name.setdefault(
                            target["name"], []).append(leader_name)
                        led_by_id.setdefault(target_id, []).append(leader_id)
                else:
                    resolved_leads.append({"id": None, "name": raw_name})
                    unresolved.append(("leads_units", leader_name, raw_name))
            if resolved_leads:
                leads_id[leader_id] = resolved_leads

            for raw_name in u.get("_led_by_names") or []:
                n = _nfkd(raw_name)
                if not (tree_index.get(n) or by_name.get(n)):
                    unresolved.append(("can_be_led_by", leader_name, raw_name))

        self.leaders_for = leaders_for_name
        self.led_by = led_by_id
        self.leads = leads_id

        if unresolved:
            logger.warning(
                "Leader resolver: %d unresolved name(s); first 10: %s",
                len(unresolved), unresolved[:10])

    def _resolve_group_members(self, ids, keywords, leader_did=None):
        """Datasheet-id set for a leader-attachment group's membership: the
        explicit id list (filtered to loaded datasheets) plus keyword-based
        membership - every datasheet carrying ALL of the group's keywords
        (e.g. Inquisitor Draxus leads any Imperium + Battleline + Infantry
        unit). The leader itself never qualifies as its own bodyguard."""
        members = {i for i in (ids or []) if i in self.ds_by_id}
        kws = {k for k in (keywords or []) if k}
        if kws:
            for u in self.datasheets:
                if u["id"] != leader_did and kws <= set(u.get("_keywords") or []):
                    members.add(u["id"])
        return members

    def _load_leader_groups(self, conn):
        """Leader-attachment groups from the `leader_group` table (exporter v3),
        which keep the enforcement conditions the flat leads/led_by name lists
        lose: bodyguard_type ('leader' fills the unit's single Leader slot,
        'support' attaches alongside it), required/excluded detachment, the
        "all units in the party share keyword X" gate, and keyword-based
        membership. Also stitches each enhancement's grants_leader_attachment
        onto its dict as `leader_grants` (same group shape, no conditions).
        Tolerates an older export without the table/column."""
        try:
            rows = conn.execute(
                "SELECT id, datasheet_id, bodyguard_type, required_detachment_id, "
                "excluded_detachment_id, requires_all_units_keyword, "
                "member_datasheet_ids, member_keywords FROM leader_group").fetchall()
        except sqlite3.OperationalError:
            return
        for r in rows:
            if r["datasheet_id"] not in self.ds_by_id:
                continue
            try:
                ids = json.loads(r["member_datasheet_ids"] or "[]")
            except (TypeError, ValueError):
                ids = []
            try:
                kws = json.loads(r["member_keywords"] or "[]")
            except (TypeError, ValueError):
                kws = []
            self.leader_groups.setdefault(r["datasheet_id"], []).append({
                "id": r["id"],
                "type": r["bodyguard_type"] or "leader",
                "required_detachment_id": r["required_detachment_id"],
                "excluded_detachment_id": r["excluded_detachment_id"],
                "requires_all_units_keyword": r["requires_all_units_keyword"],
                "member_ids": self._resolve_group_members(ids, kws, r["datasheet_id"]),
            })
        try:
            grant_rows = conn.execute(
                "SELECT id, grants_leader_attachment FROM enhancement "
                "WHERE grants_leader_attachment IS NOT NULL "
                "AND grants_leader_attachment != '[]'").fetchall()
        except sqlite3.OperationalError:
            return
        for r in grant_rows:
            enh = self.enhancement_by_id.get(str(r["id"]))
            if not enh:
                continue
            try:
                raw = json.loads(r["grants_leader_attachment"] or "[]")
            except (TypeError, ValueError):
                continue
            grants = [{
                "id": None,
                "type": g.get("type") or "leader",
                "required_detachment_id": None,
                "excluded_detachment_id": None,
                "requires_all_units_keyword": None,
                "member_ids": self._resolve_group_members(
                    g.get("datasheet_ids"), g.get("keywords")),
            } for g in raw if isinstance(g, dict)]
            if grants:
                enh["leader_grants"] = grants

    def _tree_root(self, fid):
        """Walk up parent_faction until the top. Used to scope leader-name
        resolution to a faction tree."""
        seen = set()
        cur = fid
        while cur and cur not in seen:
            seen.add(cur)
            parent = self._faction_parent.get(cur)
            if not parent:
                return cur
            cur = parent
        return fid

    def _faction_tree_roots(self, fid):
        """Tree roots a unit's leader resolver searches: its own faction, its
        parent if any, and the parent's children. So a Blood Angels unit can
        lead a generic Adeptus Astartes unit (and vice versa)."""
        roots = {fid}
        parent = self._faction_parent.get(fid)
        if parent:
            roots.add(parent)
            roots.update(self._faction_children.get(parent, []))
        # Also pull in own children (so a parent's resolver reaches chapter
        # datasheets). Cheap - most factions have no children.
        roots.update(self._faction_children.get(fid, []))
        return roots

    # ---- detachments ---------------------------------------------------

    def _load_detachment_data(self, conn):
        """Populate detachments_by_faction, detachment_by_id,
        enhancements_by_detachment, stratagems_by_detachment from w40k.db."""
        det_factions = {}
        for r in conn.execute(
                "SELECT detachment_id, faction_id FROM detachment_faction").fetchall():
            det_factions.setdefault(r["detachment_id"], []).append(r["faction_id"])

        det_rules = {}
        for r in conn.execute("""SELECT detachment_id, name, body_text
                                 FROM detachment_rule""").fetchall():
            det_rules.setdefault(r["detachment_id"], []).append(
                {"name": r["name"], "description": r["body_text"] or ""})

        for r in conn.execute("""SELECT id, name, is_combat_patrol,
                                        detachment_points_cost, restrictions,
                                        unlocks_datasheets, excludes_datasheets
                                 FROM detachment""").fetchall():
            did = r["id"]
            memberships = det_factions.get(did, [])
            primary_fid = self._pick_primary_faction(memberships) or ""
            try:
                restrictions = json.loads(r["restrictions"] or "[]")
            except (TypeError, ValueError):
                restrictions = []
            try:
                unlocks = json.loads(r["unlocks_datasheets"] or "[]")
            except (TypeError, ValueError):
                unlocks = []
            try:
                excludes = json.loads(r["excludes_datasheets"] or "[]")
            except (TypeError, ValueError):
                excludes = []
            det = {
                "id":            did,
                "name":          r["name"],
                "faction_id":    primary_fid,
                "points_cost":   r["detachment_points_cost"] or 0,
                "restrictions":  restrictions,
                "rules":         det_rules.get(did, []),
                "unlocks_datasheets": unlocks,
                "excludes_datasheets": excludes,
                "is_combat_patrol":  bool(r["is_combat_patrol"]),
            }
            self.detachment_by_id[did] = det
            for fid in memberships:
                self.detachments_by_faction.setdefault(fid, []).append(det)

        # Force Disposition: a read-only label derived 1:1 from the detachment.
        # detachment_id -> English disposition name (e.g. "Take and Hold").
        for r in conn.execute(
                "SELECT d.detachment_id detachment_id, f.name name "
                "FROM detachment_force_disposition d "
                "JOIN force_disposition f ON f.id = d.force_disposition_id"
        ).fetchall():
            self.disposition_by_detachment[r["detachment_id"]] = r["name"]

        for r in conn.execute("""SELECT id, detachment_id, name, points, type,
                                        rules_text, eligibility_text, eligibility,
                                        take_limit, counts_toward_limit,
                                        epic_hero_eligible, non_character_eligible,
                                        cannot_be_warlord
                                 FROM enhancement""").fetchall():
            try:
                eligibility_struct = json.loads(r["eligibility"] or "{}")
            except (TypeError, ValueError):
                eligibility_struct = {}
            enh = {
                "id":            r["id"],
                "name":          r["name"],
                "cost":          r["points"] or 0,
                "detachment_id": r["detachment_id"],
                "description":   r["rules_text"] or "",
                "type":          r["type"] or "",
                "eligibility":   r["eligibility_text"] or "",
                "eligibility_struct": eligibility_struct,
                # Per-enhancement rule flags (exporter v3). take_limit is how
                # many copies one army may field (1 = unique, 3 for some
                # Upgrade-type enhancements); counts_toward_limit=False rows
                # are free with respect to the battle-size enhancement cap.
                "take_limit":    r["take_limit"] or 1,
                "counts_toward_limit": bool(r["counts_toward_limit"]
                                            if r["counts_toward_limit"] is not None else 1),
                "epic_hero_eligible":   bool(r["epic_hero_eligible"]),
                "non_character_eligible": bool(r["non_character_eligible"]),
                "cannot_be_warlord":    bool(r["cannot_be_warlord"]),
            }
            self.enhancements_by_detachment.setdefault(
                r["detachment_id"], []).append(enh)
            self.enhancement_by_id[str(r["id"])] = enh

        # Model-level Enhancement bans (exporter v3): a flagged model bars its
        # whole datasheet from every Enhancement (all four flagged models are
        # their datasheet's only model). Restricted to loaded datasheets - a
        # sheet the datasheet loader skipped (e.g. Sir Hekhtur, no faction
        # membership) can never be picked, so its ban is moot.
        self.enhancement_excluded_ds = {
            r["datasheet_id"] for r in conn.execute(
                "SELECT DISTINCT datasheet_id FROM model "
                "WHERE excluded_from_enhancements=1").fetchall()
            if r["datasheet_id"] in self.ds_by_id}

        for r in conn.execute("""SELECT id, detachment_id, name, cp_cost,
                                        category, used_when, phases, when_text,
                                        target_text, effect_text,
                                        restriction_text, lore
                                 FROM stratagem ORDER BY id""").fetchall():
            row = dict(r)
            if r["detachment_id"]:
                self.stratagems_by_detachment.setdefault(
                    r["detachment_id"], []).append(row)
            else:
                self.core_stratagems.append(row)   # universal (Phase 6)

        # Allied factions (Phase 5b): each host faction's allowed ally configs.
        ally_hosts = {}      # allied_faction_id -> [host_faction_id]
        for r in conn.execute("SELECT allied_faction_id, host_faction_id FROM allied_faction_host"):
            ally_hosts.setdefault(r["allied_faction_id"], []).append(r["host_faction_id"])
        ally_dids = {}       # allied_faction_id -> {datasheet_id}
        for r in conn.execute("SELECT allied_faction_id, datasheet_id FROM allied_faction_datasheet"):
            if r["datasheet_id"]:
                ally_dids.setdefault(r["allied_faction_id"], set()).add(r["datasheet_id"])
        for r in conn.execute("""SELECT id, ally_factions, can_take_enhancements,
                                        mutually_exclusive_keyword_limit, keyword_limits,
                                        points_limits, required_detachments
                                 FROM allied_faction"""):
            try:
                ally_names = json.loads(r["ally_factions"] or "[]")
                cfg = {
                    "id": r["id"],
                    "ally_faction_names": ally_names,
                    # User-facing variants (Legiones Daemonica -> Chaos Daemons
                    # etc.); ally_faction_names stays canonical for matching.
                    "ally_faction_display_names": [
                        self.faction_display_by_name.get(n, n) for n in ally_names],
                    "datasheet_ids": ally_dids.get(r["id"], set()),
                    "can_take_enhancements": bool(r["can_take_enhancements"]),
                    "mutually_exclusive_keyword_limit": r["mutually_exclusive_keyword_limit"] or 0,
                    "keyword_limits": json.loads(r["keyword_limits"] or "[]"),
                    "points_limits": json.loads(r["points_limits"] or "[]"),
                    "required_detachments": json.loads(r["required_detachments"] or "[]"),
                }
            except (TypeError, ValueError):
                continue
            for host_fid in ally_hosts.get(r["id"], []):
                self.allied_by_host.setdefault(host_fid, []).append(cfg)

    # ---- queries -------------------------------------------------------

    def faction_parent(self, fid):
        """Parent faction id, or the input id when there is no parent."""
        parent = self._faction_parent.get(fid)
        return parent if parent else fid

    def allied_configs(self, host_fid):
        """Ally configs available to a host faction, with a parent-faction fallback
        (mirrors detachment eligibility) so a chapter inherits its parent's allies.
        De-duplicated by config id — a chapter that is itself a host shares configs
        with its parent."""
        seen, out = set(), []
        for fid in (host_fid, self.faction_parent(host_fid)):
            for cfg in self.allied_by_host.get(fid, []):
                if cfg["id"] not in seen:
                    seen.add(cfg["id"])
                    out.append(cfg)
        return out

    def ally_config_for(self, host_fid, did):
        """The ally config that makes datasheet ``did`` an allowed ally of host
        faction ``host_fid`` (parent fallback), or ``None``."""
        for cfg in self.allied_configs(host_fid):
            if did in cfg["datasheet_ids"]:
                return cfg
        return None

    def is_chapter_faction(self, fid):
        """True when fid has a parent_faction (i.e. lives one level down from a
        top-level faction)."""
        return bool(fid) and bool(self._faction_parent.get(fid))

    def detachments_for_faction(self, fid):
        """Detachments for a faction id, falling back to the parent's pool. A
        chapter card with no detachments of its own inherits the full parent
        pool - codex-divergent chapters get a slightly wider list than strict
        canon, accepted simplification."""
        own = self.detachments_by_faction.get(fid)
        if own:
            return own
        parent = self._faction_parent.get(fid)
        if parent:
            return self.detachments_by_faction.get(parent, [])
        return []

    def faction_list(self):
        out = []
        for f in self.factions:
            sheets = self.ds_by_faction.get(f["id"], [])
            if not sheets:
                continue
            out.append({
                "id": f["id"],
                "name": f["name"],
                "display_name": f.get("display_name") or f["name"],
                "parent_display_name": f.get("parent_display_name") or "",
                "unit_count": len(sheets),
            })
        out.sort(key=lambda x: x["name"])
        return out

    def units_for_faction(self, fid):
        """Strict membership: units whose primary faction equals fid. A chapter
        card shows chapter-specifics only; the parent card shows generics only.
        Used for the faction-grid display."""
        sheets = self.ds_by_faction.get(fid, [])
        units = []
        for d in sheets:
            units.append({
                "id":     d["id"],
                "name":   d["name"],
                "role":   d.get("role") or "Other",
                "points": self._cheapest_points(d["id"]),
                "foc_category": foc_category(d),
            })
        units.sort(key=lambda u: (_role_rank(u["role"]), u["name"]))
        return units

    def units_in_faction_tree(self, fid):
        """Units whose primary faction equals fid, plus units whose primary
        faction is a child of fid. Used by box/army matching: a Space-Marines-
        tagged box accepts Blood Angels units too."""
        units = self.units_for_faction(fid)
        children = self._faction_children.get(fid, [])
        for cid in children:
            units += self.units_for_faction(cid)
        units.sort(key=lambda u: (_role_rank(u["role"]), u["name"]))
        return units

    def selectable_units_for_army(self, fid):
        """Units a chapter army can field: its own units plus its parent's
        generics (one level up). Falls through to `units_for_faction` for a
        top-level faction. Without this, a Blood Angels army would not be
        offered Tactical Squad or any generic Space Marine unit - a regression
        against the old chapter-rollup behaviour."""
        units = self.units_for_faction(fid)
        parent = self._faction_parent.get(fid)
        if parent:
            units += self.units_for_faction(parent)
        # Dedupe by id while preserving sort, and drop explicit exclusions
        # (official-app parity: e.g. Black Templars are barred from Librarians
        # even though the parent tree would offer them).
        excluded = self._ds_faction_excluded.get(fid, ())
        seen = set()
        deduped = []
        for u in units:
            if u["id"] in seen or u["id"] in excluded:
                continue
            seen.add(u["id"])
            deduped.append(u)
        deduped.sort(key=lambda u: (_role_rank(u["role"]), u["name"]))
        return deduped

    def unit_in_faction(self, did, fid):
        """True when the unit is a member of fid, or fid is the parent of the
        unit's primary faction. Driven by datasheet_faction membership so a
        Blood Angels unit returns True for both Blood Angels and Adeptus
        Astartes. Explicit exclusions veto everything: a datasheet barred from
        fid is never in it, however the tree would resolve."""
        if did in self._ds_faction_excluded.get(fid, ()):
            return False
        memberships = self._ds_factions.get(did, [])
        if fid in memberships:
            return True
        for m in memberships:
            if self._faction_parent.get(m) == fid:
                return True
        # Cover the primary-faction-only case (e.g. when the override removed
        # the datasheet from datasheet_faction entirely).
        d = self.ds_by_id.get(did)
        if d:
            primary = d.get("faction_id")
            if primary == fid or self._faction_parent.get(primary) == fid:
                return True
        return False

    def _cheapest_points(self, did):
        costs = [_int(c.get("cost")) for c in self.cost.get(did, [])
                 if _int(c.get("cost"))]
        return min(costs) if costs else None

    def unit_detail(self, did):
        d = self.ds_by_id.get(did)
        if not d:
            return None
        kws = d.get("_keywords", [])
        fkw = [k for k in kws if k.startswith(FACTION_KW_PREFIX)]
        kw = [k for k in kws if not k.startswith(FACTION_KW_PREFIX)]
        composition = self.composition.get(d["id"], [])
        if not composition and isinstance(d.get("_stats"), dict) and d["_stats"]:
            composition = [{"name": d["name"], "min": 1, "max": 1}]
        abilities = d.get("_abilities") or {}
        damaged = abilities.get("damaged") or {}
        fac = self.faction_by_id.get(d["faction_id"], {})
        return {
            "id":                  d["id"],
            "name":                d["name"],
            "faction_id":          d["faction_id"],
            "faction_name":        fac.get("name", ""),
            "faction_display_name": fac.get("display_name") or fac.get("name", ""),
            "faction_parent_display_name": fac.get("parent_display_name") or "",
            "role":                d.get("role") or "Other",
            "legend":              d.get("legend") or "",
            "loadout":             self.loadout.get(d["id"], ""),
            "link":                d.get("link") or "",
            "transport":           abilities.get("transport") or "",
            "damaged_w":           damaged.get("threshold", ""),
            "damaged_description": damaged.get("description", ""),
            "led_by":              [{"id": lid, "name": self.ds_by_id[lid]["name"]}
                                    for lid in self.led_by.get(d["id"], [])
                                    if lid in self.ds_by_id],
            "leads":               self.leads.get(d["id"], []),
            "abilities":           d.get("_abilities") or {},
            "models":              d.get("_stats") or [],
            "costs":               self.cost.get(d["id"], []),
            "base_size":           d.get("base_size") or "",
            "points_steps":        d.get("_points_steps") or [],
            "composition":         composition,
            "options":             self.wargear_options.get(d["id"], []),
            "ranged":              d.get("_ranged", []),
            "melee":               d.get("_melee", []),
            "keywords":            kw,
            "faction_keywords":    fkw,
        }


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _role_rank(role):
    try:
        return ROLE_ORDER.index(role)
    except ValueError:
        return len(ROLE_ORDER)


@lru_cache(maxsize=1)
def get_store():
    return DataStore()
