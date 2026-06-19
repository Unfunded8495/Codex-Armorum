"""Loads unit and faction data from the Wahapedia-sourced SQLite catalogue tables.

Sourced from catalogue_factions, catalogue_units, catalogue_weapons, and
catalogue_unit_weapons (populated by wahapedia_importer.py from the Wahapedia
CSV export). The column names bsdata_id / unit_bsdata_id are kept as a legacy
misnomer: they now hold native Wahapedia ids (9-digit datasheet ids and faction
short codes such as "CSM").

The external interface (every public attribute and method) is unchanged so all
consuming modules continue to work; only the data source and the id values
differ from the previous BSData version.
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
