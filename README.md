# Codex Armorum — Warhammer 40,000 Collection Cataloguer

A local website (Python + Flask backend, no build step on the frontend) for cataloguing your
40K miniatures. Pick an army from a grid of icons, browse every datasheet in that faction,
record boxed-set purchases, and manage the individual minis those purchases add to your
collection. Each mini can keep its own label, wargear, paint stage, notes, and photographs.

---

## What it does

- **Army grid** — every 40K faction shown as an icon tile, with badges for owned, bought, and
  unlogged minis.
- **Faction roster** — your purchased minis for the chosen army, shown as unit tiles with a
  paint-progress bar. Click any tile to open that unit's mini page. A "Browse All Datasheets" link
  shows every datasheet in the faction with points and collection status.
- **Purchases** — record boxed sets you have bought. Logging a purchase creates unbuilt mini rows,
  including shared multikit pools when a kit can build alternate datasheets.
- **Unit detail** — the full datasheet: model stats, ranged and melee weapon profiles, composition,
  wargear options, points, and keywords. The **My Collection** tab shows the minis you already own
  for that datasheet.
- **Mini management** — each unit has its own mini page (`#/mini/<unit>`) for editing labels, gear,
  notes, photos, and paint stage on individual minis or groups.
- **Paint progress** — the `/collection` page shows an overall stats dashboard: percentage painted,
  stage breakdown, and per-faction progress with links back to each faction's roster.
- **Model catalogue** — maintain model-release records, datasheet links, and release images used by
  unit pages and box contents.
- **Army Builder** — assign owned models to rosters, add detachments and enhancements, track points
  totals, and flag short squads or wishlist units.

Your collection, photos, favourites, purchases, custom boxes, and army lists are saved in
`collection.db` (SQLite) so they persist between runs.

---

## Installation

### Step 1 — Install Python

Python is the programming language the app runs on. You only need to do this once.

1. Go to **https://www.python.org/downloads/** and click the big yellow **Download Python** button.
2. Run the installer.
3. **Important:** On the first screen, tick the box that says **"Add Python to PATH"** before you
   click Install. If you miss this, the commands in the next steps won't work.

To check it worked, follow Step 2 below to open a command window, then type:
```
python --version
```
You should see something like `Python 3.13.0`. Any version 3.10 or higher is fine.

---

### Step 2 — Open a command window in the project folder

A command window (also called a terminal or command prompt) is where you type instructions to run
the app. It looks old-fashioned but you only need a few commands.

**The easiest way on Windows:**

1. Open **File Explorer** and navigate to the `warhammer-catalogue` folder.
2. Click on the address bar at the top (where the folder path is shown).
3. Type `cmd` and press **Enter**.

A black window will open, already pointed at the right folder. You're ready to type commands.

> **Alternative:** Press the **Windows key**, search for **Command Prompt**, open it, then
> navigate to the folder by typing `cd` followed by the full path, for example:
> ```
> cd C:\Projects\warhammer-catalogue
> ```

---

### Step 3 — Install Flask

Flask is the only thing the app needs that doesn't come with Python. Run this command once:

```
pip install flask
```

You will see some text scroll past as it downloads. When it finishes and you see the prompt again,
you're done.

---

### Step 4 — Run the app

```
python app.py
```

You should see output like:

```
 * Running on http://127.0.0.1:5050
```

Open your browser and go to **http://127.0.0.1:5050**

The app is running. You can use it like any website — just one that lives on your own computer.

---

### Step 5 — Stopping and restarting

- **To stop the app:** click on the command window and press **Ctrl + C**.
- **To start it again:** open a command window in the folder (Step 2) and run `python app.py` again.
  You do not need to reinstall Flask.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Re-install Python from python.org, making sure to tick "Add Python to PATH" |
| `pip` not found | Try `python -m pip install flask` instead |
| Port already in use | Something else is using port 5050. Open `app.py`, find `port=5050`, change it to `5051` |
| Page shows but looks broken | Hard-refresh the browser: **Ctrl + Shift + R** |

---

## Optional: Virtual environments (advanced)

If you run multiple Python projects and want to keep their dependencies separated, you can use a
virtual environment. This is standard practice for developers but **completely optional** for
running this one app.

**Windows:**
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

**Mac / Linux:**
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

After activation you will see `(venv)` at the start of your prompt. You need to run the `activate`
command each time you open a new terminal window.

---

## Unit data

Unit data (factions, datasheets, weapon profiles, points) comes from the BSData Warhammer 40,000
10th Edition XML repository cloned into `bsdata/wh40k-10e/`. The database tables that power the
unit browser are populated by running `python bsdata_importer.py` — this is safe to re-run at any
time to pick up ruleset updates.

The `data/` folder also holds three Wahapedia CSV files (detachments, enhancements, and a
Wahapedia-to-BSData ID bridge) plus the model and box catalogue JSON files. Runtime catalogue edits
are stored in `data/model_catalogue_manual.json`, with linking decisions in
`data/model_catalogue_resolutions.json` and image metadata in `data/model_catalogue_images.json`.

See `CODEX_ARMORUM_ARCHITECTURE.md` for a full breakdown of all data sources, ID systems, and what
must be preserved when migrating to a new environment.

---

## Images

Out of the box, each unit shows a clean, faction-coloured placeholder with its name, so the app is
fully functional without any images. The army grid uses images from `static/icons/` when a matching
file is present and otherwise falls back to the army's first letter.

Unit pages prefer images from linked model catalogue entries. To add or change those images, open
**Model Catalogue**, edit a release, and paste an image URL or choose a local file. Box art is
edited from the **Purchases** box editor.

These reference pictures are the property of their copyright holders, including Games Workshop, and
are stored locally for your personal collection reference only.

---

## Project layout

```
warhammer-catalogue/
  app.py                  Flask backend + REST API
  data_store.py           reads BSData catalogue tables; builds faction/unit indexes
  bsdata_importer.py      parses BSData XML; populates catalogue_* tables in the DB
  catalogue_review.py     model catalogue management logic
  collection.py           mini ownership queries and wargear helpers
  box_sets.py             box set definitions and purchase creation
  army.py                 army builder helpers (points, detachments, enhancements)
  arsenal.py              Arsenal wargear feature (Flask blueprint)
  arsenal_store.py        Arsenal sqlite3 data access and sync helpers
  db.py                   SQLite schema init and legacy migrations
  factions_theme.py       faction colours and placeholder SVGs
  images.py               image upload and reference-image handling
  utils.py                shared utility helpers
  bsdata/wh40k-10e/       BSData 40K 10th Edition XML repo (gitignored — re-cloneable)
  data/                   Wahapedia CSVs (detachments/enhancements) + model catalogue JSONs
  scripts/                one-off import, migration, image, and audit helpers
  static/                 css + js + faction icons
  templates/              Flask page templates
  uploads/                gallery photos (gitignored)
  cache/images/           cached catalogue, box, and unit reference images (gitignored)
  collection.db           saved local collection (created on first run, gitignored)
```
