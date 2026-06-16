"""BSData XML catalogue importer.

Parses .gst and .cat files from bsdata/wh40k-10e/ and populates
catalogue_factions, catalogue_units, catalogue_weapons, and
catalogue_unit_weapons tables in the SQLite database.

Safe to re-run: clears and reimports all catalogue tables each time.
"""
import glob
import json
import os
import re
import sqlite3
from datetime import datetime
from xml.etree import ElementTree as ET

NS_GST = {'bs': 'http://www.battlescribe.net/schema/gameSystemSchema'}
NS_CAT = {'bs': 'http://www.battlescribe.net/schema/catalogueSchema'}

WEAPON_GROUP_NAMES = {
    'weapon', 'weapons', 'pistol', 'option', 'options',
    'crusade', 'modifications', 'relics', 'warlord',
    'upgrade', 'upgrades', 'equipment', 'wargear', 'gear',
}

LEADER_PATTERN = re.compile(
    r'attached to the following units[:\s]+((?:\s*[■▪•\-]\s*.+)+)',
    re.IGNORECASE
)
BULLET_PATTERN = re.compile(r'[■▪•\-]\s*(.+)')
INVULN_PATTERN = re.compile(r'(\d+)\+\s*invulnerable save', re.IGNORECASE)


def is_weapon_group(name: str) -> bool:
    lower = name.lower()
    return any(w in lower for w in WEAPON_GROUP_NAMES)


def parse_gst(gst_path):
    """Parse the .gst game system file.

    Returns a dict mapping profile type id -> name, e.g.:
        {'c547-1836-d8a-ff4f': 'Unit', 'f77d-b953-8fa4-b762': 'Ranged Weapons', ...}
    """
    tree = ET.parse(gst_path)
    root = tree.getroot()
    profile_types = {}
    for pt in root.findall('.//bs:profileType', NS_GST):
        profile_types[pt.get('id')] = pt.get('name')
    return profile_types


def _chars(profile, ns):
    """Return {characteristic_name: value} dict for a profile element."""
    return {
        c.get('name'): c.text
        for c in profile.findall('.//bs:characteristic', ns)
    }


def _profile_description(profile, ns):
    """Best rules-text for an ability-style profile.

    Standard 'Abilities' profiles carry a 'Description' characteristic, but
    bespoke ability types (e.g. 'Warmaster') name it 'Ability'. Prefer an
    explicit Description, then fall back to the first characteristic with text.
    """
    chars = profile.findall('.//bs:characteristic', ns)
    for ch in chars:
        if ch.get('name') == 'Description' and ch.text:
            return ch.text
    for ch in chars:
        if ch.text and ch.text.strip():
            return ch.text
    return ''


def build_rule_index(gst_files, cat_files):
    """Map every rule id -> {'name', 'description', 'source'} across the game.

    Rules defined in the .gst game system are universal **Core** abilities
    (Deep Strike, Leader, Feel No Pain, …); rules defined in a .cat (faction or
    library) are **Faction** abilities (Dark Pacts, Oath of Moment, …). This
    lets us classify the rule infoLinks that sit directly on a unit. Weapon
    keywords are also gst rules, but their infoLinks live deeper (under weapon
    entries), so the unit-level reader never sees them.
    """
    index = {}

    def harvest(root, ns, source):
        for rule in root.findall('.//bs:rule', ns):
            rid = rule.get('id')
            if not rid or rid in index:
                continue
            desc_el = rule.find('.//bs:description', ns)
            index[rid] = {
                'name':        rule.get('name', ''),
                'description': desc_el.text if desc_el is not None and desc_el.text else '',
                'source':      source,
            }

    for gst_path in gst_files:
        try:
            harvest(ET.parse(gst_path).getroot(), NS_GST, 'core')
        except ET.ParseError:
            continue
    for cat_path in cat_files:
        try:
            harvest(ET.parse(cat_path).getroot(), NS_CAT, 'faction')
        except ET.ParseError:
            continue
    return index


def parse_cat(cat_path, gst_data, rule_index=None):
    """Parse one .cat file.

    Returns:
        {
            'faction': {'bsdata_id', 'name', 'cat_file'},
            'units':   [unit_dict, ...],
            'weapons': [weapon_dict, ...],
            'unit_weapon_links': [(unit_bsdata_id, weapon_bsdata_id), ...],
        }
    """
    tree = ET.parse(cat_path)
    root = tree.getroot()

    faction = {
        'bsdata_id': root.get('id'),
        'name':      root.get('name'),
        'cat_file':  os.path.basename(cat_path),
    }

    # Collect profile type names that indicate weapon profiles (from gst)
    weapon_type_names = {'Ranged Weapons', 'Melee Weapons'}
    unit_type_name = 'Unit'
    ability_type_name = 'Abilities'

    # --- Pass 1: collect all weapon selectionEntries anywhere in the file ---
    # A weapon entry is any selectionEntry that has at least one weapon profile.
    weapons = []
    weapon_ids = set()

    for se in root.findall('.//bs:selectionEntry', NS_CAT):
        ranged_profiles = [
            p for p in se.findall('.//bs:profile', NS_CAT)
            if p.get('typeName') == 'Ranged Weapons'
        ]
        melee_profiles = [
            p for p in se.findall('.//bs:profile', NS_CAT)
            if p.get('typeName') == 'Melee Weapons'
        ]

        if not ranged_profiles and not melee_profiles:
            continue

        se_id = se.get('id')
        se_name = se.get('name', '')

        if ranged_profiles and melee_profiles:
            # Both: create two records
            for p in ranged_profiles:
                c = _chars(p, NS_CAT)
                w = {
                    'bsdata_id':   se_id + '-ranged',
                    'faction_id':  faction['bsdata_id'],
                    'name':        se_name + ' (Ranged)',
                    'weapon_type': 'ranged',
                    'range':       c.get('Range'),
                    'attacks':     c.get('A'),
                    'skill':       c.get('BS'),
                    'strength':    c.get('S'),
                    'ap':          c.get('AP'),
                    'damage':      c.get('D'),
                    'keywords':    c.get('Keywords'),
                }
                if w['bsdata_id'] not in weapon_ids:
                    weapons.append(w)
                    weapon_ids.add(w['bsdata_id'])
            for p in melee_profiles:
                c = _chars(p, NS_CAT)
                w = {
                    'bsdata_id':   se_id + '-melee',
                    'faction_id':  faction['bsdata_id'],
                    'name':        se_name + ' (Melee)',
                    'weapon_type': 'melee',
                    'range':       'Melee',
                    'attacks':     c.get('A'),
                    'skill':       c.get('WS'),
                    'strength':    c.get('S'),
                    'ap':          c.get('AP'),
                    'damage':      c.get('D'),
                    'keywords':    c.get('Keywords'),
                }
                if w['bsdata_id'] not in weapon_ids:
                    weapons.append(w)
                    weapon_ids.add(w['bsdata_id'])
            # Also register the base id as pointing to both (for link resolution)
            weapon_ids.add(se_id)
        elif ranged_profiles:
            p = ranged_profiles[0]
            c = _chars(p, NS_CAT)
            w = {
                'bsdata_id':   se_id,
                'faction_id':  faction['bsdata_id'],
                'name':        se_name,
                'weapon_type': 'ranged',
                'range':       c.get('Range'),
                'attacks':     c.get('A'),
                'skill':       c.get('BS'),
                'strength':    c.get('S'),
                'ap':          c.get('AP'),
                'damage':      c.get('D'),
                'keywords':    c.get('Keywords'),
            }
            if se_id not in weapon_ids:
                weapons.append(w)
                weapon_ids.add(se_id)
        else:
            p = melee_profiles[0]
            c = _chars(p, NS_CAT)
            w = {
                'bsdata_id':   se_id,
                'faction_id':  faction['bsdata_id'],
                'name':        se_name,
                'weapon_type': 'melee',
                'range':       'Melee',
                'attacks':     c.get('A'),
                'skill':       c.get('WS'),
                'strength':    c.get('S'),
                'ap':          c.get('AP'),
                'damage':      c.get('D'),
                'keywords':    c.get('Keywords'),
            }
            if se_id not in weapon_ids:
                weapons.append(w)
                weapon_ids.add(se_id)

    # --- Pass 2: collect unit selectionEntries and their weapon links ---
    units = []
    unit_weapon_links = []
    seen_unit_ids = set()

    # Look in sharedSelectionEntries first, then fall back to top-level selectionEntries
    shared = root.find('bs:sharedSelectionEntries', NS_CAT)
    candidates = shared.findall('bs:selectionEntry', NS_CAT) if shared is not None else []
    # Also include direct selectionEntries on root (some cats put units there)
    for se in root.findall('bs:selectionEntries/bs:selectionEntry', NS_CAT):
        if se not in candidates:
            candidates.append(se)

    for se in candidates:
        if se.get('type') not in ('unit', 'model'):
            continue

        se_id = se.get('id')
        if se_id in seen_unit_ids:
            continue
        seen_unit_ids.add(se_id)

        # Role: primary categoryLink
        role = None
        keywords = []
        for cl in se.findall('bs:categoryLinks/bs:categoryLink', NS_CAT):
            kw_name = cl.get('name', '')
            keywords.append(kw_name)
            if cl.get('primary') == 'true':
                role = kw_name

        # Points
        cost = se.find('bs:costs/bs:cost[@name="pts"]', NS_CAT)
        points = None
        if cost is not None:
            try:
                points = int(float(cost.get('value', '0')))
            except (ValueError, TypeError):
                pass

        # Stats: Unit profiles
        stat_profiles = [
            p for p in se.findall('.//bs:profile', NS_CAT)
            if p.get('typeName') == unit_type_name
        ]
        stats = None
        if len(stat_profiles) == 1:
            stats = _chars(stat_profiles[0], NS_CAT)
        elif len(stat_profiles) > 1:
            stats = []
            for p in stat_profiles:
                block = _chars(p, NS_CAT)
                block['profile_name'] = p.get('name', '')
                stats.append(block)

        # --- Abilities ---------------------------------------------------
        # Datasheet abilities (named, with rules text) come from inline
        # 'Abilities' profiles. Other profile types are bespoke ability blocks
        # (e.g. 'Warmaster' for Abaddon) and are kept grouped by their type.
        datasheet_abilities = []
        special_abilities = []
        invuln_save = None
        for p in se.findall('.//bs:profile', NS_CAT):
            type_name = p.get('typeName', '')
            if type_name == unit_type_name or type_name in weapon_type_names:
                continue
            desc = _profile_description(p, NS_CAT)
            name = p.get('name', '')
            if type_name == ability_type_name:
                if invuln_save is None and name.lower().startswith('invulnerable'):
                    m = INVULN_PATTERN.search(desc)
                    if m:
                        invuln_save = m.group(1)
                datasheet_abilities.append({'name': name, 'description': desc})
            else:
                special_abilities.append(
                    {'group': type_name, 'name': name, 'description': desc})

        # Core / Faction abilities are referenced by rule infoLinks sitting
        # directly on the unit (Deep Strike/Leader = Core, Dark Pacts =
        # Faction). Weapon-keyword infoLinks live deeper, under weapon entries,
        # so reading only the unit's own infoLinks keeps them out.
        core_abilities = []
        faction_abilities = []
        info_links = se.find('bs:infoLinks', NS_CAT)
        if info_links is not None:
            for il in info_links.findall('bs:infoLink', NS_CAT):
                if il.get('type') != 'rule':
                    continue
                rule = (rule_index or {}).get(il.get('targetId'), {})
                nm = il.get('name') or rule.get('name', '')
                if not nm:
                    continue
                entry = {'name': nm, 'description': rule.get('description', '')}
                if rule.get('source') == 'faction':
                    faction_abilities.append(entry)
                else:
                    core_abilities.append(entry)

        abilities = {
            'core':        core_abilities,
            'faction':     faction_abilities,
            'datasheet':   datasheet_abilities,
            'special':     special_abilities,
            'invuln_save': invuln_save,
        }
        has_abilities = any((core_abilities, faction_abilities,
                             datasheet_abilities, special_abilities, invuln_save))

        # Composition: model-count groups on this selectionEntry
        composition = []
        for seg in se.findall('bs:selectionEntryGroups/bs:selectionEntryGroup', NS_CAT):
            group_name = seg.get('name', '')
            if is_weapon_group(group_name):
                continue
            min_c = seg.find('bs:constraints/bs:constraint[@type="min"]', NS_CAT)
            max_c = seg.find('bs:constraints/bs:constraint[@type="max"]', NS_CAT)
            if min_c is None or max_c is None:
                continue
            try:
                min_val = int(float(min_c.get('value', 0)))
                max_val = int(float(max_c.get('value', 0)))
            except ValueError:
                continue
            if max_val < 1:
                continue
            composition.append({'name': group_name, 'min': min_val, 'max': max_val})

        # Leader targets: scan abilities for attachment text
        leader_targets = []
        for ability in datasheet_abilities:
            desc = ability.get('description', '') or ''
            m = LEADER_PATTERN.search(desc)
            if m:
                for line in m.group(1).splitlines():
                    bm = BULLET_PATTERN.match(line.strip())
                    if bm:
                        leader_targets.append(bm.group(1).strip())

        unit = {
            'bsdata_id':      se_id,
            'faction_id':     faction['bsdata_id'],
            'name':           se.get('name', ''),
            'role':           role,
            'points':         points,
            'stats':          stats,
            'abilities':      abilities if has_abilities else None,
            'keywords':       keywords if keywords else None,
            'composition':    composition,
            'leader_targets': leader_targets,
        }
        units.append(unit)

        # Weapon links: entryLinks whose targetId is a known weapon id
        seen_links = set()
        for el in se.findall('.//bs:entryLink', NS_CAT):
            target_id = el.get('targetId')
            if target_id in weapon_ids:
                # Resolve to actual weapon bsdata_id (may be base id for split weapons)
                # For split weapons (both ranged+melee) we link to both sub-ids
                base_ranged = target_id + '-ranged'
                base_melee = target_id + '-melee'
                if base_ranged in weapon_ids and base_melee in weapon_ids:
                    for wid in (base_ranged, base_melee):
                        key = (se_id, wid)
                        if key not in seen_links:
                            unit_weapon_links.append(key)
                            seen_links.add(key)
                else:
                    key = (se_id, target_id)
                    if key not in seen_links:
                        unit_weapon_links.append(key)
                        seen_links.add(key)

        # Collect inline weapon profiles directly on this unit/model entry.
        # BSData frequently defines weapons as profiles rather than linked entries,
        # particularly for characters and library-catalogue units.
        # Deduplicate within this unit by (name, weapon_type) to avoid duplicate
        # display rows when BSData defines the same weapon for multiple model variants.
        seen_inline = set()
        for profile in se.findall('.//bs:profile', NS_CAT):
            type_name = profile.get('typeName', '')
            if type_name not in ('Ranged Weapons', 'Melee Weapons'):
                continue

            profile_id = profile.get('id')
            if not profile_id:
                continue

            weapon_name = profile.get('name', '').strip()
            if not weapon_name:
                continue

            weapon_type = 'ranged' if type_name == 'Ranged Weapons' else 'melee'
            dedup_key = (weapon_name.lower(), weapon_type)
            if dedup_key in seen_inline:
                continue
            seen_inline.add(dedup_key)

            chars = {
                ch.get('name', ''): ch.text
                for ch in profile.findall('.//bs:characteristic', NS_CAT)
            }

            weapon = {
                'bsdata_id':   profile_id,
                'faction_id':  faction['bsdata_id'],
                'name':        weapon_name,
                'weapon_type': weapon_type,
                'range':       chars.get('Range'),
                'attacks':     chars.get('A'),
                'skill':       chars.get('BS') if weapon_type == 'ranged' else chars.get('WS'),
                'strength':    chars.get('S'),
                'ap':          chars.get('AP'),
                'damage':      chars.get('D'),
                'keywords':    chars.get('Keywords'),
            }
            if profile_id not in weapon_ids:
                weapons.append(weapon)
                weapon_ids.add(profile_id)

            key = (se_id, profile_id)
            if key not in seen_links:
                unit_weapon_links.append(key)
                seen_links.add(key)

    return {
        'faction':           faction,
        'units':             units,
        'weapons':           weapons,
        'unit_weapon_links': unit_weapon_links,
    }


def import_catalogue(db_path, bsdata_dir):
    """Orchestrate the full import. Clears catalogue tables and reimports."""
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = OFF')

    conn.execute('DELETE FROM catalogue_unit_weapons')
    conn.execute('DELETE FROM catalogue_weapons')
    conn.execute('DELETE FROM catalogue_units')
    conn.execute('DELETE FROM catalogue_factions')
    conn.commit()

    now = datetime.utcnow().isoformat()

    gst_files = glob.glob(os.path.join(bsdata_dir, '*.gst'))
    if not gst_files:
        raise FileNotFoundError('No .gst file found in ' + bsdata_dir)
    print(f'Parsing game system: {os.path.basename(gst_files[0])}')
    gst_data = parse_gst(gst_files[0])

    cat_files = sorted(glob.glob(os.path.join(bsdata_dir, '*.cat')))
    print(f'Found {len(cat_files)} .cat files\n')

    print('Indexing Core/Faction ability rules…')
    rule_index = build_rule_index(gst_files, cat_files)
    print(f'Indexed {len(rule_index)} rules\n')

    total_units = 0
    total_weapons = 0

    for cat_path in cat_files:
        try:
            data = parse_cat(cat_path, gst_data, rule_index)
        except Exception as e:
            print(f'  WARNING: failed to parse {os.path.basename(cat_path)}: {e}')
            continue

        conn.execute(
            'INSERT OR REPLACE INTO catalogue_factions (bsdata_id, name, cat_file, imported_at) VALUES (?, ?, ?, ?)',
            (data['faction']['bsdata_id'], data['faction']['name'],
             data['faction']['cat_file'], now)
        )

        for u in data['units']:
            conn.execute(
                '''INSERT OR REPLACE INTO catalogue_units
                   (bsdata_id, faction_id, name, role, points,
                    stats_json, abilities_json, keywords_json,
                    composition_json, leader_targets_json, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (u['bsdata_id'], u['faction_id'], u['name'], u['role'],
                 u['points'],
                 json.dumps(u['stats']) if u.get('stats') is not None else None,
                 json.dumps(u['abilities']) if u.get('abilities') else None,
                 json.dumps(u['keywords']) if u.get('keywords') else None,
                 json.dumps(u['composition']) if u.get('composition') else None,
                 json.dumps(u['leader_targets']) if u.get('leader_targets') else None,
                 now)
            )

        for w in data['weapons']:
            conn.execute(
                '''INSERT OR REPLACE INTO catalogue_weapons
                   (bsdata_id, faction_id, name, weapon_type, range, attacks,
                    skill, strength, ap, damage, keywords, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (w['bsdata_id'], w['faction_id'], w['name'], w['weapon_type'],
                 w.get('range'), w.get('attacks'), w.get('skill'),
                 w.get('strength'), w.get('ap'), w.get('damage'),
                 w.get('keywords'), now)
            )

        for unit_id, weapon_id in data['unit_weapon_links']:
            try:
                conn.execute(
                    'INSERT OR IGNORE INTO catalogue_unit_weapons (unit_id, weapon_id) VALUES (?, ?)',
                    (unit_id, weapon_id)
                )
            except sqlite3.IntegrityError:
                pass

        total_units += len(data['units'])
        total_weapons += len(data['weapons'])
        print(f'  {os.path.basename(cat_path)}: {len(data["units"])} units, {len(data["weapons"])} weapons')

    conn.commit()
    conn.execute('PRAGMA foreign_keys = ON')
    conn.close()

    print(f'\nImport complete: {len(cat_files)} cat files, {total_units} units, {total_weapons} weapons')


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.environ.get('DB_PATH', os.path.join(script_dir, 'collection.db'))
    bsdata_dir = os.environ.get('BSDATA_DIR', os.path.join(script_dir, 'bsdata', 'wh40k-10e'))

    if not os.path.isdir(bsdata_dir):
        import sys
        print(f'ERROR: BSData directory not found: {bsdata_dir}')
        print('Clone it with: git clone --depth=1 https://github.com/BSData/wh40k-10e.git bsdata/wh40k-10e')
        sys.exit(1)

    print(f'Importing from: {bsdata_dir}')
    print(f'Database:       {db_path}\n')
    import_catalogue(db_path, bsdata_dir)


if __name__ == '__main__':
    main()
