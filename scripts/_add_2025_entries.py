"""Add missing 2025 plastic releases to model_catalogue_manual.json."""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANUAL_PATH = os.path.join(BASE, "data", "model_catalogue_manual.json")


def link(did, name, fid):
    return {"datasheet_id": did, "datasheet_name": name, "faction_id": fid}


def entry(eid, name, faction_label, faction_id, links=None, note=""):
    return {
        "id": eid,
        "name": name,
        "faction_label": faction_label,
        "faction_id": faction_id,
        "release_date": "2025-01",
        "release_year": 2025,
        "material": "Plastic",
        "status": "current_or_unknown",
        "note": note,
        "flags": [],
        "datasheet_links": links or [],
    }


NEW_ENTRIES = [
    entry("chaos-space-marines-2025-01-raptors", "Raptors", "Chaos Space Marines", "CSM",
          [link("000000958", "Raptors", "CSM")]),
    entry("chaos-space-marines-2025-01-warp-talons", "Warp Talons", "Chaos Space Marines", "CSM",
          [link("000000959", "Warp Talons", "CSM")]),
    entry("emperors-children-2025-01-noise-marines", "Noise Marines", "Emperor's Children", "EC",
          [link("000004088", "Noise Marines", "EC"), link("000004099", "Noise Marines", "CSM")]),
    entry("emperors-children-2025-01-lucius-the-eternal", "Lucius the Eternal", "Emperor's Children", "EC",
          [link("000004083", "Lucius the Eternal", "EC")], "New 2025 plastic sculpt"),
    entry("world-eaters-2025-01-slaughter-bound", "Slaughter Bound", "World Eaters", "WE"),
    entry("world-eaters-2025-01-goremongers", "Goremongers", "World Eaters", "WE",
          [link("000004076", "Goremongers", "WE")]),
    entry("genestealer-cult-2025-01-first-of-the-faithful", "First of the Faithful", "Genestealer Cult", "GC"),
    entry("leagues-of-votann-2025-01-buri-aegnirssen", "Buri Aegnirssen", "Leagues of Votann", "LoV",
          [link("000004140", "Buri Aegnirssen", "LoV")]),
    entry("leagues-of-votann-2025-01-arkanyst-evaluator", "Arkanyst Evaluator", "Leagues of Votann", "LoV",
          [link("000004142", "Arkanyst Evaluator", "LoV")]),
    entry("leagues-of-votann-2025-01-cthonian-earthshakers", "Cthonian Earthshakers", "Leagues of Votann", "LoV",
          [link("000004145", "Cthonian Earthshakers", "LoV")]),
    entry("leagues-of-votann-2025-01-ironkin-steeljacks", "Ironkin Steeljacks", "Leagues of Votann", "LoV",
          [link("000004143", "Ironkin Steeljacks with Heavy Volkanite Disintegrators", "LoV"),
           link("000004144", "Ironkin Steeljacks with Melee Weapons", "LoV")]),
    entry("leagues-of-votann-2025-01-kapricus-carrier", "Kapricus Carrier", "Leagues of Votann", "LoV",
          [link("000004147", "Kapricus Carrier", "LoV")]),
    entry("leagues-of-votann-2025-01-kapricus-defender", "Kapricus Defender", "Leagues of Votann", "LoV",
          [link("000004146", "Kapricus Defenders", "LoV")]),
    entry("leagues-of-votann-2025-01-memnyr-strategist", "Memnyr Strategist", "Leagues of Votann", "LoV",
          [link("000004141", "Memnyr Strategist", "LoV")]),
    entry("necrons-2025-01-geomancer", "Geomancer", "Necrons", "NEC",
          [link("000004178", "Geomancer", "NEC")]),
    entry("necrons-2025-01-macrocyte-warriors", "Macrocyte Warriors", "Necrons", "NEC",
          [link("000004176", "Canoptek Macrocytes", "NEC")]),
    entry("necrons-2025-01-tomb-crawlers", "Tomb Crawlers", "Necrons", "NEC",
          [link("000004177", "Canoptek Tomb Crawlers", "NEC")]),
    entry("necrons-2025-01-canoptek-accelerator", "Canoptek Accelerator", "Necrons", "NEC"),
    entry("necrons-2025-01-plasmacyte-reanimator", "Plasmacyte Reanimator", "Necrons", "NEC"),
    entry("adeptus-custodes-2025-01-shield-captain", "Shield Captain", "Adeptus Custodes", "AC"),
    entry("space-marines-2025-01-cato-sicarius", "Cato Sicarius", "Space Marines", "SM",
          [link("000004184", "Cato Sicarius", "SM")]),
    entry("space-marines-2025-01-ferren-areios", "Ferren Areios", "Space Marines", "SM",
          [link("000004204", "Ferren Areios", "SM")]),
    entry("space-marines-2025-01-marneus-calgar-terminator", "Marneus Calgar in Terminator Armour", "Space Marines", "SM",
          [link("000004183", "Marneus Calgar in Armour of Antilochus", "SM")]),
    entry("space-marines-2025-01-space-marine-captain", "Space Marine Captain", "Space Marines", "SM"),
    entry("space-marines-2025-01-victrix-honour-guard", "Victrix Honour Guard", "Space Marines", "SM",
          [link("000004185", "Victrix Honour Guard", "SM")]),
    entry("space-marines-2025-01-crusade-ancient", "Crusade Ancient", "Space Marines", "SM",
          [link("000004136", "Crusade Ancient", "SM")]),
    entry("space-marines-2025-01-execrator", "Execrator", "Space Marines", "SM",
          [link("000004135", "Execrator", "SM")]),
    entry("blood-angels-2025-01-astorath", "Astorath", "Blood Angels", "SM",
          [link("000000157", "Astorath", "SM")], "New 2025 plastic sculpt"),
    entry("blood-angels-2025-01-lemartes", "Lemartes", "Blood Angels", "SM",
          [link("000000164", "Lemartes", "SM")], "New 2025 plastic sculpt"),
    entry("blood-angels-2025-01-sanguinary-guard", "Sanguinary Guard", "Blood Angels", "SM",
          [link("000000165", "Sanguinary Guard", "SM")], "New 2025 plastic sculpt"),
    entry("blood-angels-2025-01-sanguinary-priest", "Sanguinary Priest", "Blood Angels", "SM",
          [link("000000158", "Sanguinary Priest", "SM")], "New 2025 plastic sculpt"),
    entry("blood-angels-2025-01-sanguinor", "The Sanguinor", "Blood Angels", "SM",
          [link("000000156", "The Sanguinor", "SM")], "New 2025 plastic sculpt"),
    entry("imperial-agents-2025-01-miraculist", "Miraculist", "Imperial Agents", "AoI"),
    entry("imperial-agents-2025-01-salvationist", "Salvationist", "Imperial Agents", "AoI"),
    entry("imperial-agents-2025-01-death-cult-assassin", "Death Cult Assassin", "Imperial Agents", "AoI"),
    entry("imperial-agents-2025-01-missionaries", "Missionaries", "Imperial Agents", "AoI"),
    entry("imperial-agents-2025-01-sanctifiers", "Sanctifiers", "Imperial Agents", "AoI",
          [link("000004074", "Sanctifiers", "AoI")]),
    entry("adeptus-mechanicus-2025-01-servitor-underseer", "Servitor Underseer", "Adeptus Mechanicus", "AdM"),
    entry("adeptus-mechanicus-2025-01-gun-servitors", "Gun Servitors", "Adeptus Mechanicus", "AdM"),
    entry("adeptus-mechanicus-2025-01-combat-servitors", "Combat Servitors", "Adeptus Mechanicus", "AdM"),
    entry("adepta-sororitas-2025-01-warrior-cremator", "Warrior / Cremator", "Adepta Sororitas", "AS"),
    entry("adepta-sororitas-2025-01-censor", "Censor", "Adepta Sororitas", "AS"),
    entry("adepta-sororitas-2025-01-adjuror", "Adjuror", "Adepta Sororitas", "AS"),
    entry("adepta-sororitas-2025-01-denuncia-mortisanctus", "Denuncia / Mortisanctus", "Adepta Sororitas", "AS"),
    entry("adepta-sororitas-2025-01-superior-reliquarius", "Superior / Reliquarius", "Adepta Sororitas", "AS"),
]


def main():
    with open(MANUAL_PATH, encoding="utf-8") as f:
        doc = json.load(f)

    existing_ids = {r["id"] for r in doc["model_releases"]}
    added = []
    skipped = []
    for e in NEW_ENTRIES:
        if e["id"] in existing_ids:
            skipped.append(e["id"])
        else:
            doc["model_releases"].append(e)
            added.append(e["id"])

    tmp = MANUAL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, MANUAL_PATH)

    print(f"Added {len(added)} entries:")
    for i in added:
        print(f"  + {i}")
    if skipped:
        print(f"Skipped {len(skipped)} already-present:")
        for i in skipped:
            print(f"  = {i}")


if __name__ == "__main__":
    main()
