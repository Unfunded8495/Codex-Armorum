# Codex Armorum: How the App Works (Visual Breakdown)

A walkthrough of the running application — what the pieces are, how they talk to each
other, and what links to what. This is the *behavioural* companion to
[`CODEX_ARMORUM_ARCHITECTURE.md`](CODEX_ARMORUM_ARCHITECTURE.md), which covers the *data
sources, ID systems, and migration rules*. Read this one to understand the request flow;
read that one to understand where the data lives.

> Mermaid diagrams below render natively on GitHub and in most Markdown viewers
> (VS Code with a Mermaid extension, Obsidian, etc.).

---

## 1. The 30-second summary

Codex Armorum is a **single-user, locally-run Flask web app** for cataloguing a
Warhammer 40,000 miniature collection. There is **no build step** and **no frontend
framework** — just vanilla ES modules talking to a Flask REST API, backed by one SQLite
file (`collection.db`) plus a handful of CSV/JSON reference files in `data/`.

| Layer | Technology | Entry point |
|---|---|---|
| Frontend (catalogue) | Vanilla JS ES modules + hash routing (SPA) | `templates/index.html` → `static/js/app.js` |
| Frontend (tools) | Server-rendered Jinja pages + page-specific JS | `army_builder.html`, `collection.html`, `catalogue_review.html`, `arsenal/*` |
| Backend | Flask (`app.py`) + one blueprint (`arsenal.py`) | `python app.py` → `http://127.0.0.1:5050` |
| Data access | Python modules wrapping SQLite + reference files | `data_store.py`, `collection.py`, `box_sets.py`, … |
| Storage | SQLite (`collection.db`) + `data/` Wahapedia CSV + catalogue/edition JSON | `db.py` (schema), `wahapedia_importer.py` (loader) |

---

## 2. Big picture — the layered architecture

```mermaid
flowchart TB
    subgraph Browser["🖥️ Browser"]
        SPA["Catalogue SPA<br/>(index.html + app.js)<br/>hash routing #/…"]
        TOOLS["Tool pages<br/>(server-rendered Jinja)<br/>Army Builder · Paint Progress<br/>Model Catalogue · Arsenal"]
    end

    subgraph Flask["⚙️ Flask backend — app.py"]
        PAGES["Page routes<br/>/  /army-builder<br/>/collection  /catalogue-review"]
        API["REST API<br/>/api/*"]
        BP["Arsenal blueprint<br/>/arsenal/*"]
    end

    subgraph Logic["🧠 Python logic modules"]
        DS["data_store.py<br/>faction/unit/weapon index<br/>+ Space Marine chapter rollup"]
        COL["collection.py<br/>ownership + wargear"]
        BOX["box_sets.py<br/>purchases → minis"]
        ARMY["army.py<br/>points · detachments"]
        CAT["catalogue_review.py<br/>model catalogue payload"]
        EDS["editions.py<br/>edition timeline"]
        ARS["arsenal_store.py<br/>wargear data access"]
        IMG["images.py · factions_theme.py"]
    end

    subgraph Store["💾 Storage"]
        DB[("collection.db<br/>SQLite")]
        REF["data/*.csv · data/*.json<br/>(Wahapedia + catalogue + editions)"]
        FILES["uploads/ · cache/images/"]
    end

    SPA -->|fetch JSON| API
    TOOLS -->|fetch JSON / forms| API
    TOOLS --> BP
    PAGES -->|render| TOOLS
    PAGES -->|render| SPA

    API --> DS & COL & BOX & ARMY & CAT & EDS & IMG
    BP --> ARS
    DS --> DB & REF
    COL & BOX & ARMY --> DB
    CAT & EDS --> REF
    ARS --> DB
    IMG --> FILES
    REF -.->|wahapedia_importer.py<br/>one-off import| DB
```

**Reading it:** the browser only ever talks to Flask over HTTP. Flask routes delegate to
the logic modules, which read/write SQLite and the reference files. The Wahapedia CSVs are
*not* read at request time for unit data — they are imported once into `catalogue_*` tables
by `wahapedia_importer.py` (dashed line). (`data_store` does read `Detachments.csv` and
`Enhancements.csv` directly at request time for the detachment/enhancement browsers.)

---

## 3. Two front ends under one roof

The app has **two distinct frontend styles** that share the same top bar
(`templates/_topbar.html`):

```mermaid
flowchart LR
    subgraph A["SPA shell — index.html"]
        direction TB
        a1["My Armies (home)"]
        a2["Faction roster"]
        a3["Unit datasheet"]
        a4["Mini page"]
        a5["Purchases"]
        a6["Codex Archive"]
    end
    subgraph B["Server-rendered tool pages"]
        direction TB
        b1["Army Builder<br/>army_builder.html"]
        b2["Paint Progress<br/>collection.html"]
        b3["Model Catalogue<br/>catalogue_review.html"]
        b4["Arsenal / Loadouts<br/>arsenal/*.html"]
    end
    A -.shared top bar + ledger.- B
```

- **SPA shell** (`/`): one HTML page, content swapped into `<main id="view">` by JS based
  on the URL hash. Handles the core catalogue browsing loop.
- **Tool pages**: each is its own Flask route returning a full Jinja template with its own
  `<script>`. They navigate by real URLs, not hashes.

The top bar links bridge the two worlds (note hash vs. path):

| Nav button | Target | Kind |
|---|---|---|
| **My Armies** | `/` | SPA home |
| **Purchases** | `/#/purchases` | SPA route |
| **Codex Archive** | `/#/history` | SPA route |
| **Paint Progress** | `/collection` | Server page |
| **Army Builder** | `/army-builder` | Server page |
| **Weapon Loadouts** | `/arsenal/loadouts` | Blueprint page |
| **Model Catalogue** | `/catalogue-review` | Server page |
| **Seal Vault** | `POST /api/shutdown` | Stops the server |

---

## 4. Client-side routing (the SPA)

`static/js/app.js` is the router. It parses `location.hash` and calls one "show" function:

```mermaid
flowchart TD
    H["location.hash"] --> R{{"router() in app.js"}}
    R -->|"#/ (default)"| HOME["showHome()<br/>home.js — faction grid"]
    R -->|"#/faction/:fid"| FAC["showFaction()<br/>home.js — owned-mini roster"]
    R -->|"#/faction/:fid/browse"| BROWSE["showFaction(browseAll)<br/>all datasheets in faction"]
    R -->|"#/unit/:did"| UNIT["showUnit()<br/>unit.js — full datasheet"]
    R -->|"#/mini/:did"| MINI["showMiniPage()<br/>mini-page.js — manage minis"]
    R -->|"#/purchases"| PUR["showPurchases()<br/>purchases.js"]
    R -->|"#/history"| HIST["showHistory()<br/>history.js — edition timeline"]
    R -->|"#/history/:fid"| HISTF["showHistoryFaction()<br/>history.js — faction models"]

    HOME -->|click faction tile| FAC
    FAC -->|click unit tile| MINI
    FAC -->|Browse All Datasheets| BROWSE
    BROWSE -->|click datasheet| UNIT
    UNIT -->|My Collection tab| MINI
    FAC -->|empty state| PUR
```

The **Army Builder** runs its own mini-router (`army_builder.js`) with hashes
`#/army/:aid` for army detail, layered on top of the `/army-builder` server page.

---

## 5. Frontend module graph (what imports what)

Vanilla ES modules, so the import graph *is* the dependency graph. Shared leaf modules
(`utils.js`, `header.js`, `lightbox.js`) are pulled in almost everywhere.

```mermaid
flowchart TD
    appjs["app.js (SPA router)"] --> home["home.js"]
    appjs --> purchases["purchases.js"]
    appjs --> unit["unit.js"]
    appjs --> minipage["mini-page.js"]
    appjs --> history["history.js"]
    appjs --> lightbox["lightbox.js"]
    appjs --> header["header.js"]

    unit --> datasheet["datasheet.js"]
    unit --> arsenalhover["arsenal-hover.js"]
    datasheet --> ruletext["ruletext.js"]
    ruletext --> kw["/static/weapon_keywords.json"]

    home --> header
    purchases --> home
    minipage --> home

    abjs["army_builder.js (tools router)"] --> armylist["army-list.js"]
    abjs --> armydetail["army-detail.js"]
    abjs --> picker["unit-picker.js"]
    armylist --> astate["army-state.js"]
    armydetail --> astate
    picker --> astate

    creview["catalogue-review.js"] --> header
    collectionjs["collection.js"] --> header

    subgraph shared["shared leaf modules"]
        utils["utils.js (esc, api, …)"]
        header
        lightbox
    end

    home --> utils
    unit --> utils
    minipage --> utils
    purchases --> utils
    history --> utils
    armydetail --> utils
    creview --> utils
    collectionjs --> utils
    header --> utils
```

Key roles:

- **`utils.js`** — `esc()`, `api()` (the `fetch` wrapper every call uses), `withTimeout()`,
  contrast-safe colour helper `readableInk()`.
- **`header.js`** — breadcrumb + the live "ledger" (Bought / Unbuilt / Finished counts),
  refreshed via `/api/collection/summary`.
- **`datasheet.js` + `ruletext.js`** — render Wahapedia stat blocks, weapons, abilities, and
  wrap weapon keywords with glossary tooltips from `weapon_keywords.json`.
- **`arsenal-hover.js`** — hover popovers on the unit page that pull weapon cards from the
  Arsenal blueprint.

---

## 6. Backend module responsibilities

```mermaid
flowchart LR
    apppy["app.py<br/>routes + API + glue"]

    apppy --> data_store["data_store.py<br/>• loads catalogue_* tables (native Wahapedia ids)<br/>• Space Marine chapter rollup<br/>• units_for_faction / unit_by_id"]
    apppy --> collection["collection.py<br/>• owned_totals()<br/>• minis_for() / wargear choices<br/>• favourite_factions()"]
    apppy --> box_sets["box_sets.py<br/>• box_sets / purchase_payload<br/>• logging a purchase → minis<br/>• custom box CRUD"]
    apppy --> army["army.py<br/>• points_for / enhancement cost<br/>• detachment validation"]
    apppy --> catalogue_review["catalogue_review.py<br/>• model catalogue payload<br/>• resolutions + images"]
    apppy --> editions["editions.py<br/>• edition timeline loader"]
    apppy --> images["images.py<br/>uploads + reference images"]
    apppy --> factions_theme["factions_theme.py<br/>colours + placeholder SVGs"]
    apppy --> arsenal["arsenal.py (blueprint)<br/>→ arsenal_store.py"]

    db["db.py<br/>schema init + migrations"] -.provides db() + init_db.-> apppy
    wahapedia["wahapedia_importer.py<br/>CSV → catalogue_* tables"] -.one-off CLI.-> data_store
```

| Module | Responsibility | Talks to |
|---|---|---|
| `app.py` | All page routes + the `/api/*` surface; wires everything together | every logic module |
| `data_store.py` | In-memory index of factions/units/weapons from `catalogue_*` (keyed on native Wahapedia ids in `ds_by_id`); derives the **Space Marine chapter rollup** at load time | `collection.db`, `data/Detachments.csv`, `Enhancements.csv` |
| `collection.py` | Ownership counts, the minis for a datasheet, wargear-choice parsing | `minis` table |
| `box_sets.py` | Box-set definitions, purchase logging that **creates mini rows**, multikit pools | `purchases`, `minis`, `custom_box_*` |
| `army.py` | Army points maths, detachment/enhancement validation | `data/Detachments.csv`, `Enhancements.csv` |
| `catalogue_review.py` | Builds the Model Catalogue payload, resolves datasheet links via `data_store.ds_by_id` | `data/model_catalogue_*.json` |
| `editions.py` | Loads the hand-curated edition timeline for the Codex Archive | `data/editions_timeline.json` |
| `arsenal.py` / `arsenal_store.py` | The Arsenal (wargear) feature as a self-contained blueprint + its own tables | `arsenal_weapon*` tables |
| `db.py` | Creates/migrates all tables, exposes `db()` connection context | `collection.db` |
| `wahapedia_importer.py` | Parses the Wahapedia CSV export into `catalogue_*` (run manually) | `data/*.csv` → DB |
| `images.py`, `factions_theme.py`, `utils.py` | Image upload/refs, faction theming, small shared helpers | `cache/`, `uploads/` |

---

## 7. API surface (grouped by feature)

All JSON unless noted. Source: `app.py` route table + the `/arsenal` blueprint.

**Pages (HTML):** `GET /` · `GET /army-builder` · `GET /catalogue-review` · `GET /collection`

**Factions & units**
- `GET /api/factions` — faction grid with owned/bought/unlogged badges
- `GET /api/factions/<fid>/icon` — tinted faction SVG
- `POST|DELETE /api/factions/<fid>/favourite`
- `GET /api/factions/<fid>/units` — faction roster with collection status
- `GET /api/factions/<fid>/detachments` · `GET /api/detachments/<dtid>/enhancements`
- `GET /api/units/<did>` — the full datasheet payload (stats, weapons, comp, points)
- `GET /api/units/<did>/image` · `GET /api/units/search`

**Collection & minis**
- `GET /api/collection` — minis (optionally `?faction_id=`)
- `GET /api/collection/summary` — the top-bar ledger counts
- `GET /api/unassigned-minis` · `POST /api/minis/assign-datasheet` — the unassigned-minis safety net
- `POST|DELETE /api/minis/<mid>` · `POST /api/minis/<mid>/duplicate`
- `POST /api/minis/<mid>/photos` · `PATCH /api/minis/<mid>/stage` · `GET /api/minis/<mid>/multikit-options`
- `POST /api/units/<did>/wip-notes` · `POST /api/units/<did>/wip-photos` · `DELETE /api/wip-photos/<pid>` — unit-level WIP notes & gallery
- `DELETE /api/photos/<pid>` · `POST /api/photos/<pid>/caption` · `GET /uploads/<fname>`

**Purchases & box sets**
- `GET /api/purchases/page-data` · `GET|POST /api/purchases` · `DELETE /api/purchases/<pid>`
- `GET /api/box-sets` · `POST /api/box-sets` · `POST|DELETE /api/box-sets/<box_id>`
- `POST /api/box-sets/parse` · box-set image + reference endpoints

**Army builder**
- `GET|POST /api/armies` · `GET|POST|DELETE /api/armies/<aid>`
- `POST /api/armies/<aid>/units` · `POST|DELETE /api/army-units/<auid>`

**Model catalogue**
- `GET|POST /api/model-catalogue` · `GET|PATCH|DELETE /api/model-catalogue/<id>`
- `GET /api/model-catalogue/faction-cards` — faction tiles for the Codex Archive browser
- `POST /api/model-catalogue/<id>/duplicate` · image endpoints · `GET /api/model-catalogue/search`
- `POST /api/catalogue-review/<id>/resolution`

**Codex Archive**
- `GET /api/editions` — the Warhammer 40,000 edition timeline (powers `/#/history`)

**Arsenal blueprint (`/arsenal/*`, mostly HTML/forms)**
- `GET /arsenal/loadouts` · `GET /arsenal/loadouts/<datasheet_id>`
- `GET|POST /arsenal/weapon/new` · `GET /arsenal/weapon/<id>` · `GET|POST /arsenal/weapon/<id>/edit` · `POST /arsenal/weapon/<id>/delete`
- weapon photo endpoints · `GET /arsenal/api/weapon-card` (the hover card) · `GET /arsenal/audit`

**System:** `POST /api/shutdown` (localhost-only; stops the server)

---

## 8. Data sources & the two ID systems

This is summarised here for orientation; the authoritative version with migration rules is
in [`CODEX_ARMORUM_ARCHITECTURE.md`](CODEX_ARMORUM_ARCHITECTURE.md).

```mermaid
flowchart TB
    subgraph Sources["Two independent data tracks"]
        WP["① Wahapedia CSVs<br/>(regenerable: re-fetch + re-import)<br/>factions · units · weapons · points<br/>detachments · enhancements"]
        MC["② Model catalogue + editions JSON<br/>(hand-curated, keep forever)<br/>physical releases + images<br/>+ edition timeline"]
    end

    WP -->|wahapedia_importer.py| CAT["catalogue_* tables"]
    CAT --> DSS["data_store.ds_by_id<br/>(native Wahapedia index)"]
    MC -->|datasheet_links| DSS

    DSS --> UI["Unit pages · purchase browser ·<br/>army builder · arsenal links · Codex Archive"]
```

BSData has been fully retired: there is no `bsdata/` repo, no `bsdata_importer.py`, and no
runtime Wahapedia→BSData alias bridge. Every unit lookup keys on the native Wahapedia
datasheet id.

The **two ruleset ID systems** (plus the catalogue model id) that everything keys on:

| ID type | Example | Lives on |
|---|---|---|
| Wahapedia datasheet ID (9-digit) | `000002686` | `minis.datasheet_id` *and* `minis.unit_bsdata_id` |
| Wahapedia faction code | `CSM`, `SM` | `catalogue_units.faction_id`, `favourite_factions`, army/box tags |
| Catalogue model ID (`MD-`) | `MD-50836` | `minis.catalogue_model_id` |

> **Legacy column names.** `catalogue_units.bsdata_id`, `minis.unit_bsdata_id`,
> `army_units.unit_bsdata_id`, and `arsenal_weapon.weapon_bsdata_id` are a deliberate legacy
> misnomer — they now hold Wahapedia ids, not BSData GUIDs. The names were kept to avoid
> touching ~30 query sites; `minis.datasheet_id` and `minis.unit_bsdata_id` hold the same
> Wahapedia id for every row. Space Marine chapters are restored on top of Wahapedia's single
> `SM` faction by `data_store._apply_chapter_rollup()` at load time (chapter ids look like
> `SM::Blood Angels`). See [`CODEX_ARMORUM_ARCHITECTURE.md`](CODEX_ARMORUM_ARCHITECTURE.md)
> for the full reference.

---

## 9. Database schema (entity map)

`db.py` creates two families of tables in `collection.db`: **user data** (never drop) and
**Wahapedia import** (safe to rebuild). The Arsenal owns a third group via `arsenal_store.py`.

```mermaid
erDiagram
    minis ||--o{ photos : "has"
    minis }o--|| catalogue_units : "unit_bsdata_id"
    minis }o--o| custom_box_set_contents : "created from box"
    purchases }o--|| custom_box_sets : "box_set_id"
    custom_box_sets ||--o{ custom_box_set_contents : "contains"
    army_lists ||--o{ army_units : "contains"
    catalogue_factions ||--o{ catalogue_units : "faction_id"
    catalogue_units }o--o{ catalogue_weapons : "catalogue_unit_weapons"
    arsenal_weapon ||--o{ arsenal_weapon_photo : "has"
    arsenal_weapon ||--o{ arsenal_weapon_datasheet : "linked to datasheets"

    minis {
        text id PK
        text datasheet_id "Wahapedia ID"
        text unit_bsdata_id "Wahapedia ID (legacy name)"
        text catalogue_model_id "MD- id"
        text stage "paint stage"
        text wargear
        text multikit_group
    }
    purchases {
        text id PK
        text box_set_id
        int quantity
    }
    army_lists {
        text id PK
        text faction_id
        text detachment_id
        int points_limit
    }
    catalogue_units {
        text bsdata_id PK
        text faction_id FK
        int points
    }
```

| Group | Tables | Lifecycle |
|---|---|---|
| **User data** | `minis`, `photos`, `unit_wip`, `unit_wip_photos`, `favourite_factions`, `purchases`, `custom_box_sets`, `custom_box_set_contents`, `army_lists`, `army_units` | Back up — never drop |
| **Arsenal** | `arsenal_weapon`, `arsenal_weapon_photo`, `arsenal_weapon_datasheet` | User data |
| **Wahapedia import** | `catalogue_factions`, `catalogue_units`, `catalogue_weapons`, `catalogue_unit_weapons` | Drop & rebuild via importer |

---

## 10. Key user flows (end to end)

### 10a. Browse: faction → unit → mini

```mermaid
sequenceDiagram
    participant U as User
    participant SPA as SPA (JS)
    participant API as Flask /api
    participant DS as data_store + collection
    participant DB as collection.db

    U->>SPA: open / (My Armies)
    SPA->>API: GET /api/factions
    API->>DS: factions + owned/bought/unlogged
    DS->>DB: query minis, purchases
    API-->>SPA: faction grid JSON
    U->>SPA: click faction tile (#/faction/:fid)
    SPA->>API: GET /api/collection?faction_id=…  + /api/factions/:fid/units
    API-->>SPA: owned minis + roster
    U->>SPA: click a unit tile (#/mini/:did)
    SPA->>API: GET /api/units/:did (+ minis)
    API-->>SPA: datasheet + this unit's minis
    U->>SPA: edit label / gear / photo / stage
    SPA->>API: POST /api/minis/:mid · PATCH …/stage
    API->>DB: update mini row
```

### 10b. Logging a purchase creates minis

```mermaid
sequenceDiagram
    participant U as User
    participant P as purchases.js
    participant API as Flask /api
    participant BOX as box_sets.py
    participant DB as collection.db

    U->>P: pick/define a box set + quantity
    P->>API: POST /api/purchases
    API->>BOX: record purchase
    BOX->>DB: INSERT purchases row
    BOX->>DB: INSERT one minis row per model<br/>(stage='unbuilt', multikit pools where needed)
    API-->>P: updated purchase list + ledger
    Note over P,API: New minis now appear on the<br/>faction roster and Paint Progress
```

### 10c. Paint progress & the live ledger

```mermaid
sequenceDiagram
    participant U as User
    participant V as unit.js / mini-page.js
    participant API as Flask /api
    participant H as header.js (ledger)

    U->>V: change a mini's stage
    V->>API: PATCH /api/minis/:mid/stage
    API-->>V: ok
    V->>H: refreshLedger()
    H->>API: GET /api/collection/summary
    API-->>H: Bought / Unbuilt / Finished counts
    Note over U: /collection page reads the same<br/>data for the stats dashboard
```

### 10d. Arsenal — weapons linked to datasheets

```mermaid
sequenceDiagram
    participant U as User
    participant UP as Unit page (unit.js)
    participant AH as arsenal-hover.js
    participant BP as /arsenal blueprint
    participant AS as arsenal_store.py

    U->>UP: hover a weapon name
    UP->>AH: trigger popover
    AH->>BP: GET /arsenal/api/weapon-card
    BP->>AS: look up weapon by name/datasheet
    AS-->>BP: weapon card (profile + photo)
    BP-->>AH: HTML card
    Note over U,BP: /arsenal/loadouts manages weapons;<br/>arsenal_weapon_datasheet links them<br/>to datasheet IDs
```

---

## 11. Lifecycle: from clone to running app

```mermaid
flowchart LR
    A["git clone"] --> B["pip install -r requirements.txt"]
    B --> C["python scripts/fetch_wahapedia.py<br/>→ download CSVs into data/"]
    C --> D["python wahapedia_importer.py<br/>→ populate catalogue_* tables"]
    D --> E["python app.py"]
    E --> F["init_db() creates/migrates tables<br/>+ data_store builds the unit index & chapter rollup"]
    F --> G["http://127.0.0.1:5050"]
    G --> H["Seal Vault → POST /api/shutdown"]
```

`init_db()` (in `db.py`) runs on startup and is **idempotent** — it creates missing tables
and applies in-place `ALTER TABLE` migrations, so an existing `collection.db` upgrades
cleanly. The Wahapedia import is the only step you re-run by hand, and only to pick up
ruleset updates.

---

## 12. Where to look when…

| You want to change… | Start in |
|---|---|
| A page's layout / wording | `templates/…` + the matching `static/js/…` module |
| The faction grid or rosters | `home.js` ↔ `app.py` `/api/factions*` |
| How a datasheet renders | `unit.js` + `datasheet.js` + `ruletext.js` |
| How a purchase becomes minis | `box_sets.py` + `purchases.js` |
| Paint stages / progress stats | `collection.js`, `mini-page.js`, `/api/minis/:id/stage`, `/api/collection` |
| Army building & points | `army.py` + `army-*.js` |
| Wargear/weapons (Arsenal) | `arsenal.py` + `arsenal_store.py` + `templates/arsenal/` |
| Unit stats/points source data | `wahapedia_importer.py` → `catalogue_*` → `data_store.py` |
| Detachments / enhancements | `data/Detachments.csv`, `data/Enhancements.csv` |
| Physical model releases / images | `catalogue_review.py` + `data/model_catalogue_*.json` |
| The edition timeline (Codex Archive) | `editions.py` + `data/editions_timeline.json` + `history.js` |
| Space Marine chapter rollup | `data_store._apply_chapter_rollup()` |
| DB schema / a new column | `db.py` (add CREATE + a guarded `ALTER TABLE`) |

---

*Last reviewed: June 2026. Update this document when routes, frontend modules, or the
request flow change. For data-source and migration details, see
[`CODEX_ARMORUM_ARCHITECTURE.md`](CODEX_ARMORUM_ARCHITECTURE.md).*
