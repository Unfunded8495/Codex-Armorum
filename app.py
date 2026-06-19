"""Warhammer 40,000 collection cataloguer — Flask backend.

Run:  python app.py    then open http://127.0.0.1:5050

collection.db holds your models and army lists. cache/images/ holds reference
unit images. uploads/ holds your own photos.
"""
import json
import os
import re
import threading
import time
import uuid
from urllib.parse import quote, unquote

from flask import (Flask, Response, abort, jsonify, render_template, request,
                   send_file, send_from_directory)

import factions_theme as ft
from army import (
    _army_unit_row, _datasheet_in_faction, _enhancement_cost,
    _enhancement_for, _normalise_squad_size, _points_for,
    _valid_detachment_for_faction,
)
from box_sets import (
    _clean_box_payload, _save_custom_box, _unit_search_pool,
    bought_info, bought_totals, box_set_by_id, box_sets,
    compute_unlogged_map, dedup_group_total, parse_box_text,
    purchase_payload,
)
from catalogue_review import (
    add_manual_model, catalogue_faction_datasheet_index, catalogue_image_for_datasheet,
    catalogue_image_path, catalogue_payload, clear_catalogue_model_image,
    delete_manual_model, save_catalogue_model_image, save_resolution,
)
from collection import (
    _minis_for, _parse_comp_range, _squad_suggestions,
    _wargear_choice_groups, _wargear_choices, favourite_factions, owned_totals,
)
from data_store import get_store
from db import _table_exists, db, init_db
from images import (
    ALLOWED, CACHE_DIR, MAX_REF_BYTES, MAX_UPLOAD_BYTES,
    _image_ext_from_bytes,
    _open_public_url, _read_image_upload, _ref_path, _safe_image_url,
)
from arsenal import init_arsenal


from utils import _as_int, _as_bool, _icon_key, _int, _slug

BASE = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(BASE, "uploads")
ICON_DIR = os.path.join(BASE, "static", "icons")
ICON_EXTS = (".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif")
BOX_IMAGE_DIR = os.path.join(BASE, "cache", "images", "boxes")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BOX_IMAGE_DIR, exist_ok=True)


_ALIGNMENT_WORDS = {"Imperium", "Chaos", "Xenos", "Unaligned"}


def _faction_display_name(full_name):
    """Strip BSData alignment prefix; return (display_name, group).

    "Xenos - Aeldari"                             → ("Aeldari", "")
    "Imperium - Adeptus Astartes - Space Marines" → ("Space Marines", "Adeptus Astartes")
    "Chaos - Emperor's Children"                  → ("Emperor's Children", "")
    "Aeldari - Ynnari"                            → ("Ynnari", "Aeldari")
    """
    parts = [p.strip() for p in full_name.split(" - ")]
    if len(parts) <= 1:
        return full_name, ""
    display = parts[-1]
    parent = parts[-2]
    group = "" if parent in _ALIGNMENT_WORDS else parent
    return display, group


def _box_ref_path(box_id):
    slug = re.sub(r"[^a-z0-9_-]+", "_", box_id.lower()).strip("_")
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = os.path.join(BOX_IMAGE_DIR, slug + ext)
        if os.path.exists(p):
            return p
    return None


def _clear_box_ref(box_id):
    slug = re.sub(r"[^a-z0-9_-]+", "_", box_id.lower()).strip("_")
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = os.path.join(BOX_IMAGE_DIR, slug + ext)
        try:
            os.remove(p)
        except OSError:
            pass

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "codex-armorum-local")

store = get_store()
init_db()
init_arsenal(app)


# ---------------------------------------------------------------- icon helpers
def _faction_icon_url(fid, name):
    short, _ = _faction_display_name(name)
    keys = {
        _icon_key(fid), _icon_key(name), _icon_key(_slug(name)),
        _icon_key(short), _icon_key(_slug(short)),
    }
    try:
        filenames = os.listdir(ICON_DIR)
    except OSError:
        return None
    for fname in filenames:
        stem, ext = os.path.splitext(fname)
        if ext.lower() in ICON_EXTS and _icon_key(stem) in keys:
            return f"/static/icons/{quote(fname)}"
    return None


def _tinted_svg(filepath, accent):
    with open(filepath, encoding="utf-8") as f:
        svg = f.read()
    style = f'<style>path,polygon,circle,ellipse,polyline,line{{fill:{accent};stroke:none}}</style>'
    svg = re.sub(r'(<svg[^>]*>)', r'\1' + style, svg, count=1)
    return svg


def _box_set_payloads(box_list):
    return [{
        "id": b["id"],
        "name": b["name"],
        "game_system": b["game_system"],
        "release_date": b["release_date"],
        "manufacturer": b["manufacturer"],
        "status": b["status"],
        "source": b["source"],
        "editable": b["editable"],
        "faction_id": b["faction_id"],
        "total_datasheet_models": b["total_datasheet_models"],
        "total_physical_miniatures": b["total_physical_miniatures"],
        "notes": b["notes"],
        "contents": b["contents"],
        "sources": b["sources"],
        "expected_minis": b.get("expected_minis"),
    } for b in box_list]


def _summary_payload(c, info=None, owned=None):
    total_minis = c.execute("SELECT COUNT(*) n FROM minis").fetchone()["n"]
    stage_counts = c.execute("""
        SELECT
          COALESCE(SUM(CASE WHEN COALESCE(stage, 'unbuilt') = 'unbuilt' THEN 1 ELSE 0 END), 0) n_unbuilt,
          COALESCE(SUM(CASE WHEN COALESCE(stage, 'unbuilt') IN ('finished', 'display') THEN 1 ELSE 0 END), 0) n_finished,
          COALESCE(SUM(CASE WHEN COALESCE(stage, 'unbuilt') NOT IN ('unbuilt', 'finished', 'display') THEN 1 ELSE 0 END), 0) n_wip
        FROM minis
    """).fetchone()
    distinct = c.execute(
        "SELECT COUNT(DISTINCT unit_bsdata_id) n FROM minis"
        " WHERE unit_bsdata_id IS NOT NULL").fetchone()["n"]
    photo_count = c.execute("SELECT COUNT(*) n FROM photos").fetchone()["n"]
    army_count = c.execute("SELECT COUNT(*) n FROM army_lists").fetchone()["n"]
    info = info or bought_info(c)
    owned = owned if owned is not None else owned_totals()
    ul_map = compute_unlogged_map(info, owned)
    return {"total_minis": total_minis, "distinct_units": distinct,
            "photos": photo_count, "armies": army_count,
            "bought_minis": dedup_group_total(info, info["totals"]),
            "unbuilt_minis": stage_counts["n_unbuilt"],
            "wip_minis": stage_counts["n_wip"],
            "finished_minis": stage_counts["n_finished"],
            "unlogged_minis": dedup_group_total(info, ul_map)}


def _factions_payload(info=None, owned=None):
    factions   = store.faction_list()
    owned      = owned if owned is not None else owned_totals()
    info       = info or bought_info()
    bought     = info["totals"]
    favourites = favourite_factions()
    ul_map     = compute_unlogged_map(info, owned)

    by_faction = {}
    minis_by_faction = {}
    bought_by_faction = {}
    bought_minis_by_faction = {}
    unbuilt_minis_by_faction = {}
    finished_minis_by_faction = {}
    ul_by_faction = {}

    for did, qty in owned.items():
        d = store.ds_by_id.get(did)
        if d and qty > 0:
            fid = d["faction_id"]
            by_faction[fid]      = by_faction.get(fid, 0) + 1
            minis_by_faction[fid] = minis_by_faction.get(fid, 0) + qty

    with db() as c:
        rows = c.execute("""
            SELECT unit_bsdata_id, COALESCE(stage, 'unbuilt') stage, COUNT(*) cnt
            FROM minis
            WHERE unit_bsdata_id IS NOT NULL
            GROUP BY unit_bsdata_id, COALESCE(stage, 'unbuilt')
        """).fetchall()
    for r in rows:
        d = store.ds_by_id.get(r["unit_bsdata_id"])
        if not d:
            continue
        fid = d["faction_id"]
        if r["stage"] == "unbuilt":
            unbuilt_minis_by_faction[fid] = unbuilt_minis_by_faction.get(fid, 0) + r["cnt"]
        if r["stage"] in ("finished", "display"):
            finished_minis_by_faction[fid] = finished_minis_by_faction.get(fid, 0) + r["cnt"]

    counted_bought_by_fid = {}
    counted_ul_by_fid     = {}
    group_ul      = info.get("group_ul", {})
    standalone    = info.get("standalone", {})
    standalone_ul = info.get("standalone_ul", {})
    for did, qty in bought.items():
        d = store.ds_by_id.get(did)
        if not d or qty <= 0:
            continue
        fid   = d["faction_id"]
        gkeys = info["did_groups"].get(did, [])
        cb    = counted_bought_by_fid.setdefault(fid, set())
        cu    = counted_ul_by_fid.setdefault(fid, set())
        if gkeys:
            # Dedicated-kit purchases of a multikit member are per-datasheet:
            # count their minis on top of the (once-per-group) shared pool.
            sa = standalone.get(did, 0)
            if sa:
                bought_minis_by_faction[fid] = bought_minis_by_faction.get(fid, 0) + sa
                ul_by_faction[fid]           = ul_by_faction.get(fid, 0) + standalone_ul.get(did, 0)
            for gk in gkeys:
                if gk not in cb:
                    cb.add(gk)
                    bought_by_faction[fid]        = bought_by_faction.get(fid, 0) + 1
                    bought_minis_by_faction[fid] = bought_minis_by_faction.get(fid, 0) + info["groups"][gk]["pool"]
                if gk not in cu:
                    cu.add(gk)
                    ul_by_faction[fid] = ul_by_faction.get(fid, 0) + group_ul.get(gk, 0)
        else:
            bought_by_faction[fid]        = bought_by_faction.get(fid, 0) + 1
            bought_minis_by_faction[fid] = bought_minis_by_faction.get(fid, 0) + qty
            ul_by_faction[fid]            = ul_by_faction.get(fid, 0) + ul_map.get(did, 0)

    for f in factions:
        primary, accent, _ = ft.theme_for(f["name"])
        f["primary"] = primary
        f["accent"]  = accent
        f["owned_units"]      = by_faction.get(f["id"], 0)
        f["owned_minis"]     = minis_by_faction.get(f["id"], 0)
        f["bought_units"]     = bought_by_faction.get(f["id"], 0)
        f["bought_minis"]    = bought_minis_by_faction.get(f["id"], 0)
        f["unbuilt_minis"]   = unbuilt_minis_by_faction.get(f["id"], 0)
        f["finished_minis"]  = finished_minis_by_faction.get(f["id"], 0)
        f["unlogged_minis"]  = ul_by_faction.get(f["id"], 0)
        raw_icon = _faction_icon_url(f["id"], f["name"])
        if raw_icon and raw_icon.lower().endswith(".svg"):
            f["icon_url"] = f"/api/factions/{f['id']}/icon"
        else:
            f["icon_url"] = raw_icon
        dn, group = _faction_display_name(f["name"])
        f["display_name"] = dn
        f["group"] = group
        f["initial"] = dn[:1].upper() or "?"
        f["favourite"] = f["id"] in favourites
    return factions


# ---------------------------------------------------------------- pages
@app.route("/")
def index():
    return render_template("index.html", active_page="armies")


@app.route("/army-builder")
def army_builder_page():
    return render_template(
        "army_builder.html",
        active_page="army_builder",
        breadcrumb=[{"label": "Army Builder"}],
    )


@app.route("/catalogue-review")
def catalogue_review_page():
    return render_template(
        "catalogue_review.html",
        active_page="catalogue",
        breadcrumb=[{"label": "Model Catalogue"}],
    )


@app.route("/api/shutdown", methods=["POST"])
def shutdown_app():
    if request.remote_addr not in {"127.0.0.1", "::1"}:
        abort(403)

    def stop_server():
        time.sleep(0.35)
        os._exit(0)

    threading.Thread(target=stop_server, daemon=True).start()
    return jsonify({"ok": True, "message": "Vault sealed"})


# ---------------------------------------------------------------- faction api
@app.route("/api/factions")
def api_factions():
    return jsonify(_factions_payload())


@app.route("/api/factions/<fid>/icon")
def faction_icon(fid):
    fac = store.faction_by_id.get(fid)
    if not fac:
        abort(404)
    _, accent, _ = ft.theme_for(fac.get("name", ""))
    raw_url = _faction_icon_url(fid, fac.get("name", ""))
    if not raw_url or not raw_url.lower().endswith(".svg"):
        abort(404)
    fname = unquote(raw_url.split("/static/icons/", 1)[-1])
    filepath = os.path.join(ICON_DIR, fname)
    try:
        svg = _tinted_svg(filepath, accent)
    except OSError:
        abort(404)
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@app.route("/api/factions/<fid>/favourite", methods=["POST", "DELETE"])
def api_favourite_faction(fid):
    from db import db
    if fid not in store.faction_by_id:
        abort(404)
    with db() as c:
        if request.method == "POST":
            c.execute("""INSERT OR REPLACE INTO favourite_factions(faction_id, created_at)
                         VALUES(?,?)""", (fid, time.time()))
            favourite = True
        else:
            c.execute("DELETE FROM favourite_factions WHERE faction_id=?", (fid,))
            favourite = False
    return jsonify({"ok": True, "favourite": favourite})


@app.route("/api/factions/<fid>/units")
def api_faction_units(fid):
    faction = store.faction_by_id.get(fid)
    if not faction:
        abort(404)
    owned  = owned_totals()
    info   = bought_info()
    ul_map = compute_unlogged_map(info, owned)
    units  = store.units_for_faction(fid)
    for u in units:
        u["owned"]    = owned.get(u["id"], 0)
        u["bought"]   = info["totals"].get(u["id"], 0)
        u["unlogged"] = ul_map.get(u["id"], 0)
        u["multikit_groups"] = [
            {"key": gkey,
             "pool": info["groups"].get(gkey, {}).get("pool", 0),
             "members": info["groups"].get(gkey, {}).get("members", [])}
            for gkey in info["did_groups"].get(u["id"], [])
        ]
    primary, accent, _ = ft.theme_for(faction["name"])
    dn, _ = _faction_display_name(faction["name"])
    return jsonify({
        "faction": {"id": fid, "name": faction["name"], "display_name": dn, "primary": primary, "accent": accent},
        "units": units,
    })


@app.route("/api/factions/<fid>/detachments")
def api_faction_detachments(fid):
    if fid not in store.faction_by_id:
        abort(404)
    detachments = store.detachments_by_faction.get(fid, [])
    return jsonify([{"id": d["id"], "name": d["name"], "type": d.get("type", "")}
                    for d in detachments])


@app.route("/api/detachments/<dtid>/enhancements")
def api_detachment_enhancements(dtid):
    if dtid not in store.detachment_by_id:
        abort(404)
    enhs = store.enhancements_by_detachment.get(dtid, [])
    return jsonify([{
        "id": e["id"],
        "name": e["name"],
        "cost": _int(e.get("cost", 0)),
        "description": e.get("description", ""),
    } for e in enhs])


# ---------------------------------------------------------------- unit api
def _canon_did(did):
    """Resolve a datasheet id to its canonical Wahapedia id so unit-level
    records key consistently. With Wahapedia-native ids this normalises an id to
    itself. Falls back to the id as given when unresolvable."""
    return store.ds_by_id.get(did, {}).get("id") or did


def _unit_wip(c, did):
    """Return (notes, photos) for the unit-level Work in Progress section."""
    key = _canon_did(did)
    row = c.execute("SELECT notes FROM unit_wip WHERE datasheet_id=?", (key,)).fetchone()
    notes = row["notes"] if row else ""
    photos = c.execute(
        "SELECT id, filename, caption FROM unit_wip_photos"
        " WHERE datasheet_id=? ORDER BY uploaded_at", (key,)).fetchall()
    return notes, [
        {"id": p["id"], "url": f"/uploads/{p['filename']}", "caption": p["caption"]}
        for p in photos
    ]


@app.route("/api/units/<did>")
def api_unit(did):
    from db import db
    detail = store.unit_detail(did)
    if not detail:
        abort(404)
    detail["wargear_choice_groups"] = _wargear_choice_groups(detail)
    detail["wargear_choices"] = _wargear_choices(detail)
    comp_range = _parse_comp_range(detail.get("composition", []))
    detail["composition_range"] = comp_range
    from catalogue_review import catalogue_model_index
    cat_index = catalogue_model_index()
    with db() as c:
        minis = _minis_for(c, did)
        detail["wip_notes"], detail["wip_photos"] = _unit_wip(c, did)
    for m in minis:
        cid = m.get("catalogue_model_id")
        m["catalogue_model"] = cat_index.get(cid) if cid else None
    detail["collection_minis"] = minis
    detail["owned"] = len(minis)
    info   = bought_info()
    owned  = owned_totals()
    ul_map = compute_unlogged_map(info, owned)
    detail["bought"]   = info["totals"].get(did, 0)
    detail["unlogged"] = ul_map.get(did, 0)
    # Expose sibling units sharing the same physical pool
    alts = []
    for gkey in info["did_groups"].get(did, []):
        for mid in info["groups"][gkey]["members"]:
            if mid != did:
                ds = store.ds_by_id.get(mid)
                if ds:
                    alts.append({"id": mid, "name": ds.get("name", mid)})
    detail["multikit_alternatives"] = alts
    detail["squad_suggestions"] = _squad_suggestions(len(minis), comp_range)
    primary, accent, _ = ft.theme_for(detail.get("faction_name", ""))
    detail["primary"] = primary
    detail["accent"] = accent
    detail["has_reference"] = _ref_path(did) is not None
    from catalogue_review import catalogue_models_for_datasheet
    detail["linked_catalogue_models"] = catalogue_models_for_datasheet(did)
    return jsonify(detail)


def _create_minis(datasheet_id, catalogue_model_id, label, wargear, count, multikit_group=None):
    """Insert `count` mini rows and return the created dicts."""
    from db import db
    import uuid as _uuid
    # Resolve to the canonical Wahapedia datasheet id (unit_bsdata_id is a legacy
    # column name that now holds the Wahapedia id).
    unit_bsdata_id = store.ds_by_id.get(datasheet_id, {}).get("id")
    now = time.time()
    created = []
    with db() as c:
        for _ in range(count):
            mid = _uuid.uuid4().hex
            c.execute(
                """INSERT INTO minis
                       (id, datasheet_id, unit_bsdata_id, catalogue_model_id,
                        label, wargear, notes, finished, stage, multikit_group, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (mid, datasheet_id, unit_bsdata_id, catalogue_model_id,
                 label, json.dumps(wargear), "", 0, "unbuilt", multikit_group, now),
            )
            created.append({
                "id": mid,
                "catalogue_model_id": catalogue_model_id,
                "label": label,
                "wargear": wargear,
                "notes": "",
                "stage": "unbuilt",
                "multikit_group": multikit_group,
                "photos": [],
            })
    return created


def _minis_from_box(box, quantity):
    """Create unbuilt mini rows for every physical mini in a box purchase.

    Multikit groups share a physical pool — only the first content item for
    each group is used to create rows (avoid double-counting the pool).
    Multikit minis carry the group key so the user can choose which unit to
    build when they advance past 'unbuilt'.
    """
    groups_done = set()
    total = 0
    for item in box.get("contents", []):
        mg = item.get("multikit_group")
        if mg:
            if mg in groups_done:
                continue
            groups_done.add(mg)
            count = item["physical_miniatures"] * quantity
            gkey = f"{box['id']}::{mg}"
        else:
            count = item["datasheet_count"] * quantity
            gkey = None
        if count <= 0:
            continue
        total += count
        _create_minis(
            item["datasheet_id"],
            item.get("catalogue_model_id"),
            item.get("catalogue_label", ""),
            [],
            count,
            multikit_group=gkey,
        )
    return total


@app.route("/api/minis/<mid>", methods=["POST"])
def api_update_mini(mid):
    from db import db
    with db() as c:
        row = c.execute("SELECT * FROM minis WHERE id=?", (mid,)).fetchone()
        if not row:
            abort(404)
        data = request.get_json(force=True)
        label = str(data.get("label", row["label"]))[:120] if "label" in data else row["label"]
        notes = str(data.get("notes", row["notes"]))[:2000] if "notes" in data else row["notes"]
        if "wargear" in data and isinstance(data["wargear"], list):
            wargear = json.dumps([str(x)[:160] for x in data["wargear"]][:60])
        else:
            wargear = row["wargear"]
        # Accept stage directly; fall back to converting legacy finished flag
        if "stage" in data and str(data["stage"]) in _VALID_STAGES:
            stage = str(data["stage"])
        elif "finished" in data:
            stage = "finished" if _as_bool(data["finished"]) else "unbuilt"
        else:
            stage = row["stage"] if "stage" in row.keys() else "unbuilt"
        finished = 1 if stage == "finished" else 0
        catalogue_model_id = (
            str(data["catalogue_model_id"]).strip() or None
            if "catalogue_model_id" in data
            else row["catalogue_model_id"]
        )
        c.execute(
            "UPDATE minis SET label=?, notes=?, wargear=?, finished=?, stage=?, catalogue_model_id=? WHERE id=?",
            (label, notes, wargear, finished, stage, catalogue_model_id, mid),
        )
    return jsonify({"ok": True})


def _trim_army_overage(c, unit_bid, id_variants, ph, built_only):
    """Trim army-list assignments that now exceed the minis available for a unit.

    Called after a mini is reset or removed. When ``built_only`` is set, only minis
    past the unbuilt stage count as available (used when resetting a built mini back
    to the pool); otherwise every remaining mini for the unit counts.
    """
    if not id_variants:
        return
    if unit_bid:
        remaining_sql = "SELECT COUNT(*) cnt FROM minis WHERE unit_bsdata_id=?"
        if built_only:
            remaining_sql += " AND stage!='unbuilt'"
        total_remaining = c.execute(remaining_sql, (unit_bid,)).fetchone()["cnt"]
    else:
        total_remaining = 0
    total_assigned = c.execute(
        f"SELECT COALESCE(SUM(assigned_count),0) tot FROM army_units WHERE datasheet_id IN ({ph})",
        id_variants).fetchone()["tot"]
    overage = total_assigned - total_remaining
    if overage <= 0:
        return
    for au in c.execute(
            f"SELECT id, assigned_count FROM army_units WHERE datasheet_id IN ({ph}) AND assigned_count>0 ORDER BY assigned_count DESC",
            id_variants).fetchall():
        if overage <= 0:
            break
        reduce = min(overage, au["assigned_count"])
        c.execute("UPDATE army_units SET assigned_count=assigned_count-? WHERE id=?",
                  (reduce, au["id"]))
        overage -= reduce


@app.route("/api/minis/<mid>", methods=["DELETE"])
def api_delete_mini(mid):
    from db import db
    with db() as c:
        row = c.execute("SELECT * FROM minis WHERE id=?", (mid,)).fetchone()
        if not row:
            abort(404)
        stage = row["stage"] if "stage" in row.keys() else (
            "finished" if bool(row["finished"]) else "unbuilt"
        )
        photos = c.execute("SELECT filename FROM photos WHERE mini_id=?", (mid,)).fetchall()
        old_did = row["datasheet_id"]
        unit_bid = row["unit_bsdata_id"]
        id_variants = list({x for x in [unit_bid, old_did] if x})
        ph = ",".join("?" * len(id_variants)) if id_variants else "NULL"

        c.execute("DELETE FROM photos WHERE mini_id=?", (mid,))
        if stage != "unbuilt":
            # Reset to pool: clear progress data but keep the row in the collection.
            c.execute(
                "UPDATE minis SET stage='unbuilt', finished=0, wargear='[]', notes='' WHERE id=?",
                (mid,),
            )
            _trim_army_overage(c, unit_bid, id_variants, ph, built_only=True)
            action = "reset"
        else:
            # Already unbuilt — remove from the collection entirely.
            c.execute("DELETE FROM minis WHERE id=?", (mid,))
            _trim_army_overage(c, unit_bid, id_variants, ph, built_only=False)
            action = "deleted"

    for p in photos:
        try:
            os.remove(os.path.join(UPLOAD_DIR, p["filename"]))
        except OSError:
            pass
    return jsonify({"ok": True, "action": action})


@app.route("/api/minis/<mid>/duplicate", methods=["POST"])
def api_duplicate_mini(mid):
    from db import db
    from catalogue_review import catalogue_model_index
    import uuid as _uuid
    data = request.get_json(force=True)
    label = str(data.get("label", "")).strip()[:120]
    with db() as c:
        row = c.execute("SELECT * FROM minis WHERE id=?", (mid,)).fetchone()
        if not row:
            abort(404)
        if not label:
            return jsonify({"ok": False, "error": "Label is required."}), 400
        if label == (row["label"] or ""):
            return jsonify({"ok": False, "error": "Label must differ from the original."}), 400
        new_id = _uuid.uuid4().hex
        now = time.time()
        src_stage = row["stage"] if "stage" in row.keys() else "unbuilt"
        c.execute(
            """INSERT INTO minis
                   (id, datasheet_id, unit_bsdata_id, catalogue_model_id,
                    label, wargear, notes, finished, stage, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (new_id, row["datasheet_id"], row["unit_bsdata_id"], row["catalogue_model_id"], label,
             row["wargear"], "", 1 if src_stage == "finished" else 0, src_stage, now),
        )
        cid = row["catalogue_model_id"]
    try:
        wg = json.loads(row["wargear"] or "[]")
    except ValueError:
        wg = []
    cat = catalogue_model_index().get(cid) if cid else None
    return jsonify({
        "ok": True,
        "mini": {
            "id": new_id,
            "catalogue_model_id": cid,
            "catalogue_model": cat,
            "label": label,
            "wargear": wg if isinstance(wg, list) else [],
            "notes": "",
            "stage": src_stage,
            "photos": [],
        }
    })


@app.route("/api/minis/<mid>/photos", methods=["POST"])
def api_upload_mini_photos(mid):
    from db import db
    saved = []
    db_rows = []
    written_paths = []
    with db() as c:
        row = c.execute("SELECT datasheet_id FROM minis WHERE id=?", (mid,)).fetchone()
    if not row:
        abort(404)
    did = row["datasheet_id"]
    files = request.files.getlist("photos")
    try:
        for f in files:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext == ".jpeg":
                ext = ".jpg"
            if ext not in ALLOWED:
                continue
            image, error = _read_image_upload(f, MAX_UPLOAD_BYTES)
            if error:
                continue
            blob, ext = image
            pid = uuid.uuid4().hex
            fname = f"{pid}{ext}"
            path = os.path.join(UPLOAD_DIR, fname)
            with open(path, "wb") as fh:
                fh.write(blob)
            written_paths.append(path)
            db_rows.append((pid, mid, did, fname, "", time.time()))
            saved.append({"id": pid, "url": f"/uploads/{fname}", "caption": ""})
        with db() as c:
            c.executemany("""INSERT INTO photos(id, mini_id, datasheet_id, filename, caption, uploaded_at)
                             VALUES(?,?,?,?,?,?)""", db_rows)
    except Exception:
        for path in written_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        raise
    return jsonify({"ok": True, "photos": saved})


# ---------------------------------------------------------------- unit WIP notes
@app.route("/api/units/<did>/wip-notes", methods=["POST"])
def api_save_wip_notes(did):
    from db import db
    notes = str(request.get_json(force=True).get("notes", ""))[:8000]
    key = _canon_did(did)
    now = time.time()
    with db() as c:
        c.execute(
            "INSERT INTO unit_wip(datasheet_id, notes, updated_at) VALUES(?,?,?)"
            " ON CONFLICT(datasheet_id) DO UPDATE SET"
            " notes=excluded.notes, updated_at=excluded.updated_at",
            (key, notes, now),
        )
    return jsonify({"ok": True})


@app.route("/api/units/<did>/wip-photos", methods=["POST"])
def api_upload_wip_photos(did):
    from db import db
    key = _canon_did(did)
    saved = []
    db_rows = []
    written_paths = []
    files = request.files.getlist("photos")
    try:
        for f in files:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext == ".jpeg":
                ext = ".jpg"
            if ext not in ALLOWED:
                continue
            image, error = _read_image_upload(f, MAX_UPLOAD_BYTES)
            if error:
                continue
            blob, ext = image
            pid = uuid.uuid4().hex
            fname = f"{pid}{ext}"
            path = os.path.join(UPLOAD_DIR, fname)
            with open(path, "wb") as fh:
                fh.write(blob)
            written_paths.append(path)
            db_rows.append((pid, key, fname, "", time.time()))
            saved.append({"id": pid, "url": f"/uploads/{fname}", "caption": ""})
        with db() as c:
            c.executemany(
                "INSERT INTO unit_wip_photos(id, datasheet_id, filename, caption, uploaded_at)"
                " VALUES(?,?,?,?,?)", db_rows)
    except Exception:
        for path in written_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        raise
    return jsonify({"ok": True, "photos": saved})


@app.route("/api/wip-photos/<pid>", methods=["DELETE"])
def api_delete_wip_photo(pid):
    from db import db
    with db() as c:
        row = c.execute("SELECT filename FROM unit_wip_photos WHERE id=?", (pid,)).fetchone()
        if not row:
            abort(404)
        c.execute("DELETE FROM unit_wip_photos WHERE id=?", (pid,))
    try:
        os.remove(os.path.join(UPLOAD_DIR, row["filename"]))
    except OSError:
        pass
    return jsonify({"ok": True})


# ---------------------------------------------------------------- reference image
@app.route("/api/units/<did>/image")
def api_unit_image(did):
    d = store.ds_by_id.get(did)
    if not d:
        abort(404)
    p = _ref_path(did)
    if p:
        resp = send_file(p)
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    p = catalogue_image_for_datasheet(did)
    if p:
        resp = send_file(p)
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    faction_name = store.faction_by_id.get(d["faction_id"], {}).get("name", "")
    svg = ft.placeholder_svg(faction_name, d["name"], did)
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------- box set images
@app.route("/api/box-sets/<path:box_id>/image")
def api_box_image(box_id):
    from box_sets import box_set_by_id
    p = _box_ref_path(box_id)
    if p:
        resp = send_file(p)
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    box = box_set_by_id(box_id)
    name = (box or {}).get("name", box_id)
    initial = name[0].upper() if name else "?"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
        f'<rect width="200" height="200" fill="#16151b"/>'
        f'<rect x="1" y="1" width="198" height="198" fill="none" stroke="#c79a3a" stroke-width="1" opacity="0.2"/>'
        f'<text x="100" y="108" text-anchor="middle" dominant-baseline="middle" '
        f'font-family="Georgia,serif" font-size="72" fill="#c79a3a" opacity="0.25">{initial}</text>'
        f'<text x="100" y="168" text-anchor="middle" font-family="sans-serif" font-size="9" '
        f'fill="#9c9686" letter-spacing="3" opacity="0.5">NO IMAGE</text>'
        f'</svg>'
    )
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/box-sets/<path:box_id>/reference", methods=["POST"])
def api_set_box_reference(box_id):
    from box_sets import box_set_by_id
    if not box_set_by_id(box_id):
        abort(404)
    os.makedirs(BOX_IMAGE_DIR, exist_ok=True)
    slug = re.sub(r"[^a-z0-9_-]+", "_", box_id.lower()).strip("_")

    f = request.files.get("file")
    if f and f.filename:
        image, error = _read_image_upload(f, MAX_REF_BYTES)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        blob, ext = image
        _clear_box_ref(box_id)
        with open(os.path.join(BOX_IMAGE_DIR, slug + ext), "wb") as fh:
            fh.write(blob)
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "Paste an image address, or choose a file."}), 400
    if not _safe_image_url(url):
        return jsonify({"ok": False, "error": "That is not a valid public image link."}), 400
    try:
        with _open_public_url(url, timeout=20) as resp:
            blob = resp.read(MAX_REF_BYTES + 1)
    except Exception:
        return jsonify({"ok": False, "error": "Could not download that image. On the picture itself, "
                        "use right-click → 'Copy image address', then paste the link."}), 400
    if len(blob) > MAX_REF_BYTES:
        return jsonify({"ok": False, "error": "That image is too large (over 12 MB)."}), 400
    ext = _image_ext_from_bytes(blob)
    if not ext:
        return jsonify({"ok": False, "error": "That link did not point to an image file."}), 400
    _clear_box_ref(box_id)
    with open(os.path.join(BOX_IMAGE_DIR, slug + ext), "wb") as fh:
        fh.write(blob)
    return jsonify({"ok": True})


@app.route("/api/box-sets/<path:box_id>/reference", methods=["DELETE"])
def api_clear_box_reference(box_id):
    _clear_box_ref(box_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------- photos
@app.route("/api/photos/<pid>", methods=["DELETE"])
def api_delete_photo(pid):
    from db import db
    with db() as c:
        row = c.execute("SELECT filename FROM photos WHERE id=?", (pid,)).fetchone()
        if not row:
            abort(404)
        c.execute("DELETE FROM photos WHERE id=?", (pid,))
    try:
        os.remove(os.path.join(UPLOAD_DIR, row["filename"]))
    except OSError:
        pass
    return jsonify({"ok": True})


@app.route("/api/photos/<pid>/caption", methods=["POST"])
def api_caption(pid):
    from db import db
    caption = str(request.get_json(force=True).get("caption", ""))[:300]
    with db() as c:
        cur = c.execute("UPDATE photos SET caption=? WHERE id=?", (caption, pid))
        if cur.rowcount == 0:
            abort(404)
    return jsonify({"ok": True})


@app.route("/uploads/<path:fname>")
def serve_upload(fname):
    return send_from_directory(UPLOAD_DIR, fname)


# ---------------------------------------------------------------- army api
@app.route("/api/armies")
def api_list_armies():
    from db import db
    with db() as c:
        rows = c.execute("SELECT * FROM army_lists ORDER BY created_at").fetchall()
        out = []
        for r in rows:
            units = c.execute(
                "SELECT squad_size, datasheet_id, enhancement_id FROM army_units WHERE army_list_id=?",
                (r["id"],)).fetchall()
            total_pts = sum(
                _points_for(u["datasheet_id"], u["squad_size"]) +
                _enhancement_cost(u["enhancement_id"], r["detachment_id"] or "")
                for u in units)
            fac = store.faction_by_id.get(r["faction_id"], {})
            primary, accent, _ = ft.theme_for(fac.get("name", ""))
            dt = store.detachment_by_id.get(r["detachment_id"] or "", {})
            out.append({
                "id": r["id"],
                "name": r["name"],
                "faction_id": r["faction_id"],
                "faction_name": fac.get("name", r["faction_id"]),
                "icon_url": _faction_icon_url(r["faction_id"], fac.get("name", "")),
                "detachment_id": r["detachment_id"] or "",
                "detachment_name": dt.get("name", ""),
                "points_limit": r["points_limit"],
                "total_points": total_pts,
                "unit_count": len(units),
                "primary": primary,
                "accent": accent,
            })
    return jsonify(out)


@app.route("/api/armies", methods=["POST"])
def api_create_army():
    from db import db
    data = request.get_json(force=True)
    name = str(data.get("name", "New Army"))[:120].strip() or "New Army"
    fid = str(data.get("faction_id", ""))
    if fid not in store.faction_by_id:
        return jsonify({"ok": False, "error": "Unknown faction"}), 400
    dtid = str(data.get("detachment_id", ""))
    if not _valid_detachment_for_faction(fid, dtid):
        return jsonify({"ok": False, "error": "Detachment does not belong to that faction"}), 400
    pts_limit = _as_int(data.get("points_limit"), 2000, minimum=0)
    notes = str(data.get("notes", ""))[:2000]
    aid = uuid.uuid4().hex
    with db() as c:
        c.execute("""INSERT INTO army_lists(id, name, faction_id, detachment_id, points_limit, notes, created_at)
                     VALUES(?,?,?,?,?,?,?)""", (aid, name, fid, dtid, pts_limit, notes, time.time()))
    return jsonify({"ok": True, "id": aid})


@app.route("/api/armies/<aid>")
def api_get_army(aid):
    from db import db
    with db() as c:
        row = c.execute("SELECT * FROM army_lists WHERE id=?", (aid,)).fetchone()
        if not row:
            abort(404)
        units_rows = c.execute(
            "SELECT * FROM army_units WHERE army_list_id=? ORDER BY sort_order, rowid",
            (aid,)).fetchall()
        units = [_army_unit_row(c, u) for u in units_rows]
    total_pts = sum(u["points"] + (u["enhancement_cost"] or 0) for u in units)
    fac = store.faction_by_id.get(row["faction_id"], {})
    primary, accent, _ = ft.theme_for(fac.get("name", ""))
    dt = store.detachment_by_id.get(row["detachment_id"] or "", {})
    return jsonify({
        "id": row["id"],
        "name": row["name"],
        "faction_id": row["faction_id"],
        "faction_name": fac.get("name", row["faction_id"]),
        "icon_url": _faction_icon_url(row["faction_id"], fac.get("name", "")),
        "detachment_id": row["detachment_id"] or "",
        "detachment_name": dt.get("name", ""),
        "points_limit": row["points_limit"],
        "total_points": total_pts,
        "notes": row["notes"] or "",
        "units": units,
        "primary": primary,
        "accent": accent,
    })


@app.route("/api/armies/<aid>", methods=["POST"])
def api_update_army(aid):
    from db import db
    with db() as c:
        row = c.execute("SELECT * FROM army_lists WHERE id=?", (aid,)).fetchone()
        if not row:
            abort(404)
        data = request.get_json(force=True)
        name = str(data.get("name", row["name"]))[:120].strip() or row["name"]
        dtid = str(data.get("detachment_id", row["detachment_id"] or ""))
        if not _valid_detachment_for_faction(row["faction_id"], dtid):
            return jsonify({"ok": False, "error": "Detachment does not belong to this army's faction"}), 400
        pts_limit = _as_int(data.get("points_limit", row["points_limit"]), row["points_limit"], minimum=0)
        notes = str(data.get("notes", row["notes"] or ""))[:2000]
        c.execute("UPDATE army_lists SET name=?, detachment_id=?, points_limit=?, notes=? WHERE id=?",
                  (name, dtid, pts_limit, notes, aid))
        if dtid != (row["detachment_id"] or ""):
            c.execute("UPDATE army_units SET enhancement_id='' WHERE army_list_id=?", (aid,))
    return jsonify({"ok": True})


@app.route("/api/armies/<aid>", methods=["DELETE"])
def api_delete_army(aid):
    from db import db
    with db() as c:
        if not _table_exists(c, "army_lists") or not c.execute(
                "SELECT id FROM army_lists WHERE id=?", (aid,)).fetchone():
            abort(404)
        c.execute("DELETE FROM army_units WHERE army_list_id=?", (aid,))
        c.execute("DELETE FROM army_lists WHERE id=?", (aid,))
    return jsonify({"ok": True})


@app.route("/api/armies/<aid>/units", methods=["POST"])
def api_add_army_unit(aid):
    from db import db
    with db() as c:
        army = c.execute("SELECT * FROM army_lists WHERE id=?", (aid,)).fetchone()
        if not army:
            abort(404)
    data = request.get_json(force=True)
    did = str(data.get("datasheet_id", ""))
    if did not in store.ds_by_id:
        return jsonify({"ok": False, "error": "Unknown datasheet"}), 400
    did = store.ds_by_id[did]["id"]  # Normalize to canonical Wahapedia id
    if not _datasheet_in_faction(did, army["faction_id"]):
        return jsonify({"ok": False, "error": "Unit does not belong to this army's faction"}), 400
    comp_range = _parse_comp_range(store.composition.get(did, []))
    default_size = comp_range["min"] if comp_range else 1
    squad_size = _normalise_squad_size(did, data.get("squad_size", default_size), default_size)
    auid = uuid.uuid4().hex
    with db() as c:
        max_order = c.execute(
            "SELECT COALESCE(MAX(sort_order),0) m FROM army_units WHERE army_list_id=?",
            (aid,)).fetchone()["m"]
        c.execute("""INSERT INTO army_units(id, army_list_id, datasheet_id, squad_size, assigned_count,
                     enhancement_id, notes, sort_order) VALUES(?,?,?,?,?,?,?,?)""",
                  (auid, aid, did, squad_size, 0, "", "", max_order + 1))
        row = c.execute("SELECT * FROM army_units WHERE id=?", (auid,)).fetchone()
        unit_data = _army_unit_row(c, row)
    return jsonify({"ok": True, "unit": unit_data})


@app.route("/api/army-units/<auid>", methods=["POST"])
def api_update_army_unit(auid):
    from db import db
    with db() as c:
        row = c.execute("SELECT * FROM army_units WHERE id=?", (auid,)).fetchone()
        if not row:
            abort(404)
        data = request.get_json(force=True)
        did = row["datasheet_id"]
        army = c.execute("SELECT * FROM army_lists WHERE id=?", (row["army_list_id"],)).fetchone()
        if not army:
            abort(404)
        # Normalize to the canonical Wahapedia datasheet id
        canonical_did = store.ds_by_id.get(did, {}).get("id") or did
        if canonical_did != did:
            c.execute("UPDATE army_units SET datasheet_id=? WHERE id=?", (canonical_did, auid))
            did = canonical_did

        squad_size = _normalise_squad_size(
            did, data.get("squad_size", row["squad_size"]), row["squad_size"])
        enhancement_id = str(data.get("enhancement_id", row["enhancement_id"] or ""))[:64]
        if enhancement_id and not _enhancement_for(enhancement_id, army["detachment_id"] or ""):
            return jsonify({"ok": False, "error": "Enhancement does not belong to this army's detachment"}), 400
        notes = str(data.get("notes", row["notes"] or ""))[:2000]

        owned = c.execute(
            "SELECT COUNT(*) cnt FROM minis WHERE unit_bsdata_id=?", (did,)).fetchone()["cnt"]
        other_assigned = c.execute(
            "SELECT COALESCE(SUM(assigned_count),0) tot FROM army_units WHERE datasheet_id=? AND id!=?",
            (did, auid)).fetchone()["tot"]
        max_assignable = min(squad_size, max(0, owned - other_assigned))
        requested_assigned = data["assigned_count"] if "assigned_count" in data else row["assigned_count"]
        assigned = max(0, min(_as_int(requested_assigned, 0), max_assignable))

        c.execute("""UPDATE army_units SET squad_size=?, assigned_count=?, enhancement_id=?, notes=?
                     WHERE id=?""", (squad_size, assigned, enhancement_id, notes, auid))
        updated_row = c.execute("SELECT * FROM army_units WHERE id=?", (auid,)).fetchone()
        unit_data = _army_unit_row(c, updated_row)
    return jsonify({"ok": True, "unit": unit_data})


@app.route("/api/army-units/<auid>", methods=["DELETE"])
def api_delete_army_unit(auid):
    from db import db
    with db() as c:
        if not c.execute("SELECT id FROM army_units WHERE id=?", (auid,)).fetchone():
            abort(404)
        c.execute("DELETE FROM army_units WHERE id=?", (auid,))
    return jsonify({"ok": True})


# ---------------------------------------------------------------- purchases api
@app.route("/api/box-sets")
def api_box_sets():
    return jsonify(_box_set_payloads(box_sets()))


@app.route("/api/editions")
def api_editions():
    """Hand-curated edition timeline (editions_timeline.json), sorted by edition."""
    from editions import editions_document
    return jsonify(editions_document())


@app.route("/api/model-catalogue")
def api_model_catalogue():
    return jsonify(catalogue_payload())


@app.route("/api/model-catalogue/faction-cards")
def api_model_catalogue_faction_cards():
    """One card per canonical faction label, themed, with model count, year range
    and a server-resolved photographic image URL. Excludes Test Faction."""
    from catalogue_review import faction_cards
    return jsonify({"cards": faction_cards()})


@app.route("/api/model-catalogue", methods=["POST"])
def api_add_model():
    data = request.get_json(force=True)
    record, error = add_manual_model(data)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "record": record}), 201


@app.route("/api/model-catalogue/<catalogue_model_id>", methods=["GET"])
def api_get_catalogue_model(catalogue_model_id):
    from catalogue_review import catalogue_payload
    cat = catalogue_payload()
    item = next((i for i in cat.get("items", []) if i["id"] == catalogue_model_id), None)
    if not item:
        abort(404)
    return jsonify({"item": item, "factions": cat.get("factions", [])})


@app.route("/api/model-catalogue/<catalogue_model_id>", methods=["PATCH"])
def api_patch_catalogue_model(catalogue_model_id):
    from catalogue_review import save_field_overrides, catalogue_payload
    cat = catalogue_payload()
    if not any(i["id"] == catalogue_model_id for i in cat.get("items", [])):
        abort(404)
    data = request.get_json(force=True)
    overrides = {}
    if "name" in data:
        name = str(data["name"]).strip()[:300]
        if not name:
            return jsonify({"ok": False, "error": "Name cannot be empty."}), 400
        overrides["name"] = name
    if "release_date" in data:
        rd = str(data["release_date"]).strip()
        if rd and not re.match(r'^\d{4}(-\d{2})?$', rd):
            return jsonify({"ok": False, "error": "Release date must be YYYY or YYYY-MM."}), 400
        overrides["release_date"] = rd
        if rd:
            try:
                overrides["release_year"] = int(rd[:4])
            except ValueError:
                pass
    if "material" in data:
        overrides["material"] = str(data["material"]).strip()[:50]
    if "status" in data:
        status = str(data["status"]).strip()
        if status not in ("current_or_unknown", "discontinued"):
            return jsonify({"ok": False, "error": "Invalid status value."}), 400
        overrides["status"] = status
    if "note" in data:
        overrides["note"] = str(data["note"]).strip()[:500]
    if "flags" in data:
        raw = data["flags"]
        if isinstance(raw, list):
            overrides["flags"] = [str(f).strip()[:50] for f in raw if str(f).strip()][:20]
        else:
            overrides["flags"] = []
    if "faction_id" in data:
        fid = str(data["faction_id"]).strip()
        overrides["faction_id"] = fid
        overrides["faction_label"] = store.faction_by_id.get(fid, {}).get("name", fid) if fid else ""
    if "faction_label" in data:
        # Direct canonical-label edit (History view). Re-files a model under the
        # right card without touching faction_id. Sub-factions like Blood Angels
        # share one Wahapedia faction code, so the label is the meaningful
        # grouping key. An
        # explicit faction_label wins over one derived from faction_id above.
        from catalogue_review import canonical_faction_label
        overrides["faction_label"] = canonical_faction_label(str(data["faction_label"]).strip())
    _, error = save_field_overrides(catalogue_model_id, overrides)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True})


@app.route("/api/model-catalogue/<catalogue_model_id>", methods=["DELETE"])
def api_delete_catalogue_model(catalogue_model_id):
    ok, error = delete_manual_model(catalogue_model_id)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True}), 200


@app.route("/api/model-catalogue/<catalogue_model_id>/duplicate", methods=["POST"])
def api_duplicate_catalogue_model(catalogue_model_id):
    from catalogue_review import duplicate_manual_model, catalogue_payload
    data = request.get_json(force=True)
    new_name = str(data.get("name") or "").strip()
    record, error = duplicate_manual_model(catalogue_model_id, new_name)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    payload = catalogue_payload()
    new_item = next((i for i in payload.get("items", []) if i["id"] == record["id"]), record)
    return jsonify({"ok": True, "record": new_item}), 201


@app.route("/api/model-catalogue/<catalogue_model_id>/image")
def api_model_catalogue_image(catalogue_model_id):
    path = catalogue_image_path(catalogue_model_id)
    if not path:
        abort(404)
    resp = send_file(path)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/api/model-catalogue/<catalogue_model_id>/image", methods=["POST"])
def api_set_model_catalogue_image(catalogue_model_id):
    f = request.files.get("file")
    if f and f.filename:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext == ".jpeg":
            ext = ".jpg"
        if ext not in ALLOWED:
            return jsonify({"ok": False, "error": "Unsupported image type."}), 400
        image, error = _read_image_upload(f, MAX_REF_BYTES)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        blob, ext = image
        _, err = save_catalogue_model_image(catalogue_model_id, blob, ext)
        if err:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True,
                        "image_url": f"/api/model-catalogue/{catalogue_model_id}/image"})

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "Paste an image address, or choose a file."}), 400
    if not _safe_image_url(url):
        return jsonify({"ok": False, "error": "That is not a valid public image link."}), 400
    try:
        with _open_public_url(url, timeout=20) as resp:
            blob = resp.read(MAX_REF_BYTES + 1)
    except Exception:
        return jsonify({"ok": False, "error": "Could not download that image. "
                        "On the picture, use right-click then 'Copy image address'."}), 400
    if len(blob) > MAX_REF_BYTES:
        return jsonify({"ok": False, "error": "That image is too large (over 12 MB)."}), 400
    ext = _image_ext_from_bytes(blob)
    if not ext:
        return jsonify({"ok": False, "error": "That link did not point to an image file. "
                        "Try 'Copy image address' on the picture itself."}), 400
    _, err = save_catalogue_model_image(catalogue_model_id, blob, ext)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True,
                    "image_url": f"/api/model-catalogue/{catalogue_model_id}/image"})


@app.route("/api/model-catalogue/<catalogue_model_id>/image", methods=["DELETE"])
def api_clear_model_catalogue_image(catalogue_model_id):
    clear_catalogue_model_image(catalogue_model_id)
    return jsonify({"ok": True})


@app.route("/api/catalogue-review/<catalogue_model_id>/resolution", methods=["POST"])
def api_catalogue_review_resolution(catalogue_model_id):
    data = request.get_json(force=True)
    resolution, error = save_resolution(catalogue_model_id, data)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "resolution": resolution})


def _catalogue_display_label(item):
    name = item.get("name") or item.get("id", "")
    year = item.get("release_year")
    return f"{name} ({year} release)" if year else name


@app.route("/api/model-catalogue/search")
def api_search_model_catalogue():
    from catalogue_review import canonical_faction_label
    fid = request.args.get("faction_id", "")
    # Optional canonical-label scope used by the History view's in-card search so a
    # Blood Angels search returns only Blood Angels, not every Space Marine (they
    # share one faction_id). The faction_id path below is untouched.
    faction_label = canonical_faction_label((request.args.get("faction_label", "") or "").strip())
    q = (request.args.get("q", "") or "").strip().lower()
    if fid and fid not in store.faction_by_id:
        abort(404)
    if len(q) < 2:
        return jsonify([])

    results = []
    for item in catalogue_payload().get("items", []):
        links = item.get("datasheet_links", [])
        if not links:
            continue
        if faction_label and item.get("faction_label", "") != faction_label:
            continue
        army_ids = set(item.get("army_ids") or [])
        if fid and fid not in army_ids and item.get("faction_id") != fid:
            continue
        searchable = " ".join([
            item.get("name", ""),
            item.get("faction_label", ""),
            item.get("release_date", ""),
            item.get("note", ""),
            " ".join(l.get("datasheet_name", "") for l in links),
        ]).lower()
        if q not in searchable:
            continue
        name_l = (item.get("name") or "").lower()
        score = 0
        if name_l == q:
            score = 100
        elif name_l.startswith(q):
            score = 90
        elif q in name_l:
            score = 80
        else:
            score = 60
        results.append((score, {
            "id": item["id"],
            "catalogue_model_id": item["id"],
            "name": item.get("name", ""),
            "display_label": _catalogue_display_label(item),
            "catalogue_label": _catalogue_display_label(item),
            "faction_label": item.get("faction_label", ""),
            "faction_id": item.get("faction_id", ""),
            "army_ids": item.get("army_ids", []),
            "release_date": item.get("release_date", ""),
            "release_year": item.get("release_year"),
            "material": item.get("material", ""),
            "status": item.get("status", ""),
            "note": item.get("note", ""),
            "datasheet_links": links,
        }))

    results.sort(key=lambda r: (
        -r[0],
        -(r[1].get("release_year") or 0),
        r[1].get("name", ""),
        r[1].get("id", ""),
    ))
    return jsonify([r[1] for r in results[:50]])


@app.route("/api/units/search")
def api_search_units():
    fid = request.args.get("faction_id", "")
    q = (request.args.get("q", "") or "").strip().lower()
    expand_catalogue = (request.args.get("catalogue", "") or "").lower() in {"1", "true", "yes"}
    if fid and fid not in store.faction_by_id:
        return jsonify([])
    sheets = _unit_search_pool(fid)
    if fid:
        for u in sheets:
            u["faction_id"] = fid
    if q:
        sheets = [u for u in sheets if q in u["name"].lower()]
    if expand_catalogue:
        from catalogue_review import catalogue_models_for_datasheet
        expanded = []
        for u in sheets:
            models = catalogue_models_for_datasheet(u["id"])
            if not models:
                expanded.append({**u, "catalogue_model_id": None, "catalogue_label": ""})
                continue
            models.sort(key=lambda m: (m.get("release_year") or 0, m.get("name", "")), reverse=True)
            for model in models:
                year = model.get("release_year")
                model_name = model.get("name") or u["name"]
                if year:
                    label = f"{u['name']} ({year} release)" if model_name == u["name"] else f"{model_name} ({year})"
                else:
                    label = model_name if model_name != u["name"] else ""
                expanded.append({
                    **u,
                    "catalogue_model_id": model["id"],
                    "catalogue_model": model,
                    "catalogue_label": label,
                })
        return jsonify(expanded[:50])
    return jsonify(sheets[:50])


@app.route("/api/box-sets/parse", methods=["POST"])
def api_parse_box_set():
    data = request.get_json(force=True)
    fid = str(data.get("faction_id", ""))
    if fid and fid not in store.faction_by_id:
        return jsonify({"ok": False, "error": "Unknown faction"}), 400
    parsed = parse_box_text(str(data.get("text", "")), fid)
    parsed["ok"] = True
    return jsonify(parsed)


@app.route("/api/box-sets", methods=["POST"])
def api_create_box_set():
    from db import db
    data = request.get_json(force=True)
    box, error = _clean_box_payload(data)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    original_id = box["id"]
    existing = box_set_by_id(box["id"])
    if existing:
        box["id"] = f"{box['id']}-{uuid.uuid4().hex[:6]}"
    with db() as c:
        _save_custom_box(c, box)
    return jsonify({"ok": True, "id": box["id"], "renamed_from": original_id if existing else ""})


@app.route("/api/box-sets/<box_id>", methods=["POST"])
def api_update_box_set(box_id):
    from db import db
    if not box_set_by_id(box_id):
        abort(404)
    data = request.get_json(force=True)
    box, error = _clean_box_payload(data, existing_id=box_id)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    box["status"] = box["status"] if box["status"] != "seeded" else "manual"
    with db() as c:
        _save_custom_box(c, box)
    return jsonify({"ok": True, "id": box_id})


@app.route("/api/box-sets/<box_id>", methods=["DELETE"])
def api_delete_box_set(box_id):
    from db import db
    box = box_set_by_id(box_id)
    if not box:
        abort(404)
    if box["source"] != "local":
        return jsonify({"ok": False, "error": "Seeded box sets can be edited but not deleted."}), 400
    with db() as c:
        if c.execute("SELECT id FROM purchases WHERE box_set_id=? LIMIT 1", (box_id,)).fetchone():
            return jsonify({"ok": False, "error": "Remove purchases for this box before deleting it."}), 400
        c.execute("DELETE FROM custom_box_set_contents WHERE box_set_id=?", (box_id,))
        c.execute("DELETE FROM custom_box_sets WHERE id=?", (box_id,))
    return jsonify({"ok": True})


def _purchases_data(c, boxes_by_id):
    rows = c.execute("SELECT * FROM purchases ORDER BY bought_at DESC").fetchall()
    purchases = [purchase_payload(r, boxes_by_id) for r in rows]
    info = bought_info(c, boxes_by_id)
    owned  = owned_totals()
    ul_map = compute_unlogged_map(info, owned)
    return {
        "purchases":     purchases,
        "bought_totals": info["totals"],
        "total_bought":  dedup_group_total(info, info["totals"]),
        "total_unlogged": dedup_group_total(info, ul_map),
    }, info, owned


@app.route("/api/purchases/page-data")
def api_purchases_page_data():
    boxes = box_sets()
    boxes_by_id = {b["id"]: b for b in boxes}
    with db() as c:
        data, info, owned = _purchases_data(c, boxes_by_id)
        data["summary"] = _summary_payload(c, info, owned)
    data["box_options"] = [{"id": b["id"], "name": b["name"]} for b in boxes]
    data["factions"] = _factions_payload(info, owned)
    return jsonify(data)


@app.route("/api/purchases")
def api_purchases():
    boxes_by_id = {b["id"]: b for b in box_sets()}
    with db() as c:
        data, _, _ = _purchases_data(c, boxes_by_id)
    return jsonify(data)


@app.route("/api/purchases", methods=["POST"])
def api_create_purchase():
    from db import db
    data = request.get_json(force=True)
    box_set_id = str(data.get("box_set_id", ""))
    box = box_set_by_id(box_set_id)
    if not box:
        return jsonify({"ok": False, "error": "Unknown box set"}), 400
    quantity = min(200, _as_int(data.get("quantity"), 1, minimum=1))
    notes = str(data.get("notes", ""))[:1000]
    pid = uuid.uuid4().hex
    with db() as c:
        c.execute("""INSERT INTO purchases(id, box_set_id, quantity, notes, bought_at)
                     VALUES(?,?,?,?,?)""", (pid, box_set_id, quantity, notes, time.time()))
    _minis_from_box(box, quantity)
    return jsonify({"ok": True, "id": pid})


@app.route("/api/purchases/<pid>", methods=["DELETE"])
def api_delete_purchase(pid):
    from db import db
    with db() as c:
        cur = c.execute("DELETE FROM purchases WHERE id=?", (pid,))
        if cur.rowcount == 0:
            abort(404)
    return jsonify({"ok": True})


# ---------------------------------------------------------------- collection page
@app.route("/collection")
def collection_page():
    return render_template(
        "collection.html",
        active_page="collection",
        breadcrumb=[{"label": "Paint Progress"}],
    )


_VALID_STAGES = ['unbuilt', 'assembled', 'primed', 'base_coated', 'washed',
                 'highlighted', 'finished', 'display']


def _multikit_options_for_group(gkey):
    if not gkey:
        return []
    try:
        box_id, mg_name = gkey.split("::", 1)
    except ValueError:
        return []
    box = box_set_by_id(box_id)
    if not box:
        return []

    options = []
    for item in box["contents"]:
        if item.get("multikit_group") != mg_name:
            continue
        did = item["datasheet_id"]
        ds = store.ds_by_id.get(did, {})
        fid = ds.get("faction_id") or item.get("faction_id", "")
        faction = store.faction_by_id.get(fid, {})
        options.append({
            "datasheet_id": did,
            "name": item.get("name") or ds.get("name", did),
            "faction_id": fid,
            "faction_name": faction.get("name", fid),
            "catalogue_model_id": item.get("catalogue_model_id"),
            "catalogue_label": item.get("catalogue_label", ""),
        })
    return options


@app.route("/api/collection")
def api_collection():
    faction_id = request.args.get("faction_id", "").strip()
    datasheet_id = request.args.get("datasheet_id", "").strip()
    stage_filter = request.args.get("stage", "").strip()
    search = request.args.get("search", "").strip().lower()

    if faction_id and faction_id not in store.faction_by_id:
        abort(404)

    cat_fac_index = catalogue_faction_datasheet_index() if (faction_id or datasheet_id) else {}

    with db() as c:
        rows = c.execute(
            "SELECT * FROM minis ORDER BY datasheet_id, created_at"
        ).fetchall()
        mini_ids = [r["id"] for r in rows]
        if mini_ids:
            placeholders = ",".join("?" * len(mini_ids))
            photo_rows = c.execute(
                f"SELECT mini_id, id, filename, caption FROM photos"
                f" WHERE mini_id IN ({placeholders}) ORDER BY uploaded_at",
                mini_ids,
            ).fetchall()
        else:
            photo_rows = []

    photos_by_mid = {}
    for p in photo_rows:
        photos_by_mid.setdefault(p["mini_id"], []).append({
            "id": p["id"],
            "url": f"/uploads/{p['filename']}",
            "caption": p["caption"],
        })

    result = []
    for r in rows:
        did = r["unit_bsdata_id"]
        ds = store.ds_by_id.get(did) if did else None
        if not ds:
            continue
        fid = ds["faction_id"]

        mini_stage = r["stage"] if "stage" in r.keys() else "unbuilt"
        multikit_group = r["multikit_group"] if "multikit_group" in r.keys() else None
        multikit_options = _multikit_options_for_group(multikit_group) if mini_stage == "unbuilt" else []
        option_by_did = {o["datasheet_id"]: o for o in multikit_options}

        display_did = did
        display_ds = ds
        display_fid = fid
        display_cid = r["catalogue_model_id"] if "catalogue_model_id" in r.keys() else None
        display_label = r["label"] or ""

        if faction_id and fid != faction_id and not any(o["faction_id"] == faction_id for o in multikit_options):
            cid = r["catalogue_model_id"] if "catalogue_model_id" in r.keys() else None
            alt_did = cat_fac_index.get(cid or "", {}).get(faction_id) if cid else None
            alt_ds = store.ds_by_id.get(alt_did) if alt_did else None
            if not alt_ds:
                continue
            display_did = alt_did
            display_ds = alt_ds
            display_fid = faction_id

        if datasheet_id and did != datasheet_id and datasheet_id not in option_by_did:
            cid = r["catalogue_model_id"] if "catalogue_model_id" in r.keys() else None
            if not (cid and datasheet_id in cat_fac_index.get(cid, {}).values()):
                continue
            alt_ds = store.ds_by_id.get(datasheet_id)
            if alt_ds:
                display_did = datasheet_id
                display_ds = alt_ds
                display_fid = alt_ds["faction_id"]
        elif datasheet_id and datasheet_id != did and datasheet_id in option_by_did:
            display_did = datasheet_id
            display_ds = store.ds_by_id.get(datasheet_id, ds)
            display_fid = display_ds.get("faction_id", option_by_did[datasheet_id]["faction_id"])
            # A multikit builds different units from the same box, each with its own
            # sculpt. Remap to the sibling unit's catalogue model so the mini page shows
            # the release the user actually owns, not every release linked to this unit.
            display_cid = option_by_did[datasheet_id].get("catalogue_model_id") or display_cid
            # Minis are stored under one member of the group with that member's
            # auto-generated label. When viewed as the sibling, swap in the sibling's
            # label (e.g. "Warp Talons (2025 release)") so the group reads as the unit
            # being viewed. A user's custom rename won't match and is left untouched.
            src_label = option_by_did.get(did, {}).get("catalogue_label", "")
            dst_label = option_by_did[datasheet_id].get("catalogue_label", "")
            if dst_label and display_label == src_label:
                display_label = dst_label

        if stage_filter and mini_stage != stage_filter:
            continue

        ds_name = display_ds.get("name", option_by_did.get(display_did, {}).get("name", ""))
        faction_name = store.faction_by_id.get(display_fid, {}).get("name", display_fid)
        label = display_label

        option_names = " ".join(o["name"] for o in multikit_options).lower()
        if search and search not in ds_name.lower() and search not in label.lower() and search not in option_names:
            continue

        try:
            wg = json.loads(r["wargear"] or "[]")
        except (ValueError, TypeError):
            wg = []

        result.append({
            "id": r["id"],
            "datasheet_id": display_did,
            "datasheet_name": ds_name,
            "faction_id": display_fid,
            "faction_name": faction_name,
            "label": label,
            "wargear": wg if isinstance(wg, list) else [],
            "notes": r["notes"] or "",
            "stage": mini_stage,
            "multikit_group": multikit_group,
            "multikit_options": multikit_options,
            "assigned_datasheet_id": did,
            "catalogue_model_id": display_cid,
            "created_at": r["created_at"],
            "photos": photos_by_mid.get(r["id"], []),
        })

    return jsonify(result)


@app.route("/api/unassigned-minis")
def api_unassigned_minis():
    """Safety net: minis whose unit_bsdata_id is missing or no longer resolves to a real
    datasheet. Such minis are invisible to every faction/unit view (owned_totals and the
    collection API are both keyed by datasheet), so surface them here grouped by sculpt +
    label so they can be filed under a unit. Normally returns []."""
    from catalogue_review import catalogue_payload
    cat_by_id = {i["id"]: i for i in catalogue_payload().get("items", [])}
    with db() as c:
        rows = c.execute("SELECT * FROM minis ORDER BY created_at").fetchall()

    groups = {}
    for r in rows:
        did = r["unit_bsdata_id"]
        if did and store.ds_by_id.get(did):
            continue  # properly assigned — skip
        cid   = r["catalogue_model_id"] if "catalogue_model_id" in r.keys() else None
        label = r["label"] or ""
        key   = f"{cid or ''}\x01{label}"
        g = groups.get(key)
        if not g:
            item = cat_by_id.get(cid) if cid else None
            if item:
                name = item.get("name") or label or "Unknown kit"
            else:
                name = label or (f"Kit {cid}" if cid else "Unknown kit")
            g = groups[key] = {
                "catalogue_model_id": cid,
                "name": name,
                "faction_id": (item or {}).get("faction_id", ""),
                "faction_label": (item or {}).get("faction_label", ""),
                "label": label,
                "image_url": f"/api/model-catalogue/{cid}/image" if (item and item.get("image")) else None,
                "mini_ids": [],
            }
        g["mini_ids"].append(r["id"])

    out = sorted(groups.values(), key=lambda g: (g["name"] or "").lower())
    for g in out:
        g["count"] = len(g["mini_ids"])
    return jsonify(out)


@app.route("/api/minis/assign-datasheet", methods=["POST"])
def api_assign_datasheet():
    """File a set of (typically unassigned) minis under a datasheet, stamping both
    datasheet_id and the canonical Wahapedia id so they show up under the right unit."""
    data = request.get_json(force=True)
    datasheet_id = str(data.get("datasheet_id", "")).strip()
    mini_ids = data.get("mini_ids", [])
    if not datasheet_id or not isinstance(mini_ids, list) or not mini_ids:
        return jsonify({"ok": False, "error": "datasheet_id and mini_ids are required"}), 400
    ds = store.ds_by_id.get(datasheet_id)
    if not ds:
        return jsonify({"ok": False, "error": "Unknown datasheet"}), 400
    unit_bsdata_id = ds["id"]
    mini_ids = [str(m) for m in mini_ids][:500]
    ph = ",".join("?" * len(mini_ids))
    with db() as c:
        c.execute(
            f"UPDATE minis SET datasheet_id=?, unit_bsdata_id=? WHERE id IN ({ph})",
            [datasheet_id, unit_bsdata_id, *mini_ids],
        )
        assigned = c.execute(
            f"SELECT COUNT(*) n FROM minis WHERE unit_bsdata_id=? AND id IN ({ph})",
            [unit_bsdata_id, *mini_ids]).fetchone()["n"]
    return jsonify({"ok": True, "assigned": assigned, "datasheet_id": unit_bsdata_id})


@app.route("/api/minis/<mid>/multikit-options")
def api_mini_multikit_options(mid):
    """Return the build options for an unresolved multikit mini."""
    with db() as c:
        row = c.execute("SELECT multikit_group FROM minis WHERE id=?", (mid,)).fetchone()
    if not row:
        abort(404)
    gkey = row["multikit_group"] if "multikit_group" in row.keys() else None
    if not gkey:
        return jsonify({"ok": True, "options": []})
    try:
        box_id, _ = gkey.split("::", 1)
    except ValueError:
        return jsonify({"ok": True, "options": []})
    if not box_set_by_id(box_id):
        return jsonify({"ok": False, "error": "Original box set not found."}), 404
    options = _multikit_options_for_group(gkey)
    return jsonify({"ok": True, "options": options})


@app.route("/api/minis/<mid>/stage", methods=["PATCH"])
def api_update_mini_stage(mid):
    with db() as c:
        row = c.execute("SELECT * FROM minis WHERE id=?", (mid,)).fetchone()
        if not row:
            abort(404)
        data = request.get_json(force=True)
        stage = str(data.get("stage", "")).strip()
        if stage not in _VALID_STAGES:
            return jsonify({"ok": False,
                            "error": f"Invalid stage. Must be one of: {', '.join(_VALID_STAGES)}"}), 400

        multikit_group = row["multikit_group"] if "multikit_group" in row.keys() else None
        new_datasheet_id = None
        new_catalogue_model_id = None
        new_label = None

        if multikit_group and stage != "unbuilt":
            new_datasheet_id = str(data.get("datasheet_id", "")).strip()
            if not new_datasheet_id:
                return jsonify({"ok": False, "requires_assignment": True,
                                "error": "Select which unit to build before advancing stage."}), 409
            # Validate the chosen DID belongs to the group
            try:
                box_id, mg_name = multikit_group.split("::", 1)
            except ValueError:
                box_id = mg_name = None
            valid_dids = set()
            chosen_item = None
            if box_id:
                box = box_set_by_id(box_id)
                if box:
                    for i in box["contents"]:
                        if i.get("multikit_group") != mg_name:
                            continue
                        valid_dids.add(i["datasheet_id"])
                        if i["datasheet_id"] == new_datasheet_id:
                            chosen_item = i
            if valid_dids and new_datasheet_id not in valid_dids:
                return jsonify({"ok": False, "error": "Invalid unit for this multikit group."}), 400
            # The pooled mini was created from the group's first kit option. Now that
            # the user has chosen which unit to build, repoint it at that unit's own
            # catalogue model and label so it no longer shows the wrong kit.
            if chosen_item:
                new_catalogue_model_id = chosen_item.get("catalogue_model_id")
                new_label = chosen_item.get("catalogue_label") or None

        finished = 1 if stage == "finished" else 0
        if new_datasheet_id:
            new_unit_bsdata_id = store.ds_by_id.get(new_datasheet_id, {}).get("id") or new_datasheet_id
            sets = "stage=?, finished=?, datasheet_id=?, unit_bsdata_id=?, multikit_group=NULL"
            params = [stage, finished, new_datasheet_id, new_unit_bsdata_id]
            if new_catalogue_model_id:
                sets += ", catalogue_model_id=?"
                params.append(new_catalogue_model_id)
            if new_label:
                sets += ", label=?"
                params.append(new_label)
            params.append(mid)
            c.execute(f"UPDATE minis SET {sets} WHERE id=?", params)
        else:
            c.execute("UPDATE minis SET stage=?, finished=? WHERE id=?", (stage, finished, mid))

    result = {"ok": True, "stage": stage}
    if new_datasheet_id:
        result["datasheet_id"] = new_datasheet_id
    return jsonify(result)


# ---------------------------------------------------------------- summary
@app.route("/api/collection/summary")
def api_summary():
    with db() as c:
        return jsonify(_summary_payload(c))


if __name__ == "__main__":
    print("\n  Warhammer 40,000 Collection Cataloguer")
    print("  Open http://127.0.0.1:5050 in your browser\n")
    app.run(debug=False, host='0.0.0.0', port=5050)
