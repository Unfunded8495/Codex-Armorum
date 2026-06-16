"""BSData XML catalogue importer.

Parses .gst and .cat files from bsdata/wh40k-10e/ and populates
catalogue_factions, catalogue_units, catalogue_weapons, and
catalogue_unit_weapons tables in the SQLite database.

Safe to re-run: clears and reimports all catalogue tables each time.
"""
import glob
import html
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


# ---------------------------------------------------------------------------
# Unit composition + wargear-options reconstruction
#
# BSData stores no datasheet prose: composition and wargear options are encoded
# structurally as nested selectionEntry trees with min/max constraints. These
# helpers re-derive the GW-style "Unit Composition" model lines and "Wargear
# Options" sentences from that structure. The reconstruction is heuristic and
# covers the common datasheet shapes (squad with a champion + rank-and-file,
# per-model loadout choices, single-model characters/vehicles); unusual
# structures fall back to emitting nothing rather than guessing.
# ---------------------------------------------------------------------------

WEAPON_TYPE_NAMES = {'Ranged Weapons', 'Melee Weapons'}
_COUNT_PREFIX = re.compile(r'^\d+(?:-\d+)?\s+')


def _lower1(s):
    return s[:1].lower() + s[1:] if s else s


def _sel_con(node, ctype):
    """Value of a direct-child selections constraint of `ctype`, or None."""
    cons = node.find('bs:constraints', NS_CAT)
    if cons is None:
        return None
    for c in cons.findall('bs:constraint', NS_CAT):
        if c.get('type') == ctype and c.get('field') == 'selections' \
                and c.get('scope') in ('parent', 'self'):
            try:
                return int(float(c.get('value')))
            except (TypeError, ValueError):
                pass
    return None


def _has_weapon_profile(entry):
    return any(p.get('typeName') in WEAPON_TYPE_NAMES
               for p in entry.findall('.//bs:profile', NS_CAT))


def _ul(items):
    return '<ul>' + ''.join(f'<li>{html.escape(i)}</li>' for i in items) + '</ul>'


def _option_members(group):
    """(node, default_id, name, weapon_id) for each option member of a group.

    Covers child selectionEntries plus entryLinks that point at a selectionEntry
    (sub-groups and shared 'Weapon Modifications' links are excluded). A group's
    `defaultSelectionEntryId` matches a selectionEntry's own id, but an
    entryLink's `id` (not its targetId) — so `default_id` is what to compare
    against the group default, while `weapon_id` (the targetId for links) is what
    to test for weapon membership.
    """
    out = []
    ses = group.find('bs:selectionEntries', NS_CAT)
    if ses is not None:
        for se in ses.findall('bs:selectionEntry', NS_CAT):
            out.append((se, se.get('id'), se.get('name', ''), se.get('id')))
    els = group.find('bs:entryLinks', NS_CAT)
    if els is not None:
        for el in els.findall('bs:entryLink', NS_CAT):
            if el.get('type') == 'selectionEntry':
                out.append((el, el.get('id'), el.get('name', ''), el.get('targetId')))
    return out


def _process_option_group(group, label):
    """Option lines for an option-bearing selectionEntryGroup on a model."""
    lines = []
    gmin, gmax = _sel_con(group, 'min'), _sel_con(group, 'max')
    default_id = group.get('defaultSelectionEntryId')
    members = _option_members(group)

    if gmin == 1 and gmax == 1 and default_id:
        # Pick-exactly-one: the default is the base weapon, others replace it.
        base = next((nm for (_, i, nm, _w) in members if i == default_id), None)
        if base is None:
            gname = group.get('name', '')
            base = gname[8:] if gname.lower().startswith('replace ') else gname
        base = _lower1(base)
        others = [nm for (_, i, nm, _w) in members if i != default_id]
        if len(others) == 1:
            lines.append(f"{label}'s {base} can be replaced with 1 {others[0]}.")
        elif others:
            lines.append(f"{label}'s {base} can be replaced with one of the "
                         f"following:{_ul(others)}")
    elif gmax == 1 and gmin in (None, 0) and len(members) > 1:
        lines.append(f"{label} can be equipped with one of the "
                     f"following:{_ul([nm for (_, _, nm, _w) in members])}")
    else:
        # Container / multi-pick group: each optional member is its own add-on.
        for (node, _i, nm, _w) in members:
            if _sel_con(node, 'max') and not _sel_con(node, 'min'):
                lines.append(f"{label} can be equipped with {_sel_con(node, 'max')} {nm}.")

    for sub in group.findall('bs:selectionEntryGroups/bs:selectionEntryGroup', NS_CAT):
        lines += _process_option_group(sub, label)
    return lines


def _process_model_options(model, label):
    """Options attached directly to one model/single-model entry."""
    lines = []
    ses = model.find('bs:selectionEntries', NS_CAT)
    if ses is not None:
        for se in ses.findall('bs:selectionEntry', NS_CAT):
            if _sel_con(se, 'max') and not _sel_con(se, 'min'):
                lines.append(f"{label} can be equipped with {_sel_con(se, 'max')} {se.get('name', '')}.")
    els = model.find('bs:entryLinks', NS_CAT)
    if els is not None:
        for el in els.findall('bs:entryLink', NS_CAT):
            if el.get('type') == 'selectionEntry' \
                    and _sel_con(el, 'max') and not _sel_con(el, 'min'):
                lines.append(f"{label} can be equipped with {_sel_con(el, 'max')} {el.get('name', '')}.")
    groups = model.find('bs:selectionEntryGroups', NS_CAT)
    if groups is not None:
        for g in groups.findall('bs:selectionEntryGroup', NS_CAT):
            lines += _process_option_group(g, label)
    return lines


def _model_item_names(model):
    """(weapon names, other-item names) for a model's child selectionEntries."""
    weapons, other = set(), set()
    ses = model.find('bs:selectionEntries', NS_CAT)
    if ses is not None:
        for se in ses.findall('bs:selectionEntry', NS_CAT):
            (weapons if _has_weapon_profile(se) else other).add(se.get('name', ''))
    return weapons, other


def _loadout_text(model_name):
    m = re.search(r'\((.+)\)', model_name)
    return m.group(1) if m else model_name


def _bulk_model_members(group):
    child = group.find('bs:selectionEntries', NS_CAT)
    return [m for m in (child.findall('bs:selectionEntry', NS_CAT) if child is not None else [])
            if m.get('type') == 'model']


def _process_bulk_group(group):
    """Options for a rank-and-file group whose members are model variants."""
    variants = _bulk_model_members(group)
    if not variants:
        return []
    plural = _COUNT_PREFIX.sub('', group.get('name', ''))

    high = [v for v in variants if (_sel_con(v, 'max') or 1) > 1]
    # Mode A — every variant interchangeable: a per-model loadout choice.
    if len(high) == len(variants) and len(variants) > 1:
        return [f"All {plural} can each be equipped with one of the "
                f"following:{_ul([_loadout_text(v.get('name', '')) for v in variants])}"]
    # Mode B — one base model (high max) plus low-max variant swaps/add-ons.
    if len(high) != 1:
        return []
    base = high[0]
    singular = base.get('name', '').split(' w/ ', 1)[0]
    base_weapons, base_other = _model_item_names(base)

    lines, addons = [], []
    for v in variants:
        if v is base:
            continue
        vmax = _sel_con(v, 'max') or 1
        vw, vo = _model_item_names(v)
        replaced = base_weapons - vw
        added_w = vw - base_weapons
        added_o = vo - base_other
        if len(replaced) == 1 and len(added_w) == 1:
            lines.append(f"{vmax} {singular}'s {_lower1(next(iter(replaced)))} "
                         f"can be replaced with 1 {next(iter(added_w))}.")
        elif added_w and not replaced:
            for w in sorted(added_w):
                lines.append(f"{vmax} {singular} can be equipped with 1 {w}.")
        addons += sorted(added_o)
    if addons:
        qual = ''
        if len(base_weapons) == 1:
            qual = f" equipped with a {_lower1(next(iter(base_weapons)))}"
        if len(addons) == 1:
            lines.append(f"1 {singular}{qual} can be equipped with 1 {addons[0]}.")
        else:
            lines.append(f"1 {singular}{qual} can be equipped with one of the "
                         f"following:{_ul(['1 ' + a for a in addons])}")
    return lines


# --- 'Unit Composition' combo-group pattern -------------------------------
# Some units (e.g. Astra Militarum infantry, several Ork mobs, Kill Teams)
# wrap their whole roster in a pick-one group whose members are *upgrade*
# combos like "1 Sergeant and 9 Troopers"; the models themselves are reached
# by entryLink into shared/library selectionEntries. These helpers resolve
# those references (via a global id->element index) so composition and loadout
# can still be reconstructed. They run only as a fallback, so units handled by
# the normal model/bulk logic are unaffected.

def _entry_has_model_ref(node, entry_index):
    ses = node.find('bs:selectionEntries', NS_CAT)
    if ses is not None and any(se.get('type') == 'model'
                               for se in ses.findall('bs:selectionEntry', NS_CAT)):
        return True
    els = node.find('bs:entryLinks', NS_CAT)
    if els is not None:
        for el in els.findall('bs:entryLink', NS_CAT):
            tgt = entry_index.get(el.get('targetId'))
            if tgt is None:
                continue
            if tgt.tag.endswith('selectionEntry') and tgt.get('type') == 'model':
                return True
            if tgt.tag.endswith('selectionEntryGroup') and _entry_has_model_ref(tgt, entry_index):
                return True
    segs = node.find('bs:selectionEntryGroups', NS_CAT)
    if segs is not None:
        for g in segs.findall('bs:selectionEntryGroup', NS_CAT):
            if _entry_has_model_ref(g, entry_index):
                return True
    return False


def _combo_groups(unit_se, entry_index):
    """Top-level groups whose members are upgrade combos that reference models."""
    out = []
    segs = unit_se.find('bs:selectionEntryGroups', NS_CAT)
    if segs is None or entry_index is None:
        return out
    for g in segs.findall('bs:selectionEntryGroup', NS_CAT):
        child = g.find('bs:selectionEntries', NS_CAT)
        mems = child.findall('bs:selectionEntry', NS_CAT) if child is not None else []
        if mems and all(m.get('type') != 'model' for m in mems) \
                and any(_entry_has_model_ref(m, entry_index) for m in mems):
            out.append(g)
    return out


def _default_combo(group):
    child = group.find('bs:selectionEntries', NS_CAT)
    mems = child.findall('bs:selectionEntry', NS_CAT) if child is not None else []
    if not mems:
        return None
    default_id = group.get('defaultSelectionEntryId')
    return next((m for m in mems if m.get('id') == default_id), mems[0])


def _group_base_model(group, entry_index):
    """The base (highest-count) model of a model group, plus its count."""
    cands = []
    ses = group.find('bs:selectionEntries', NS_CAT)
    if ses is not None:
        for se in ses.findall('bs:selectionEntry', NS_CAT):
            if se.get('type') == 'model':
                cands.append((_sel_con(se, 'max') or 1, se))
    els = group.find('bs:entryLinks', NS_CAT)
    if els is not None:
        for el in els.findall('bs:entryLink', NS_CAT):
            tgt = entry_index.get(el.get('targetId'))
            if tgt is not None and tgt.tag.endswith('selectionEntry') and tgt.get('type') == 'model':
                cands.append((_sel_con(el, 'max') or 1, tgt))
    if not cands:
        return None, 0
    base = max(cands, key=lambda c: c[0])
    return base[1], (_sel_con(group, 'max') or base[0])


def _combo_unit_models(combo, entry_index):
    """(champions, rankfile) model elements resolved from a composition combo."""
    champions, rankfile = [], None

    def consider(count, elem):
        nonlocal rankfile
        if elem is None:
            return
        if count <= 1:
            champions.append(elem)
        elif rankfile is None or count > rankfile[0]:
            rankfile = (count, elem)

    ses = combo.find('bs:selectionEntries', NS_CAT)
    if ses is not None:
        for se in ses.findall('bs:selectionEntry', NS_CAT):
            if se.get('type') == 'model':
                consider(_sel_con(se, 'max') or 1, se)
    els = combo.find('bs:entryLinks', NS_CAT)
    if els is not None:
        for el in els.findall('bs:entryLink', NS_CAT):
            tgt = entry_index.get(el.get('targetId'))
            if tgt is not None and tgt.tag.endswith('selectionEntry') and tgt.get('type') == 'model':
                consider(_sel_con(el, 'max') or _sel_con(el, 'min') or 1, tgt)
    segs = combo.find('bs:selectionEntryGroups', NS_CAT)
    if segs is not None:
        for g in segs.findall('bs:selectionEntryGroup', NS_CAT):
            base, cnt = _group_base_model(g, entry_index)
            consider(cnt, base)
    return champions, rankfile


def _combo_composition_lines(combo, entry_index):
    lines = []
    for ch in list(combo):
        tag = ch.tag.split('}')[-1]
        if tag == 'entryLinks':
            for el in ch.findall('bs:entryLink', NS_CAT):
                tgt = entry_index.get(el.get('targetId'))
                if tgt is None or not tgt.tag.endswith('selectionEntry') \
                        or tgt.get('type') != 'model':
                    continue
                cnt = _sel_con(el, 'min') or _sel_con(el, 'max') or 1
                lines.append(f"{cnt} {el.get('name', '')}")
        elif tag == 'selectionEntryGroups':
            for g in ch.findall('bs:selectionEntryGroup', NS_CAT):
                if not _entry_has_model_ref(g, entry_index):
                    continue
                nm = g.get('name', '')
                if re.match(r'^\d', nm):
                    lines.append(nm)
                else:
                    lo, hi = _sel_con(g, 'min') or 1, _sel_con(g, 'max') or 1
                    lines.append(f"{lo} {nm}" if lo == hi else f"{lo}-{hi} {nm}")
    return lines


def extract_composition(unit_se, entry_index=None):
    """Return ordered composition lines as [{'name': '<line>'}, ...]."""
    is_single = unit_se.get('type') == 'model'
    ses = unit_se.find('bs:selectionEntries', NS_CAT)
    segs = unit_se.find('bs:selectionEntryGroups', NS_CAT)

    items = []
    if ses is not None:
        for se in ses.findall('bs:selectionEntry', NS_CAT):
            if se.get('type') == 'model':
                items.append((int(se.get('sortIndex', '0')), 'model', se))
    if segs is not None:
        for g in segs.findall('bs:selectionEntryGroup', NS_CAT):
            if _bulk_model_members(g):
                items.append((int(g.get('sortIndex', '0')), 'bulk', g))
    items.sort(key=lambda t: t[0])

    lines = []
    for (_, kind, node) in items:
        name = node.get('name', '')
        if kind == 'model':
            lo, hi = _sel_con(node, 'min') or 1, _sel_con(node, 'max') or 1
            lines.append(f"{lo} {name}" if lo == hi else f"{lo}-{hi} {name}")
        elif re.match(r'^\d', name):
            lines.append(name)  # group name already embeds the count
        else:
            lo, hi = _sel_con(node, 'min') or 1, _sel_con(node, 'max') or 1
            lines.append(f"{lo} {name}" if lo == hi else f"{lo}-{hi} {name}")
    if not lines and not is_single:
        for cg in _combo_groups(unit_se, entry_index):
            combo = _default_combo(cg)
            if combo is not None:
                lines += _combo_composition_lines(combo, entry_index)
            if lines:
                break
    if not lines and is_single:
        lines.append(f"1 {unit_se.get('name', '')}")
    return [{'name': ln} for ln in lines]


def extract_wargear_options(unit_se):
    """Return reconstructed wargear-option lines as [{'description': '<line>'}, ...]."""
    is_single = unit_se.get('type') == 'model'
    ses = unit_se.find('bs:selectionEntries', NS_CAT)
    segs = unit_se.find('bs:selectionEntryGroups', NS_CAT)

    opts = []
    if ses is not None:
        for se in ses.findall('bs:selectionEntry', NS_CAT):
            if se.get('type') != 'model':
                continue
            mx = _sel_con(se, 'max') or 1
            label = f"The {se.get('name', '')}" if mx <= 1 else f"{mx} {se.get('name', '')}"
            opts += _process_model_options(se, label)
    if not is_single and segs is not None:
        for g in segs.findall('bs:selectionEntryGroup', NS_CAT):
            if _bulk_model_members(g):
                opts += _process_bulk_group(g)
            else:
                opts += _process_option_group(g, "This unit")
    if is_single:
        opts += _process_model_options(unit_se, "This model")
    return [{'description': o} for o in opts]


def _weapon_rank(entry):
    """0 for a ranged-weapon profile, 1 for melee/unknown — for loadout ordering."""
    for p in entry.findall('.//bs:profile', NS_CAT):
        if p.get('typeName') == 'Ranged Weapons':
            return 0
        if p.get('typeName') == 'Melee Weapons':
            return 1
    return 1


def _add_loadout_weapon(acc, seen, name, rank):
    key = name.strip().lower()
    if key and key not in seen:
        seen.add(key)
        acc.append((rank, name.strip()))


def _direct_weapon(entry):
    """True if a selectionEntry has its own (direct) weapon profile — i.e. it is a
    weapon leaf, not a loadout-combo container that merely nests weapons."""
    profs = entry.find('bs:profiles', NS_CAT)
    return profs is not None and any(
        p.get('typeName') in WEAPON_TYPE_NAMES for p in profs.findall('bs:profile', NS_CAT))


def _collect_loadout(node, weapon_ids, acc, seen):
    """Gather the weapons a model is *always* equipped with (its default loadout).

    Recurses into pure container groups and into mandatory members that are
    loadout-combo wrappers; for a mandatory pick-one group it follows the default
    member, so the alternatives in that group are not mistaken for base equipment.
    """
    ses = node.find('bs:selectionEntries', NS_CAT)
    if ses is not None:
        for se in ses.findall('bs:selectionEntry', NS_CAT):
            if (_sel_con(se, 'min') or 0) >= 1:  # mandatory
                if _direct_weapon(se):
                    _add_loadout_weapon(acc, seen, se.get('name', ''), _weapon_rank(se))
                else:
                    _collect_loadout(se, weapon_ids, acc, seen)  # combo wrapper
    els = node.find('bs:entryLinks', NS_CAT)
    if els is not None:
        for el in els.findall('bs:entryLink', NS_CAT):
            if el.get('type') != 'selectionEntry':
                continue
            mn, mx = _sel_con(el, 'min'), _sel_con(el, 'max')
            always = (mn is not None and mn >= 1) or (mn is None and mx is None)
            if always and el.get('targetId') in weapon_ids:
                _add_loadout_weapon(acc, seen, el.get('name', ''), 1)
    groups = node.find('bs:selectionEntryGroups', NS_CAT)
    if groups is not None:
        for g in groups.findall('bs:selectionEntryGroup', NS_CAT):
            gmin, gmax = _sel_con(g, 'min'), _sel_con(g, 'max')
            if gmin is None and gmax is None:
                _collect_loadout(g, weapon_ids, acc, seen)  # container group
            elif gmin and gmin >= 1:
                default_id = g.get('defaultSelectionEntryId')
                members = _option_members(g)
                chosen = next((m for m in members if m[1] == default_id), None)
                if chosen is None and members:
                    chosen = members[0]
                if chosen is None:
                    continue
                sub, _i, nm, wid = chosen
                if sub.tag.endswith('entryLink'):
                    if wid in weapon_ids:
                        _add_loadout_weapon(acc, seen, nm, 1)
                elif _direct_weapon(sub):
                    _add_loadout_weapon(acc, seen, nm, _weapon_rank(sub))
                else:
                    _collect_loadout(sub, weapon_ids, acc, seen)  # combo wrapper


def _model_loadout(model, weapon_ids):
    acc, seen = [], set()
    _collect_loadout(model, weapon_ids, acc, seen)
    acc.sort(key=lambda t: t[0])  # ranged weapons before melee/other; stable
    return [_lower1(n) for (_, n) in acc]


def _bulk_default_variant(group):
    variants = _bulk_model_members(group)
    if not variants:
        return None
    default_id = group.get('defaultSelectionEntryId')
    for v in variants:
        if v.get('id') == default_id:
            return v
    high = [v for v in variants if (_sel_con(v, 'max') or 1) > 1]
    return high[0] if len(high) == 1 else variants[0]


def extract_loadout(unit_se, weapon_ids, entry_index=None):
    """Reconstruct the 'Every model is equipped with: …' line(s) from BSData.

    Returns an HTML string (bold prefix) or '' when no default weapons are found.
    A named single model (max 1 — a sergeant/champion/character) gets its own
    'The <name>' line; the bulk of the unit collapses to a generic 'Every model'
    line. Uniform loadouts across all models become a single 'Every model' line.
    Bulk variant names (often loadout descriptions, not model nouns) are never
    used as labels, so no nonsensical line is produced.
    """
    is_single = unit_se.get('type') == 'model'
    ses = unit_se.find('bs:selectionEntries', NS_CAT)
    segs = unit_se.find('bs:selectionEntryGroups', NS_CAT)

    if is_single:
        lo = _model_loadout(unit_se, weapon_ids)
        return (f"<b>This model is equipped with:</b> " + "; ".join(lo) + "."
                if lo else '')

    champions = []          # [(label, loadout)] — named max-1 models
    rankfile = None         # (label, loadout) — representative bulk loadout
    rankfile_max = 0

    def consider(node, count, name):
        nonlocal rankfile, rankfile_max
        lo = _model_loadout(node, weapon_ids)
        if not lo:
            return
        if count <= 1:
            champions.append((f"The {name}", lo))
        elif count > rankfile_max:
            rankfile = ("Every model", lo)
            rankfile_max = count

    if ses is not None:
        for se in ses.findall('bs:selectionEntry', NS_CAT):
            if se.get('type') == 'model':
                consider(se, _sel_con(se, 'max') or 1, se.get('name', ''))
    if segs is not None:
        for g in segs.findall('bs:selectionEntryGroup', NS_CAT):
            base = _bulk_default_variant(g)
            if base is None:
                continue
            count = _sel_con(g, 'max') or _sel_con(base, 'max') or 1
            consider(base, count, base.get('name', ''))

    # Fallback: resolve a 'Unit Composition' combo group's model references.
    if not champions and rankfile is None:
        for cg in _combo_groups(unit_se, entry_index):
            combo = _default_combo(cg)
            if combo is None:
                continue
            champs, rf = _combo_unit_models(combo, entry_index)
            for elem in champs:
                consider(elem, 1, elem.get('name', ''))
            if rf is not None:
                consider(rf[1], rf[0], rf[1].get('name', ''))
            if champions or rankfile is not None:
                break

    contexts = champions + ([rankfile] if rankfile else [])
    if not contexts:
        return ''
    loadouts = [w for (_, w) in contexts]
    if all(w == loadouts[0] for w in loadouts):
        return f"<b>Every model is equipped with:</b> " + "; ".join(loadouts[0]) + "."
    return "<br>".join(
        f"<b>{lbl} is equipped with:</b> " + "; ".join(w) + "."
        for (lbl, w) in contexts)


def collect_weapon_ids(cat_files):
    """Global set of every selectionEntry id that defines a weapon, across all
    catalogues. Loadout reconstruction needs this because units frequently
    reference shared weapons via entryLinks whose target lives in another .cat
    (a library), so a per-file weapon set would miss them.

    A selectionEntry counts as a weapon if it has a direct weapon profile, or an
    infoLink to a weapon-type shared profile (many weapons carry no inline
    profile and instead reference a shared one).
    """
    bs = NS_CAT['bs']
    weapon_profile_ids = set()
    candidates = []  # (se_id, is_direct_weapon, [infoLink profile target ids])
    for cat_path in cat_files:
        try:
            root = ET.parse(cat_path).getroot()
        except ET.ParseError:
            continue
        for p in root.iter('{%s}profile' % bs):
            if p.get('typeName') in WEAPON_TYPE_NAMES:
                weapon_profile_ids.add(p.get('id'))
        for se in root.iter('{%s}selectionEntry' % bs):
            il = se.find('bs:infoLinks', NS_CAT)
            targets = [l.get('targetId') for l in il.findall('bs:infoLink', NS_CAT)
                       if l.get('type') == 'profile'] if il is not None else []
            candidates.append((se.get('id'), _direct_weapon(se), targets))

    ids = set()
    for (sid, direct, targets) in candidates:
        if direct or any(t in weapon_profile_ids for t in targets):
            ids.add(sid)
    return ids


def build_entry_index(cat_files):
    """Global id -> element map for every selectionEntry / selectionEntryGroup
    across all catalogues, so entryLinks that target shared/library entries
    (e.g. models inside a 'Unit Composition' combo) can be resolved."""
    bs = NS_CAT['bs']
    idx = {}
    for cat_path in cat_files:
        try:
            root = ET.parse(cat_path).getroot()
        except ET.ParseError:
            continue
        for tag in ('selectionEntry', 'selectionEntryGroup'):
            for e in root.iter('{%s}%s' % (bs, tag)):
                eid = e.get('id')
                if eid and eid not in idx:
                    idx[eid] = e
    return idx


def parse_cat(cat_path, gst_data, rule_index=None, global_weapon_ids=None,
              entry_index=None):
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

        # Composition, loadout + wargear options: reconstructed from the
        # selectionEntry structure (BSData carries no datasheet prose for these).
        composition = extract_composition(se, entry_index)
        wargear_options = extract_wargear_options(se)
        loadout = extract_loadout(
            se, global_weapon_ids if global_weapon_ids is not None else weapon_ids,
            entry_index)

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
            'wargear_options': wargear_options,
            'loadout':        loadout,
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

    # Ensure newer columns exist when the importer is run standalone (before
    # db.init_db has had a chance to migrate the schema).
    for stmt in (
        'ALTER TABLE catalogue_units ADD COLUMN wargear_options_json TEXT',
        'ALTER TABLE catalogue_units ADD COLUMN loadout TEXT',
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass

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
    print(f'Indexed {len(rule_index)} rules')

    print('Indexing weapon definitions across catalogues…')
    weapon_id_index = collect_weapon_ids(cat_files)
    print(f'Indexed {len(weapon_id_index)} weapons')

    print('Indexing catalogue entries for cross-references…')
    entry_index = build_entry_index(cat_files)
    print(f'Indexed {len(entry_index)} entries\n')

    total_units = 0
    total_weapons = 0

    for cat_path in cat_files:
        try:
            data = parse_cat(cat_path, gst_data, rule_index, weapon_id_index,
                             entry_index)
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
                    composition_json, wargear_options_json, loadout,
                    leader_targets_json, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (u['bsdata_id'], u['faction_id'], u['name'], u['role'],
                 u['points'],
                 json.dumps(u['stats']) if u.get('stats') is not None else None,
                 json.dumps(u['abilities']) if u.get('abilities') else None,
                 json.dumps(u['keywords']) if u.get('keywords') else None,
                 json.dumps(u['composition']) if u.get('composition') else None,
                 json.dumps(u['wargear_options']) if u.get('wargear_options') else None,
                 u.get('loadout') or None,
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
