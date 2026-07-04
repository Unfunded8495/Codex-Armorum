"""Plain sqlite3 data-access and sync helpers for the Arsenal feature."""
from html import unescape
import os
import re
import time

from data_store import get_store, strip_html
from db import db


CATEGORIES = ("ranged", "melee")
PROFILE_RE = re.compile(r"\s+[\u2013\u2014-]\s+\S.*$")
MANUAL_REFERENCE_STATUSES = {"verified", "base_fallback", "skip", "no_match", "needs_check"}


def rowdict(row):
    return dict(row) if row else None


def rowsdict(rows):
    return [dict(row) for row in rows]


def now_ts():
    return int(time.time())


def display_name(raw):
    name = strip_html(unescape(str(raw or "").strip()))
    name = PROFILE_RE.sub("", name)
    return re.sub(r"\s+", " ", name).strip()


def name_key(name):
    return display_name(name).lower()


def _table_exists(c, table):
    return c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _columns(c, table):
    if not _table_exists(c, table):
        return []
    return [row["name"] for row in c.execute(f"PRAGMA table_info({table})").fetchall()]


SOURCE_BLOCK_RE = re.compile(r"\n*\s*Source:\s*(?P<source>.+?)\s*$", re.I | re.S)
SOURCE_URL_RE = re.compile(r"https?://[^\s|)]+")


def _source_attrs(source):
    text = (source or "").strip()
    match = SOURCE_URL_RE.search(text)
    return {
        "source": text,
        "source_url": match.group(0) if match else "",
        "source_label": re.sub(r"\s*\|\s*https?://\S+\s*$", "", text).strip(),
    }


def wiki_search_url(name):
    from urllib.parse import quote_plus

    query_name = display_name(name) or str(name or "").strip()
    query = f"{query_name} warhammer 40k wiki".strip()
    return "https://www.google.com/search?q=" + quote_plus(query)


def manual_wiki_control(weapon):
    status = (weapon.get("wiki_status") or "").strip()
    url = (weapon.get("wiki_url") or "").strip()
    if status in {"verified", "base_fallback"} and url:
        return {
            "mode": "open",
            "label": "Open wiki page",
            "href": url,
            "muted_label": "",
            "note": "points at the base weapon's page" if status == "base_fallback" else "",
        }
    if status == "skip":
        return {
            "mode": "muted",
            "label": "",
            "href": "",
            "muted_label": "no model weapon (skip)",
            "note": "",
        }
    if status == "no_match":
        return {
            "mode": "search",
            "label": "Search wiki",
            "href": wiki_search_url(weapon.get("name", "")),
            "muted_label": "no wiki article",
            "note": "",
        }
    return {
        "mode": "search",
        "label": "Search wiki",
        "href": wiki_search_url(weapon.get("name", "")),
        "muted_label": "",
        "note": "",
    }


def _add_manual_wiki_attrs(weapon):
    if not weapon:
        return weapon
    weapon["wiki_status"] = (weapon.get("wiki_status") or "").strip()
    weapon["wiki_url"] = (weapon.get("wiki_url") or "").strip()
    weapon["wiki_control"] = manual_wiki_control(weapon)
    return weapon


def _migrate_weapon_source_blocks(c):
    rows = c.execute("""SELECT id, spotting_notes, source
                        FROM arsenal_weapon
                        WHERE spotting_notes LIKE '%Source:%'""").fetchall()
    for row in rows:
        notes = row["spotting_notes"] or ""
        match = SOURCE_BLOCK_RE.search(notes)
        if not match:
            continue
        source = (row["source"] or "").strip()
        moved_source = match.group("source").strip()
        clean_notes = notes[:match.start()].rstrip()
        if not source:
            source = moved_source
        elif moved_source and moved_source not in source:
            source = f"{source} | {moved_source}"
        c.execute(
            "UPDATE arsenal_weapon SET spotting_notes=?, source=? WHERE id=?",
            (clean_notes, source, row["id"]),
        )


def ensure_manual_wiki_schema(c):
    columns = _columns(c, "arsenal_weapon")
    if not columns:
        return
    if "wiki_url" not in columns:
        c.execute("ALTER TABLE arsenal_weapon ADD COLUMN wiki_url TEXT DEFAULT ''")
    if "wiki_status" not in columns:
        c.execute("ALTER TABLE arsenal_weapon ADD COLUMN wiki_status TEXT DEFAULT ''")
    retired_table = "arsenal_" + "wiki_" + "import"
    c.execute(f"DROP TABLE IF EXISTS {retired_table}")
    c.execute("CREATE INDEX IF NOT EXISTS idx_arsenal_weapon_wiki_status ON arsenal_weapon(wiki_status)")


def init_arsenal_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS arsenal_weapon(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            faction_id TEXT DEFAULT '',
            faction_name TEXT DEFAULT '',
            spotting_notes TEXT DEFAULT '',
            distinguishing TEXT DEFAULT '',
            source TEXT DEFAULT '',
            wiki_url TEXT DEFAULT '',
            wiki_status TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )""")
        if "source" not in _columns(c, "arsenal_weapon"):
            c.execute("ALTER TABLE arsenal_weapon ADD COLUMN source TEXT DEFAULT ''")
        ensure_manual_wiki_schema(c)
        retired_name_column = "ali" + "ases"
        if retired_name_column in _columns(c, "arsenal_weapon"):
            c.execute(f"ALTER TABLE arsenal_weapon DROP COLUMN {retired_name_column}")
        c.execute("""CREATE TABLE IF NOT EXISTS arsenal_weapon_photo(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            weapon_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            caption TEXT DEFAULT '',
            is_primary INTEGER DEFAULT 0,
            source TEXT DEFAULT 'user_photo',
            source_url TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            FOREIGN KEY(weapon_id) REFERENCES arsenal_weapon(id) ON DELETE CASCADE
        )""")
        if "source_url" not in _columns(c, "arsenal_weapon_photo"):
            c.execute("ALTER TABLE arsenal_weapon_photo ADD COLUMN source_url TEXT DEFAULT ''")
        c.execute("""CREATE TABLE IF NOT EXISTS arsenal_weapon_datasheet(
            weapon_id INTEGER NOT NULL,
            datasheet_id TEXT NOT NULL,
            raw_name TEXT NOT NULL,
            loadout_role TEXT NOT NULL DEFAULT 'wargear',
            PRIMARY KEY(weapon_id, datasheet_id, raw_name),
            FOREIGN KEY(weapon_id) REFERENCES arsenal_weapon(id) ON DELETE CASCADE
        )""")
        c.execute("DROP TABLE IF EXISTS arsenal_identify_log")
        retired_gap_table = "arsenal_" + "un" + "matched_weapon"
        c.execute(f"DROP TABLE IF EXISTS {retired_gap_table}")
        c.execute("CREATE INDEX IF NOT EXISTS idx_arsenal_weapon_name ON arsenal_weapon(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_arsenal_weapon_category ON arsenal_weapon(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_arsenal_weapon_datasheet ON arsenal_weapon_datasheet(datasheet_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_arsenal_photo_weapon ON arsenal_weapon_photo(weapon_id)")
        _migrate_weapon_source_blocks(c)
    generate_from_datasheets()


def faction_options(include_blank=True):
    options = []
    if include_blank:
        options.append({"id": "", "name": "Generic"})
    for faction in get_store().faction_list():
        options.append({"id": faction["id"], "name": faction["name"]})
    names = {item["name"] for item in options}
    with db() as c:
        for row in c.execute(
            "SELECT DISTINCT faction_name FROM arsenal_weapon WHERE faction_name<>'' ORDER BY faction_name"
        ).fetchall():
            if row["faction_name"] not in names:
                options.append({"id": "", "name": row["faction_name"]})
    return options


def faction_id_for_label(label):
    label_norm = _compact_label(label)
    for faction in get_store().factions:
        if _compact_label(faction.get("name")) == label_norm:
            return faction.get("id", "")
    extra_labels = {"tauempire": "TAU", "emperorschildren": "EC"}
    return extra_labels.get(label_norm, "")


def faction_name_for_id(fid):
    return get_store().faction_by_id.get(fid, {}).get("name", "")


def _compact_label(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def validate_weapon_payload(data, partial=False):
    errors = {}
    payload = {}
    fields = ("name", "category", "faction_id", "faction_name", "spotting_notes", "distinguishing")
    for field in fields:
        if field in data:
            payload[field] = str(data.get(field) or "").strip()
    if not partial or "name" in payload:
        if not payload.get("name"):
            errors["name"] = "Name is required."
        elif len(payload["name"]) > 160:
            errors["name"] = "Name must be 160 characters or fewer."
    if "category" in payload and payload["category"] not in CATEGORIES:
        errors["category"] = "Choose a valid category."
    if not partial and "category" not in payload:
        payload["category"] = "ranged"
    if "faction_id" in payload and payload["faction_id"]:
        name = faction_name_for_id(payload["faction_id"])
        if name:
            payload.setdefault("faction_name", name)
    if "faction_name" in payload and payload["faction_name"] and "faction_id" not in payload:
        payload["faction_id"] = faction_id_for_label(payload["faction_name"])
    if "faction_name" in payload:
        payload["faction_name"] = payload["faction_name"][:300]
    for field in ("spotting_notes", "distinguishing"):
        if field in payload:
            payload[field] = payload[field][:4000]
    return payload, errors


def list_weapons(q="", faction="", category=""):
    sql = """SELECT w.*,
             p.file_name AS primary_file,
             COUNT(DISTINCT allp.id) AS photo_count,
             COUNT(DISTINCT wd.datasheet_id) AS unit_count
             FROM arsenal_weapon w
             LEFT JOIN arsenal_weapon_photo p ON p.weapon_id=w.id AND p.is_primary=1
             LEFT JOIN arsenal_weapon_photo allp ON allp.weapon_id=w.id
             LEFT JOIN arsenal_weapon_datasheet wd ON wd.weapon_id=w.id
             WHERE 1=1"""
    params = []
    if q:
        like = f"%{q.lower()}%"
        sql += " AND (lower(w.name) LIKE ? OR lower(w.spotting_notes) LIKE ? OR lower(w.distinguishing) LIKE ?)"
        params.extend([like, like, like])
    if category:
        sql += " AND w.category=?"
        params.append(category)
    if faction:
        fname = faction_name_for_id(faction) or faction
        sql += " AND (w.faction_id=? OR w.faction_name=? OR COALESCE(w.faction_id,'')='' OR COALESCE(w.faction_name,'')='')"
        params.extend([faction, fname])
    sql += " GROUP BY w.id ORDER BY COALESCE(NULLIF(w.faction_name,''),'Generic'), w.name"
    with db() as c:
        return [_weapon_with_urls(rowdict(row)) for row in c.execute(sql, params).fetchall()]


def get_weapon(weapon_id):
    with db() as c:
        row = c.execute("""SELECT w.*,
                           p.file_name AS primary_file,
                           COUNT(DISTINCT allp.id) AS photo_count,
                           COUNT(DISTINCT wd.datasheet_id) AS unit_count
                           FROM arsenal_weapon w
                           LEFT JOIN arsenal_weapon_photo p ON p.weapon_id=w.id AND p.is_primary=1
                           LEFT JOIN arsenal_weapon_photo allp ON allp.weapon_id=w.id
                           LEFT JOIN arsenal_weapon_datasheet wd ON wd.weapon_id=w.id
                           WHERE w.id=?
                           GROUP BY w.id""", (weapon_id,)).fetchone()
        if not row:
            return None
        weapon = _weapon_with_urls(rowdict(row))
        weapon["photos"] = rowsdict(c.execute(
            "SELECT * FROM arsenal_weapon_photo WHERE weapon_id=? ORDER BY is_primary DESC, created_at DESC, id DESC",
            (weapon_id,),
        ).fetchall())
        for photo in weapon["photos"]:
            photo["url"] = photo_url(photo["file_name"])
        weapon["datasheets"] = weapon_datasheets(c, weapon_id)
        return weapon


def weapon_by_exact_name(name):
    key_name = display_name(name)
    if not key_name:
        return None
    with db() as c:
        row = c.execute("SELECT * FROM arsenal_weapon WHERE lower(name)=lower(?) ORDER BY id LIMIT 1", (key_name,)).fetchone()
        return rowdict(row)


def create_weapon(data):
    payload, errors = validate_weapon_payload(data)
    if not errors:
        existing = weapon_by_exact_name(payload["name"])
        if existing:
            errors["name"] = "An Arsenal entry with this name already exists."
    if errors:
        return None, errors
    ts = now_ts()
    with db() as c:
        cur = c.execute("""INSERT INTO arsenal_weapon(
            name, category, faction_id, faction_name, spotting_notes,
            distinguishing, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?)""", (
            display_name(payload["name"]), payload["category"],
            payload.get("faction_id", ""), payload.get("faction_name", ""),
            payload.get("spotting_notes", ""), payload.get("distinguishing", ""), ts, ts,
        ))
        weapon_id = cur.lastrowid
    return get_weapon(weapon_id), {}


def update_weapon(weapon_id, data, partial=False):
    payload, errors = validate_weapon_payload(data, partial=partial)
    if "name" in payload:
        payload["name"] = display_name(payload["name"])
    if errors:
        return None, errors
    if not payload:
        return get_weapon(weapon_id), {}
    fields = []
    params = []
    for key, value in payload.items():
        fields.append(f"{key}=?")
        params.append(value)
    fields.append("updated_at=?")
    params.append(now_ts())
    params.append(weapon_id)
    with db() as c:
        exists = c.execute("SELECT id FROM arsenal_weapon WHERE id=?", (weapon_id,)).fetchone()
        if not exists:
            return None, {"weapon": "Weapon not found."}
        c.execute(f"UPDATE arsenal_weapon SET {', '.join(fields)} WHERE id=?", params)
    return get_weapon(weapon_id), {}


def delete_weapon(weapon_id):
    with db() as c:
        photos = rowsdict(c.execute(
            "SELECT file_name FROM arsenal_weapon_photo WHERE weapon_id=?", (weapon_id,)
        ).fetchall())
        c.execute("DELETE FROM arsenal_weapon WHERE id=?", (weapon_id,))
    return [p["file_name"] for p in photos]


def add_weapon_photo(weapon_id, file_name, caption="", source="user_photo", source_url=""):
    with db() as c:
        count = c.execute(
            "SELECT COUNT(*) n FROM arsenal_weapon_photo WHERE weapon_id=?", (weapon_id,)
        ).fetchone()["n"]
        is_primary = 1 if count == 0 else 0
        cur = c.execute("""INSERT INTO arsenal_weapon_photo(
            weapon_id, file_name, caption, is_primary, source, source_url, created_at
        ) VALUES(?,?,?,?,?,?,?)""", (
            weapon_id, file_name, caption[:300], is_primary, source, str(source_url or "")[:1000], now_ts(),
        ))
        return rowdict(c.execute(
            "SELECT * FROM arsenal_weapon_photo WHERE id=?", (cur.lastrowid,)
        ).fetchone())


def get_photo(photo_id):
    with db() as c:
        return rowdict(c.execute("SELECT * FROM arsenal_weapon_photo WHERE id=?", (photo_id,)).fetchone())


def set_primary_photo(weapon_id, photo_id):
    with db() as c:
        exists = c.execute(
            "SELECT id FROM arsenal_weapon_photo WHERE id=? AND weapon_id=?", (photo_id, weapon_id)
        ).fetchone()
        if not exists:
            return False
        c.execute("UPDATE arsenal_weapon_photo SET is_primary=0 WHERE weapon_id=?", (weapon_id,))
        c.execute("UPDATE arsenal_weapon_photo SET is_primary=1 WHERE id=?", (photo_id,))
    return True


def delete_photo(weapon_id, photo_id):
    with db() as c:
        row = c.execute(
            "SELECT * FROM arsenal_weapon_photo WHERE id=? AND weapon_id=?", (photo_id, weapon_id)
        ).fetchone()
        if not row:
            return None
        was_primary = bool(row["is_primary"])
        file_name = row["file_name"]
        c.execute("DELETE FROM arsenal_weapon_photo WHERE id=?", (photo_id,))
        if was_primary:
            replacement = c.execute(
                "SELECT id FROM arsenal_weapon_photo WHERE weapon_id=? ORDER BY created_at DESC, id DESC LIMIT 1",
                (weapon_id,),
            ).fetchone()
            if replacement:
                c.execute("UPDATE arsenal_weapon_photo SET is_primary=1 WHERE id=?", (replacement["id"],))
        return file_name


def photo_url(file_name):
    return f"/arsenal/photo/{file_name}" if file_name else ""


def _weapon_with_urls(weapon):
    if not weapon:
        return None
    weapon["primary_url"] = photo_url(weapon.get("primary_file"))
    weapon["faction_label"] = weapon.get("faction_name") or "Generic"
    weapon.update(_source_attrs(weapon.get("source")))
    _add_manual_wiki_attrs(weapon)
    return weapon


def weapon_datasheets(c, weapon_id):
    store = get_store()
    rows = c.execute(
        "SELECT * FROM arsenal_weapon_datasheet WHERE weapon_id=? ORDER BY datasheet_id, raw_name",
        (weapon_id,),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        ds = store.ds_by_id.get(item["datasheet_id"], {})
        faction = store.faction_by_id.get(ds.get("faction_id", ""), {})
        item["unit_name"] = ds.get("name", item["datasheet_id"])
        item["faction_name"] = faction.get("name", ds.get("faction_id", ""))
        out.append(item)
    return out


def upload_dir(base):
    path = os.environ.get("ARSENAL_UPLOAD_DIR") or os.path.join(base, "uploads", "arsenal")
    os.makedirs(path, exist_ok=True)
    return path


def safe_photo_path(base_dir, file_name):
    if os.path.basename(file_name) != file_name:
        return None
    path = os.path.abspath(os.path.join(base_dir, file_name))
    root = os.path.abspath(base_dir)
    if not path.startswith(root + os.sep):
        return None
    return path


def all_weapon_rows():
    with db() as c:
        return rowsdict(c.execute("SELECT * FROM arsenal_weapon ORDER BY name").fetchall())


def datasheet_weapon_catalogue(store=None):
    store = store or get_store()
    names = {}
    links = []
    units = set()
    for ds in store.datasheets:
        if ds.get("virtual_bool"):
            continue
        detail = store.unit_detail(ds["id"])
        if not detail:
            continue
        units.add(ds["id"])
        for category, weapons in (("ranged", detail.get("ranged") or []), ("melee", detail.get("melee") or [])):
            for weapon in weapons:
                raw = (weapon.get("name") or "").strip()
                if not raw:
                    continue
                disp = display_name(raw)
                if not disp:
                    continue
                key = name_key(disp)
                rec = names.setdefault(key, {"name": disp, "category": category, "factions": set()})
                rec["factions"].add(ds.get("faction_id", ""))
                links.append((key, ds["id"], raw, category))
    return names, links, units


def _photo_counts(c):
    return {
        row["weapon_id"]: row["n"]
        for row in c.execute("SELECT weapon_id, COUNT(*) n FROM arsenal_weapon_photo GROUP BY weapon_id").fetchall()
    }


def _has_user_text(row, legacy_seed_mode=False):
    if not ((row.get("spotting_notes") or "").strip() or (row.get("distinguishing") or "").strip()):
        return False
    if not legacy_seed_mode:
        return True
    return str(row.get("updated_at") or "") != str(row.get("created_at") or "")


def _choose_existing_row(rows, photo_counts, legacy_seed_mode=False):
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: (
            0 if photo_counts.get(row["id"], 0) else 1,
            0 if _has_user_text(row, legacy_seed_mode) else 1,
            row["id"],
        ),
    )[0]


def _faction_for_record(rec, store):
    factions = {fid for fid in rec["factions"] if fid}
    if len(factions) != 1:
        return "", ""
    fid = next(iter(factions))
    return fid, store.faction_by_id.get(fid, {}).get("name", "")


def _merge_text(c, target_id, source, legacy_seed_mode=False):
    if not _has_user_text(source, legacy_seed_mode):
        return
    target = c.execute("SELECT * FROM arsenal_weapon WHERE id=?", (target_id,)).fetchone()
    if not target:
        return
    updates = {}
    for field in ("spotting_notes", "distinguishing"):
        if not (target[field] or "").strip() and (source[field] or "").strip():
            updates[field] = source[field]
    if not updates:
        return
    fields = [f"{field}=?" for field in updates]
    params = list(updates.values()) + [now_ts(), target_id]
    c.execute(f"UPDATE arsenal_weapon SET {', '.join(fields)}, updated_at=? WHERE id=?", params)


def _normalise_primary_photos(c, weapon_ids):
    for weapon_id in weapon_ids:
        photos = c.execute(
            "SELECT id, is_primary FROM arsenal_weapon_photo WHERE weapon_id=? ORDER BY is_primary DESC, created_at DESC, id DESC",
            (weapon_id,),
        ).fetchall()
        if not photos:
            continue
        primary_count = sum(1 for photo in photos if photo["is_primary"])
        if primary_count == 1:
            continue
        keep = photos[0]["id"]
        c.execute("UPDATE arsenal_weapon_photo SET is_primary=0 WHERE weapon_id=?", (weapon_id,))
        c.execute("UPDATE arsenal_weapon_photo SET is_primary=1 WHERE id=?", (keep,))


def generate_from_datasheets(store=None):
    store = store or get_store()
    names, links, units = datasheet_weapon_catalogue(store)
    ts = now_ts()
    with db() as c:
        existing = rowsdict(c.execute("SELECT * FROM arsenal_weapon").fetchall())
        photo_counts = _photo_counts(c)
        legacy_seed_mode = (
            0 < len(existing) < 500
            and len(names) > 1000
            and any((row.get("spotting_notes") or "").strip() or (row.get("distinguishing") or "").strip() for row in existing)
        )
        existing_by_key = {}
        for row in existing:
            key = name_key(row["name"])
            if key:
                existing_by_key.setdefault(key, []).append(row)

        generated_ids = {}
        for key, rec in names.items():
            existing_row = _choose_existing_row(existing_by_key.get(key, []), photo_counts, legacy_seed_mode)
            faction_id, faction_name = _faction_for_record(rec, store)
            if existing_row:
                weapon_id = existing_row["id"]
                preserve_text = _has_user_text(existing_row, legacy_seed_mode)
                category = existing_row["category"] if preserve_text and existing_row["category"] else rec["category"]
                spotting_notes = existing_row["spotting_notes"] if preserve_text else ""
                distinguishing = existing_row["distinguishing"] if preserve_text else ""
                c.execute("""UPDATE arsenal_weapon
                             SET name=?, category=?, faction_id=?, faction_name=?,
                                 spotting_notes=?, distinguishing=?, updated_at=?
                             WHERE id=?""", (
                    rec["name"], category, faction_id, faction_name,
                    spotting_notes, distinguishing, now_ts(), weapon_id,
                ))
            else:
                c.execute("""INSERT INTO arsenal_weapon(
                    name, category, faction_id, faction_name, spotting_notes,
                    distinguishing, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?)""", (
                    rec["name"], rec["category"], faction_id, faction_name, "", "", ts, ts,
                ))
                weapon_id = c.execute("SELECT last_insert_rowid() id").fetchone()["id"]
            generated_ids[key] = weapon_id

        for row in existing:
            key = name_key(row["name"])
            target_id = generated_ids.get(key)
            if not target_id:
                continue
            if row["id"] != target_id:
                c.execute("UPDATE arsenal_weapon_photo SET weapon_id=? WHERE weapon_id=?", (target_id, row["id"]))
            _merge_text(c, target_id, row, legacy_seed_mode)

        keep_ids = set(generated_ids.values())
        if keep_ids:
            placeholders = ",".join("?" for _ in keep_ids)
            c.execute(f"DELETE FROM arsenal_weapon WHERE id NOT IN ({placeholders})", tuple(keep_ids))
        else:
            c.execute("DELETE FROM arsenal_weapon")

        _normalise_primary_photos(c, keep_ids)

        c.execute("DELETE FROM arsenal_weapon_datasheet")
        for key, datasheet_id, raw_name, _category in links:
            weapon_id = generated_ids.get(key)
            if not weapon_id:
                continue
            c.execute("""INSERT OR IGNORE INTO arsenal_weapon_datasheet(
                weapon_id, datasheet_id, raw_name, loadout_role
            ) VALUES(?,?,?,?)""", (weapon_id, datasheet_id, raw_name, "wargear"))

        link_count = c.execute("SELECT COUNT(*) n FROM arsenal_weapon_datasheet").fetchone()["n"]
    return {"weapons": len(generated_ids), "links": link_count, "units": len(units)}


def sync_datasheets(store=None):
    return generate_from_datasheets(store)


def loadouts_index():
    """Faction -> unit tiles with weapon/link coverage. A weapon row counts as
    "linked" once its Arsenal entry carries real spotting content (notes,
    distinguishing text or a photo) — a bare auto-generated entry does not."""
    store = get_store()
    with db() as c:
        counts = {}
        for row in c.execute(
            """SELECT wd.datasheet_id,
                      COUNT(DISTINCT wd.weapon_id) n,
                      COUNT(DISTINCT CASE WHEN COALESCE(w.spotting_notes,'')<>''
                                            OR COALESCE(w.distinguishing,'')<>''
                                            OR ph.weapon_id IS NOT NULL
                                          THEN wd.weapon_id END) linked
               FROM arsenal_weapon_datasheet wd
               JOIN arsenal_weapon w ON w.id=wd.weapon_id
               LEFT JOIN (SELECT DISTINCT weapon_id FROM arsenal_weapon_photo) ph
                      ON ph.weapon_id=w.id
               GROUP BY wd.datasheet_id"""
        ).fetchall():
            counts[row["datasheet_id"]] = (row["n"], row["linked"])
    groups = []
    for faction in store.faction_list():
        units = []
        for unit in store.units_for_faction(faction["id"]):
            n, linked = counts.get(unit["id"], (0, 0))
            units.append({
                **unit,
                "weapon_count": n,
                "linked_count": linked,
            })
        groups.append({
            "faction": faction,
            "units": units,
            "weapon_count": sum(u["weapon_count"] for u in units),
            "linked_count": sum(u["linked_count"] for u in units),
        })
    return groups


def unit_loadout(datasheet_id):
    store = get_store()
    ds = store.ds_by_id.get(datasheet_id)
    if not ds:
        return None
    faction = store.faction_by_id.get(ds.get("faction_id", ""), {})
    with db() as c:
        rows = rowsdict(c.execute("""SELECT wd.*, w.name, w.category, w.faction_name,
                              w.spotting_notes, w.distinguishing, p.file_name AS primary_file
                              FROM arsenal_weapon_datasheet wd
                              JOIN arsenal_weapon w ON w.id=wd.weapon_id
                              LEFT JOIN arsenal_weapon_photo p ON p.weapon_id=w.id AND p.is_primary=1
                              WHERE wd.datasheet_id=?
                              ORDER BY CASE w.category WHEN 'ranged' THEN 0 WHEN 'melee' THEN 1 ELSE 2 END,
                                  w.name, wd.raw_name""", (datasheet_id,)).fetchall())

    # Datasheet weapon profiles for the stat strip. raw_name is the profile
    # display name emitted by data_store._build_weapons, so this is 1:1.
    detail = store.unit_detail(datasheet_id) or {}
    profile_by_name = {}
    for bucket in ("ranged", "melee"):
        for p in detail.get(bucket) or []:
            profile_by_name.setdefault((p.get("name") or "").lower(), p)

    for row in rows:
        row["primary_url"] = photo_url(row.get("primary_file"))
        row["linked"] = bool(
            (row.get("spotting_notes") or "").strip()
            or (row.get("distinguishing") or "").strip()
            or row.get("primary_file")
        )
        profile = profile_by_name.get((row.get("raw_name") or "").lower())
        row["profile"] = profile
        row["profile_keywords"] = [
            kw.strip() for kw in (profile.get("keywords") or "").split(",")
            if kw.strip()
        ] if profile else []
    groups = _group_by_category(rows)
    return {
        "datasheet": ds,
        "faction": {"id": ds.get("faction_id", ""), "name": faction.get("name", ds.get("faction_id", ""))},
        "groups": groups,
        "weapon_count": len(rows),
        "linked_count": sum(1 for row in rows if row["linked"]),
    }


def _group_by_category(rows):
    out = []
    for category in CATEGORIES:
        category_rows = [row for row in rows if row["category"] == category]
        if category_rows:
            out.append({"role": category, "rows": category_rows})
    other_rows = [row for row in rows if row["category"] not in CATEGORIES]
    if other_rows:
        out.append({"role": "other", "rows": other_rows})
    return out


def weapon_card_payload(name="", weapon_id=None):
    with db() as c:
        row = None
        if weapon_id:
            row = c.execute("""SELECT w.*, p.file_name AS primary_file
                               FROM arsenal_weapon w
                               LEFT JOIN arsenal_weapon_photo p ON p.weapon_id=w.id AND p.is_primary=1
                               WHERE w.id=?""", (weapon_id,)).fetchone()
        if not row and name:
            key_name = display_name(name)
            if key_name:
                row = c.execute("""SELECT w.*, p.file_name AS primary_file
                                   FROM arsenal_weapon w
                                   LEFT JOIN arsenal_weapon_photo p ON p.weapon_id=w.id AND p.is_primary=1
                                   WHERE lower(w.name)=lower(?)
                                   ORDER BY w.id LIMIT 1""", (key_name,)).fetchone()
    if not row:
        return {
            "found": False,
            "name": display_name(name) or name,
            "add_url": f"/arsenal/weapon/new?name={_url_quote(display_name(name) or name)}",
            "message": "No Arsenal entry yet.",
        }
    weapon = _weapon_with_urls(rowdict(row))
    description = (weapon.get("spotting_notes") or "")[:220]
    return {
        "found": True,
        "id": weapon["id"],
        "name": weapon["name"],
        "photo_url": weapon["primary_url"],
        "description": description,
        "spotting_notes": description,
        "entry_url": f"/arsenal/weapon/{weapon['id']}",
    }


def _url_quote(value):
    from urllib.parse import quote
    return quote(str(value or ""))


def audit_data(faction_filter="", problem="", q=""):
    store = get_store()
    ql = q.lower().strip()
    with db() as c:
        linked = rowsdict(c.execute("""SELECT wd.*, w.name, w.category, w.faction_id,
                                w.faction_name, w.spotting_notes, w.distinguishing, w.source,
                                w.wiki_url, w.wiki_status,
                                p.file_name AS primary_file,
                                COUNT(DISTINCT allp.id) AS photo_count,
                                (SELECT COUNT(DISTINCT wd2.datasheet_id)
                                 FROM arsenal_weapon_datasheet wd2
                                 WHERE wd2.weapon_id=w.id) AS unit_count
                                FROM arsenal_weapon_datasheet wd
                                JOIN arsenal_weapon w ON w.id=wd.weapon_id
                                LEFT JOIN arsenal_weapon_photo p ON p.weapon_id=w.id AND p.is_primary=1
                                LEFT JOIN arsenal_weapon_photo allp ON allp.weapon_id=w.id
                                GROUP BY wd.weapon_id, wd.datasheet_id, wd.raw_name
                                ORDER BY w.name""").fetchall())
        catalogue_rows = rowsdict(c.execute("""SELECT w.*,
                                COUNT(DISTINCT p.id) AS photo_count
                                FROM arsenal_weapon w
                                LEFT JOIN arsenal_weapon_photo p ON p.weapon_id=w.id
                                GROUP BY w.id""").fetchall())
    problem_counts = {"missing-photo": 0, "missing-description": 0}
    for row in catalogue_rows:
        problems = row_problems(row)
        if "missing-photo" in problems:
            problem_counts["missing-photo"] += 1
        if "missing-description" in problems:
            problem_counts["missing-description"] += 1

    groups = {}
    for row in linked:
        ds = store.ds_by_id.get(row["datasheet_id"], {})
        if not ds:
            continue
        faction = store.faction_by_id.get(ds.get("faction_id", ""), {})
        row["unit_name"] = ds.get("name", row["datasheet_id"])
        row["datasheet_faction_id"] = ds.get("faction_id", "")
        row["datasheet_faction_name"] = faction.get("name", ds.get("faction_id", ""))
        row["primary_url"] = photo_url(row.get("primary_file"))
        row.update(_source_attrs(row.get("source")))
        _add_manual_wiki_attrs(row)
        row["problems"] = row_problems(row)
        if not audit_row_matches(row, faction_filter, problem, ql):
            continue
        fname = row["datasheet_faction_name"] or "Unknown"
        unit_key = row["datasheet_id"]
        fgroup = groups.setdefault(fname, {"faction_name": fname, "units": {}})
        unit = fgroup["units"].setdefault(unit_key, {
            "datasheet_id": row["datasheet_id"],
            "unit_name": row["unit_name"],
            "rows": [],
        })
        unit["rows"].append(row)

    out_groups = []
    for group in groups.values():
        units = list(group["units"].values())
        units.sort(key=lambda u: u["unit_name"])
        group["units"] = units
        group["weapon_count"] = sum(len(unit["rows"]) for unit in units)
        group["problem_count"] = sum(
            len(row.get("problems", [])) for unit in units for row in unit["rows"]
        )
        out_groups.append(group)
    out_groups.sort(key=lambda g: g["faction_name"])
    return {
        "groups": out_groups,
        "weapons": list_weapons(),
        "factions": faction_options(include_blank=False),
        "problem_counts": problem_counts,
    }


def row_problems(row):
    problems = []
    if not row.get("photo_count"):
        problems.append("missing-photo")
    if not (row.get("spotting_notes") or "").strip():
        problems.append("missing-description")
    if row.get("faction_name") and not row.get("faction_id"):
        problems.append("missing-faction-id")
    return problems


def audit_row_matches(row, faction_filter, problem, ql):
    if faction_filter:
        if row.get("datasheet_faction_id") != faction_filter and row.get("faction_id") != faction_filter:
            return False
    if problem and problem != "all":
        if problem not in row.get("problems", []):
            return False
    if ql:
        hay = " ".join(str(row.get(k, "")) for k in (
            "name", "category", "faction_name", "spotting_notes",
            "distinguishing", "raw_name", "unit_name",
        )).lower()
        if ql not in hay:
            return False
    return True
