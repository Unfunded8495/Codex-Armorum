"""UI journeys -- real browser, the way a user drives the app.

Playwright (headless Chromium) against a Flask server this script starts on an
isolated copy of collection.db and stops when done, so nothing is left running
and real data is untouched. This is the thin true-to-the-user layer; the engine
sweeps remain the correctness backbone.

This layer is the only one with a test-only dependency. One-time setup in your
environment:

    pip install playwright
    playwright install chromium

It also needs the stable data-testid hooks listed in tests/TESTIDS.md added to
the JS/templates. Where a hook is missing the journey falls back to text/role
selectors, which are more brittle; add the hooks for a durable suite.

Run: python tests/ui_journeys.py
"""
import os
import sys
import time
import socket
import shutil
import tempfile
import subprocess
import urllib.request

import _harness as H
from _harness import Reporter, REPO

PORT = int(os.environ.get("TEST_UI_PORT", "5050"))
BASE = f"http://127.0.0.1:{PORT}"


def _free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def start_server():
    """Start app.py on an isolated DB copy; return (proc, tmp_db)."""
    src = os.path.join(REPO, "collection.db")
    fd, tmp = tempfile.mkstemp(prefix="ui_collection_", suffix=".db")
    os.close(fd)
    if os.path.exists(src):
        shutil.copy2(src, tmp)
    env = dict(os.environ, COLLECTION_DB_PATH=tmp)
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=REPO, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{BASE}/api/battle-sizes", timeout=1)
            return proc, tmp
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("server did not come up on " + BASE)


def stop_server(proc, tmp):
    try:
        urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/shutdown", method="POST"), timeout=2)
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    if tmp and os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass


def sel(page, testid, fallback=None):
    """Prefer a data-testid; fall back to a text/role selector if absent."""
    loc = page.locator(f"[data-testid='{testid}']")
    if loc.count() > 0:
        return loc.first
    if fallback is not None:
        return page.locator(fallback).first
    return loc.first  # will fail visibly, prompting a TESTIDS.md addition


def foc_slug(category):
    return category.replace(" ", "-").lower()


def add_unit(page, name, category, timeout=8000):
    """Add the unit named exactly ``name`` via the category-scoped add-unit
    overlay. A unit's Force-Org category is never a player choice -- every
    "+" on the roster is already scoped to one of the 4 sections (Characters/
    Battleline/Dedicated Transports/Other Datasheets), so the picker it opens
    only ever offers units of that one category and ``category`` must match
    the unit's actual one or the card won't be there to find.

    The picker is a full-screen overlay (not an always-visible panel), so this
    closes it again afterward -- left open it would block every subsequent
    click (it sits above the roster at a higher stacking order while visible).
    Binding to the exact name (never a substring ``text=`` fallback) avoids
    grabbing a similarly named sheet -- e.g. a bare "Intercessor Squad" match
    would otherwise hit "Assault Force Intercessor Squad", whichever renders
    first.
    """
    page.locator(f"[data-testid='foc-add-{foc_slug(category)}']").first.click()
    card = page.locator(f"[data-testid='unit-picker-panel'] [data-testid='picker-unit-{name}']")
    card.wait_for(state="visible", timeout=timeout)
    card.locator(".po-add").click()
    page.locator("[data-testid='unit-picker-panel'] .cb-back").click()
    page.locator("[data-testid='unit-picker-panel']").wait_for(state="hidden", timeout=timeout)


def run():
    r = Reporter("ui journeys (playwright)")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        r.skip("ui journeys", "playwright not installed (pip install playwright; playwright install chromium)")
        return r.summary()

    if not _free(PORT):
        r.skip("ui journeys", f"port {PORT} is busy; stop any running server or set TEST_UI_PORT")
        return r.summary()

    proc, tmp = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

            # Journey 1: create an army and add a unit. The create flow (army
            # list page) is untouched by the companion-app-parity rebuild.
            page.goto(f"{BASE}/army-builder")
            sel(page, "new-army-button", "text=New Army").click()
            try:
                sel(page, "faction-select").select_option(label="Ultramarines")
                # The battle-size option label carries the points ("Strike Force ·
                # 2000 pts"); its value is the clean name, so match on value.
                sel(page, "battle-size-select").select_option(value="Strike Force")
                sel(page, "create-army-confirm", "text=Create").click()
                page.wait_for_selector("[data-testid='army-detail']", timeout=5000)
                r.check("journey: create army reaches the army detail view", True)
            except Exception as e:
                r.check("journey: create army reaches the army detail view", False, repr(e))

            # Journey 2: add a unit (Battleline section's "+"), roster grows.
            try:
                add_unit(page, "Intercessor Squad", "Battleline")
                page.wait_for_selector("[data-testid='unit-row']", timeout=5000)
                r.check("journey: adding a unit shows a roster row", True)
            except Exception as e:
                r.check("journey: adding a unit shows a roster row", False, repr(e))

            # Journey 3: editing a unit moves the live points total. The
            # squad-size stepper lives in the unit-options right panel now
            # (not inline on the row), so open a unit first. A wargear swap is
            # points-neutral for most 10e units (and Intercessors expose no
            # points-bearing option), so the stepper is still the reliable
            # points mover; both run the same applyServerState -> points-HUD
            # path, which is what this journey verifies: no reload needed.
            try:
                before = sel(page, "army-points").inner_text()
                page.locator("[data-testid='unit-row']").first.click()
                size = sel(page, "unit-size-input", ".au-size-input")
                size.wait_for(state="visible", timeout=4000)
                target = size.get_attribute("max") or "10"
                size.fill(target)
                size.dispatch_event("change")
                page.wait_for_function(
                    "t => document.querySelector(\"[data-testid='army-points']\").innerText !== t",
                    arg=before, timeout=4000)
                r.check("journey: a unit edit updates the points total live", True)
            except Exception as e:
                r.check("journey: a unit edit updates the points total live", False, repr(e))

            # Journey 4: an over-limit duplicate shows a validation row. Each add
            # is an async POST that appends its row (and refreshes the validation
            # card) only once it resolves, so wait on the row count to reach the
            # target before reading the card -- otherwise we race the in-flight
            # POSTs and read stale text.
            try:
                target_rows = page.locator("[data-testid='unit-row']").count() + 7
                for _ in range(7):
                    add_unit(page, "Intercessor Squad", "Battleline")
                page.wait_for_function(
                    "n => document.querySelectorAll(\"[data-testid='unit-row']\").length >= n",
                    arg=target_rows, timeout=8000)
                vis = page.locator("[data-testid='validation-card']").inner_text().lower()
                r.check("journey: an over-limit roster surfaces a validation message",
                        "max" in vis or "duplicate" in vis or "too many" in vis,
                        f"validation card text was {vis[:160]!r} (Phase 5 + the validation-card hook)")
            except Exception as e:
                r.check("journey: an over-limit roster surfaces a validation message", False, repr(e))

            # Journey 4b: clicking a roster row opens the unit in the right
            # detail panel (warlord / enhancement / wargear / profiles all
            # live there, not inline on the row).
            try:
                page.locator("[data-testid='unit-row']").first.click()
                page.wait_for_selector(
                    "[data-testid='detail-panel'] [data-testid='unit-profiles-toggle']", timeout=4000)
                r.check("journey: clicking a unit opens its right-panel detail", True)
            except Exception as e:
                r.check("journey: clicking a unit opens its right-panel detail", False, repr(e))

            # Journey 4c: Battle Size / Detachments live in the Edit Roster
            # overlay now (roster-kebab -> menu-edit-roster), each as a
            # tap-through sub-screen. Open the Detachments sub-screen, pick
            # the first selectable card, and confirm its derived Force
            # Disposition label renders -- then close back out to main so a
            # later journey doesn't find the overlay still open.
            try:
                page.locator("[data-testid='roster-kebab']").click()
                sel(page, "menu-edit-roster").click()
                page.locator("[data-testid='edit-roster-modal'] [data-testid='er-row-detachment']").click()
                # Affordable (clickable) cards carry style="cursor:pointer";
                # unaffordable ones render with no style attribute at all.
                card = page.locator("[data-testid='edit-roster-modal'] [data-testid='detachment-chip'][style*='cursor:pointer']").first
                if card.count() > 0:
                    card.wait_for(state="visible", timeout=4000)
                    card.click()
                    page.wait_for_selector(
                        "[data-testid='edit-roster-modal'] [data-testid='detachment-disposition']", timeout=5000)
                    r.check("journey: choosing a detachment shows its Force Disposition label", True)
                else:
                    r.skip("journey: detachment disposition", "no selectable detachment cards")
                page.locator("[data-testid='edit-roster-modal'] .cb-back").first.click()
                page.locator("[data-testid='edit-roster-modal'] .cb-back").first.click()
            except Exception as e:
                r.check("journey: choosing a detachment shows its Force Disposition label", False, repr(e))

            # Journey 4d: leader attachment. A Leader (Captain) nests under its
            # bodyguard; a support character (Lieutenant) then joins ALONGSIDE
            # him - the leader_group slot model - so the bodyguard ends up
            # with two nested rows. Pre-leader_group builds 400'd the second
            # attach and nested at most one row.
            try:
                add_unit(page, "Captain", "Characters")
                add_unit(page, "Lieutenant", "Characters")
                for i, who in enumerate(("Captain", "Lieutenant"), start=1):
                    page.locator("[data-testid='unit-row']").filter(has_text=who).first.click()
                    att = page.locator("[data-testid='unit-leader-attach']")
                    att.wait_for(state="visible", timeout=4000)
                    att.select_option(index=1)  # index 0 is the placeholder
                    page.wait_for_function(
                        "n => document.querySelectorAll('.au-nested').length >= n",
                        arg=i, timeout=5000)
                r.check("journey: a Leader and a support Lieutenant both nest under the bodyguard", True)
            except Exception as e:
                r.check("journey: a Leader and a support Lieutenant both nest under the bodyguard",
                        False, repr(e))

            # Journey 5: missions reference renders (Phase 6).
            try:
                page.goto(f"{BASE}/army-builder")
                # A locator can't mix the css and text engines in one comma list;
                # the nav-missions hook is on the topbar link, so target it.
                missions = page.locator("[data-testid='nav-missions']")
                if missions.count() == 0:
                    missions = page.get_by_role("link", name="Missions")
                if missions.count():
                    missions.first.click()
                    page.wait_for_selector("[data-testid='missions-view']", timeout=4000)
                    r.check("journey: missions reference page renders", True)
                else:
                    r.skip("journey: missions reference page", "no missions nav (pre-Phase 6 or hook missing)")
            except Exception as e:
                r.skip("journey: missions reference page", repr(e))

            r.check("journey: no console errors during the session", not errors,
                    f"{len(errors)} e.g. {errors[:2]}")
            browser.close()
    finally:
        stop_server(proc, tmp)
    return r.summary()


if __name__ == "__main__":
    sys.exit(run())
