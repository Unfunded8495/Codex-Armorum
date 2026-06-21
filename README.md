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
- **Codex Archive** — browse the model catalogue along a Warhammer 40,000 edition timeline, with an
  in-place model editor for release dates and images.
- **Army Builder** — assign owned models to rosters, add detachments and enhancements, track points
  totals, and flag short squads or wishlist units.

Your collection, photos, favourites, purchases, custom boxes, and army lists are saved in
`collection.db` (SQLite) so they persist between runs.

---

## Installation

### Step 1 — Get the project files onto your computer

Before anything else you need the app's files sitting in a folder on your computer.

**If you were given a ZIP file** (the most common way):

1. Find the `.zip` file — usually in your **Downloads** folder.
2. Right-click it and choose **Extract All…**, then click **Extract**.
3. This creates an ordinary folder named `warhammer-catalogue` (or similar). You can move it
   anywhere you like, for example into your **Documents** folder. Remember where you put it — you
   will need to find it again in Step 3.

> **If you were given a GitHub link instead:** open the link, click the green **Code** button, choose
> **Download ZIP**, then follow the three steps above.

---

### Step 2 — Install Python

Python is the programming language the app runs on. You only need to do this once.

1. Go to **https://www.python.org/downloads/** and click the big yellow **Download Python** button.
2. Run the installer.
3. **Important:** On the first screen, tick the box that says **"Add Python to PATH"** before you
   click Install. If you miss this, the commands in the next steps won't work.

To check it worked, follow Step 3 below to open a command window, then type:
```
python --version
```
You should see something like `Python 3.13.0`. Any version 3.10 or higher is fine.

---

### Step 3 — Open a command window in the project folder

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

### Step 4 — Install Flask

Flask is the only thing the app needs that doesn't come with Python. Run this command once:

```
pip install flask
```

You will see some text scroll past as it downloads. When it finishes and you see the prompt again,
you're done.

---

### Step 5 — Run the app

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

### Step 6 — Stopping and restarting

- **To stop the app:** click on the command window and press **Ctrl + C**.
- **To start it again:** open a command window in the folder (Step 3) and run `python app.py` again.
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

## How to use the app

Once the app is running (browser open at **http://127.0.0.1:5050**), here is how to actually use it.
You don't need to understand everything at once — work through the quick start, then dip into the
task you need.

### Getting your bearings

Along the top of every page is the **navigation bar**:

- **Codex Armorum** (top-left) — click the title any time to go back to the home page.
- **My Armies** — the home page: every 40K faction shown as an icon tile.
- **Purchases** — record the boxed sets you have bought.
- **Codex Archive** — browse models along a Warhammer 40,000 edition timeline.
- **Paint Progress** — your painting stats dashboard.
- **☰ Tools** — a menu holding the extra tools: **Army Builder**, **Weapon Loadouts**, and
  **Model Catalogue**.
- **Seal Vault** — stops the app (see *Closing the app* at the end).

You will also see a small running tally in the bar — how many minis you have **Bought**, how many are
still **Unbuilt**, and how many are **Finished**. It updates automatically as you work.

### Quick start — your first five minutes

1. **Pick your army.** On **My Armies**, click the tile for a faction you collect (for example
   *Space Marines* or *Necrons*).
2. **Record something you own.** Go to **Purchases**, find the boxed set you bought, set the quantity,
   and log it. The app instantly adds one mini for every model in that box to your collection.
3. **See your minis.** Go back to **My Armies** and click your faction again — your newly added units
   now appear as tiles.
4. **Track your painting.** Open a unit and move each mini along its paint stage as you work on it.
5. **Check your progress.** Click **Paint Progress** to see the percentage of your whole collection
   that's painted.

That's the core loop. The sections below go into each part.

### 1. Find your army

**My Armies** shows every faction as a tile. Each tile has small badges telling you how many minis you
**own**, have **bought**, or have **yet to log** for that army. Click a tile to open that faction's
roster — the units you personally own, shown as tiles with a **paint-progress bar** across each one.

To browse *every* datasheet in a faction (not just the ones you own), click **Browse All Datasheets**
on the faction page. This lists every unit with its points cost and whether you own it.

### 2. Record what you've bought

Go to **Purchases**. Pick the boxed set you bought, choose how many, and log the purchase. The app
then **creates the individual minis** from that box and adds them to your collection as **Unbuilt**.

- If a box isn't listed, you can **define your own box** and say what's inside it.
- If a kit can be built as more than one unit (a "multikit"), the app keeps those models as a shared
  pool until you decide what to build them as.

### 3. Look up a unit's rules

From **Browse All Datasheets**, click any unit to open its **datasheet** — model stats, ranged and
melee weapon profiles, unit composition, wargear options, points, and keywords. **Hover a weapon
name** to see its full profile in a pop-up card. The **My Collection** tab on the datasheet shows the
minis you already own for that unit.

> Hover over a highlighted **weapon keyword** (like *Assault* or *Lethal Hits*) to see what it means.

### 4. Manage your individual minis

Click a unit tile on your faction roster to open that unit's **mini page**. Here you manage the
models one at a time (or in groups):

- Give a mini a **label** (e.g. "Sergeant with power fist").
- Choose its **wargear** from the options the kit allows.
- Add **notes** and upload **photos**.
- Set its **paint stage** (see below).

### 5. Track your painting

Every mini moves through eight paint stages:

**Unbuilt → Assembled → Primed → Base Coated → Washed → Highlighted → Finished → Display**

Change a mini's stage on its **mini page** (or the unit's **My Collection** tab) as you make progress.
Then open **Paint Progress** for the big picture: the percentage of your collection that's painted, a
breakdown of how many minis sit at each stage, and per-faction progress with links back to each army.

### 6. Build an army list

Open **☰ Tools → Army Builder** to plan a game. Create an army list, add units from the models you
own, choose a **detachment** and **enhancements**, and the app tracks your running **points total**.
It flags squads that are short of models or units you'd need to buy.

### The extra tools

- **Weapon Loadouts** (under Tools) — manage the weapon cards that power the hover pop-ups on
  datasheets, and link them to the units that use them.
- **Model Catalogue** (under Tools) — maintain your model-release records, the images shown on unit
  pages, and links between physical kits and their datasheets. Some models that don't have a game
  datasheet can still be catalogued and tracked here.
- **Codex Archive** — browse the model catalogue along the 40K edition timeline, with an in-place
  editor for release dates and images.

### Closing the app

When you're finished, click **Seal Vault** in the top bar to stop the app cleanly. (You can also
press **Ctrl + C** in the command window, as in Step 6 above.) Your collection is saved in
`collection.db`, so everything is exactly as you left it next time you start.

---

## Unit data

Unit data (factions, datasheets, weapon profiles, points, detachments, enhancements) comes from the
Wahapedia Warhammer 40,000 10th Edition CSV export — pipe-delimited CSV files stored in `data/`.
Re-fetch the export with `python scripts/fetch_wahapedia.py`, then populate the database tables that
power the unit browser by running `python wahapedia_importer.py`. The importer drops and rebuilds the
`catalogue_*` tables and is safe to re-run at any time to pick up ruleset updates; no user data is
touched.

The `data/` folder also holds the hand-curated model catalogue JSON files and the edition timeline.
Runtime catalogue edits are stored in `data/model_catalogue_manual.json`, with linking decisions in
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
  data_store.py           reads Wahapedia catalogue tables; builds faction/unit indexes
  wahapedia_importer.py   parses Wahapedia CSVs; populates catalogue_* tables in the DB
  catalogue_review.py     model catalogue management logic
  collection.py           mini ownership queries and wargear helpers
  box_sets.py             box set definitions and purchase creation
  army.py                 army builder helpers (points, detachments, enhancements)
  editions.py             loads the hand-curated edition timeline (Codex Archive)
  arsenal.py              Arsenal wargear feature (Flask blueprint)
  arsenal_store.py        Arsenal sqlite3 data access and sync helpers
  db.py                   SQLite schema init and legacy migrations
  factions_theme.py       faction colours and placeholder SVGs
  images.py               image upload and reference-image handling
  utils.py                shared utility helpers
  data/                   Wahapedia ruleset CSVs + model catalogue & edition-timeline JSONs
  scripts/                one-off import, migration, image, and audit helpers
  static/                 css + js + faction icons
  templates/              Flask page templates
  uploads/                gallery photos (gitignored)
  cache/images/           cached catalogue, box, and unit reference images (gitignored)
  collection.db           saved local collection (created on first run, gitignored)
```
