"""Flask blueprint for The Arsenal."""
import json
import os
import uuid

from flask import (
    Blueprint, abort, flash, jsonify, redirect, render_template,
    request, send_from_directory, url_for,
)

import arsenal_store as store


arsenal_bp = Blueprint("arsenal", __name__, url_prefix="/arsenal")
ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def init_arsenal(app):
    store.init_arsenal_db()
    app.register_blueprint(arsenal_bp)


def _base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _arsenal_upload_dir():
    return store.upload_dir(_base_dir())


def _wants_json():
    return request.headers.get("x-requested-with") == "fetch" or (
        request.accept_mimetypes.best == "application/json"
    )


def _save_photo_file(file_storage):
    if not file_storage or not file_storage.filename:
        return None, "Choose a photo to upload."
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_PHOTO_EXTS:
        return None, "Upload a JPG, PNG, WebP or GIF photo."
    file_name = f"{uuid.uuid4().hex}{ext}"
    path = store.safe_photo_path(_arsenal_upload_dir(), file_name)
    if not path:
        return None, "Could not build a safe upload path."
    file_storage.save(path)
    return file_name, None


def _remove_photo_file(file_name):
    path = store.safe_photo_path(_arsenal_upload_dir(), file_name)
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _loadouts_breadcrumb(*items):
    return [{"label": "Weapon Loadouts", "href": url_for("arsenal.loadouts")}, *items]


@arsenal_bp.get("/")
def index():
    return redirect(url_for("arsenal.loadouts"))


@arsenal_bp.route("/weapon/new", methods=["GET", "POST"])
def weapon_new():
    if request.method == "POST":
        weapon, errors = store.create_weapon(request.form)
        if not errors:
            flash("Weapon added to the Arsenal.")
            return redirect(url_for("arsenal.weapon_detail", weapon_id=weapon["id"]))
        return render_template(
            "arsenal/weapon_form.html",
            active_page="arsenal_loadouts",
            breadcrumb=_loadouts_breadcrumb({"label": "New Weapon"}),
            mode="new",
            weapon={**request.form},
            errors=errors,
            factions=store.faction_options(),
            categories=store.CATEGORIES,
        ), 400
    return render_template(
        "arsenal/weapon_form.html",
        active_page="arsenal_loadouts",
        breadcrumb=_loadouts_breadcrumb({"label": "New Weapon"}),
        mode="new",
        weapon={"name": request.args.get("name", "").strip(), "category": "ranged"},
        errors={},
        factions=store.faction_options(),
        categories=store.CATEGORIES,
    )


@arsenal_bp.get("/weapon/<int:weapon_id>")
def weapon_detail(weapon_id):
    weapon = store.get_weapon(weapon_id)
    if not weapon:
        abort(404)
    return render_template(
        "arsenal/weapon_detail.html",
        active_page="arsenal_loadouts",
        breadcrumb=_loadouts_breadcrumb({"label": weapon["name"]}),
        weapon=weapon,
    )


@arsenal_bp.route("/weapon/<int:weapon_id>/edit", methods=["GET", "POST"])
def weapon_edit(weapon_id):
    weapon = store.get_weapon(weapon_id)
    if not weapon:
        abort(404)
    if request.method == "POST":
        updated, errors = store.update_weapon(weapon_id, request.form)
        if not errors:
            flash("Weapon updated.")
            return redirect(url_for("arsenal.weapon_detail", weapon_id=weapon_id))
        form_weapon = {**weapon, **request.form}
        return render_template(
            "arsenal/weapon_form.html",
            active_page="arsenal_loadouts",
            breadcrumb=_loadouts_breadcrumb(
                {"label": weapon["name"], "href": url_for("arsenal.weapon_detail", weapon_id=weapon_id)},
                {"label": "Edit"},
            ),
            mode="edit",
            weapon=form_weapon,
            errors=errors,
            factions=store.faction_options(),
            categories=store.CATEGORIES,
        ), 400
    return render_template(
        "arsenal/weapon_form.html",
        active_page="arsenal_loadouts",
        breadcrumb=_loadouts_breadcrumb(
            {"label": weapon["name"], "href": url_for("arsenal.weapon_detail", weapon_id=weapon_id)},
            {"label": "Edit"},
        ),
        mode="edit",
        weapon=weapon,
        errors={},
        factions=store.faction_options(),
        categories=store.CATEGORIES,
    )


@arsenal_bp.post("/weapon/<int:weapon_id>/delete")
def weapon_delete(weapon_id):
    file_names = store.delete_weapon(weapon_id)
    for file_name in file_names:
        _remove_photo_file(file_name)
    flash("Weapon removed from the Arsenal.")
    return redirect(url_for("arsenal.loadouts"))


@arsenal_bp.post("/weapon/<int:weapon_id>/photo")
def weapon_photo_upload(weapon_id):
    if not store.get_weapon(weapon_id):
        abort(404)
    file_name, error = _save_photo_file(request.files.get("photo"))
    if error:
        if _wants_json():
            return jsonify({"ok": False, "error": error}), 400
        flash(error)
        return redirect(url_for("arsenal.weapon_detail", weapon_id=weapon_id))
    photo = store.add_weapon_photo(
        weapon_id,
        file_name,
        caption=request.form.get("caption", ""),
        source=request.form.get("source", "user_photo") or "user_photo",
    )
    if _wants_json():
        photo["url"] = store.photo_url(photo["file_name"])
        return jsonify({"ok": True, "photo": photo, "weapon": store.get_weapon(weapon_id)})
    flash("Photo added.")
    return redirect(url_for("arsenal.weapon_detail", weapon_id=weapon_id))


@arsenal_bp.get("/photo/<path:file_name>")
def photo(file_name):
    path = store.safe_photo_path(_arsenal_upload_dir(), file_name)
    if not path or not os.path.exists(path):
        abort(404)
    return send_from_directory(_arsenal_upload_dir(), file_name)


@arsenal_bp.post("/weapon/<int:weapon_id>/photo/<int:photo_id>/primary")
def photo_primary(weapon_id, photo_id):
    if not store.set_primary_photo(weapon_id, photo_id):
        abort(404)
    if _wants_json():
        return jsonify({"ok": True, "weapon": store.get_weapon(weapon_id)})
    return redirect(url_for("arsenal.weapon_detail", weapon_id=weapon_id))


@arsenal_bp.post("/weapon/<int:weapon_id>/photo/<int:photo_id>/delete")
def photo_delete(weapon_id, photo_id):
    file_name = store.delete_photo(weapon_id, photo_id)
    if file_name is None:
        abort(404)
    _remove_photo_file(file_name)
    if _wants_json():
        return jsonify({"ok": True, "weapon": store.get_weapon(weapon_id)})
    flash("Photo removed.")
    return redirect(url_for("arsenal.weapon_detail", weapon_id=weapon_id))


@arsenal_bp.post("/sync")
def sync():
    counts = store.sync_datasheets()
    flash(
        f"Catalogue rebuilt from datasheets: {counts['weapons']} weapons, "
        f"{counts['links']} unit links, {counts['units']} units covered."
    )
    return redirect(request.referrer or url_for("arsenal.loadouts"))


@arsenal_bp.get("/loadouts")
def loadouts():
    return render_template(
        "arsenal/loadouts_index.html",
        active_page="arsenal_loadouts",
        breadcrumb=[{"label": "Weapon Loadouts"}],
        groups=store.loadouts_index(),
    )


@arsenal_bp.get("/loadouts/<datasheet_id>")
def unit_loadout(datasheet_id):
    data = store.unit_loadout(datasheet_id)
    if not data:
        abort(404)
    return render_template(
        "arsenal/unit_loadout.html",
        active_page="arsenal_loadouts",
        breadcrumb=_loadouts_breadcrumb({"label": data["datasheet"]["name"]}),
        data=data,
    )


@arsenal_bp.get("/api/weapon-card")
def api_weapon_card():
    weapon_id = request.args.get("id", type=int)
    name = request.args.get("name", "").strip()
    return jsonify(store.weapon_card_payload(name=name, weapon_id=weapon_id))


@arsenal_bp.get("/audit")
def audit():
    faction = request.args.get("faction", "").strip()
    problem = request.args.get("problem", "all").strip() or "all"
    q = request.args.get("q", "").strip()
    data = store.audit_data(faction_filter=faction, problem=problem, q=q)
    return render_template(
        "arsenal/audit.html",
        active_page="arsenal_audit",
        breadcrumb=_loadouts_breadcrumb({"label": "Audit"}),
        data=data,
        filters={"faction": faction, "problem": problem, "q": q},
        categories=store.CATEGORIES,
    )


@arsenal_bp.post("/audit/weapon/<int:weapon_id>")
def audit_weapon_save(weapon_id):
    payload = request.get_json(silent=True) or {}
    allowed = {"name", "category", "faction_id", "faction_name", "spotting_notes", "distinguishing"}
    payload = {key: value for key, value in payload.items() if key in allowed}
    weapon, errors = store.update_weapon(weapon_id, payload, partial=True)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    return jsonify({"ok": True, "weapon": weapon})


@arsenal_bp.app_context_processor
def arsenal_context():
    def arsenal_json(value):
        return json.dumps(value)
    return {"arsenal_json": arsenal_json}
