#!/usr/bin/env python3
"""
Warhammer 40,000 App Data Exporter (unified)

Point this tool at a Warhammer 40,000 App APK (base.apk). It reads the bundled
game database (assets/dump.json) and exports everything relevant to factions and
datasheets into a tidy folder tree, in both JSON and CSV.

Two ways to run it:

  1. Window mode (just double click, or run with no arguments):
         python w40k_exporter.py
     A small window opens. Choose the APK, choose an output folder, press Export.

  2. Command line mode:
         python w40k_exporter.py base.apk -o w40k_export
         python w40k_exporter.py base.apk -o out --no-csv
         python w40k_exporter.py base.apk -o out --no-json

A README.md describing the full output is written into the output folder.

No third party libraries are required. Standard library only.
"""

import argparse
import csv
import html
import json
import os
import re
import sqlite3
import sys
import zipfile
from collections import defaultdict


# ===========================================================================
# Loading and shared helpers
# ===========================================================================

def load_dump_from_apk(apk_path):
    if not os.path.isfile(apk_path):
        raise FileNotFoundError("APK not found: %s" % apk_path)
    with zipfile.ZipFile(apk_path) as zf:
        names = zf.namelist()
        target = None
        for candidate in ("assets/dump.json", "dump.json"):
            if candidate in names:
                target = candidate
                break
        if target is None:
            for n in names:
                if n.lower().endswith("dump.json"):
                    target = n
                    break
        if target is None:
            raise ValueError("No dump.json found inside the APK.")
        raw = zf.read(target)
    parsed = json.loads(raw.decode("utf-8"))
    if "data" not in parsed:
        raise ValueError("dump.json has an unexpected shape (no 'data' key).")
    return parsed


def en(obj, field="name"):
    if not isinstance(obj, dict):
        return None
    loc = obj.get("localisations") or {}
    e = loc.get("en") or {}
    return e.get(field)


def sanitise(name):
    if not name:
        name = "Unknown"
    cleaned = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "Unknown"


def to_plain_text(markup):
    if not markup:
        return ""
    text = markup.replace("\r", "\n")
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/\s*li\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*li\s*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/?\s*(ul|ol|p|div)\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return "\n".join(ln.strip() for ln in text.split("\n")).strip()


def cell(text):
    if text is None:
        return ""
    return re.sub(r"\s*\n\s*", " | ", str(text)).strip()


def join_cell(parts, sep="; "):
    return sep.join(str(p) for p in parts if p not in (None, "", []))


WHEN_LABEL = {"yourTurn": "Your turn", "opponentsTurn": "Opponent's turn",
              "eitherPlayer": "Either player"}
PHASE_LABEL = {"commandPhase": "Command", "movementPhase": "Movement",
               "shootingPhase": "Shooting", "chargePhase": "Charge",
               "fightPhase": "Fight", "anyPhase": "Any"}


# ===========================================================================
# Index
# ===========================================================================

def build_index(parsed):
    data = parsed["data"]
    idx = {"data_version": (parsed.get("metadata") or {}).get("data_version")}

    def by_id(table):
        return {x["id"]: x for x in data[table]}

    def group(table, key):
        g = defaultdict(list)
        for r in data[table]:
            g[r.get(key)].append(r)
        return g

    def group_sorted(table, key):
        g = defaultdict(list)
        for r in sorted(data[table], key=lambda r: r.get("displayOrder") or 0):
            g[r.get(key)].append(r)
        return g

    idx["datasheet_by_id"] = by_id("datasheet")
    idx["faction_by_id"] = by_id("faction_keyword")
    idx["ability_by_id"] = by_id("datasheet_ability")
    idx["keyword_by_id"] = by_id("keyword")
    idx["wargear_item_by_id"] = by_id("wargear_item")
    idx["wargear_option_by_id"] = by_id("wargear_option")
    idx["wargear_ability_by_id"] = by_id("wargear_ability")
    idx["publication_by_id"] = by_id("publication")

    # faction links
    ds_fac = defaultdict(list)
    for r in sorted(data["datasheet_faction_keyword"], key=lambda r: r.get("displayOrder") or 0):
        ds_fac[r["datasheetId"]].append(r["factionKeywordId"])
    # Remove explicit faction exclusions. A datasheet can carry a faction keyword
    # yet be barred from that faction's roster (for example Sir Hekhtur carries
    # the Imperial Knights keyword but is excluded from Imperial Knights). Source
    # table: faction_keyword_excluded_datasheet. Applying it here fixes both the
    # JSON faction folders and the SQLite datasheet_faction junction in one place.
    excluded = set()
    for r in data.get("faction_keyword_excluded_datasheet", []):
        if r.get("datasheetId") and r.get("factionKeywordId"):
            excluded.add((r["datasheetId"], r["factionKeywordId"]))
    if excluded:
        for dsid in list(ds_fac.keys()):
            ds_fac[dsid] = [f for f in ds_fac[dsid] if (dsid, f) not in excluded]
    idx["ds_faction_ids"] = ds_fac
    idx["excluded_ds_faction"] = excluded

    # datasheet sub structures
    idx["minis_by_ds"] = group_sorted("miniature", "datasheetId")
    idx["mini_to_ds"] = {m["id"]: m["datasheetId"] for m in data["miniature"]}
    mini_kw = defaultdict(list)
    for r in sorted(data["miniature_keyword"], key=lambda r: r.get("displayOrder") or 0):
        mini_kw[r["miniatureId"]].append(r["keywordId"])
    idx["mini_keyword_ids"] = mini_kw

    inv_ds, inv_mini = {}, {}
    for r in data["invulnerable_save"]:
        (inv_mini if r.get("miniatureId") else inv_ds)[r.get("miniatureId") or r["datasheetId"]] = r
    idx["inv_by_ds"], idx["inv_by_mini"] = inv_ds, inv_mini

    idx["ds_ability_links"] = group_sorted("datasheet_datasheet_ability", "datasheetId")
    idx["sub_ability_by_ability"] = group_sorted("datasheet_sub_ability", "datasheetAbilityId")
    idx["comp_by_ds"] = group_sorted("unit_composition", "datasheetId")
    idx["comp_mini"] = group("unit_composition_miniature", "unitCompositionId")
    idx["steps_by_ds"] = group("datasheet_points_step", "datasheetId")
    idx["damage_by_ds"] = group_sorted("datasheet_damage", "datasheetId")
    idx["ds_rule_by_ds"] = group_sorted("datasheet_rule", "datasheetId")
    idx["cond_kw_by_ds"] = group("conditional_keyword", "datasheetId")

    # weapon profiles
    idx["profiles_by_item"] = group_sorted("wargear_item_profile", "wargearItemId")
    prof_ab = defaultdict(list)
    for r in sorted(data["wargear_item_profile_wargear_ability"], key=lambda r: r.get("displayOrder") or 0):
        prof_ab[r["wargearItemProfileId"]].append(r["wargearAbilityId"])
    idx["profile_ability_ids"] = prof_ab

    # leader / bodyguard attachment
    bg_members = defaultdict(list)
    for r in data["datasheet_bodyguard_group_datasheet"]:
        bg_members[r["datasheetBodyguardGroupId"]].append(r["datasheetId"])
    leads = defaultdict(set)
    led_by = defaultdict(set)
    for g in data["datasheet_bodyguard_group"]:
        leader = g.get("datasheetId")
        for member in bg_members.get(g["id"], []):
            if leader:
                leads[leader].add(member)
                led_by[member].add(leader)
    idx["leads"] = leads
    idx["led_by"] = led_by

    # ----- wargear loadout enforcement -----
    idx["wog_by_ds"] = group_sorted("wargear_option_group", "datasheetId")
    wo_by_group = defaultdict(list)
    for r in sorted(data["wargear_option"], key=lambda r: r.get("displayOrder") or 0):
        if r.get("wargearOptionGroupId"):
            wo_by_group[r["wargearOptionGroupId"]].append(r)
    idx["wo_by_group"] = wo_by_group

    # default loadout (equipped with)
    bml_by_ds = group("base_miniature_loadout", "datasheetId")
    idx["bml_by_ds"] = bml_by_ds
    bml_opts = defaultdict(list)
    for r in data["base_miniature_loadout_wargear_option"]:
        bml_opts[r["baseMiniatureLoadoutId"]].append(r["wargearOptionId"])
    idx["bml_opts"] = bml_opts

    # choose from sets
    idx["lcs_by_ds"] = group("loadout_choice_set", "datasheetId")
    idx["lc_by_set"] = group("loadout_choice", "loadoutChoiceSetId")
    idx["lci_by_choice"] = group("loadout_choice_wargear_item", "loadoutChoiceId")

    # limited choice sets (per N models)
    idx["lwcs_by_ds"] = group("limited_wargear_choice_set", "datasheetId")
    idx["lwc_by_set"] = group("limited_wargear_choice", "limitedWargearChoiceSetId")
    idx["lwci_by_choice"] = group("limited_wargear_choice_wargear_item", "limitedWargearChoiceId")
    idx["wlimit_by_set"] = group("wargear_limit", "limitedWargearChoiceSetId")

    # all model choice sets
    idx["amcs_by_ds"] = group("all_model_wargear_choice_set", "datasheetId")
    idx["amc_by_set"] = group("all_model_wargear_choice", "allModelWargearChoiceSetId")
    idx["amci_by_choice"] = group("all_model_wargear_choice_wargear_item", "allModelWargearChoiceId")

    idx["wargear_rule_by_ds"] = group_sorted("wargear_rule", "datasheetId")

    # ----- detachment -----
    det_fac = defaultdict(list)
    for r in data["detachment_faction_keyword"]:
        det_fac[r["detachmentId"]].append(r["factionKeywordId"])
    idx["det_faction_ids"] = det_fac
    idx["rules_by_det"] = group_sorted("detachment_rule", "detachmentId")
    comp_by_rule = defaultdict(list)
    comp_by_armyrule = defaultdict(list)
    for c in data["rule_container_component"]:
        if c.get("detachmentRuleId"):
            comp_by_rule[c["detachmentRuleId"]].append(c)
        if c.get("armyRuleId"):
            comp_by_armyrule[c["armyRuleId"]].append(c)
    for store in (comp_by_rule, comp_by_armyrule):
        for k in store:
            store[k].sort(key=lambda c: c.get("displayOrder") or 0)
    idx["comp_by_rule"] = comp_by_rule
    idx["comp_by_armyrule"] = comp_by_armyrule
    idx["detail_by_det"] = group_sorted("detachment_detail", "detachmentId")
    idx["bullets_by_detail"] = group_sorted("detachment_detail_bullet_point", "detachmentDetailId")
    idx["enh_by_det"] = group_sorted("enhancement", "detachmentId")
    idx["strat_by_det"] = group_sorted("stratagem", "detachmentId")
    idx["phases_by_strat"] = defaultdict(list)
    for r in data["stratagem_phase"]:
        idx["phases_by_strat"][r["stratagemId"]].append(r["phase"])
    idx["det_linked_ds"] = group("detachment_linked_datasheet", "detachmentId")
    idx["det_excluded_ds"] = group("detachment_excluded_datasheet", "detachmentId")

    # enhancement eligibility
    grp_fac = defaultdict(list)
    for r in data["enhancement_required_keyword_group_faction_keyword"]:
        grp_fac[r["enhancementRequiredKeywordGroupId"]].append(r["factionKeywordId"])
    grp_kw = defaultdict(list)
    for r in data["enhancement_required_keyword_group_keyword"]:
        grp_kw[r["enhancementRequiredKeywordGroupId"]].append(r["keywordId"])
    idx["enh_groups"] = group("enhancement_required_keyword_group", "enhancementId")
    idx["enh_grp_fac"] = grp_fac
    idx["enh_grp_kw"] = grp_kw
    idx["enh_excluded"] = group("enhancement_excluded_keyword", "enhancementId")

    # army rules and allegiance abilities
    idx["army_rule_by_id"] = by_id("army_rule")
    army_by_fac = defaultdict(list)
    for r in data["army_rule_faction_keyword"]:
        army_by_fac[r["factionKeywordId"]].append(r["armyRuleId"])
    idx["army_by_fac"] = army_by_fac
    idx["alleg_group_by_id"] = by_id("allegiance_ability_group")
    idx["alleg_by_group"] = group_sorted("allegiance_ability", "allegianceAbilityGroupId")

    # publications by faction
    pub_by_fac = defaultdict(list)
    for p in sorted(data["publication"], key=lambda p: p.get("displayOrder") or 0):
        if p.get("factionKeywordId"):
            pub_by_fac[p["factionKeywordId"]].append(p)
    idx["pub_by_fac"] = pub_by_fac

    idx["raw"] = data
    return data, idx


# ===========================================================================
# Datasheet resolution
# ===========================================================================

def weapon_for_item(item_id, idx):
    item = idx["wargear_item_by_id"].get(item_id)
    if not item:
        return None
    profiles = []
    for p in idx["profiles_by_item"].get(item_id, []):
        ab = [en(idx["wargear_ability_by_id"].get(a)) for a in idx["profile_ability_ids"].get(p["id"], [])]
        profiles.append({
            "name": en(p), "type": p.get("type"), "range": p.get("range"),
            "A": p.get("attacks"), "BS": p.get("ballisticSkill"),
            "WS": p.get("weaponSkill"), "S": p.get("strength"),
            "AP": p.get("armourPenetration"), "D": p.get("damage"),
            "abilities": [a for a in ab if a],
        })
    return {"name": en(item), "wargear_type": item.get("wargearType"),
            "rule_text": en(item, "ruleText"), "profiles": profiles}


def item_name(item_id, idx):
    return en(idx["wargear_item_by_id"].get(item_id))


def resolve_models(dsid, idx):
    models = []
    for m in idx["minis_by_ds"].get(dsid, []):
        inv = idx["inv_by_mini"].get(m["id"]) or idx["inv_by_ds"].get(dsid)
        kws = [en(idx["keyword_by_id"].get(k)) for k in idx["mini_keyword_ids"].get(m["id"], [])]
        models.append({
            "id": m["id"], "name": en(m), "statline_hidden": bool(m.get("statlineHidden")),
            "M": m.get("movement"), "T": m.get("toughness"), "Sv": m.get("save"),
            "Inv": (inv or {}).get("save") if inv else None,
            "W": m.get("wounds"), "Ld": m.get("leadership"), "OC": m.get("objectiveControl"),
            "keywords": [k for k in kws if k],
        })
    return models


def resolve_abilities(dsid, idx):
    out = []
    for link in idx["ds_ability_links"].get(dsid, []):
        ab = idx["ability_by_id"].get(link["datasheetAbilityId"])
        if not ab:
            continue
        subs = [{"name": en(s), "rules": en(s, "rules")}
                for s in idx["sub_ability_by_ability"].get(ab["id"], [])]
        out.append({
            "name": en(ab), "type": ab.get("abilityType"),
            "is_aura": bool(ab.get("isAura")), "is_psychic": bool(ab.get("isPsychic")),
            "rules": en(ab, "rules"), "restriction": en(link, "restriction"),
            "sub_abilities": subs,
        })
    return out


def resolve_weapons(dsid, idx):
    seen, out = set(), []
    for loadout_id in [b["id"] for b in idx["bml_by_ds"].get(dsid, [])]:
        for opt_id in idx["bml_opts"].get(loadout_id, []):
            opt = idx["wargear_option_by_id"].get(opt_id)
            if opt and opt.get("wargearItemId") and opt["wargearItemId"] not in seen:
                seen.add(opt["wargearItemId"])
    for g in idx["wog_by_ds"].get(dsid, []):
        for opt in idx["wo_by_group"].get(g["id"], []):
            if opt.get("wargearItemId"):
                seen.add(opt["wargearItemId"])
    for item_id in seen:
        w = weapon_for_item(item_id, idx)
        if w:
            out.append(w)
    out.sort(key=lambda w: w["name"] or "")
    return out


def resolve_wargear_loadout(dsid, idx):
    mini_name = {m["id"]: en(m) for m in idx["minis_by_ds"].get(dsid, [])}

    # 1. options with points and input behaviour
    options = []
    for g in idx["wog_by_ds"].get(dsid, []):
        for opt in idx["wo_by_group"].get(g["id"], []):
            options.append({
                "group": en(g, "instructionText"),
                "miniature": mini_name.get(g.get("miniatureId")),
                "is_static_wargear": bool(g.get("isStaticWargear")),
                "item": item_name(opt.get("wargearItemId"), idx),
                "points": opt.get("points"),
                "input_type": opt.get("inputType"),
                "default_value": opt.get("defaultValue"),
            })

    # 2. choose-from sets ("select 'limit' of the following")
    choose_from = []
    for s in idx["lcs_by_ds"].get(dsid, []):
        choices = []
        for c in idx["lc_by_set"].get(s["id"], []):
            items = [{"item": item_name(i["wargearItemId"], idx), "count": i.get("count")}
                     for i in idx["lci_by_choice"].get(c["id"], [])]
            choices.append([i for i in items if i["item"]])
        choose_from.append({
            "miniature": mini_name.get(s.get("miniatureId")),
            "limit": s.get("limit"), "allow_duplicates": bool(s.get("allowDuplicates")),
            "alternate": bool(s.get("alternate")), "choices": choices,
        })

    # 3. limited choices ("for every N models, up to X may take")
    limited = []
    for s in idx["lwcs_by_ds"].get(dsid, []):
        limits = [{"per_models": w.get("modelCount"), "max_choices": w.get("choiceLimit"),
                   "duplicate_limit": w.get("duplicateLimit")}
                  for w in idx["wlimit_by_set"].get(s["id"], [])]
        choices = []
        for c in idx["lwc_by_set"].get(s["id"], []):
            items = [{"item": item_name(i["wargearItemId"], idx), "count": i.get("count")}
                     for i in idx["lwci_by_choice"].get(c["id"], [])]
            choices.append([i for i in items if i["item"]])
        limited.append({
            "miniature": mini_name.get(s.get("miniatureId")),
            "mandatory": bool(s.get("mandatory")), "limits": limits, "choices": choices,
        })

    # 4. all-model choices
    all_model = []
    for s in idx["amcs_by_ds"].get(dsid, []):
        choices = []
        for c in idx["amc_by_set"].get(s["id"], []):
            items = [{"item": item_name(i["wargearItemId"], idx), "count": i.get("count")}
                     for i in idx["amci_by_choice"].get(c["id"], [])]
            choices.append({"substitute": bool(c.get("substitute")),
                            "items": [i for i in items if i["item"]]})
        all_model.append({"miniature": mini_name.get(s.get("miniatureId")), "choices": choices})

    rules_text = [en(r, "rulesText") for r in idx["wargear_rule_by_ds"].get(dsid, [])
                  if en(r, "rulesText")]

    return {
        "rules_text": rules_text,
        "priced_options": [o for o in options if o.get("points")],
        "options": options,
        "choose_from": choose_from,
        "limited_choices": limited,
        "all_model_choices": all_model,
    }


def resolve_conditional_keywords(dsid, idx):
    out = []
    for r in idx["cond_kw_by_ds"].get(dsid, []):
        cond = []
        if r.get("requiredDetachmentId"):
            cond.append("in a specific detachment")
        if r.get("requiredAllegianceAbilityId"):
            cond.append("with a specific allegiance ability")
        if r.get("requiredWarlordMiniatureId"):
            cond.append("when a specific warlord is present")
        if r.get("requiredRosterFactionKeywordId"):
            fk = en(idx["faction_by_id"].get(r["requiredRosterFactionKeywordId"]))
            if fk:
                cond.append("in a %s army" % fk)
        out.append({"keyword": en(idx["keyword_by_id"].get(r["keywordId"])),
                    "condition": ", ".join(cond) or "conditional"})
    return [c for c in out if c["keyword"]]


def resolve_datasheet(dsid, idx):
    ds = idx["datasheet_by_id"][dsid]
    fac_names = [en(idx["faction_by_id"].get(f)) for f in idx["ds_faction_ids"].get(dsid, [])]
    models = resolve_models(dsid, idx)
    comps = []
    for c in idx["comp_by_ds"].get(dsid, []):
        members = []
        for cm in idx["comp_mini"].get(c["id"], []):
            mn = next((m["name"] for m in models if m["id"] == cm["miniatureId"]), None)
            members.append({"model": mn, "min": cm.get("min"), "max": cm.get("max")})
        comps.append({"points": c.get("points"), "is_default": bool(c.get("isDefault")),
                      "models": members})
    steps = [{"step_at": s.get("stepAt"), "step_points": s.get("stepPoints")}
             for s in idx["steps_by_ds"].get(dsid, [])]

    unit_keywords, seen = [], set()
    for m in models:
        for k in m["keywords"]:
            if k not in seen:
                seen.add(k)
                unit_keywords.append(k)

    pub = idx["publication_by_id"].get(ds.get("publicationId"))
    leads = sorted(en(idx["datasheet_by_id"].get(x)) for x in idx["leads"].get(dsid, []))
    led_by = sorted(en(idx["datasheet_by_id"].get(x)) for x in idx["led_by"].get(dsid, []))

    # strip the id helper field from models for output
    out_models = [{k: v for k, v in m.items() if k != "id"} for m in models]

    return {
        "id": dsid, "name": en(ds), "faction_keywords": [f for f in fac_names if f],
        "source_publication": en(pub) if pub else None,
        "is_legends": bool(ds.get("isLegends")),
        "is_free_from_entitlements": bool(ds.get("isFreeFromEntitlements")),
        "base_size": en(ds, "baseSize"), "max_model_count": ds.get("maxModelCount"),
        "keywords": unit_keywords,
        "conditional_keywords": resolve_conditional_keywords(dsid, idx),
        "lore": en(ds, "lore"), "unit_composition_text": en(ds, "unitComposition"),
        "points": comps, "points_steps": steps,
        "models": out_models,
        "abilities": resolve_abilities(dsid, idx),
        "extra_rules": [{"name": en(r), "rules": en(r, "rules")}
                        for r in idx["ds_rule_by_ds"].get(dsid, [])],
        "weapons": resolve_weapons(dsid, idx),
        "wargear_loadout": resolve_wargear_loadout(dsid, idx),
        "leads_units": [x for x in leads if x],
        "can_be_led_by": [x for x in led_by if x],
        "damage_brackets": [{"name": en(r), "rules": en(r, "rules")}
                            for r in idx["damage_by_ds"].get(dsid, [])],
    }


# ===========================================================================
# Detachment resolution
# ===========================================================================

def assemble_components(components):
    body, lore = [], []
    for c in components:
        title = en(c, "title")
        content = en(c, "textContent")
        trigger = en(c, "trigger")
        effect = en(c, "effect")
        chunk = "\n".join(p for p in [title, content] if p)
        if trigger or effect:
            extra = "\n".join(p for p in ["Trigger: " + trigger if trigger else None,
                                          "Effect: " + effect if effect else None] if p)
            chunk = "\n".join(p for p in [chunk, extra] if p)
        if c.get("type") in ("loreAccordion", "accordion"):
            if content:
                lore.append(content)
        elif chunk:
            body.append(chunk)
    return "\n\n".join(body), "\n\n".join(lore)


def resolve_detachment_rule(rule, idx):
    body_html, lore_html = assemble_components(idx["comp_by_rule"].get(rule["id"], []))
    return {"name": en(rule), "hidden_from_command_bunker": bool(rule.get("hiddenFromCommandBunker")),
            "body_html": body_html, "body_text": to_plain_text(body_html),
            "lore_text": to_plain_text(lore_html)}


def resolve_enhancement(e, idx):
    groups = []
    for g in idx["enh_groups"].get(e["id"], []):
        facs = [en(idx["faction_by_id"].get(f)) for f in idx["enh_grp_fac"].get(g["id"], [])]
        kws = [en(idx["keyword_by_id"].get(k)) for k in idx["enh_grp_kw"].get(g["id"], [])]
        ds = en(idx["datasheet_by_id"].get(g["datasheetId"])) if g.get("datasheetId") else None
        groups.append({"datasheet": ds, "faction_keywords": [f for f in facs if f],
                       "keywords": [k for k in kws if k]})
    excluded = [en(idx["keyword_by_id"].get(k)) for k in
                [r["keywordId"] for r in idx["enh_excluded"].get(e["id"], [])]]
    excluded = [k for k in excluded if k]
    group_strs = []
    for g in groups:
        toks = ([g["datasheet"]] if g["datasheet"] else []) + g["keywords"] + g["faction_keywords"]
        if toks:
            group_strs.append(" + ".join(toks))
    text = ("Bearer must be: " + " OR ".join(group_strs)) if group_strs else ""
    if excluded:
        text += ("; " if text else "") + "excluding: " + ", ".join(excluded)
    return {"name": en(e), "points": e.get("basePointsCost"), "type": e.get("enhancementType"),
            "is_combat_patrol": bool(e.get("isCombatPatrol")),
            "cannot_be_warlord": bool(e.get("cannotBeWarlord")),
            "lore": to_plain_text(en(e, "lore")),
            "rules_html": en(e, "rules"), "rules_text": to_plain_text(en(e, "rules")),
            "eligibility": {"required_groups": groups, "excluded_keywords": excluded},
            "eligibility_text": text}


def resolve_stratagem(s, idx):
    phases = [PHASE_LABEL.get(p, p) for p in idx["phases_by_strat"].get(s["id"], [])]
    return {"name": en(s), "cp_cost": s.get("cpCost"), "category": s.get("category"),
            "used_when": WHEN_LABEL.get(s.get("key"), s.get("key")), "phases": phases,
            "lore": to_plain_text(en(s, "lore")),
            "when_html": en(s, "whenRules"), "when_text": to_plain_text(en(s, "whenRules")),
            "target_text": to_plain_text(en(s, "targetRules")),
            "effect_html": en(s, "effectRules"), "effect_text": to_plain_text(en(s, "effectRules")),
            "restriction_text": to_plain_text(en(s, "restrictionRules")),
            "secondary_effect_text": to_plain_text(en(s, "secondaryEffect"))}


def resolve_detachment(det, idx):
    did = det["id"]
    restr = []
    for detail in idx["detail_by_det"].get(did, []):
        bullets = [to_plain_text(en(b, "text")) for b in idx["bullets_by_detail"].get(detail["id"], [])]
        restr.append({"title": en(detail, "title"), "bullets": [b for b in bullets if b]})
    linked = sorted(en(idx["datasheet_by_id"].get(r["datasheetId"]))
                    for r in idx["det_linked_ds"].get(did, []))
    excluded = sorted(en(idx["datasheet_by_id"].get(r["datasheetId"]))
                      for r in idx["det_excluded_ds"].get(did, []))
    pub = idx["publication_by_id"].get(det.get("publicationId"))
    return {"id": did, "name": en(det), "is_combat_patrol": bool(det.get("isCombatPatrol")),
            "is_free_from_entitlements": bool(det.get("isFreeFromEntitlements")),
            "source_publication": en(pub) if pub else None,
            "detachment_points_cost": det.get("detachmentPointsCost"),
            "restrictions": restr,
            "unlocks_datasheets": [x for x in linked if x],
            "excludes_datasheets": [x for x in excluded if x],
            "rules": [resolve_detachment_rule(r, idx) for r in idx["rules_by_det"].get(did, [])],
            "enhancements": [resolve_enhancement(e, idx) for e in idx["enh_by_det"].get(did, [])],
            "stratagems": [resolve_stratagem(s, idx) for s in idx["strat_by_det"].get(did, [])]}


# ===========================================================================
# Faction meta resolution
# ===========================================================================

def resolve_faction_meta(fid, idx):
    fac = idx["faction_by_id"].get(fid)
    parent = idx["faction_by_id"].get(fac.get("parentFactionKeywordId")) if fac else None
    army_rules = []
    for arid in idx["army_by_fac"].get(fid, []):
        ar = idx["army_rule_by_id"].get(arid)
        if not ar:
            continue
        body_html, _ = assemble_components(idx["comp_by_armyrule"].get(arid, []))
        army_rules.append({"name": en(ar), "body_html": body_html,
                           "body_text": to_plain_text(body_html)})
    # allegiance abilities scoped to this faction (via their group's detachment faction)
    alleg = []
    for grp in idx["alleg_group_by_id"].values():
        det_id = grp.get("detachmentId")
        if det_id and fid in idx["det_faction_ids"].get(det_id, []):
            abilities = [{"name": en(a), "rules": en(a, "rules")}
                         for a in idx["alleg_by_group"].get(grp["id"], [])]
            if abilities:
                alleg.append({"group": en(grp), "is_mandatory": bool(grp.get("isMandatory")),
                              "min": grp.get("minRosterLimit"), "max": grp.get("maxRosterLimit"),
                              "abilities": abilities})
    pubs = [{"name": en(p), "is_core_rules": bool(p.get("isCoreRules")),
             "is_legends": bool(p.get("isLegends")), "errata_date": p.get("errataDate")}
            for p in idx["pub_by_fac"].get(fid, [])]
    # Display labels. The base Warhammer 40,000 app shows commonName when it is
    # present and falls back to name otherwise. name and parent_faction stay as
    # the canonical keys (parent linking is keyed on name), so the display swap
    # is precomputed here and never mutates those keys.
    fac_name = en(fac)
    fac_display = en(fac, "commonName") or fac_name
    parent_name = en(parent) if parent else None
    parent_display = (en(parent, "commonName") or en(parent)) if parent else None
    return {
        "id": fid, "name": fac_name, "common_name": en(fac, "commonName"),
        "display_name": fac_display,
        "parent_faction": parent_name,
        "parent_display_name": parent_display,
        "excluded_from_army_builder": bool(fac.get("excludedFromArmyBuilder")),
        "lore": en(fac, "lore"),
        "army_rules": army_rules,
        "allegiance_abilities": alleg,
        "publications": pubs,
    }


# ===========================================================================
# Reference (cross faction) resolution
# ===========================================================================

def resolve_allied_factions(data, idx):
    """Resolve the allied faction system into a name resolved, queryable shape.

    Each allied faction lets one or more host factions bring a slice of another
    faction's units (for example Drukhari allying Harlequins, or several Chaos
    factions allying Legiones Daemonica). The source spreads this across many
    tables keyed on allied faction id; this pulls them together.
    """
    bs_name = {b["id"]: en(b) for b in data.get("battle_size", [])}
    det_name = {d["id"]: en(d) for d in data.get("detachment", [])}

    host = defaultdict(list)
    for r in data.get("faction_keyword_allied_faction", []):
        host[r["alliedFactionId"]].append(r["factionKeywordId"])
    parent = defaultdict(list)
    for r in data.get("allied_faction_parent_faction_keyword", []):
        parent[r["alliedFactionId"]].append(r["factionKeywordId"])
    af_ds = defaultdict(list)
    for r in data.get("allied_faction_datasheet", []):
        af_ds[r["alliedFactionId"]].append(r["datasheetId"])
    plim = defaultdict(list)
    for r in data.get("allied_faction_points_limit", []):
        plim[r["alliedFactionId"]].append({"battle_size": bs_name.get(r.get("battleSizeId")),
                                            "points": r.get("pointsLimit")})
    reqdet = defaultdict(list)
    for r in data.get("allied_faction_required_detachment", []):
        nm = det_name.get(r.get("detachmentId"))
        if nm:
            reqdet[r["alliedFactionId"]].append(nm)
    kwlim = defaultdict(list)
    for r in data.get("allied_faction_keyword", []):
        kwlim[r["alliedFactionId"]].append({
            "keyword": en(idx["keyword_by_id"].get(r.get("keywordId"))),
            "limit": r.get("limitCount"),
            "battle_size": bs_name.get(r.get("battleSizeId"))})

    out = []
    for af in data.get("allied_faction", []):
        aid = af["id"]
        host_ids = host.get(aid, [])
        ds_ids = af_ds.get(aid, [])
        out.append({
            "id": aid,
            "ally_factions": [en(idx["faction_by_id"].get(f)) for f in parent.get(aid, [])],
            "host_factions": [en(idx["faction_by_id"].get(f)) for f in host_ids],
            "host_faction_ids": host_ids,
            "can_take_enhancements": bool(af.get("canTakeEnhancements")),
            "is_sibling_faction": bool(af.get("isSiblingFaction")),
            "replaces_roster_keyword": bool(af.get("replacesRosterFactionKeyword")),
            "mutually_exclusive_keyword_limit": bool(af.get("isMutuallyExclusiveKeywordLimit")),
            "datasheets": [en(idx["datasheet_by_id"].get(d)) for d in ds_ids],
            "datasheet_ids": ds_ids,
            "keyword_limits": kwlim.get(aid, []),
            "points_limits": plim.get(aid, []),
            "required_detachments": reqdet.get(aid, []),
        })
    out.sort(key=lambda a: ((a["host_factions"][0] if a["host_factions"] else "").lower(),
                            (a["ally_factions"][0] if a["ally_factions"] else "").lower()))
    return out


def resolve_reference(data, idx):
    keywords = [{"name": en(k)} for k in data["keyword"] if en(k)]
    keywords.sort(key=lambda x: x["name"].lower())

    wargear_abilities = [{"name": en(a), "rules": to_plain_text(en(a, "rules")),
                          "lore": to_plain_text(en(a, "lore"))}
                         for a in data["wargear_ability"] if en(a)]
    wargear_abilities.sort(key=lambda x: x["name"].lower())

    publications = [{"name": en(p), "faction": en(idx["faction_by_id"].get(p.get("factionKeywordId"))),
                     "is_core_rules": bool(p.get("isCoreRules")), "is_legends": bool(p.get("isLegends")),
                     "is_combat_patrol": bool(p.get("isCombatPatrol")), "errata_date": p.get("errataDate")}
                    for p in data["publication"]]
    publications.sort(key=lambda x: (x["name"] or "").lower())

    battle_sizes = [{"name": en(b), "points_limit": b.get("pointsLimit"),
                     "detachment_points_limit": b.get("detachmentPointsLimit"),
                     "enhancement_limit": b.get("enhancementLimit"),
                     "duplicate_unit_limit": b.get("duplicateUnitLimit")}
                    for b in data["battle_size"]]

    behaviour_types = [{"name": en(b), "type": b.get("type"),
                        "rule_reference": en(b, "ruleReference"),
                        "eligible_if": to_plain_text(en(b, "eligibleIf")),
                        "effect": to_plain_text(en(b, "effect"))}
                       for b in data["behaviour_type"]]

    # core rules: sections -> containers -> text components
    sec_by_id = {s["id"]: s for s in data["rule_section"]}
    cont_by_section = defaultdict(list)
    for c in sorted(data["rule_container"], key=lambda c: c.get("displayOrder") or 0):
        cont_by_section[c.get("ruleSectionId")].append(c)
    comp_by_container = defaultdict(list)
    for comp in sorted(data["rule_container_component"], key=lambda c: c.get("displayOrder") or 0):
        if comp.get("ruleContainerId"):
            comp_by_container[comp["ruleContainerId"]].append(comp)
    core_rules = []
    for s in sorted(data["rule_section"], key=lambda s: s.get("displayOrder") or 0):
        containers = []
        for c in cont_by_section.get(s["id"], []):
            comps = []
            for comp in comp_by_container.get(c["id"], []):
                txt = to_plain_text(en(comp, "textContent"))
                if txt or en(comp, "title"):
                    comps.append({"type": comp.get("type"), "title": en(comp, "title"),
                                  "text": txt})
            containers.append({"title": en(c, "title"), "subtitle": en(c, "subtitle"),
                               "components": comps})
        core_rules.append({"section": en(s), "containers": containers})

    # missions
    pm_obj = defaultdict(list)
    for o in sorted(data["primary_mission_objective"], key=lambda o: o.get("displayOrder") or 0):
        pm_obj[o["primaryMissionId"]].append({"name": en(o), "when": to_plain_text(en(o, "whenText"))})
    primary = [{"id": m["id"], "pack": m.get("missionPackId"), "name": en(m),
                "lore": to_plain_text(en(m, "lore")),
                "description": to_plain_text(en(m, "description")),
                "objectives": pm_obj.get(m["id"], [])} for m in data["primary_mission"]]
    secondary = [{"id": m["id"], "pack": m.get("missionPackId"), "name": en(m),
                  "fixed": bool(m.get("isFixedSecondary")),
                  "scorable_first_turn": bool(m.get("isScorableFirstTurn")),
                  "lore": to_plain_text(en(m, "lore")),
                  "description": to_plain_text(en(m, "description"))}
                 for m in data["secondary_mission"]]
    deployments = [{"id": m["id"], "pack": m.get("missionPackId"), "name": en(m)}
                   for m in data["mission_deployment"]]
    layouts = [{"id": m["id"], "pack": m.get("missionPackId"), "name": en(m)}
               for m in data["mission_layout"]]
    presets = [{"id": m["id"], "pack": m.get("missionPackId"),
                "layout_id": m.get("missionLayoutId"),
                "deployment_id": m.get("missionDeploymentId"), "name": en(m)}
               for m in data["mission_preset"]]
    twists = [{"id": m["id"], "pack": m.get("missionPackId"), "name": en(m),
               "lore": to_plain_text(en(m, "lore")), "rules": to_plain_text(en(m, "rules"))}
              for m in data["mission_twist"]]
    packs = [{"id": m["id"], "name": en(m)} for m in data["mission_pack"]]
    dispositions = [{"name": en(m)} for m in data["force_disposition"]]
    missions = {"packs": packs, "primary_missions": primary, "secondary_missions": secondary,
                "deployments": deployments, "layouts": layouts, "presets": presets,
                "twists": twists, "force_dispositions": dispositions}

    # faqs
    cfg_by_faq = defaultdict(list)
    for c in data["faq_config"]:
        cfg_by_faq[c.get("faqId")].append(c)

    def faq_applies(fid):
        labels = []
        for c in cfg_by_faq.get(fid, []):
            if c.get("datasheetId"):
                labels.append("datasheet: " + (en(idx["datasheet_by_id"].get(c["datasheetId"])) or "?"))
            if c.get("detachmentId"):
                labels.append("detachment")
            if c.get("enhancementId"):
                labels.append("enhancement")
            if c.get("stratagemId"):
                labels.append("stratagem")
            if c.get("armyRuleId"):
                labels.append("army rule: " + (en(idx["army_rule_by_id"].get(c["armyRuleId"])) or "?"))
        return sorted(set(labels))

    faqs = []
    for f in sorted(data["faq"], key=lambda f: f.get("displayOrder") or 0):
        faqs.append({"id": f["id"], "errata_header": en(f, "errataHeader"),
                     "errata_text": to_plain_text(en(f, "errataText")),
                     "question": to_plain_text(en(f, "question")),
                     "answer": to_plain_text(en(f, "answer")),
                     "applies_to": faq_applies(f["id"])})

    return {"keywords": keywords, "wargear_abilities": wargear_abilities,
            "publications": publications, "battle_sizes": battle_sizes,
            "behaviour_types": behaviour_types, "core_rules": core_rules,
            "missions": missions, "faqs": faqs,
            "allied_factions": resolve_allied_factions(data, idx)}


# ===========================================================================
# CSV writers
# ===========================================================================

def write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def weapon_text(w):
    bits = []
    for p in w["profiles"]:
        skill = p.get("BS") or p.get("WS") or "-"
        label = "BS" if p.get("BS") else ("WS" if p.get("WS") else "Sk")
        stat = "Rng:%s A:%s %s:%s S:%s AP:%s D:%s" % (p.get("range") or "-", p.get("A") or "-",
                label, skill, p.get("S") or "-", p.get("AP") or "-", p.get("D") or "-")
        ab = (" [" + ", ".join(p["abilities"]) + "]") if p["abilities"] else ""
        bits.append("%s (%s)%s" % (p.get("name") or w["name"], stat, ab))
    return " / ".join(bits) if bits else w["name"]


def flatten(text):
    return re.sub(r"\s*\n\s*", " ", str(text)).replace("\r", " ").strip()


DS_COLS = ["faction", "unit_name", "points", "points_options", "legends",
           "free_from_entitlements", "source", "base_size", "keywords",
           "conditional_keywords", "model_count", "M", "T", "Sv", "Inv", "W", "Ld", "OC",
           "models_detail", "abilities", "extra_rules", "weapons",
           "wargear_options", "wargear_upgrades", "leads_units", "can_be_led_by",
           "unit_composition", "datasheet_id"]


def datasheet_row(faction, u):
    vis = [m for m in u["models"] if not m["statline_hidden"]]
    primary = vis[0] if vis else (u["models"][0] if u["models"] else {})
    dflt = next((c for c in u["points"] if c["is_default"]), None) or (u["points"][0] if u["points"] else {})
    allpts = sorted({c["points"] for c in u["points"] if c.get("points") is not None})
    return {
        "faction": faction, "unit_name": u["name"], "points": dflt.get("points"),
        "points_options": join_cell(allpts, ", ") if len(allpts) > 1 else "",
        "legends": "yes" if u["is_legends"] else "no",
        "free_from_entitlements": "yes" if u["is_free_from_entitlements"] else "no",
        "source": u.get("source_publication") or "",
        "base_size": u.get("base_size") or "",
        "keywords": join_cell(u["keywords"], ", "),
        "conditional_keywords": join_cell(["%s (%s)" % (c["keyword"], c["condition"]) for c in u["conditional_keywords"]]),
        "model_count": len(vis),
        "M": primary.get("M") or "", "T": primary.get("T") or "", "Sv": primary.get("Sv") or "",
        "Inv": primary.get("Inv") or "", "W": primary.get("W") or "",
        "Ld": primary.get("Ld") or "", "OC": primary.get("OC") or "",
        "models_detail": join_cell(["%s [M:%s T:%s Sv:%s Inv:%s W:%s Ld:%s OC:%s]" % (
            m.get("name") or "Model", m.get("M") or "-", m.get("T") or "-", m.get("Sv") or "-",
            m.get("Inv") or "-", m.get("W") or "-", m.get("Ld") or "-", m.get("OC") or "-")
            for m in vis]),
        "abilities": join_cell([a["name"] for a in u["abilities"]]),
        "extra_rules": join_cell([r["name"] for r in u["extra_rules"]]),
        "weapons": join_cell([weapon_text(w) for w in u["weapons"]]),
        "wargear_options": join_cell([flatten(o) for o in u["wargear_loadout"]["rules_text"]]),
        "wargear_upgrades": join_cell(["%s (+%s pts)" % (o["item"], o["points"])
                                       for o in u["wargear_loadout"]["priced_options"]]),
        "leads_units": join_cell(u["leads_units"], ", "),
        "can_be_led_by": join_cell(u["can_be_led_by"], ", "),
        "unit_composition": flatten(u.get("unit_composition_text") or ""),
        "datasheet_id": u["id"],
    }


WL_COLS = ["faction", "unit_name", "miniature", "mechanism", "detail", "items", "points"]


def wargear_loadout_rows(faction, u):
    rows = []
    wl = u["wargear_loadout"]
    for o in wl["options"]:
        if o.get("points") or o.get("input_type") not in ("stepper",):
            rows.append({"faction": faction, "unit_name": u["name"], "miniature": o.get("miniature") or "",
                         "mechanism": "option", "detail": (o.get("group") or "") +
                         (" [%s]" % o["input_type"] if o.get("input_type") else ""),
                         "items": o.get("item") or "", "points": o.get("points") or ""})
    for s in wl["choose_from"]:
        for choice in s["choices"]:
            items = join_cell(["%s x%s" % (i["item"], i["count"]) if i.get("count") and i["count"] != 1
                               else i["item"] for i in choice], ", ")
            rows.append({"faction": faction, "unit_name": u["name"], "miniature": s.get("miniature") or "",
                         "mechanism": "choose %s" % (s.get("limit") or 1),
                         "detail": "alternate" if s.get("alternate") else
                         ("duplicates allowed" if s.get("allow_duplicates") else ""),
                         "items": items, "points": ""})
    for s in wl["limited_choices"]:
        lim = "; ".join("for every %s models up to %s%s" % (
            l.get("per_models") or 0, l.get("max_choices") or 0,
            (" (max %s each)" % l["duplicate_limit"]) if l.get("duplicate_limit") else "")
            for l in s["limits"])
        for choice in s["choices"]:
            items = join_cell([i["item"] for i in choice], ", ")
            rows.append({"faction": faction, "unit_name": u["name"], "miniature": s.get("miniature") or "",
                         "mechanism": "limited" + (" (mandatory)" if s.get("mandatory") else ""),
                         "detail": lim, "items": items, "points": ""})
    for s in wl["all_model_choices"]:
        for choice in s["choices"]:
            items = join_cell([i["item"] for i in choice["items"]], ", ")
            rows.append({"faction": faction, "unit_name": u["name"], "miniature": s.get("miniature") or "",
                         "mechanism": "all models" + (" (substitute)" if choice.get("substitute") else ""),
                         "detail": "", "items": items, "points": ""})
    return rows


DET_COLS = ["faction", "detachment", "combat_patrol", "source", "detachment_points_cost",
            "rule_names", "enhancement_count", "stratagem_count", "unlocks", "excludes",
            "restrictions", "detachment_id"]
RULE_COLS = ["faction", "detachment", "rule_name", "rule_text", "lore"]
ENH_COLS = ["faction", "detachment", "enhancement", "points", "type", "combat_patrol",
            "eligibility", "rules", "lore"]
STRAT_COLS = ["faction", "detachment", "stratagem", "cp_cost", "category", "used_when",
              "phases", "when", "target", "effect", "restriction", "secondary_effect", "lore"]


def detachment_csv_rows(faction, dets):
    drow, rrow, erow, srow = [], [], [], []
    for d in dets:
        restr = " || ".join("%s: %s" % (r["title"] or "", "; ".join(r["bullets"])) for r in d["restrictions"])
        drow.append({"faction": faction, "detachment": d["name"],
                     "combat_patrol": "yes" if d["is_combat_patrol"] else "no",
                     "source": d.get("source_publication") or "",
                     "detachment_points_cost": d.get("detachment_points_cost"),
                     "rule_names": "; ".join(r["name"] for r in d["rules"] if r["name"]),
                     "enhancement_count": len(d["enhancements"]), "stratagem_count": len(d["stratagems"]),
                     "unlocks": join_cell(d["unlocks_datasheets"], ", "),
                     "excludes": join_cell(d["excludes_datasheets"], ", "),
                     "restrictions": cell(restr), "detachment_id": d["id"]})
        for r in d["rules"]:
            rrow.append({"faction": faction, "detachment": d["name"], "rule_name": r["name"],
                         "rule_text": cell(r["body_text"]), "lore": cell(r["lore_text"])})
        for e in d["enhancements"]:
            erow.append({"faction": faction, "detachment": d["name"], "enhancement": e["name"],
                         "points": e["points"], "type": e["type"],
                         "combat_patrol": "yes" if e["is_combat_patrol"] else "no",
                         "eligibility": cell(e["eligibility_text"]),
                         "rules": cell(e["rules_text"]), "lore": cell(e["lore"])})
        for s in d["stratagems"]:
            srow.append({"faction": faction, "detachment": d["name"], "stratagem": s["name"],
                         "cp_cost": s["cp_cost"], "category": s["category"] or "",
                         "used_when": s["used_when"] or "", "phases": ", ".join(s["phases"]),
                         "when": cell(s["when_text"]), "target": cell(s["target_text"]),
                         "effect": cell(s["effect_text"]), "restriction": cell(s["restriction_text"]),
                         "secondary_effect": cell(s["secondary_effect_text"]), "lore": cell(s["lore"])})
    return drow, rrow, erow, srow


# ===========================================================================
# Export driver
# ===========================================================================

def export(apk_path, out_dir, write_json=True, csv_on=True, sqlite_on=False, log=print):
    parsed = load_dump_from_apk(apk_path)
    data, idx = build_index(parsed)
    log("Data version: %s" % idx["data_version"])

    # group datasheets and detachments by faction keyword
    ds_by_fac, det_by_fac = defaultdict(list), defaultdict(list)
    for dsid in idx["datasheet_by_id"]:
        rec = resolve_datasheet(dsid, idx)
        fids = idx["ds_faction_ids"].get(dsid, []) or [None]
        for fid in fids:
            ds_by_fac[fid].append((en(idx["faction_by_id"].get(fid)) or "Unaligned", rec))
    for det in data["detachment"]:
        rec = resolve_detachment(det, idx)
        fids = idx["det_faction_ids"].get(det["id"], []) or [None]
        for fid in fids:
            det_by_fac[fid].append((en(idx["faction_by_id"].get(fid)) or "Unaligned", rec))

    faction_ids = set(ds_by_fac) | set(det_by_fac)
    os.makedirs(out_dir, exist_ok=True)
    factions_root = os.path.join(out_dir, "factions")
    os.makedirs(factions_root, exist_ok=True)

    manifest = {"data_version": idx["data_version"], "source_apk": os.path.basename(apk_path),
                "factions": {}, "reference": {}}
    totals = defaultdict(int)

    for fid in sorted(faction_ids, key=lambda f: (en(idx["faction_by_id"].get(f)) or "Unaligned").lower()):
        fname = en(idx["faction_by_id"].get(fid)) or "Unaligned"
        stem = sanitise(fname)
        fdir = os.path.join(factions_root, stem)
        os.makedirs(fdir, exist_ok=True)

        units = [r for _, r in sorted(ds_by_fac.get(fid, []), key=lambda x: (x[1]["name"] or "").lower())]
        dets = [r for _, r in sorted(det_by_fac.get(fid, []), key=lambda x: (x[1]["name"] or "").lower())]
        meta = resolve_faction_meta(fid, idx) if fid else {"id": None, "name": "Unaligned"}

        totals["datasheets"] += len(units)
        totals["detachments"] += len(dets)
        totals["enhancements"] += sum(len(d["enhancements"]) for d in dets)
        totals["stratagems"] += sum(len(d["stratagems"]) for d in dets)
        totals["detachment_rules"] += sum(len(d["rules"]) for d in dets)

        files = []
        if write_json:
            with open(os.path.join(fdir, "faction.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            files.append("faction.json")
            with open(os.path.join(fdir, "datasheets.json"), "w", encoding="utf-8") as f:
                json.dump({"faction": fname, "unit_count": len(units), "units": units},
                          f, ensure_ascii=False, indent=2)
            files.append("datasheets.json")
            with open(os.path.join(fdir, "detachments.json"), "w", encoding="utf-8") as f:
                json.dump({"faction": fname, "detachment_count": len(dets), "detachments": dets},
                          f, ensure_ascii=False, indent=2)
            files.append("detachments.json")

        if csv_on:
            if units:
                write_csv(os.path.join(fdir, "datasheets.csv"), DS_COLS,
                          [datasheet_row(fname, u) for u in units])
                files.append("datasheets.csv")
                wl_rows = []
                for u in units:
                    wl_rows.extend(wargear_loadout_rows(fname, u))
                if wl_rows:
                    write_csv(os.path.join(fdir, "wargear_loadouts.csv"), WL_COLS, wl_rows)
                    files.append("wargear_loadouts.csv")
            if dets:
                drow, rrow, erow, srow = detachment_csv_rows(fname, dets)
                for fn, cols, rows in [("detachments.csv", DET_COLS, drow),
                                       ("detachment_rules.csv", RULE_COLS, rrow),
                                       ("enhancements.csv", ENH_COLS, erow),
                                       ("stratagems.csv", STRAT_COLS, srow)]:
                    if rows:
                        write_csv(os.path.join(fdir, fn), cols, rows)
                        files.append(fn)

        manifest["factions"][fname] = {"datasheets": len(units), "detachments": len(dets),
                                       "files": files}
        log("  %-28s units %3d  detachments %2d" % (fname, len(units), len(dets)))

    # reference data
    log("Writing reference data...")
    ref = resolve_reference(data, idx)
    ref_dir = os.path.join(out_dir, "_reference")
    os.makedirs(ref_dir, exist_ok=True)
    write_reference(ref_dir, ref, write_json, csv_on, manifest)

    manifest["totals"] = dict(totals)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    write_readme(out_dir, manifest, ref)

    if sqlite_on:
        log("Building SQLite database...")
        db_path = os.path.join(out_dir, "w40k.db")
        build_sqlite(data, idx, ref, db_path, log=log)
        manifest["sqlite"] = os.path.basename(db_path)

    log("")
    log("Done. Output folder: %s" % out_dir)
    log("Factions: %d | datasheets: %d | detachments: %d | enhancements: %d | stratagems: %d"
        % (len(manifest["factions"]), totals["datasheets"], totals["detachments"],
           totals["enhancements"], totals["stratagems"]))
    return manifest


def write_reference(ref_dir, ref, write_json, csv_on, manifest):
    # Public copy of allies without the internal id helper fields used for joins.
    allies_public = []
    for a in ref.get("allied_factions", []):
        allies_public.append({k: v for k, v in a.items()
                              if k not in ("id", "host_faction_ids", "datasheet_ids")})
    if write_json:
        for name in ["keywords", "wargear_abilities", "publications", "battle_sizes",
                     "behaviour_types", "core_rules", "missions", "faqs"]:
            with open(os.path.join(ref_dir, name + ".json"), "w", encoding="utf-8") as f:
                json.dump(ref[name], f, ensure_ascii=False, indent=2)
        with open(os.path.join(ref_dir, "allied_factions.json"), "w", encoding="utf-8") as f:
            json.dump(allies_public, f, ensure_ascii=False, indent=2)
    if csv_on:
        write_csv(os.path.join(ref_dir, "keywords.csv"), ["keyword"],
                  [{"keyword": k["name"]} for k in ref["keywords"]])
        write_csv(os.path.join(ref_dir, "wargear_abilities.csv"), ["name", "rules", "lore"],
                  [{"name": a["name"], "rules": cell(a["rules"]), "lore": cell(a["lore"])}
                   for a in ref["wargear_abilities"]])
        write_csv(os.path.join(ref_dir, "publications.csv"),
                  ["name", "faction", "is_core_rules", "is_legends", "is_combat_patrol", "errata_date"],
                  [{"name": p["name"], "faction": p["faction"] or "",
                    "is_core_rules": p["is_core_rules"], "is_legends": p["is_legends"],
                    "is_combat_patrol": p["is_combat_patrol"], "errata_date": p["errata_date"] or ""}
                   for p in ref["publications"]])
        write_csv(os.path.join(ref_dir, "battle_sizes.csv"),
                  ["name", "points_limit", "detachment_points_limit", "enhancement_limit", "duplicate_unit_limit"],
                  [{"name": b["name"], "points_limit": b["points_limit"],
                    "detachment_points_limit": b["detachment_points_limit"],
                    "enhancement_limit": b["enhancement_limit"],
                    "duplicate_unit_limit": b["duplicate_unit_limit"]} for b in ref["battle_sizes"]])
        write_csv(os.path.join(ref_dir, "behaviour_types.csv"),
                  ["name", "type", "rule_reference", "eligible_if", "effect"],
                  [{"name": b["name"], "type": b["type"], "rule_reference": b["rule_reference"] or "",
                    "eligible_if": cell(b["eligible_if"]), "effect": cell(b["effect"])}
                   for b in ref["behaviour_types"]])
        crows = []
        for sec in ref["core_rules"]:
            for cont in sec["containers"]:
                for comp in cont["components"]:
                    crows.append({"section": sec["section"], "container": cont["title"] or "",
                                  "subtitle": cont["subtitle"] or "", "type": comp["type"] or "",
                                  "title": comp["title"] or "", "text": cell(comp["text"])})
        write_csv(os.path.join(ref_dir, "core_rules.csv"),
                  ["section", "container", "subtitle", "type", "title", "text"], crows)
        mrows = []
        for m in ref["missions"]["primary_missions"]:
            mrows.append({"type": "primary", "name": m["name"], "detail": cell(m["lore"] or m["description"])})
        for m in ref["missions"]["secondary_missions"]:
            mrows.append({"type": "secondary", "name": m["name"], "detail": cell(m["description"])})
        for key in ["deployments", "layouts", "presets", "force_dispositions"]:
            for m in ref["missions"][key]:
                mrows.append({"type": key[:-1], "name": m["name"], "detail": ""})
        write_csv(os.path.join(ref_dir, "missions.csv"), ["type", "name", "detail"], mrows)
        write_csv(os.path.join(ref_dir, "faqs.csv"),
                  ["errata_header", "errata_text", "question", "answer", "applies_to"],
                  [{"errata_header": f["errata_header"] or "", "errata_text": cell(f["errata_text"]),
                    "question": cell(f["question"]), "answer": cell(f["answer"]),
                    "applies_to": "; ".join(f["applies_to"])} for f in ref["faqs"]])
        arows = []
        for a in ref.get("allied_factions", []):
            pts = ", ".join("%s %s" % (p["battle_size"], p["points"]) for p in a["points_limits"])
            kwl = ", ".join("%s x%s %s" % (k["keyword"], k["limit"], k["battle_size"])
                            for k in a["keyword_limits"])
            arows.append({
                "host_factions": "; ".join(x for x in a["host_factions"] if x),
                "ally_factions": "; ".join(x for x in a["ally_factions"] if x),
                "datasheets": "; ".join(x for x in a["datasheets"] if x),
                "keyword_limits": kwl, "points_limits": pts,
                "required_detachments": "; ".join(a["required_detachments"]),
                "can_take_enhancements": a["can_take_enhancements"],
                "is_sibling_faction": a["is_sibling_faction"]})
        write_csv(os.path.join(ref_dir, "allied_factions.csv"),
                  ["host_factions", "ally_factions", "datasheets", "keyword_limits",
                   "points_limits", "required_detachments", "can_take_enhancements",
                   "is_sibling_faction"], arows)
    manifest["reference"] = {
        "keywords": len(ref["keywords"]), "wargear_abilities": len(ref["wargear_abilities"]),
        "publications": len(ref["publications"]), "battle_sizes": len(ref["battle_sizes"]),
        "behaviour_types": len(ref["behaviour_types"]),
        "core_rules_sections": len(ref["core_rules"]),
        "primary_missions": len(ref["missions"]["primary_missions"]),
        "secondary_missions": len(ref["missions"]["secondary_missions"]),
        "faqs": len(ref["faqs"]),
        "allied_factions": len(ref.get("allied_factions", [])),
    }


# ===========================================================================
# README
# ===========================================================================

def write_readme(out_dir, manifest, ref):
    t = manifest["totals"]
    r = manifest["reference"]
    lines = []
    A = lines.append
    A("# Warhammer 40,000 App Data Export")
    A("")
    A("Generated from `%s`, game data version **%s**." % (manifest["source_apk"], manifest["data_version"]))
    A("")
    A("## Contents at a glance")
    A("")
    A("- Factions: **%d**" % len(manifest["factions"]))
    A("- Datasheet records: **%d** (units are filed under each faction keyword they carry, so sub faction units appear in both the parent army folder and their own)" % t["datasheets"])
    A("- Detachments: **%d**, with %d detachment rules, %d enhancements, %d stratagems"
      % (t["detachments"], t["detachment_rules"], t["enhancements"], t["stratagems"]))
    A("- Reference: %d keywords, %d weapon abilities, %d publications, %d core rule sections, %d primary and %d secondary missions, %d FAQ entries"
      % (r["keywords"], r["wargear_abilities"], r["publications"], r["core_rules_sections"],
         r["primary_missions"], r["secondary_missions"], r["faqs"]))
    A("")
    A("Every dataset is written as both JSON (full nested fidelity) and CSV (flattened, one row per record). Text fields keep the source's light markup in the JSON `*_html` fields and a cleaned plain text version everywhere else. CSV files are UTF-8 with a BOM so they open cleanly in Excel.")
    A("")
    A("## Folder layout")
    A("")
    A("```")
    A("<output>/")
    A("  README.md                 this file")
    A("  manifest.json             machine readable summary and per faction file list")
    A("  factions/")
    A("    <Faction>/")
    A("      faction.json          faction meta: lore, army rules (with body text),")
    A("                            allegiance abilities, publications")
    A("      datasheets.json       full nested unit records")
    A("      datasheets.csv        one row per unit (summary)")
    A("      wargear_loadouts.csv  structured loadout enforcement, one row per choice")
    A("      detachments.json      full nested detachment records")
    A("      detachments.csv       one row per detachment")
    A("      detachment_rules.csv  one row per detachment rule (full text)")
    A("      enhancements.csv      one row per enhancement (with eligibility)")
    A("      stratagems.csv        one row per stratagem")
    A("  _reference/               cross faction data (shared by all armies)")
    A("      keywords.(json|csv)")
    A("      wargear_abilities.(json|csv)   weapon ability glossary (Rapid Fire, Lethal Hits, ...)")
    A("      publications.(json|csv)        source books")
    A("      battle_sizes.(json|csv)        points and detachment limits per game size")
    A("      behaviour_types.(json|csv)     movement behaviours")
    A("      core_rules.(json|csv)          the bundled core rulebook text")
    A("      missions.(json|csv)            primary and secondary missions, deployments, layouts")
    A("      faqs.(json|csv)                official FAQ and errata")
    A("```")
    A("")
    A("## What each datasheet record contains")
    A("")
    A("Full identity and stats: name, faction keywords, source publication, base size, Legends flag, entitlement flag, unit keywords, and any conditional keywords with the condition that grants them. Per model statline (M, T, Sv, Invulnerable, W, Ld, OC) with each model's own keywords. Points for every unit composition (for example 10 or 20 model options) plus any per model step pricing.")
    A("")
    A("Rules content: abilities with full rules text and any sub abilities; extra datasheet rules (Transport, Deadly Demise and similar); damage brackets for vehicles and monsters.")
    A("")
    A("Weapons: every weapon the unit can field, each with all of its profiles (range, attacks, BS or WS, S, AP, D) and the weapon abilities on each profile.")
    A("")
    A("Leader attachment: `leads_units` lists the units a character can join, and `can_be_led_by` lists the characters that can join a unit.")
    A("")
    A("Wargear loadout, captured as structured enforcement logic under `wargear_loadout`:")
    A("")
    A("- `rules_text`: the human readable swap rules as shown on the datasheet.")
    A("- `options`: each selectable wargear option with its points cost, input type (stepper, checkbox, select) and default. `priced_options` is the subset that costs points.")
    A("- `choose_from`: \"select N of the following\" sets, with the limit, whether duplicates are allowed, and each choice as a bundle of items.")
    A("- `limited_choices`: \"for every N models, up to X may take\" sets, with the model count, choice limit and duplicate limit, plus whether the choice is mandatory.")
    A("- `all_model_choices`: choices applied across all models in the unit, including whether each is a substitution.")
    A("")
    A("The `wargear_loadouts.csv` flattens all four of these mechanisms into one row per choice, with a `mechanism` column identifying which system it came from.")
    A("")
    A("## What each detachment record contains")
    A("")
    A("Detachment name, source publication, Combat Patrol flag, detachment points cost, restriction boxes (the keyword and army restriction text), and the lists of datasheets a detachment unlocks or excludes. Then its detachment rules (full reconstructed body text plus lore), its enhancements, and its stratagems.")
    A("")
    A("Enhancements include name, points, type, rules text, lore, and structured `eligibility`: the required keyword groups (treated as alternatives, with the keywords inside a group all required) and the excluded keywords, plus a one line `eligibility_text` summary such as \"Bearer must be: Infantry + Warboss; excluding: Mega Armour\".")
    A("")
    A("Stratagems include CP cost, category (battle tactic, strategic ploy, epic deed, wargear), when in the turn they can be used, the game phases, and the when, target, effect, restriction and secondary effect text.")
    A("")
    A("## Optional SQLite database (w40k.db)")
    A("")
    A("If built, `w40k.db` holds the same resolved data in a relational schema designed for querying from a Python app (sqlite3 is in the standard library, so no driver is needed). Unlike the JSON folders, each datasheet and detachment is stored once; faction membership is handled by the `datasheet_faction` and `detachment_faction` junction tables, so sub faction units are not duplicated.")
    A("")
    A("Main tables: `faction`, `army_rule`, `publication`, `datasheet`, `datasheet_faction`, `allied_faction`, `allied_faction_host`, `allied_faction_datasheet`, `model`, `ability`, `extra_rule`, `weapon`, `weapon_profile`, `detachment`, `detachment_faction`, `detachment_rule`, `enhancement`, `stratagem`, plus reference tables `keyword`, `wargear_ability`, `battle_size`, `behaviour_type`, `mission_primary`, `mission_secondary`, `faq`. Deeply nested or list shaped fields (points compositions, the wargear loadout enforcement, enhancement eligibility, damage brackets, weapon ability lists, keyword lists) are stored as JSON text columns, so a top level value is queryable in SQL while the full structure is one `json.loads` away in Python.")
    A("")
    A("Faction membership in `datasheet_faction` respects explicit exclusions: a unit that carries a faction keyword but is barred from that faction (source `faction_keyword_excluded_datasheet`, for example Sir Hekhtur under Imperial Knights) is not listed under it.")
    A("")
    A("The allied faction system is captured in three tables. `allied_faction` is one row per allowance (a host faction bringing a slice of another faction), with `ally_factions` and `host_factions` as JSON name lists, the boolean flags (`can_take_enhancements`, `is_sibling_faction`, `replaces_roster_keyword`, `mutually_exclusive_keyword_limit`), and JSON columns for `datasheets`, `keyword_limits`, `points_limits` and `required_detachments`. `allied_faction_host` and `allied_faction_datasheet` are junctions keyed on faction id and datasheet id, so an app can answer 'what can faction X ally, and which units does it bring' with a join rather than parsing JSON.")
    A("")
    A("The `faction` table carries both canonical and display labels. `name` is the official faction keyword (for example `Adeptus Astartes`) and is the key that `parent_faction` points at, so neither should be overwritten. `display_name` is the label to show in a UI: it is `common_name` when the app provides one (so `Adeptus Astartes` displays as `Space Marines`) and falls back to `name` otherwise. `parent_display_name` is the same precomputed swap for the parent, so a chapter such as `Blood Angels` keeps its own name, links to its parent by `parent_faction = 'Adeptus Astartes'`, and can be shown nested under `Space Marines` without an extra lookup.")
    A("")
    A("### Rules reader tables")
    A("")
    A("The core rulebook is modelled for a reader app, not just dumped flat. `rule_section` is the navigation tree (each row carries `parent_id`, `mpath` and `depth`, ordered by `display_order`). `rule_block` is the ordered content of each section: one row per block with its `type` (text, header, accordion, image), the original markup in `content_html` (with the `<k>keyword</k>` tags kept for cross linking), a cleaned `content_text`, and `image_url` plus `alt_text` for image blocks. `rule_reference` resolves every `<k>` mention in a block to its target (`keyword`, `wargear_ability`, `datasheet`, or `unmatched`), so the app can render in text references as clickable links. `faq_reference` links FAQ entries to the datasheet, army rule, detachment, enhancement or stratagem they correct. (A flat `core_rule` table is also kept for simple cases.)")
    A("")
    A("A `datasheet_fts` full text search table (FTS5) over unit name, keywords and abilities is created when the SQLite build supports it. Example:")
    A("")
    A("```sql")
    A("-- every unit with a 4+ invulnerable save")
    A("SELECT DISTINCT d.name FROM datasheet d JOIN model m ON m.datasheet_id = d.id WHERE m.inv = '4+';")
    A("-- Orks units by points, most expensive first")
    A("SELECT d.name, d.default_points FROM datasheet d")
    A("  JOIN datasheet_faction df ON df.datasheet_id = d.id")
    A("  JOIN faction f ON f.id = df.faction_id")
    A("  WHERE f.name = 'Orks' ORDER BY d.default_points DESC;")
    A("```")
    A("")
    A("## Notes")
    A("")
    A("- Universal stratagems that belong to no detachment are not faction specific; they are not duplicated into every faction folder.")
    A("- A small number of records carry no faction keyword in the data (for example one Combat Patrol box variant). These are filed under an `Unaligned` faction folder rather than dropped.")
    A("- All data is read locally from your own copy of the APK. The artwork referenced by image URLs in the source is not downloaded.")
    A("")
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ===========================================================================
# SQLite build
# ===========================================================================

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE faction (
    id TEXT PRIMARY KEY, name TEXT, common_name TEXT, display_name TEXT,
    parent_faction TEXT, parent_display_name TEXT,
    excluded_from_army_builder INTEGER, lore TEXT, allegiance_abilities TEXT
);

CREATE TABLE army_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT, faction_id TEXT, name TEXT,
    body_text TEXT, body_html TEXT,
    FOREIGN KEY (faction_id) REFERENCES faction(id)
);

CREATE TABLE publication (
    id TEXT PRIMARY KEY, name TEXT, faction_id TEXT, is_core_rules INTEGER,
    is_legends INTEGER, is_combat_patrol INTEGER, errata_date TEXT
);

CREATE TABLE datasheet (
    id TEXT PRIMARY KEY, name TEXT, source_publication TEXT,
    is_legends INTEGER, is_free_from_entitlements INTEGER,
    base_size TEXT, max_model_count INTEGER, lore TEXT,
    unit_composition_text TEXT, keywords TEXT, conditional_keywords TEXT,
    points TEXT, points_steps TEXT, wargear_loadout TEXT,
    leads_units TEXT, can_be_led_by TEXT, damage_brackets TEXT,
    default_points INTEGER
);

CREATE TABLE datasheet_faction (
    datasheet_id TEXT, faction_id TEXT,
    PRIMARY KEY (datasheet_id, faction_id),
    FOREIGN KEY (datasheet_id) REFERENCES datasheet(id),
    FOREIGN KEY (faction_id) REFERENCES faction(id)
);

CREATE TABLE allied_faction (
    id TEXT PRIMARY KEY, ally_factions TEXT, host_factions TEXT,
    can_take_enhancements INTEGER, is_sibling_faction INTEGER,
    replaces_roster_keyword INTEGER, mutually_exclusive_keyword_limit INTEGER,
    datasheets TEXT, keyword_limits TEXT, points_limits TEXT,
    required_detachments TEXT
);

CREATE TABLE allied_faction_host (
    allied_faction_id TEXT, host_faction_id TEXT, host_faction TEXT,
    PRIMARY KEY (allied_faction_id, host_faction_id),
    FOREIGN KEY (allied_faction_id) REFERENCES allied_faction(id),
    FOREIGN KEY (host_faction_id) REFERENCES faction(id)
);

CREATE TABLE allied_faction_datasheet (
    allied_faction_id TEXT, datasheet_id TEXT, datasheet TEXT,
    PRIMARY KEY (allied_faction_id, datasheet_id),
    FOREIGN KEY (allied_faction_id) REFERENCES allied_faction(id),
    FOREIGN KEY (datasheet_id) REFERENCES datasheet(id)
);

CREATE TABLE model (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datasheet_id TEXT, name TEXT,
    statline_hidden INTEGER, m TEXT, t TEXT, sv TEXT, inv TEXT, w TEXT,
    ld TEXT, oc TEXT, keywords TEXT,
    FOREIGN KEY (datasheet_id) REFERENCES datasheet(id)
);

CREATE TABLE ability (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datasheet_id TEXT, name TEXT,
    type TEXT, is_aura INTEGER, is_psychic INTEGER, rules TEXT,
    restriction TEXT, sub_abilities TEXT,
    FOREIGN KEY (datasheet_id) REFERENCES datasheet(id)
);

CREATE TABLE extra_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datasheet_id TEXT, name TEXT, rules TEXT,
    FOREIGN KEY (datasheet_id) REFERENCES datasheet(id)
);

CREATE TABLE weapon (
    id INTEGER PRIMARY KEY AUTOINCREMENT, datasheet_id TEXT, name TEXT,
    wargear_type TEXT, rule_text TEXT,
    FOREIGN KEY (datasheet_id) REFERENCES datasheet(id)
);

CREATE TABLE weapon_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT, weapon_id INTEGER, name TEXT,
    type TEXT, range TEXT, attacks TEXT, bs TEXT, ws TEXT, strength TEXT,
    ap TEXT, damage TEXT, abilities TEXT,
    FOREIGN KEY (weapon_id) REFERENCES weapon(id)
);

CREATE TABLE detachment (
    id TEXT PRIMARY KEY, name TEXT, is_combat_patrol INTEGER,
    source_publication TEXT, detachment_points_cost INTEGER,
    restrictions TEXT, unlocks_datasheets TEXT, excludes_datasheets TEXT
);

CREATE TABLE detachment_faction (
    detachment_id TEXT, faction_id TEXT,
    PRIMARY KEY (detachment_id, faction_id),
    FOREIGN KEY (detachment_id) REFERENCES detachment(id),
    FOREIGN KEY (faction_id) REFERENCES faction(id)
);

CREATE TABLE detachment_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT, detachment_id TEXT, name TEXT,
    body_text TEXT, body_html TEXT, lore_text TEXT,
    FOREIGN KEY (detachment_id) REFERENCES detachment(id)
);

CREATE TABLE enhancement (
    id INTEGER PRIMARY KEY AUTOINCREMENT, detachment_id TEXT, name TEXT,
    points INTEGER, type TEXT, is_combat_patrol INTEGER,
    rules_text TEXT, rules_html TEXT, lore TEXT,
    eligibility_text TEXT, eligibility TEXT,
    FOREIGN KEY (detachment_id) REFERENCES detachment(id)
);

CREATE TABLE stratagem (
    id INTEGER PRIMARY KEY AUTOINCREMENT, detachment_id TEXT, name TEXT,
    cp_cost TEXT, category TEXT, used_when TEXT, phases TEXT,
    when_text TEXT, target_text TEXT, effect_text TEXT,
    restriction_text TEXT, secondary_effect_text TEXT, lore TEXT,
    FOREIGN KEY (detachment_id) REFERENCES detachment(id)
);

CREATE TABLE keyword (name TEXT PRIMARY KEY);
CREATE TABLE wargear_ability (name TEXT, rules TEXT, lore TEXT);
CREATE TABLE battle_size (
    name TEXT, points_limit INTEGER, detachment_points_limit INTEGER,
    enhancement_limit INTEGER, duplicate_unit_limit INTEGER
);
CREATE TABLE behaviour_type (
    name TEXT, type TEXT, rule_reference TEXT, eligible_if TEXT, effect TEXT
);
CREATE TABLE mission_primary (
    id TEXT, mission_pack_id TEXT, name TEXT, lore TEXT, description TEXT, objectives TEXT
);
CREATE TABLE mission_secondary (
    id TEXT, mission_pack_id TEXT, name TEXT, fixed INTEGER, scorable_first_turn INTEGER,
    lore TEXT, description TEXT
);
CREATE TABLE mission_pack (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE mission_deployment (id TEXT PRIMARY KEY, mission_pack_id TEXT, name TEXT);
CREATE TABLE mission_layout (id TEXT PRIMARY KEY, mission_pack_id TEXT, name TEXT);
CREATE TABLE mission_preset (
    id TEXT PRIMARY KEY, mission_pack_id TEXT, mission_layout_id TEXT,
    mission_deployment_id TEXT, name TEXT
);
CREATE TABLE mission_twist (
    id TEXT PRIMARY KEY, mission_pack_id TEXT, name TEXT, lore TEXT, rules TEXT
);
CREATE TABLE core_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT, section TEXT, container TEXT,
    subtitle TEXT, type TEXT, title TEXT, text TEXT
);

CREATE TABLE rule_section (
    id TEXT PRIMARY KEY, parent_id TEXT, mpath TEXT, depth INTEGER,
    display_order INTEGER, title TEXT, publication TEXT
);

CREATE TABLE rule_block (
    id INTEGER PRIMARY KEY AUTOINCREMENT, section_id TEXT, container_id TEXT,
    container_title TEXT, container_subtitle TEXT, container_order INTEGER,
    block_order INTEGER, type TEXT, title TEXT,
    content_html TEXT, content_text TEXT, image_url TEXT, alt_text TEXT,
    FOREIGN KEY (section_id) REFERENCES rule_section(id)
);

CREATE TABLE rule_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT, block_id INTEGER,
    mention TEXT, target_type TEXT, target_name TEXT,
    FOREIGN KEY (block_id) REFERENCES rule_block(id)
);

CREATE TABLE faq_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT, faq_id INTEGER,
    target_type TEXT, target_name TEXT,
    FOREIGN KEY (faq_id) REFERENCES faq(id)
);
CREATE TABLE faq (
    id INTEGER PRIMARY KEY AUTOINCREMENT, errata_header TEXT, errata_text TEXT,
    question TEXT, answer TEXT, applies_to TEXT
);
"""

INDEX_SQL = """
CREATE INDEX idx_ds_name ON datasheet(name);
CREATE INDEX idx_dsfac_faction ON datasheet_faction(faction_id);
CREATE INDEX idx_afhost_host ON allied_faction_host(host_faction_id);
CREATE INDEX idx_afds_ds ON allied_faction_datasheet(datasheet_id);
CREATE INDEX idx_model_ds ON model(datasheet_id);
CREATE INDEX idx_ability_ds ON ability(datasheet_id);
CREATE INDEX idx_weapon_ds ON weapon(datasheet_id);
CREATE INDEX idx_profile_weapon ON weapon_profile(weapon_id);
CREATE INDEX idx_det_name ON detachment(name);
CREATE INDEX idx_detfac_faction ON detachment_faction(faction_id);
CREATE INDEX idx_detrule_det ON detachment_rule(detachment_id);
CREATE INDEX idx_enh_det ON enhancement(detachment_id);
CREATE INDEX idx_strat_det ON stratagem(detachment_id);
CREATE INDEX idx_strat_cat ON stratagem(category);
CREATE INDEX idx_block_section ON rule_block(section_id);
CREATE INDEX idx_block_type ON rule_block(type);
CREATE INDEX idx_ref_block ON rule_reference(block_id);
CREATE INDEX idx_ref_target ON rule_reference(target_name);
CREATE INDEX idx_faqref_faq ON faq_reference(faq_id);
CREATE INDEX idx_section_parent ON rule_section(parent_id);
"""


def _b(x):
    return 1 if x else 0


def build_sqlite(data, idx, ref, db_path, log=print):
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA_SQL)
    cur = con.cursor()

    cur.executemany("INSERT INTO meta VALUES (?,?)", [
        ("data_version", str(idx["data_version"])),
        ("schema", "resolved-english"),
    ])

    # factions and their army rules
    for fid in idx["faction_by_id"]:
        meta = resolve_faction_meta(fid, idx)
        cur.execute(
            "INSERT INTO faction VALUES (?,?,?,?,?,?,?,?,?)",
            (fid, meta["name"], meta.get("common_name"), meta.get("display_name"),
             meta.get("parent_faction"), meta.get("parent_display_name"),
             _b(meta.get("excluded_from_army_builder")), meta.get("lore"),
             json.dumps(meta.get("allegiance_abilities", []), ensure_ascii=False)))
        for ar in meta["army_rules"]:
            cur.execute("INSERT INTO army_rule (faction_id,name,body_text,body_html) VALUES (?,?,?,?)",
                        (fid, ar["name"], ar["body_text"], ar["body_html"]))

    for p in data["publication"]:
        cur.execute("INSERT INTO publication VALUES (?,?,?,?,?,?,?)",
                    (p["id"], en(p), p.get("factionKeywordId"), _b(p.get("isCoreRules")),
                     _b(p.get("isLegends")), _b(p.get("isCombatPatrol")), p.get("errataDate")))

    # datasheets (each stored once, faction links via junction)
    for dsid in idx["datasheet_by_id"]:
        u = resolve_datasheet(dsid, idx)
        default_pts = None
        for c in u["points"]:
            if c.get("is_default"):
                default_pts = c.get("points")
                break
        if default_pts is None and u["points"]:
            default_pts = u["points"][0].get("points")
        cur.execute("INSERT INTO datasheet VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            u["id"], u["name"], u.get("source_publication"),
            _b(u["is_legends"]), _b(u["is_free_from_entitlements"]),
            u.get("base_size"), u.get("max_model_count"), u.get("lore"),
            u.get("unit_composition_text"),
            json.dumps(u["keywords"], ensure_ascii=False),
            json.dumps(u["conditional_keywords"], ensure_ascii=False),
            json.dumps(u["points"], ensure_ascii=False),
            json.dumps(u["points_steps"], ensure_ascii=False),
            json.dumps(u["wargear_loadout"], ensure_ascii=False),
            json.dumps(u["leads_units"], ensure_ascii=False),
            json.dumps(u["can_be_led_by"], ensure_ascii=False),
            json.dumps(u["damage_brackets"], ensure_ascii=False),
            default_pts))
        for fid in idx["ds_faction_ids"].get(dsid, []):
            cur.execute("INSERT OR IGNORE INTO datasheet_faction VALUES (?,?)", (dsid, fid))
        for m in u["models"]:
            cur.execute("INSERT INTO model (datasheet_id,name,statline_hidden,m,t,sv,inv,w,ld,oc,keywords)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (dsid, m["name"], _b(m["statline_hidden"]), m["M"], m["T"], m["Sv"],
                         m["Inv"], m["W"], m["Ld"], m["OC"],
                         json.dumps(m["keywords"], ensure_ascii=False)))
        for a in u["abilities"]:
            cur.execute("INSERT INTO ability (datasheet_id,name,type,is_aura,is_psychic,rules,restriction,sub_abilities)"
                        " VALUES (?,?,?,?,?,?,?,?)",
                        (dsid, a["name"], a["type"], _b(a["is_aura"]), _b(a["is_psychic"]),
                         a["rules"], a["restriction"],
                         json.dumps(a["sub_abilities"], ensure_ascii=False)))
        for r in u["extra_rules"]:
            cur.execute("INSERT INTO extra_rule (datasheet_id,name,rules) VALUES (?,?,?)",
                        (dsid, r["name"], r["rules"]))
        for w in u["weapons"]:
            cur.execute("INSERT INTO weapon (datasheet_id,name,wargear_type,rule_text) VALUES (?,?,?,?)",
                        (dsid, w["name"], w["wargear_type"], w["rule_text"]))
            wid = cur.lastrowid
            for p in w["profiles"]:
                cur.execute("INSERT INTO weapon_profile (weapon_id,name,type,range,attacks,bs,ws,strength,ap,damage,abilities)"
                            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (wid, p["name"], p["type"], p["range"], p["A"], p["BS"], p["WS"],
                             p["S"], p["AP"], p["D"],
                             json.dumps(p["abilities"], ensure_ascii=False)))

    # detachments (each stored once)
    for det in data["detachment"]:
        d = resolve_detachment(det, idx)
        cur.execute("INSERT INTO detachment VALUES (?,?,?,?,?,?,?,?)", (
            d["id"], d["name"], _b(d["is_combat_patrol"]), d.get("source_publication"),
            d.get("detachment_points_cost"),
            json.dumps(d["restrictions"], ensure_ascii=False),
            json.dumps(d["unlocks_datasheets"], ensure_ascii=False),
            json.dumps(d["excludes_datasheets"], ensure_ascii=False)))
        for fid in idx["det_faction_ids"].get(det["id"], []):
            cur.execute("INSERT OR IGNORE INTO detachment_faction VALUES (?,?)", (det["id"], fid))
        for r in d["rules"]:
            cur.execute("INSERT INTO detachment_rule (detachment_id,name,body_text,body_html,lore_text)"
                        " VALUES (?,?,?,?,?)",
                        (d["id"], r["name"], r["body_text"], r["body_html"], r["lore_text"]))
        for e in d["enhancements"]:
            cur.execute("INSERT INTO enhancement (detachment_id,name,points,type,is_combat_patrol,rules_text,rules_html,lore,eligibility_text,eligibility)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (d["id"], e["name"], e["points"], e["type"], _b(e["is_combat_patrol"]),
                         e["rules_text"], e["rules_html"], e["lore"], e["eligibility_text"],
                         json.dumps(e["eligibility"], ensure_ascii=False)))
        for s in d["stratagems"]:
            cur.execute("INSERT INTO stratagem (detachment_id,name,cp_cost,category,used_when,phases,when_text,target_text,effect_text,restriction_text,secondary_effect_text,lore)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (d["id"], s["name"], s["cp_cost"], s["category"], s["used_when"],
                         json.dumps(s["phases"], ensure_ascii=False),
                         s["when_text"], s["target_text"], s["effect_text"],
                         s["restriction_text"], s["secondary_effect_text"], s["lore"]))

    # Core (universal) stratagems carry no detachmentId in the source, so the
    # detachment loop above skipped them. Insert them last (resolved via en(), same
    # path as detachment stratagems) so the 1421 detachment rows keep ids 1-1421 and
    # the 11 core land at ids 1422-1432, with detachment_id = NULL.
    for s in data["stratagem"]:
        if s.get("detachmentId"):
            continue
        cs = resolve_stratagem(s, idx)
        cur.execute("INSERT INTO stratagem (detachment_id,name,cp_cost,category,used_when,phases,when_text,target_text,effect_text,restriction_text,secondary_effect_text,lore)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (None, cs["name"], cs["cp_cost"], cs["category"], cs["used_when"],
                     json.dumps(cs["phases"], ensure_ascii=False),
                     cs["when_text"], cs["target_text"], cs["effect_text"],
                     cs["restriction_text"], cs["secondary_effect_text"], cs["lore"]))

    # reference tables
    cur.executemany("INSERT OR IGNORE INTO keyword VALUES (?)", [(k["name"],) for k in ref["keywords"]])
    for a in ref.get("allied_factions", []):
        cur.execute("INSERT INTO allied_faction VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            a["id"],
            json.dumps([x for x in a["ally_factions"] if x], ensure_ascii=False),
            json.dumps([x for x in a["host_factions"] if x], ensure_ascii=False),
            _b(a["can_take_enhancements"]), _b(a["is_sibling_faction"]),
            _b(a["replaces_roster_keyword"]), _b(a["mutually_exclusive_keyword_limit"]),
            json.dumps([x for x in a["datasheets"] if x], ensure_ascii=False),
            json.dumps(a["keyword_limits"], ensure_ascii=False),
            json.dumps(a["points_limits"], ensure_ascii=False),
            json.dumps(a["required_detachments"], ensure_ascii=False)))
        for hid, hname in zip(a["host_faction_ids"], a["host_factions"]):
            cur.execute("INSERT OR IGNORE INTO allied_faction_host VALUES (?,?,?)",
                        (a["id"], hid, hname))
        for did, dname in zip(a["datasheet_ids"], a["datasheets"]):
            cur.execute("INSERT OR IGNORE INTO allied_faction_datasheet VALUES (?,?,?)",
                        (a["id"], did, dname))
    cur.executemany("INSERT INTO wargear_ability VALUES (?,?,?)",
                    [(a["name"], a["rules"], a["lore"]) for a in ref["wargear_abilities"]])
    cur.executemany("INSERT INTO battle_size VALUES (?,?,?,?,?)",
                    [(b["name"], b["points_limit"], b["detachment_points_limit"],
                      b["enhancement_limit"], b["duplicate_unit_limit"]) for b in ref["battle_sizes"]])
    cur.executemany("INSERT INTO behaviour_type VALUES (?,?,?,?,?)",
                    [(b["name"], b["type"], b["rule_reference"], b["eligible_if"], b["effect"])
                     for b in ref["behaviour_types"]])
    cur.executemany("INSERT INTO mission_primary VALUES (?,?,?,?,?,?)",
                    [(m["id"], m["pack"], m["name"], m["lore"], m["description"],
                      json.dumps(m["objectives"], ensure_ascii=False))
                     for m in ref["missions"]["primary_missions"]])
    cur.executemany("INSERT INTO mission_secondary VALUES (?,?,?,?,?,?,?)",
                    [(m["id"], m["pack"], m["name"], _b(m["fixed"]), _b(m["scorable_first_turn"]),
                      m["lore"], m["description"])
                     for m in ref["missions"]["secondary_missions"]])
    cur.executemany("INSERT INTO mission_pack VALUES (?,?)",
                    [(m["id"], m["name"]) for m in ref["missions"]["packs"]])
    cur.executemany("INSERT INTO mission_deployment VALUES (?,?,?)",
                    [(m["id"], m["pack"], m["name"]) for m in ref["missions"]["deployments"]])
    cur.executemany("INSERT INTO mission_layout VALUES (?,?,?)",
                    [(m["id"], m["pack"], m["name"]) for m in ref["missions"]["layouts"]])
    cur.executemany("INSERT INTO mission_preset VALUES (?,?,?,?,?)",
                    [(m["id"], m["pack"], m["layout_id"], m["deployment_id"], m["name"])
                     for m in ref["missions"]["presets"]])
    cur.executemany("INSERT INTO mission_twist VALUES (?,?,?,?,?)",
                    [(m["id"], m["pack"], m["name"], m["lore"], m["rules"])
                     for m in ref["missions"]["twists"]])
    for sec in ref["core_rules"]:
        for cont in sec["containers"]:
            for comp in cont["components"]:
                cur.execute("INSERT INTO core_rule (section,container,subtitle,type,title,text)"
                            " VALUES (?,?,?,?,?,?)",
                            (sec["section"], cont["title"], cont["subtitle"],
                             comp["type"], comp["title"], comp["text"]))
    faq_id_map = {}
    for f in ref["faqs"]:
        cur.execute("INSERT INTO faq (errata_header,errata_text,question,answer,applies_to) VALUES (?,?,?,?,?)",
                    (f["errata_header"], f["errata_text"], f["question"], f["answer"],
                     json.dumps(f["applies_to"], ensure_ascii=False)))
        faq_id_map[f["id"]] = cur.lastrowid

    build_rules_tables(data, idx, cur, faq_id_map, log)

    con.executescript(INDEX_SQL)

    # optional full text search over datasheets and rules, if FTS5 is available
    try:
        con.executescript("""
            CREATE VIRTUAL TABLE datasheet_fts USING fts5(
                datasheet_id UNINDEXED, name, keywords, abilities, weapons
            );
            CREATE VIRTUAL TABLE rules_fts USING fts5(
                block_id UNINDEXED, section, title, text
            );
        """)
        rows = []
        for dsid in idx["datasheet_by_id"]:
            ds = idx["datasheet_by_id"][dsid]
            ab = " ".join(en(idx["ability_by_id"].get(l["datasheetAbilityId"])) or ""
                          for l in idx["ds_ability_links"].get(dsid, []))
            kw = " ".join(en(idx["keyword_by_id"].get(k)) or ""
                          for m in idx["minis_by_ds"].get(dsid, [])
                          for k in idx["mini_keyword_ids"].get(m["id"], []))
            rows.append((dsid, en(ds) or "", kw, ab, ""))
        cur.executemany("INSERT INTO datasheet_fts VALUES (?,?,?,?,?)", rows)
        cur.execute("""INSERT INTO rules_fts (block_id, section, title, text)
                       SELECT b.id, s.title, b.title, b.content_text
                       FROM rule_block b JOIN rule_section s ON s.id = b.section_id""")
        log("  full text search tables created (FTS5): datasheet_fts, rules_fts")
    except sqlite3.OperationalError:
        log("  FTS5 not available in this SQLite build; skipping search tables")

    con.commit()
    con.execute("VACUUM")
    con.close()
    log("  database written: %s" % os.path.basename(db_path))


def build_rules_tables(data, idx, cur, faq_id_map, log):
    # name sets for resolving <k> cross references
    kw_names = {en(k).lower(): en(k) for k in data["keyword"] if en(k)}
    wa_names = {en(a).lower(): en(a) for a in data["wargear_ability"] if en(a)}
    ds_names = {(en(x) or "").lower(): en(x) for x in data["datasheet"] if en(x)}

    def resolve_mention(raw):
        clean = re.sub(r"<[^>]+>", "", raw).strip()
        key = clean.strip("[]").strip().lower()
        if key in kw_names:
            return clean, "keyword", kw_names[key]
        if key in wa_names:
            return clean, "wargear_ability", wa_names[key]
        if key in ds_names:
            return clean, "datasheet", ds_names[key]
        return clean, "unmatched", None

    # sections
    for s in data["rule_section"]:
        mpath = s.get("mpath") or ""
        depth = mpath.count(".")
        pub = idx["publication_by_id"].get(s.get("publicationId"))
        cur.execute("INSERT INTO rule_section VALUES (?,?,?,?,?,?,?)",
                    (s["id"], s.get("parentId"), mpath, depth, s.get("displayOrder"),
                     en(s), en(pub) if pub else None))

    # containers grouped by section, components grouped by container
    cont_by_section = defaultdict(list)
    for c in sorted(data["rule_container"], key=lambda c: c.get("displayOrder") or 0):
        cont_by_section[c.get("ruleSectionId")].append(c)
    comp_by_container = defaultdict(list)
    for comp in sorted(data["rule_container_component"], key=lambda c: c.get("displayOrder") or 0):
        if comp.get("ruleContainerId"):
            comp_by_container[comp["ruleContainerId"]].append(comp)

    block_count = ref_count = 0
    for s in data["rule_section"]:
        for ci, cont in enumerate(cont_by_section.get(s["id"], [])):
            for comp in comp_by_container.get(cont["id"], []):
                content_html = en(comp, "textContent")
                cur.execute(
                    "INSERT INTO rule_block (section_id,container_id,container_title,"
                    "container_subtitle,container_order,block_order,type,title,"
                    "content_html,content_text,image_url,alt_text) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (s["id"], cont["id"], en(cont, "title"), en(cont, "subtitle"),
                     ci, comp.get("displayOrder"), comp.get("type"), en(comp, "title"),
                     content_html, to_plain_text(content_html),
                     comp.get("imageUrl"), en(comp, "altText")))
                block_id = cur.lastrowid
                block_count += 1
                seen = set()
                for raw in re.findall(r"<k>(.*?)</k>", content_html or ""):
                    mention, ttype, tname = resolve_mention(raw)
                    if mention and mention.lower() not in seen:
                        seen.add(mention.lower())
                        cur.execute("INSERT INTO rule_reference (block_id,mention,target_type,target_name)"
                                    " VALUES (?,?,?,?)", (block_id, mention, ttype, tname))
                        ref_count += 1

    # faq cross references resolved to their targets
    fr = 0
    for c in data["faq_config"]:
        fid = faq_id_map.get(c.get("faqId"))
        if not fid:
            continue
        targets = []
        if c.get("datasheetId"):
            targets.append(("datasheet", en(idx["datasheet_by_id"].get(c["datasheetId"]))))
        if c.get("armyRuleId"):
            targets.append(("army_rule", en(idx["army_rule_by_id"].get(c["armyRuleId"]))))
        if c.get("detachmentId"):
            targets.append(("detachment", None))
        if c.get("enhancementId"):
            targets.append(("enhancement", None))
        if c.get("stratagemId"):
            targets.append(("stratagem", None))
        for ttype, tname in targets:
            cur.execute("INSERT INTO faq_reference (faq_id,target_type,target_name) VALUES (?,?,?)",
                        (fid, ttype, tname))
            fr += 1

    log("  rules: %d sections, %d blocks, %d cross references, %d FAQ links"
        % (len(data["rule_section"]), block_count, ref_count, fr))


# ===========================================================================
# Window mode
# ===========================================================================

def run_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox, scrolledtext
    except Exception:
        print("A graphical display is not available. Use command line mode:")
        print("    python w40k_exporter.py base.apk -o output_folder")
        return
    import threading

    root = tk.Tk()
    root.title("Warhammer 40,000 Data Exporter")
    root.geometry("780x560")
    apk_var = tk.StringVar()
    out_var = tk.StringVar(value=os.path.join(os.getcwd(), "w40k_export"))
    json_var = tk.BooleanVar(value=True)
    csv_var = tk.BooleanVar(value=True)
    sqlite_var = tk.BooleanVar(value=True)

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text="APK file:").grid(row=0, column=0, sticky="w")
    ttk.Entry(frm, textvariable=apk_var, width=68).grid(row=0, column=1, padx=6, sticky="we")

    def pick_apk():
        p = filedialog.askopenfilename(title="Choose the Warhammer 40,000 App APK",
                                       filetypes=[("APK files", "*.apk"), ("All files", "*.*")])
        if p:
            apk_var.set(p)
    ttk.Button(frm, text="Browse", command=pick_apk).grid(row=0, column=2)

    ttk.Label(frm, text="Output folder:").grid(row=1, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(frm, textvariable=out_var, width=68).grid(row=1, column=1, padx=6, sticky="we", pady=(8, 0))

    def pick_out():
        p = filedialog.askdirectory(title="Choose an output folder")
        if p:
            out_var.set(p)
    ttk.Button(frm, text="Browse", command=pick_out).grid(row=1, column=2, pady=(8, 0))

    opt = ttk.Frame(frm)
    opt.grid(row=2, column=1, sticky="w", pady=8)
    ttk.Checkbutton(opt, text="Write JSON", variable=json_var).pack(side="left", padx=(0, 12))
    ttk.Checkbutton(opt, text="Write CSV", variable=csv_var).pack(side="left", padx=(0, 12))
    ttk.Checkbutton(opt, text="Build SQLite", variable=sqlite_var).pack(side="left")

    logbox = scrolledtext.ScrolledText(frm, height=20, wrap="word")
    logbox.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
    frm.rowconfigure(4, weight=1)
    frm.columnconfigure(1, weight=1)

    def log(msg):
        logbox.insert("end", str(msg) + "\n")
        logbox.see("end")
        root.update_idletasks()

    run_btn = ttk.Button(frm, text="Export")

    def do_export():
        apk, out = apk_var.get().strip(), out_var.get().strip()
        if not apk:
            messagebox.showwarning("Missing APK", "Choose an APK file first.")
            return
        if not out:
            messagebox.showwarning("Missing folder", "Choose an output folder first.")
            return
        if not json_var.get() and not csv_var.get() and not sqlite_var.get():
            messagebox.showwarning("Nothing to write", "Enable JSON, CSV or SQLite.")
            return
        run_btn.configure(state="disabled")
        logbox.delete("1.0", "end")

        def worker():
            try:
                log("Reading APK: %s" % apk)
                export(apk, out, json_var.get(), csv_var.get(), sqlite_var.get(), log=log)
                messagebox.showinfo("Finished", "Export complete.\n\nFolder:\n%s" % out)
            except Exception as exc:
                log("ERROR: %s" % exc)
                messagebox.showerror("Export failed", str(exc))
            finally:
                run_btn.configure(state="normal")
        threading.Thread(target=worker, daemon=True).start()

    run_btn.configure(command=do_export)
    run_btn.grid(row=3, column=1, sticky="w")
    root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export all Warhammer 40,000 App faction and datasheet data to a foldered JSON and CSV tree.")
    parser.add_argument("apk", nargs="?", help="Path to the APK file (base.apk).")
    parser.add_argument("-o", "--output", default="w40k_export", help="Output folder.")
    parser.add_argument("--no-json", action="store_true", help="Skip JSON output.")
    parser.add_argument("--no-csv", action="store_true", help="Skip CSV output.")
    parser.add_argument("--sqlite", action="store_true", help="Also build a SQLite database (w40k.db).")
    parser.add_argument("--only-sqlite", action="store_true",
                        help="Build only the SQLite database, no JSON or CSV folders.")
    args = parser.parse_args(argv)
    if not args.apk:
        run_gui()
        return 0
    try:
        if args.only_sqlite:
            export(args.apk, args.output, write_json=False, csv_on=False, sqlite_on=True)
        else:
            export(args.apk, args.output, write_json=not args.no_json,
                   csv_on=not args.no_csv, sqlite_on=args.sqlite)
    except Exception as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
