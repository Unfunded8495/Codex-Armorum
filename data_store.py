"""Loads unit and faction data from the Wahapedia-sourced SQLite catalogue tables.

Sourced from catalogue_factions, catalogue_units, catalogue_weapons, and
catalogue_unit_weapons (populated by wahapedia_importer.py from the Wahapedia
CSV export). The column names bsdata_id / unit_bsdata_id are kept as a legacy
misnomer: they now hold native Wahapedia ids (9-digit datasheet ids and faction
short codes such as "CSM").

The external interface (every public attribute and method) is unchanged so all
consuming modules continue to work; only the data source and the id values
differ from the previous BSData version.

Chapter rollup (Space Marines):
    Wahapedia carries one Space Marines faction code, "SM", holding every chapter
    (Blood Angels, Dark Angels, Space Wolves, Deathwatch, Black Templars, and the
    codex chapters). This module derives a per-chapter "faction" card at load
    time from the faction keywords present on SM datasheets, so each chapter is
    its own browsable, favouritable card whose datasheets are the chapter-specific
    ones, while generic Space Marine datasheets stay under Space Marines.

    The rollup is purely load-time and data-driven. The importer stays unaware of
    chapters and writes no chapter rows: after any CSV reimport this module
    rebuilds the chapter cards from whatever keywords the fresh data carries.
    Chapter faction ids are deterministic and stable (parent code, "::", chapter
    keyword, e.g. "SM::Blood Angels") so favourites, box tags and army faction
    references that persist in collection.db keep resolving across reimports.
"""
import json
import logging
import os
import re
import sqlite3
from functools import lru_cache

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "collection.db")

# Battlefield-role display order used when listing a faction's units.
ROLE_ORDER = [
    "Epic Hero", "Character", "Battleline", "Infantry", "Mounted",
    "Beast", "Monster", "Vehicle", "Swarm", "Transport",
    "Fortification", "Other", "Unaligned",
]

# ---------------------------------------------------------------------------
# Chapter rollup configuration
# ---------------------------------------------------------------------------
# Faction codes that get the chapter rollup. Only Space Marines for now. The
# mechanism is parameterised by parent code so it is extensible, but the Chaos
# legions and Aeldari subfactions already have their own Wahapedia codes and need
# no rollup.
PARENT_FACTIONS = {"SM"}

# Universal faction keywords that are never a chapter. At runtime this is also
# unioned with every real faction name (so cross-faction tags that equal a
# faction name are dropped too). "Agents of the Imperium" is listed explicitly
# because the real faction is named "Imperial Agents", so the faction-name rule
# alone would not catch this cross-faction tag (it appears on Kill Team Cassius).
CHAPTER_KEYWORD_EXCLUDE = {"Adeptus Astartes", "Imperium", "Agents of the Imperium"}

# Optional curated set of chapter keywords to surface. Empty means surface every
# detected chapter (fully data-driven). The owner can trim this later without
# touching logic.
CHAPTER_ALLOWLIST = set()

# Used only by the load-time assertion: if any of these does not resolve to a
# non-empty chapter card after the rollup, a single prominent warning is logged
# (the Wahapedia keyword structure may have changed). The app still starts.
CORE_EXPECTED_CHAPTERS = {"Blood Angels", "Dark Angels", "Space Wolves",
                          "Deathwatch", "Black Templars"}

# data_store stores faction keywords on each unit dict with this prefix (set by
# wahapedia_importer.build_keywords from is_faction_keyword=true rows).
FACTION_KW_PREFIX = "Faction: "

# The separator in a synthetic chapter faction id. Cannot occur in a real
# Wahapedia faction code, so there is no collision risk.
CHAPTER_SEP = "::"


def strip_html(text):
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
    text = re.sub(r"(^|[^A-Za-z-])(\d+)\s*-\s*(\d+)\b",
                  lambda m: m.group(1) + m.group(2) + "–" + m.group(3), text)
    return text.strip()


class DataStore:
    def __init__(self):
        self.factions = []
        self.faction_by_id = {}
        self.datasheets = []
        self.ds_by_id = {}
        self.ds_by_faction = {}
        self.cost = {}
        self.composition = {}
        self.wargear_options = {}
        self.loadout = {}
        self.wargear = {}
        self.keywords = {}
        self.detachments_by_faction = {}
        self.detachment_by_id = {}
        self.enhancements_by_detachment = {}
        self.leaders_for = {}
        self.led_by = {}
        self.leads = {}
        # Chapter rollup bookkeeping (populated by _apply_chapter_rollup).
        self.chapter_faction_ids = set()
        self.chapters_by_parent = {}
        # MFM overlay version tag, set by _apply_mfm_overrides ("" when off or
        # not imported). Surfaced on the unit detail payload for the points stamp.
        self.mfm_version = ""
        self._load()

    def _load(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        all_fac_rows = conn.execute(
            "SELECT bsdata_id, name FROM catalogue_factions ORDER BY name"
        ).fetchall()

        all_unit_rows = conn.execute(
            "SELECT bsdata_id, faction_id, name, role, points, virtual,"
            "       legend, link, loadout,"
            "       stats_json, abilities_json, keywords_json, points_tiers_json,"
            "       composition_json, wargear_options_json, leader_targets_json"
            " FROM catalogue_units"
        ).fetchall()

        all_weapon_rows = conn.execute("""
            SELECT cuw.unit_id,
                   cw.name        w_name,
                   cw.weapon_type,
                   cw.range,
                   cw.attacks,
                   cw.skill,
                   cw.strength,
                   cw.ap,
                   cw.damage,
                   cw.keywords    w_keywords,
                   cw.description w_description
            FROM catalogue_unit_weapons cuw
            JOIN catalogue_weapons cw ON cw.bsdata_id = cuw.weapon_id
        """).fetchall()

        conn.close()

        # --- index weapons by unit_id ---
        weapons_by_unit = {}
        for w in all_weapon_rows:
            weapons_by_unit.setdefault(w["unit_id"], []).append(w)

        # --- build unit dicts keyed by Wahapedia datasheet id ---
        raw_units = {}
        for u in all_unit_rows:
            did = u["bsdata_id"]
            kws = json.loads(u["keywords_json"]) if u["keywords_json"] else []
            stats = json.loads(u["stats_json"]) if u["stats_json"] else {}
            abilities = json.loads(u["abilities_json"]) if u["abilities_json"] else {}
            points_tiers = (json.loads(u["points_tiers_json"])
                            if u["points_tiers_json"] else None)
            leader_targets = (json.loads(u["leader_targets_json"])
                              if u["leader_targets_json"] else [])

            ranged = []
            melee = []
            for w in weapons_by_unit.get(did, []):
                entry = {
                    "name":     w["w_name"],
                    "range":    w["range"] or "",
                    "A":        w["attacks"] or "",
                    "BS_WS":    w["skill"] or "",
                    "S":        w["strength"] or "",
                    "AP":       w["ap"] or "",
                    "D":        w["damage"] or "",
                    "keywords": w["w_keywords"] or "",
                    "description": w["w_description"] or "",
                }
                if w["weapon_type"] == "melee":
                    melee.append(entry)
                else:
                    ranged.append(entry)

            unit_dict = {
                "id":            did,
                "bsdata_id":     did,
                "name":          u["name"],
                "faction_id":    u["faction_id"],
                "role":          u["role"] or "Other",
                "points":        u["points"],
                "_points_tiers": points_tiers,
                "virtual_bool":  bool(u["virtual"]),
                "legend":        u["legend"] or "",
                "link":          u["link"] or "",
                "_keywords":     kws,
                "_stats":        stats,
                "_abilities":    abilities,
                "_ranged":       ranged,
                "_melee":        melee,
                "_composition":  (json.loads(u["composition_json"])
                                  if u["composition_json"] else None),
                "_options":      (json.loads(u["wargear_options_json"])
                                  if u["wargear_options_json"] else None),
                "_loadout":      u["loadout"],
                "_leader_targets": leader_targets,
            }
            raw_units[did] = unit_dict

        # --- process factions: a unit belongs to a faction when its faction_id
        #     equals the faction code (Wahapedia carries this directly) ---
        units_by_faction = {}
        for u in raw_units.values():
            units_by_faction.setdefault(u["faction_id"], []).append(u)

        for row in all_fac_rows:
            fid = row["bsdata_id"]
            name = row["name"]
            faction_units = units_by_faction.get(fid, [])
            if not faction_units:
                continue
            faction_dict = {
                "id":         fid,
                "name":       name,
                "unit_count": len(faction_units),
            }
            self.factions.append(faction_dict)
            self.faction_by_id[fid] = faction_dict
            for u in faction_units:
                self.ds_by_faction.setdefault(fid, []).append(u)
                self.ds_by_id[u["id"]] = u

        self.datasheets = list(self.ds_by_id.values())

        # Derive the Space Marine chapter cards from the faction keywords now that
        # the base factions and units are built. Real faction names feed the
        # exclude rule, so capture them before any synthetic chapter is added.
        real_faction_names = {row["name"] for row in all_fac_rows}
        self._apply_chapter_rollup(real_faction_names)

        # cost: {did: [{"cost": points, "description": label}]}: used by the
        # datasheet Points section and the army builder. Multi-size units carry
        # per-size tiers; everything else is a single base price.
        for u in self.datasheets:
            tiers = u.get("_points_tiers")
            if tiers:
                self.cost[u["id"]] = tiers
            elif u.get("points") is not None:
                self.cost[u["id"]] = [{"cost": u["points"]}]

        # keywords: {did: list of kw strings} (kept for API compat)
        for u in self.datasheets:
            kws = u.get("_keywords", [])
            if kws:
                self.keywords[u["id"]] = kws

        # composition / wargear_options / loadout / wargear
        for u in self.datasheets:
            if u.get("_composition"):
                self.composition[u["id"]] = u["_composition"]
            if u.get("_options"):
                self.wargear_options[u["id"]] = u["_options"]
            if u.get("_loadout"):
                self.loadout[u["id"]] = u["_loadout"]
            gear = [{"name": w["name"], "type": "melee"} for w in u["_melee"]]
            gear += [{"name": w["name"], "type": "ranged"} for w in u["_ranged"]]
            if gear:
                self.wargear[u["id"]] = gear

        # leaders: leader_targets are attached datasheet ids (Wahapedia native).
        leaders_for_name = {}
        led_by_id = {}
        leads_id = {}
        for u in self.datasheets:
            targets = u.get("_leader_targets") or []
            leader_id = u["id"]
            leader_name = u["name"]
            for target_id in targets:
                target = self.ds_by_id.get(target_id)
                if not target:
                    continue
                leaders_for_name.setdefault(target["name"], []).append(leader_name)
                led_by_id.setdefault(target_id, []).append(leader_id)
                leads_id.setdefault(leader_id, []).append(
                    {"id": target_id, "name": target["name"]})
        self.leaders_for = leaders_for_name
        self.led_by = led_by_id
        self.leads = leads_id

        self._load_detachment_data()

        # Apply the MFM points overlay last, after self.cost and the detachment
        # enhancements are fully populated, so it overrides the final values.
        self._apply_mfm_overrides()

    # ---- MFM points overlay --------------------------------------------

    def _apply_mfm_overrides(self):
        """Overlay MFM points for any faction toggled on, over the Wahapedia
        base data. Non-destructive: only the in-memory unit dicts, self.cost,
        and enhancement cost values are touched, never the catalogue tables.
        Defensive on first boot, when the mfm_* tables may not exist yet."""
        try:
            from mfm_store import (
                enabled_overrides, meta_version,
            )
        except Exception:
            return
        try:
            self.mfm_version = meta_version() or ""
        except Exception:
            self.mfm_version = ""
        unit_ov, enh_ov, active_sources = enabled_overrides()
        for u in self.datasheets:
            did = u["id"]
            parent = self.faction_parent(u.get("faction_id"))
            slug = active_sources.get(parent)
            override = unit_ov.get((did, slug))
            if not override:
                continue
            base, tiers = override
            u["points"] = base
            u["_points_tiers"] = tiers
            u["mfm"] = True
            self.cost[did] = (tiers if tiers
                              else ([{"cost": base}] if base is not None else []))
        for detachment_id, enhs in self.enhancements_by_detachment.items():
            detachment = self.detachment_by_id.get(detachment_id, {})
            slug = active_sources.get(detachment.get("faction_id"))
            for e in enhs:
                override = enh_ov.get((e.get("id"), slug))
                if override is not None:
                    e["cost"] = override
                    e["mfm"] = True

    # ---- chapter rollup ------------------------------------------------

    @staticmethod
    def faction_parent(fid):
        """Return the parent code of a faction id. For a chapter id such as
        "SM::Blood Angels" this is "SM"; for a plain code it is the code itself."""
        if fid and CHAPTER_SEP in fid:
            return fid.split(CHAPTER_SEP, 1)[0]
        return fid

    @staticmethod
    def is_chapter_faction(fid):
        """True when fid is a synthetic chapter faction id (contains "::")."""
        return bool(fid) and CHAPTER_SEP in fid

    @staticmethod
    def _unit_faction_keywords(unit):
        """The bare faction keywords on a unit dict (the "Faction: " prefix that
        data_store stores them with, stripped back off)."""
        return [k[len(FACTION_KW_PREFIX):] for k in unit.get("_keywords", [])
                if k.startswith(FACTION_KW_PREFIX)]

    def _apply_chapter_rollup(self, real_faction_names):
        """Split each PARENT_FACTIONS code into per-chapter faction cards.

        Chapters are detected from the faction keywords on the parent's
        datasheets, minus the universal/configured excludes and any keyword that
        equals a real faction name. Each detected chapter becomes a synthetic
        faction whose datasheets are the ones carrying exactly that one chapter
        keyword; generic datasheets stay under the parent.
        """
        exclude_names = set(CHAPTER_KEYWORD_EXCLUDE) | set(real_faction_names)

        for parent in sorted(PARENT_FACTIONS):
            if parent not in self.faction_by_id:
                continue
            parent_units = list(self.ds_by_faction.get(parent, []))

            # Detect the chapter keyword set across the parent's datasheets.
            detected = set()
            for u in parent_units:
                for kw in self._unit_faction_keywords(u):
                    if kw and kw not in exclude_names:
                        detected.add(kw)
            if CHAPTER_ALLOWLIST:
                detected &= set(CHAPTER_ALLOWLIST)

            # Create a synthetic faction card per detected chapter.
            chapter_ids = {}
            for chapter in sorted(detected):
                cid = f"{parent}{CHAPTER_SEP}{chapter}"
                chapter_ids[chapter] = cid
                faction_dict = {"id": cid, "name": chapter, "unit_count": 0}
                self.factions.append(faction_dict)
                self.faction_by_id[cid] = faction_dict
                self.ds_by_faction.setdefault(cid, [])
                self.chapter_faction_ids.add(cid)
                self.chapters_by_parent.setdefault(parent, []).append(cid)

            # Reassign each parent datasheet that carries exactly one detected
            # chapter keyword to that chapter; leave generic ones under the parent.
            remaining = []
            for u in parent_units:
                chs = sorted(kw for kw in self._unit_faction_keywords(u)
                             if kw in detected)
                if not chs:
                    remaining.append(u)
                    continue
                if len(chs) > 1:
                    logger.warning(
                        "Chapter rollup: datasheet %s (%s) carries multiple "
                        "chapter keywords %s; assigning to %r for determinism.",
                        u["id"], u.get("name", ""), chs, chs[0])
                cid = chapter_ids[chs[0]]
                u["faction_id"] = cid
                self.ds_by_faction[cid].append(u)
            self.ds_by_faction[parent] = remaining

            # Recompute unit counts so the faction grid reflects the split.
            self.faction_by_id[parent]["unit_count"] = len(remaining)
            for chapter, cid in chapter_ids.items():
                self.faction_by_id[cid]["unit_count"] = len(self.ds_by_faction[cid])

        self._assert_core_chapters()

    def _assert_core_chapters(self):
        """Warn loudly if any core expected chapter did not resolve to a
        non-empty card. Does not raise: the app must still start."""
        missing = []
        for parent in sorted(PARENT_FACTIONS):
            for chapter in sorted(CORE_EXPECTED_CHAPTERS):
                cid = f"{parent}{CHAPTER_SEP}{chapter}"
                if not self.ds_by_faction.get(cid):
                    missing.append(cid)
        if missing:
            logger.warning(
                "\n" + "=" * 70 +
                "\nCHAPTER ROLLUP: expected chapter card(s) missing or empty: %s"
                "\nThe Wahapedia faction keyword structure may have changed; "
                "chapters may have silently re-merged into Space Marines."
                "\n" + "=" * 70, ", ".join(missing))

    def _chapter_children(self, fid):
        """Chapter faction ids whose parent is fid (empty for a chapter id)."""
        return list(self.chapters_by_parent.get(fid, []))

    def detachments_for_faction(self, fid):
        """Detachments for a faction id, falling back to the parent's pool. A
        chapter card has no detachments of its own because Wahapedia does not
        attribute detachments to chapters, so it inherits the full parent pool."""
        return (self.detachments_by_faction.get(fid)
                or self.detachments_by_faction.get(self.faction_parent(fid), []))

    def _load_detachment_data(self):
        """Populate detachments_by_faction, detachment_by_id,
        enhancements_by_detachment from the Wahapedia CSVs. Faction ids are now
        native Wahapedia codes, matching Detachments.csv directly.
        """
        import csv as _csv

        data_dir = os.path.join(os.path.dirname(__file__), "data")

        det_path = os.path.join(data_dir, "Detachments.csv")
        if not os.path.exists(det_path):
            return
        try:
            with open(det_path, encoding="utf-8-sig", newline="") as fh:
                reader = _csv.DictReader(fh, delimiter="|")
                for row in reader:
                    dtid = (row.get("id") or "").strip()
                    fid  = (row.get("faction_id") or "").strip()
                    name = (row.get("name") or "").strip()
                    if not dtid or not name or not fid:
                        continue
                    det = {
                        "id":         dtid,
                        "name":       name,
                        "faction_id": fid,
                        "legend":     (row.get("legend") or "").strip(),
                    }
                    self.detachments_by_faction.setdefault(fid, []).append(det)
                    self.detachment_by_id[dtid] = det
        except Exception:
            pass

        enh_path = os.path.join(data_dir, "Enhancements.csv")
        if not os.path.exists(enh_path):
            return
        try:
            with open(enh_path, encoding="utf-8-sig", newline="") as fh:
                reader = _csv.DictReader(fh, delimiter="|")
                for row in reader:
                    eid  = (row.get("id") or "").strip()
                    dtid = (row.get("detachment_id") or "").strip()
                    name = (row.get("name") or "").strip()
                    if not eid or not dtid or not name:
                        continue
                    try:
                        cost = int((row.get("cost") or "0").strip())
                    except ValueError:
                        cost = 0
                    enh = {
                        "id":            eid,
                        "name":          name,
                        "cost":          cost,
                        "detachment_id": dtid,
                        "description":   strip_html((row.get("description") or "").strip()),
                    }
                    self.enhancements_by_detachment.setdefault(dtid, []).append(enh)
        except Exception:
            pass

    # ---- queries -------------------------------------------------------

    def faction_list(self):
        out = []
        for f in self.factions:
            sheets = [d for d in self.ds_by_faction.get(f["id"], [])
                      if not d["virtual_bool"]]
            if not sheets:
                continue
            out.append({"id": f["id"], "name": f["name"], "unit_count": len(sheets)})
        out.sort(key=lambda x: x["name"])
        return out

    def units_for_faction(self, fid):
        """Strict membership: only units whose canonical faction_id equals fid.
        The Space Marines card shows generic units only; a chapter card shows its
        own units only. This is the un-merged view used by the browse grid."""
        sheets = [d for d in self.ds_by_faction.get(fid, [])
                  if not d["virtual_bool"]]
        units = []
        for d in sheets:
            units.append({
                "id":     d["id"],
                "name":   d["name"],
                "role":   d.get("role") or "Other",
                "points": self._cheapest_points(d["id"]),
                "mfm":    bool(d.get("mfm")),
            })
        units.sort(key=lambda u: (_role_rank(u["role"]), u["name"]))
        return units

    def units_in_faction_tree(self, fid):
        """Units for fid plus, when fid is a parent, all units of its chapter
        children. Used by faction-scoped matching and validation, not the browse
        grid (e.g. a Space Marines box should match Blood Angels units)."""
        units = self.units_for_faction(fid)
        children = self._chapter_children(fid)
        if not children:
            return units
        for cid in children:
            units += self.units_for_faction(cid)
        units.sort(key=lambda u: (_role_rank(u["role"]), u["name"]))
        return units

    def unit_in_faction(self, did, fid):
        """True when the unit's canonical faction equals fid, or when fid is the
        parent of the unit's chapter faction. So a Blood Angels unit counts as in
        both "SM" and "SM::Blood Angels"."""
        d = self.ds_by_id.get(did)
        if not d:
            return False
        ufid = d.get("faction_id")
        return ufid == fid or self.faction_parent(ufid) == fid

    def _cheapest_points(self, did):
        costs = [_int(c.get("cost")) for c in self.cost.get(did, [])
                 if _int(c.get("cost"))]
        return min(costs) if costs else None

    def unit_detail(self, did):
        d = self.ds_by_id.get(did)
        if not d:
            return None
        kws = d.get("_keywords", [])
        faction_kw_prefix = FACTION_KW_PREFIX
        fkw = [k for k in kws if k.startswith(faction_kw_prefix)]
        kw = [k for k in kws if not k.startswith(faction_kw_prefix)]
        # Single-model datasheets carry a stats dict; synthesise the "1 <name>"
        # composition line if Wahapedia gave no composition rows.
        composition = self.composition.get(d["id"], [])
        if not composition and isinstance(d.get("_stats"), dict) and d["_stats"]:
            composition = [{"name": d["name"], "min": 1, "max": 1}]
        abilities = d.get("_abilities") or {}
        damaged = abilities.get("damaged") or {}
        return {
            "id":                  d["id"],
            "name":                d["name"],
            "faction_id":          d["faction_id"],
            "faction_name":        self.faction_by_id.get(d["faction_id"], {}).get("name", ""),
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
            "composition":         composition,
            "options":             self.wargear_options.get(d["id"], []),
            "ranged":              d.get("_ranged", []),
            "melee":               d.get("_melee", []),
            "keywords":            kw,
            "faction_keywords":    fkw,
            "points_source":       "mfm" if d.get("mfm") else "wahapedia",
            "mfm_version":         self.mfm_version,
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
