# Warhammer 40,000 App Data Export

Generated from `base.apk`, game data version **886**.

## Contents at a glance

- Factions: **44**
- Datasheet records: **1257** (units are filed under each faction keyword they carry, so sub faction units appear in both the parent army folder and their own)
- Detachments: **457**, with 473 detachment rules, 1583 enhancements, 2285 stratagems
- Reference: 1239 keywords, 121 weapon abilities, 69 publications, 33 core rule sections, 49 primary and 18 secondary missions, 728 FAQ entries

Every dataset is written as both JSON (full nested fidelity) and CSV (flattened, one row per record). Text fields keep the source's light markup in the JSON `*_html` fields and a cleaned plain text version everywhere else. CSV files are UTF-8 with a BOM so they open cleanly in Excel.

## Folder layout

```
<output>/
  README.md                 this file
  manifest.json             machine readable summary and per faction file list
  factions/
    <Faction>/
      faction.json          faction meta: lore, army rules (with body text),
                            allegiance abilities, publications
      datasheets.json       full nested unit records
      datasheets.csv        one row per unit (summary)
      wargear_loadouts.csv  structured loadout enforcement, one row per choice
      detachments.json      full nested detachment records
      detachments.csv       one row per detachment
      detachment_rules.csv  one row per detachment rule (full text)
      enhancements.csv      one row per enhancement (with eligibility)
      stratagems.csv        one row per stratagem
  _reference/               cross faction data (shared by all armies)
      keywords.(json|csv)
      wargear_abilities.(json|csv)   weapon ability glossary (Rapid Fire, Lethal Hits, ...)
      publications.(json|csv)        source books
      battle_sizes.(json|csv)        points and detachment limits per game size
      behaviour_types.(json|csv)     movement behaviours
      core_rules.(json|csv)          the bundled core rulebook text
      missions.(json|csv)            primary and secondary missions, deployments, layouts
      faqs.(json|csv)                official FAQ and errata
```

## What each datasheet record contains

Full identity and stats: name, faction keywords, source publication, base size, Legends flag, entitlement flag, unit keywords, and any conditional keywords with the condition that grants them. Per model statline (M, T, Sv, Invulnerable, W, Ld, OC) with each model's own keywords. Points for every unit composition (for example 10 or 20 model options) plus any per model step pricing.

Rules content: abilities with full rules text and any sub abilities; extra datasheet rules (Transport, Deadly Demise and similar); damage brackets for vehicles and monsters.

Weapons: every weapon the unit can field, each with all of its profiles (range, attacks, BS or WS, S, AP, D) and the weapon abilities on each profile.

Leader attachment: `leads_units` lists the units a character can join, and `can_be_led_by` lists the characters that can join a unit.

Wargear loadout, captured as structured enforcement logic under `wargear_loadout`:

- `rules_text`: the human readable swap rules as shown on the datasheet.
- `options`: each selectable wargear option with its points cost, input type (stepper, checkbox, select) and default. `priced_options` is the subset that costs points.
- `choose_from`: "select N of the following" sets, with the limit, whether duplicates are allowed, and each choice as a bundle of items.
- `limited_choices`: "for every N models, up to X may take" sets, with the model count, choice limit and duplicate limit, plus whether the choice is mandatory.
- `all_model_choices`: choices applied across all models in the unit, including whether each is a substitution.

The `wargear_loadouts.csv` flattens all four of these mechanisms into one row per choice, with a `mechanism` column identifying which system it came from.

## What each detachment record contains

Detachment name, source publication, Combat Patrol flag, detachment points cost, restriction boxes (the keyword and army restriction text), and the lists of datasheets a detachment unlocks or excludes. Then its detachment rules (full reconstructed body text plus lore), its enhancements, and its stratagems.

Enhancements include name, points, type, rules text, lore, and structured `eligibility`: the required keyword groups (treated as alternatives, with the keywords inside a group all required) and the excluded keywords, plus a one line `eligibility_text` summary such as "Bearer must be: Infantry + Warboss; excluding: Mega Armour".

Stratagems include CP cost, category (battle tactic, strategic ploy, epic deed, wargear), when in the turn they can be used, the game phases, and the when, target, effect, restriction and secondary effect text.

## Optional SQLite database (w40k.db)

If built, `w40k.db` holds the same resolved data in a relational schema designed for querying from a Python app (sqlite3 is in the standard library, so no driver is needed). Unlike the JSON folders, each datasheet and detachment is stored once; faction membership is handled by the `datasheet_faction` and `detachment_faction` junction tables, so sub faction units are not duplicated.

Main tables: `faction`, `army_rule`, `publication`, `datasheet`, `datasheet_faction`, `allied_faction`, `allied_faction_host`, `allied_faction_datasheet`, `model`, `ability`, `extra_rule`, `weapon`, `weapon_profile`, `detachment`, `detachment_faction`, `detachment_rule`, `enhancement`, `stratagem`, plus reference tables `keyword`, `wargear_ability`, `battle_size`, `behaviour_type`, `mission_primary`, `mission_secondary`, `faq`. Deeply nested or list shaped fields (points compositions, the wargear loadout enforcement, enhancement eligibility, damage brackets, weapon ability lists, keyword lists) are stored as JSON text columns, so a top level value is queryable in SQL while the full structure is one `json.loads` away in Python.

Faction membership in `datasheet_faction` respects explicit exclusions: a unit that carries a faction keyword but is barred from that faction (source `faction_keyword_excluded_datasheet`, for example Sir Hekhtur under Imperial Knights) is not listed under it. All exclusion rows are also exported verbatim to `datasheet_faction_excluded` because most of them bar a *parent-faction generic* from a chapter (for example Librarians from Black Templars) - those never appear in `datasheet_faction`, so a consumer that resolves membership through the faction tree must subtract this table.

### Army-building enforcement tables

`leader_group` is one row per leader-attachment group with its conditions: `bodyguard_type` (`leader` fills the unit's Leader slot, `support` attaches alongside an existing Leader), required/excluded detachment, the "all units must share keyword X" gate, and both id- and keyword-based membership. The flat `leads_units` / `can_be_led_by` name lists on `datasheet` remain for display; `leader_group` (also embedded as the `leader_groups` JSON column) is the enforceable form.

`model` rows carry the Warlord flags (`cannot_be_warlord`, `can_be_non_character_warlord`, `is_supreme_commander` - a Supreme Commander must be the army's Warlord - and `excluded_from_enhancements`), plus split melee/ranged invulnerable saves where present.

`enhancement` rows carry `take_limit` (most are unique, some Upgrade-type ones allow 3 copies), `counts_toward_limit` (a few do not count against the battle-size enhancement cap), `epic_hero_eligible`, `non_character_eligible`, `cannot_be_warlord`, and `grants_leader_attachment` (units the bearer may lead because of the enhancement).

`detachment` rows add `linked_datasheets` (structured unlocks with the forced-Warlord flag and count), `unique_keywords`, and mandatory/granted Warlord miniatures. `detachment_faction_points_cost` holds the per-faction Detachment Points overrides.

Per-composition points tiers inside `datasheet.points` carry `required_detachments` / `required_faction_keywords` keys when a tier is only offered in a specific detachment or roster faction (for example 10-model Assault Intercessor tiers are Blood Angels only). `wargear_loadout` embeds each miniature's `default_loadout` with item counts, and each conditional keyword carries a structured `requires` object alongside the prose condition.

`keyword_limit_group` (+ `keyword_limit_group_detachment`) holds roster-wide keyword limits ("max 1 Death Jester", "min 3 War Dogs in this detachment"), and `keyword_ally_restriction` the ally-restricting Chaos mark keywords. `allied_faction` adds the Warlord conditions (`required_warlord_miniature`, `allowed_warlord_miniatures`) and its `keyword_limits` entries carry slotless-group and required-Warlord details.

The allied faction system is captured in three tables. `allied_faction` is one row per allowance (a host faction bringing a slice of another faction), with `ally_factions` and `host_factions` as JSON name lists, the boolean flags (`can_take_enhancements`, `is_sibling_faction`, `replaces_roster_keyword`, `mutually_exclusive_keyword_limit`), and JSON columns for `datasheets`, `keyword_limits`, `points_limits` and `required_detachments`. `allied_faction_host` and `allied_faction_datasheet` are junctions keyed on faction id and datasheet id, so an app can answer 'what can faction X ally, and which units does it bring' with a join rather than parsing JSON.

The `faction` table carries both canonical and display labels. `name` is the official faction keyword (for example `Adeptus Astartes`) and is the key that `parent_faction` points at, so neither should be overwritten. `display_name` is the label to show in a UI: it is `common_name` when the app provides one (so `Adeptus Astartes` displays as `Space Marines`) and falls back to `name` otherwise. `parent_display_name` is the same precomputed swap for the parent, so a chapter such as `Blood Angels` keeps its own name, links to its parent by `parent_faction = 'Adeptus Astartes'`, and can be shown nested under `Space Marines` without an extra lookup.

### Rules reader tables

The core rulebook is modelled for a reader app, not just dumped flat. `rule_section` is the navigation tree (each row carries `parent_id`, `mpath` and `depth`, ordered by `display_order`). `rule_block` is the ordered content of each section: one row per block with its `type` (text, header, accordion, image), the original markup in `content_html` (with the `<k>keyword</k>` tags kept for cross linking), a cleaned `content_text`, and `image_url` plus `alt_text` for image blocks. `rule_reference` resolves every `<k>` mention in a block to its target (`keyword`, `wargear_ability`, `datasheet`, or `unmatched`), so the app can render in text references as clickable links. `faq_reference` links FAQ entries to the datasheet, army rule, detachment, enhancement or stratagem they correct. (A flat `core_rule` table is also kept for simple cases.)

A `datasheet_fts` full text search table (FTS5) over unit name, keywords and abilities is created when the SQLite build supports it. Example:

```sql
-- every unit with a 4+ invulnerable save
SELECT DISTINCT d.name FROM datasheet d JOIN model m ON m.datasheet_id = d.id WHERE m.inv = '4+';
-- Orks units by points, most expensive first
SELECT d.name, d.default_points FROM datasheet d
  JOIN datasheet_faction df ON df.datasheet_id = d.id
  JOIN faction f ON f.id = df.faction_id
  WHERE f.name = 'Orks' ORDER BY d.default_points DESC;
```

## Notes

- Universal stratagems that belong to no detachment are not faction specific; they are not duplicated into every faction folder.
- A small number of records carry no faction keyword in the data (for example one Combat Patrol box variant). These are filed under an `Unaligned` faction folder rather than dropped.
- All data is read locally from your own copy of the APK. The artwork referenced by image URLs in the source is not downloaded.
