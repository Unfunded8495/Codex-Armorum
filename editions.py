"""Loader for the hand-curated Warhammer 40,000 edition timeline.

editions_timeline.json is curated source data, treated like the model_catalogue_*
JSONs: copied on every migration, never regenerated from BSData. The file is the
edition authority — model releases in model_catalogue_manual.json hang off it via
their release_date / release_year and the per-edition era ranges.

Mirrors the read-once, cache-by-mtime loader style used by data_store and
catalogue_review. No database table is involved.
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
EDITIONS_PATH = os.path.join(BASE, "data", "editions_timeline.json")

_CACHE = {}


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def editions_document():
    """Return the whole timeline document with `editions` sorted by edition number."""
    key = _mtime(EDITIONS_PATH)
    cached = _CACHE.get("doc")
    if cached and cached[0] == key:
        return cached[1]
    try:
        with open(EDITIONS_PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {"schema_version": 1, "editions": []}
    editions = sorted(doc.get("editions", []), key=lambda e: e.get("edition", 0))
    doc = {**doc, "editions": editions}
    _CACHE["doc"] = (key, doc)
    return doc


def load_editions():
    """Return the editions list, sorted by edition number ascending."""
    return editions_document().get("editions", [])
