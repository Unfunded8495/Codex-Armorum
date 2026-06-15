"""Loads unit and faction data from the BSData SQLite catalogue tables.

Sourced from catalogue_factions, catalogue_units, catalogue_weapons, and
catalogue_unit_weapons (populated by bsdata_importer.py).

The external interface (every public attribute and method) is identical to the
previous Wahapedia CSV version so that all consuming modules continue to work.
"""
import json
import os
import re
import sqlite3
from functools import lru_cache

DB_PATH = os.path.join(os.path.dirname(__file__), "collection.db")

# Battlefield-role display order used when listing a faction's units.
ROLE_ORDER = [
    "Epic Hero", "Character", "Battleline", "Infantry", "Mounted",
    "Beast", "Monster", "Vehicle", "Swarm", "Transport",
    "Fortification", "Other", "Unaligned",
]

# Maps a display-faction catalogue name to the keyword fragment that identifies
# its units inside the shared library catalogue.  Only needed when a faction
# catalogue has 0 direct units and pulls from a library cat instead.
FACTION_KEYWORD_MAP = {
    "Xenos - Aeldari":             "Faction: Asuryani",
    "Xenos - Drukhari":            "Faction: Drukhari",
    "Aeldari - Ynnari":            "Faction: Ynnari",
    "Imperium - Astra Militarum":  "Faction: Astra Militarum",
    "Imperium - Imperial Knights": "Faction: Imperial Knights",
    "Chaos - Chaos Knights":       "Faction: Chaos Knights",
    "Chaos - Chaos Daemons":       "Faction: Legiones Daemonica",
}

# Maps a library-only catalogue name to the display faction it should roll up into.
# These libraries have no zero-unit partner; units are merged directly into the parent.
LIBRARY_PARENT_MAP = {
    "Library - Tyranids": "Xenos - Tyranids",
}

# Maps Wahapedia faction short codes (from Detachments.csv) to BSData catalogue names.
# Used to populate detachments_by_faction with BSData GUIDs as keys.
_WAHAPEDIA_CODE_TO_BSDATA_NAME = {
    "SM":  "Imperium - Adeptus Astartes - Space Marines",
    "AC":  "Imperium - Adeptus Custodes",
    "AE":  "Xenos - Aeldari",
    "AM":  "Imperium - Astra Militarum",
    "AS":  "Imperium - Adepta Sororitas",
    "AdM": "Imperium - Adeptus Mechanicus",
    "AoI": "Imperium - Agents of the Imperium",
    "CD":  "Chaos - Chaos Daemons",
    "CSM": "Chaos - Chaos Space Marines",
    "DG":  "Chaos - Death Guard",
    "DRU": "Xenos - Drukhari",
    "EC":  "Chaos - Emperor’s Children",
    "GC":  "Xenos - Genestealer Cults",
    "GK":  "Imperium - Grey Knights",
    "LoV": "Xenos - Leagues of Votann",
    "NEC": "Xenos - Necrons",
    "ORK": "Xenos - Orks",
    "QI":  "Imperium - Imperial Knights",
    "QT":  "Chaos - Chaos Knights",
    "TAU": "Xenos - T’au Empire",
    "TS":  "Chaos - Thousand Sons",
    "TYR": "Xenos - Tyranids",
    "WE":  "Chaos - World Eaters",
    "UN":  "Unaligned Forces",
}


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
        self.wargear = {}
        self.keywords = {}
        self.detachments_by_faction = {}
        self.detachment_by_id = {}
        self.enhancements_by_detachment = {}
        self.leaders_for = {}
        self.led_by = {}
        self._load()

    def _load(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # Load all factions (we'll filter below)
        all_fac_rows = conn.execute(
            "SELECT bsdata_id, name FROM catalogue_factions ORDER BY name"
        ).fetchall()

        # Load every unit
        all_unit_rows = conn.execute(
            "SELECT bsdata_id, faction_id, name, role, points,"
            "       stats_json, abilities_json, keywords_json"
            " FROM catalogue_units"
        ).fetchall()

        # Load all weapons joined to unit links
        all_weapon_rows = conn.execute("""
            SELECT cuw.unit_id,
                   cw.bsdata_id  w_id,
                   cw.name       w_name,
                   cw.weapon_type,
                   cw.range,
                   cw.attacks,
                   cw.skill,
                   cw.strength,
                   cw.ap,
                   cw.damage,
                   cw.keywords   w_keywords
            FROM catalogue_unit_weapons cuw
            JOIN catalogue_weapons cw ON cw.bsdata_id = cuw.weapon_id
        """).fetchall()

        conn.close()

        # --- index weapons by unit_id ---
        weapons_by_unit = {}
        for w in all_weapon_rows:
            weapons_by_unit.setdefault(w["unit_id"], []).append(w)

        # --- build unit dicts keyed by bsdata_id ---
        raw_units = {}
        for u in all_unit_rows:
            did = u["bsdata_id"]
            kws = json.loads(u["keywords_json"]) if u["keywords_json"] else []
            stats = json.loads(u["stats_json"]) if u["stats_json"] else {}

            ranged = []
            melee = []
            for w in weapons_by_unit.get(did, []):
                entry = {
                    "name":    w["w_name"],
                    "range":   w["range"] or "",
                    "A":       w["attacks"] or "",
                    "BS_WS":   w["skill"] or "",
                    "S":       w["strength"] or "",
                    "AP":      w["ap"] or "",
                    "D":       w["damage"] or "",
                    "keywords": w["w_keywords"] or "",
                    "description": "",
                }
                if w["weapon_type"] == "melee":
                    melee.append(entry)
                else:
                    ranged.append(entry)

            unit_dict = {
                "id":          did,
                "bsdata_id":   did,
                "name":        u["name"],
                "faction_id":  u["faction_id"],  # may be overridden below
                "role":        u["role"] or "Other",
                "points":      u["points"],
                "virtual_bool": False,
                "_keywords":   kws,   # internal; used by faction keyword filter
                "_stats":      stats,
                "_ranged":     ranged,
                "_melee":      melee,
            }
            raw_units[did] = unit_dict

        # --- build keyword index for fast lookup ---
        # kw_units[keyword_fragment] = list of unit dicts
        kw_units = {}
        for u in raw_units.values():
            for kw in u["_keywords"]:
                kw_units.setdefault(kw, []).append(u)

        # --- process factions ---
        for row in all_fac_rows:
            fid = row["bsdata_id"]
            name = row["name"]

            # Skip library-only catalogues from the visible list
            if "Library" in name:
                continue

            if name in FACTION_KEYWORD_MAP:
                keyword = FACTION_KEYWORD_MAP[name]
                faction_units = kw_units.get(keyword, [])
            else:
                faction_units = [u for u in raw_units.values() if u["faction_id"] == fid]

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
                # For keyword-mapped factions, use a copy with overridden faction_id
                if name in FACTION_KEYWORD_MAP:
                    unit = dict(u)
                    unit["faction_id"] = fid
                else:
                    unit = u

                self.ds_by_faction.setdefault(fid, []).append(unit)
                # ds_by_id: last keyword-mapped faction wins for shared units
                self.ds_by_id[unit["id"]] = unit

        self.datasheets = list(self.ds_by_id.values())

        # Merge library-catalogue units into their parent display faction
        fac_by_name = {f["name"]: f for f in self.factions}
        for lib_name, display_name in LIBRARY_PARENT_MAP.items():
            display_fac = fac_by_name.get(display_name)
            if not display_fac:
                continue
            fid = display_fac["id"]
            lib_fac = next((r for r in all_fac_rows if r["name"] == lib_name), None)
            if not lib_fac:
                continue
            lib_units = [u for u in raw_units.values()
                         if u["faction_id"] == lib_fac["bsdata_id"]]
            for u in lib_units:
                if u["id"] in self.ds_by_id:
                    continue
                unit = dict(u)
                unit["faction_id"] = fid
                self.ds_by_id[unit["id"]] = unit
                self.ds_by_faction.setdefault(fid, []).append(unit)
                display_fac["unit_count"] += 1
            self.datasheets = list(self.ds_by_id.values())

        # cost: {did: [{"cost": points}]} — used by army builder
        for u in self.datasheets:
            if u.get("points") is not None:
                self.cost[u["id"]] = [{"cost": u["points"]}]

        # keywords: {did: list of kw strings} — kept for API compat
        for u in self.datasheets:
            kws = u.get("_keywords", [])
            if kws:
                self.keywords[u["id"]] = kws

        # Add Wahapedia 9-digit ID aliases so box_sets / purchases keep working
        self._build_wahapedia_aliases()

        # Populate composition, wargear, leaders_for, led_by from DB
        conn2 = sqlite3.connect(DB_PATH)
        conn2.row_factory = sqlite3.Row

        for row in conn2.execute(
            "SELECT bsdata_id, composition_json FROM catalogue_units"
            " WHERE composition_json IS NOT NULL"
        ).fetchall():
            self.composition[row["bsdata_id"]] = json.loads(row["composition_json"])

        for row in conn2.execute("""
            SELECT cuw.unit_id,
                   json_group_array(json_object('name', cw.name, 'type', cw.weapon_type)) AS gear
            FROM catalogue_unit_weapons cuw
            JOIN catalogue_weapons cw ON cuw.weapon_id = cw.bsdata_id
            GROUP BY cuw.unit_id
        """).fetchall():
            self.wargear[row["unit_id"]] = json.loads(row["gear"])

        _name_to_id = {u["name"]: u["id"] for u in self.datasheets}
        leaders_for_name = {}
        led_by_id = {}
        for row in conn2.execute(
            "SELECT bsdata_id, name, leader_targets_json FROM catalogue_units"
            " WHERE leader_targets_json IS NOT NULL"
        ).fetchall():
            targets = json.loads(row["leader_targets_json"])
            leader_id = row["bsdata_id"]
            leader_name = row["name"]
            for target_name in targets:
                leaders_for_name.setdefault(target_name, []).append(leader_name)
                target_id = _name_to_id.get(target_name)
                if target_id:
                    led_by_id.setdefault(target_id, []).append(leader_id)
        self.leaders_for = leaders_for_name
        self.led_by = led_by_id

        conn2.close()

        self._load_detachment_data()

    def _load_detachment_data(self):
        """Populate detachments_by_faction, detachment_by_id, enhancements_by_detachment
        from the Wahapedia CSVs. These data sets have no equivalent in BSData XML.
        """
        import csv as _csv

        data_dir = os.path.join(os.path.dirname(__file__), "data")

        # Build BSData faction name → GUID map (only display factions, not libraries)
        bsdata_name_to_id = {f["name"]: f["id"] for f in self.factions}

        # Wahapedia faction code → BSData faction GUID
        code_to_fid = {}
        for code, bsdata_name in _WAHAPEDIA_CODE_TO_BSDATA_NAME.items():
            fid = bsdata_name_to_id.get(bsdata_name)
            if fid:
                code_to_fid[code] = fid

        # Load detachments
        det_path = os.path.join(data_dir, "Detachments.csv")
        if not os.path.exists(det_path):
            return
        try:
            with open(det_path, encoding="utf-8-sig", newline="") as fh:
                reader = _csv.DictReader(fh, delimiter="|")
                for row in reader:
                    dtid  = (row.get("id") or "").strip()
                    wcode = (row.get("faction_id") or "").strip()
                    name  = (row.get("name") or "").strip()
                    if not dtid or not name or not wcode:
                        continue
                    fid = code_to_fid.get(wcode)
                    if not fid:
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

        # Load enhancements
        enh_path = os.path.join(data_dir, "Enhancements.csv")
        if not os.path.exists(enh_path):
            return
        try:
            with open(enh_path, encoding="utf-8-sig", newline="") as fh:
                reader = _csv.DictReader(fh, delimiter="|")
                for row in reader:
                    eid   = (row.get("id") or "").strip()
                    dtid  = (row.get("detachment_id") or "").strip()
                    name  = (row.get("name") or "").strip()
                    if not eid or not dtid or not name:
                        continue
                    try:
                        cost = int((row.get("cost") or "0").strip())
                    except ValueError:
                        cost = 0
                    enh = {
                        "id":             eid,
                        "name":           name,
                        "cost":           cost,
                        "detachment_id":  dtid,
                        "description":    strip_html((row.get("description") or "").strip()),
                    }
                    self.enhancements_by_detachment.setdefault(dtid, []).append(enh)
        except Exception:
            pass

    def _build_wahapedia_aliases(self):
        """Populate ds_by_id with Wahapedia 9-digit ID → BSData unit aliases.

        box_sets.json and custom_box_set_contents still store Wahapedia IDs.
        We use two sources:
          1. minis table (migration-verified exact matches, highest confidence)
          2. Datasheets.csv name-matching for any IDs not yet covered
        """
        import csv as _csv

        # 1. Exact matches from the Phase 3 migration
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT DISTINCT datasheet_id, unit_bsdata_id FROM minis"
                " WHERE unit_bsdata_id IS NOT NULL"
            ).fetchall()
            conn.close()
            for r in rows:
                wid, bsid = r[0], r[1]
                if wid and bsid and bsid in self.ds_by_id and wid not in self.ds_by_id:
                    self.ds_by_id[wid] = self.ds_by_id[bsid]
        except Exception:
            pass

        # 2. Name-based fallback from Datasheets.csv for remaining IDs
        ds_path = os.path.join(os.path.dirname(__file__), "data", "Datasheets.csv")
        if not os.path.exists(ds_path):
            return

        _R = "’"
        _L = "‘"

        def _norm(s):
            return s.replace(_R, "'").replace(_L, "'").lower()

        name_to_unit = {_norm(u["name"]): u for u in self.datasheets}

        try:
            with open(ds_path, encoding="utf-8-sig", newline="") as fh:
                reader = _csv.DictReader(fh, delimiter="|")
                for row in reader:
                    wid = (row.get("id") or "").strip()
                    name = (row.get("name") or "").strip()
                    if not wid or not name or wid in self.ds_by_id:
                        continue
                    unit = name_to_unit.get(_norm(name))
                    if unit:
                        self.ds_by_id[wid] = unit
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
        sheets = [d for d in self.ds_by_faction.get(fid, [])
                  if not d["virtual_bool"]]
        units = []
        for d in sheets:
            units.append({
                "id":     d["id"],
                "name":   d["name"],
                "role":   d.get("role") or "Other",
                "points": self._cheapest_points(d["id"]),
            })
        units.sort(key=lambda u: (_role_rank(u["role"]), u["name"]))
        return units

    def _cheapest_points(self, did):
        costs = [_int(c.get("cost")) for c in self.cost.get(did, [])
                 if _int(c.get("cost"))]
        return min(costs) if costs else None

    def unit_detail(self, did):
        d = self.ds_by_id.get(did)
        if not d:
            return None
        kws = d.get("_keywords", [])
        faction_kw_prefix = "Faction: "
        fkw = [k for k in kws if k.startswith(faction_kw_prefix)]
        kw = [k for k in kws if not k.startswith(faction_kw_prefix)]
        return {
            "id":                  d["id"],
            "name":                d["name"],
            "faction_id":          d["faction_id"],
            "faction_name":        self.faction_by_id.get(d["faction_id"], {}).get("name", ""),
            "role":                d.get("role") or "Other",
            "legend":              "",
            "loadout":             "",
            "link":                "",
            "transport":           "",
            "damaged_w":           "",
            "damaged_description": "",
            "led_by":              [self.ds_by_id[lid]["name"]
                                    for lid in self.led_by.get(d["id"], [])
                                    if lid in self.ds_by_id],
            "models":              d.get("_stats") or [],
            "costs":               self.cost.get(d["id"], []),
            "composition":         self.composition.get(d["id"], []),
            "options":             [],
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
