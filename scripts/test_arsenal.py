"""Small no-network harness for The Arsenal feature."""
import csv
from io import BytesIO
import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def bootstrap(tmpdir):
    import db as db_module
    db_module.DB_PATH = os.path.join(tmpdir, "collection.db")
    os.environ["ARSENAL_UPLOAD_DIR"] = os.path.join(tmpdir, "uploads")
    os.environ.pop("ANTHROPIC_API_KEY", None)
    import app as app_module
    return app_module


class FakeStore:
    def __init__(self):
        self.datasheets = [{
            "id": "T1",
            "name": "Harness Squad",
            "faction_id": "SM",
            "virtual_bool": False,
        }, {
            "id": "T2",
            "name": "Harness Veterans",
            "faction_id": "SM",
            "virtual_bool": False,
        }]
        self.faction_by_id = {"SM": {"name": "Space Marines"}}
        self.ds_by_id = {ds["id"]: ds for ds in self.datasheets}

    def unit_detail(self, did):
        if did == "T2":
            return {
                "id": did,
                "name": "Harness Veterans",
                "faction_id": "SM",
                "ranged": [{"name": "Storm Bolter"}],
                "melee": [],
                "options": [],
            }
        return {
            "id": did,
            "name": "Harness Squad",
            "faction_id": "SM",
            "loadout": "<b>Every model is equipped with:</b> boltgun; plasma gun.",
            "ranged": [
                {"name": "Boltgun"},
                {"name": "Plasma Gun - standard"},
                {"name": "Plasma Gun - supercharge"},
                {"name": "Mystery Pipe"},
                {"name": "Storm Bolter"},
            ],
            "melee": [{"name": "Chainsword"}],
            "options": [{
                "line": "1",
                "description": "This model can be equipped with 1 chainsword.",
            }],
        }


def post_image(client, url):
    return client.post(
        url,
        data={"photo": (BytesIO(b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"), "tiny.gif")},
        content_type="multipart/form-data",
    )


def write_override_csv(path):
    rows = [
        {
            "weapon_name": "Boltgun",
            "wiki_title": "Boltgun",
            "wiki_url": "https://warhammer40k.fandom.com/wiki/Boltgun",
            "confidence": "verified",
            "notes": "",
        },
        {
            "weapon_name": "Plasma Gun",
            "wiki_title": "Plasma Weapon",
            "wiki_url": "https://warhammer40k.fandom.com/wiki/Plasma_Weapon",
            "confidence": "base_fallback",
            "notes": "base page",
        },
        {
            "weapon_name": "Mystery Pipe",
            "wiki_title": "",
            "wiki_url": "https://example.com/ignored",
            "confidence": "no_match",
            "notes": "",
        },
        {
            "weapon_name": "Storm Bolter",
            "wiki_title": "",
            "wiki_url": "",
            "confidence": "skip",
            "notes": "no model weapon",
        },
        {
            "weapon_name": "Chainsword",
            "wiki_title": "",
            "wiki_url": "",
            "confidence": "needs_check",
            "notes": "",
        },
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["weapon_name", "wiki_title", "wiki_url", "confidence", "notes"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        app_module = bootstrap(tmpdir)
        import arsenal_store as store
        from scripts.import_wiki_overrides import import_wiki_overrides

        client = app_module.app.test_client()

        counts1 = store.sync_datasheets(FakeStore())
        counts2 = store.sync_datasheets(FakeStore())
        assert_true(counts1 == counts2, "datasheet generation is idempotent")
        assert_true(counts1["weapons"] == 5, "generator creates one distinct entry per collapsed weapon")
        assert_true(counts1["links"] == 7, "generator preserves raw profile links")

        weapons = store.all_weapon_rows()
        names = {w["name"] for w in weapons}
        assert_true(names == {"Boltgun", "Plasma Gun", "Mystery Pipe", "Storm Bolter", "Chainsword"}, "generated names match datasheet weapons")
        assert_true(store.weapon_by_exact_name("Plasma Gun - supercharge")["name"] == "Plasma Gun", "profile lookup resolves exactly after collapse")
        assert_true(store.weapon_card_payload(name="Plasma Gun - standard")["name"] == "Plasma Gun", "card lookup uses exact collapsed name")
        assert_true(store.weapon_by_exact_name("Hellforged Weapons") is None, "old archetype-only name is absent after rebuild")

        for path in [
            "/arsenal/weapon/new",
            "/arsenal/loadouts",
            "/arsenal/loadouts/000000882",
            "/arsenal/audit",
            "/arsenal/api/weapon-card?name=Boltgun",
            "/arsenal/api/weapon-card?name=Unknown%20Bit",
        ]:
            res = client.get(path)
            assert_true(res.status_code == 200, f"GET {path} returns 200")
        arsenal_root = client.get("/arsenal/")
        assert_true(arsenal_root.status_code == 302 and arsenal_root.headers["Location"].endswith("/arsenal/loadouts"), "arsenal root redirects to loadouts")
        assert_true(client.get("/arsenal/identify").status_code == 404, "identify page is gone")
        assert_true(client.get("/arsenal/api/weapon-card?name=Boltgun").json["found"], "weapon card known")
        assert_true(not client.get("/arsenal/api/weapon-card?name=Unknown%20Bit").json["found"], "weapon card unknown")

        weapon = store.weapon_by_exact_name("Boltgun")
        save = client.post(f"/arsenal/audit/weapon/{weapon['id']}", json={"spotting_notes": "Saved from audit."})
        assert_true(save.status_code == 200 and save.json["weapon"]["spotting_notes"] == "Saved from audit.", "audit save persists")
        upload = post_image(client, f"/arsenal/weapon/{weapon['id']}/photo")
        assert_true(upload.status_code == 302, "photo upload redirects")
        photo = store.get_weapon(weapon["id"])["photos"][0]
        assert_true(client.get(f"/arsenal/photo/{photo['file_name']}").status_code == 200, "photo serve")
        assert_true(client.get("/arsenal/photo/../bad.gif").status_code == 404, "photo traversal blocked")

        store.sync_datasheets(FakeStore())
        rebuilt = store.weapon_by_exact_name("Boltgun")
        rebuilt_full = store.get_weapon(rebuilt["id"])
        assert_true(rebuilt_full["spotting_notes"] == "Saved from audit.", "description survives rebuild")
        assert_true(rebuilt_full["photos"], "photo survives rebuild")

        storm = store.weapon_by_exact_name("Storm Bolter")
        with store.db() as c:
            unit_count = c.execute(
                "SELECT COUNT(DISTINCT datasheet_id) n FROM arsenal_weapon_datasheet WHERE weapon_id=?",
                (storm["id"],),
            ).fetchone()["n"]
        assert_true(unit_count == 2, "shared Storm Bolter entry links to every unit that fields it")

        before = rebuilt_full["category"]
        bad = client.post(f"/arsenal/audit/weapon/{rebuilt['id']}", json={"category": "bad"})
        assert_true(bad.status_code == 400 and "category" in bad.json["errors"], "audit invalid category returns error")
        assert_true(store.get_weapon(rebuilt["id"])["category"] == before, "invalid audit save changes nothing")

        override_csv = os.path.join(tmpdir, "manual_overrides.csv")
        write_override_csv(override_csv)
        summary = import_wiki_overrides(override_csv)
        assert_true(summary["updated"] == 5 and not summary["unmatched"], "manual import updates every harness weapon")
        assert_true(summary["text_fields_unchanged"], "manual import preserves descriptions and sources")
        assert_true(summary["status_counts"] == {
            "base_fallback": 1,
            "needs_check": 1,
            "no_match": 1,
            "skip": 1,
            "verified": 1,
        }, "manual import stores expected status counts")

        with store.db() as c:
            weapon_cols = [r["name"] for r in c.execute("PRAGMA table_info(arsenal_weapon)").fetchall()]
            photo_cols = [r["name"] for r in c.execute("PRAGMA table_info(arsenal_weapon_photo)").fetchall()]
            retired_table = "arsenal_" + "wiki_" + "import"
            retired = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (retired_table,),
            ).fetchone()
            assert_true(retired is None, "retired staging table is gone")
            assert_true("source" in weapon_cols and "wiki_url" in weapon_cols and "wiki_status" in weapon_cols, "weapon source and manual fields are created")
            assert_true("source_url" in photo_cols, "photo source URL field is created")

        bolt = store.get_weapon(store.weapon_by_exact_name("Boltgun")["id"])
        plasma = store.get_weapon(store.weapon_by_exact_name("Plasma Gun")["id"])
        pipe = store.get_weapon(store.weapon_by_exact_name("Mystery Pipe")["id"])
        storm = store.get_weapon(store.weapon_by_exact_name("Storm Bolter")["id"])
        chain = store.get_weapon(store.weapon_by_exact_name("Chainsword")["id"])
        assert_true(bolt["wiki_control"]["href"] == "https://warhammer40k.fandom.com/wiki/Boltgun", "verified manual link opens known page")
        assert_true(plasma["wiki_control"]["href"] == "https://warhammer40k.fandom.com/wiki/Plasma_Weapon", "base fallback manual link opens known page")
        assert_true("base weapon" in plasma["wiki_control"]["note"], "base fallback explains the base page")
        assert_true(pipe["wiki_control"]["muted_label"] == "no wiki article" and pipe["wiki_control"]["href"] == store.wiki_search_url("Mystery Pipe"), "no-match manual link searches as fallback")
        assert_true(storm["wiki_control"]["muted_label"] == "no model weapon (skip)" and not storm["wiki_control"]["href"], "skip manual control has no link")
        assert_true(chain["wiki_control"]["href"] == store.wiki_search_url("Chainsword"), "needs-check manual link searches")

        bolt_page = client.get(f"/arsenal/weapon/{bolt['id']}").data
        plasma_page = client.get(f"/arsenal/weapon/{plasma['id']}").data
        pipe_page = client.get(f"/arsenal/weapon/{pipe['id']}").data
        storm_page = client.get(f"/arsenal/weapon/{storm['id']}").data
        chain_page = client.get(f"/arsenal/weapon/{chain['id']}").data
        assert_true(b"Open wiki page" in bolt_page and b"https://warhammer40k.fandom.com/wiki/Boltgun" in bolt_page, "verified detail shows open page link")
        assert_true(b"points at the base weapon" in plasma_page, "base fallback detail shows note")
        assert_true(b"no wiki article" in pipe_page and store.wiki_search_url("Mystery Pipe").encode() in pipe_page, "no-match detail shows label and search")
        assert_true(b"no model weapon (skip)" in storm_page and b"Search wiki" not in storm_page, "skip detail shows muted label only")
        assert_true(store.wiki_search_url("Chainsword").encode() in chain_page, "needs-check detail shows search URL")
        audit_template = app_module.app.jinja_env.get_template("arsenal/_audit_weapon_row.html")
        audit_bolt = audit_template.render(
            row={**bolt, "weapon_id": bolt["id"], "problems": [], "raw_name": "", "unit_count": 1},
            categories=store.CATEGORIES,
        ).encode()
        audit_chain = audit_template.render(
            row={**chain, "weapon_id": chain["id"], "problems": [], "raw_name": "", "unit_count": 1},
            categories=store.CATEGORIES,
        ).encode()
        assert_true(b"Open wiki page" in audit_bolt and b"Search wiki" in audit_chain, "audit rows include manual links")
        assert_true(client.get("/arsenal/wiki/review").status_code == 404, "old review route is gone")
        assert_true(client.post("/arsenal/wiki/fetch").status_code == 404, "old fetch route is gone")
        assert_true(client.post(f"/arsenal/wiki/{pipe['id']}/image/accept", json={"image_url": "https://example.com/not-wiki.jpg"}).status_code == 404, "old image route is gone")

        sync = client.post("/arsenal/sync")
        assert_true(sync.status_code == 302, "sync route redirects")

        print("Arsenal harness passed")


if __name__ == "__main__":
    main()
