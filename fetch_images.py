"""Optional: populate cache/images/ with reference photos for each unit.

Usage:
    python fetch_images.py                # all factions
    python fetch_images.py SM ORK NEC     # only these faction ids
    python fetch_images.py --limit 20 AE  # cap how many to fetch

How it works: each datasheet in the export carries a `link` to its page on
Wahapedia (a community rules reference that mirrors the official datasheets and
hosts a model photo per unit). This script fetches that page, finds the unit's
image and saves it as cache/images/<datasheet_id>.<ext>. Already-cached units are
skipped, so the run is resumable. If the site layout changes or you are offline,
the app simply falls back to its themed placeholder for any missing image.

Note on images: model photos belong to Games Workshop / the source site. This
tool caches them locally for your personal collection reference only.
"""
import os
import re
import sys
import time
import urllib.request
from urllib.parse import urljoin

from data_store import get_store

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache", "images")
os.makedirs(CACHE_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (personal-collection-tool)"}
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)


def cached(did):
    return any(os.path.exists(os.path.join(CACHE_DIR, did + e))
               for e in (".jpg", ".jpeg", ".png", ".webp"))


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read() if binary else r.read().decode("utf-8", "ignore")


def pick_image(html, page_url, faction_slug):
    """Return the most likely unit-photo URL from a datasheet page."""
    candidates = []
    for src in IMG_RE.findall(html):
        low = src.lower()
        if low.endswith((".svg",)) or "icon" in low or "logo" in low:
            continue
        if not low.endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        score = 0
        if faction_slug and faction_slug in low:
            score += 3
        if "/img/" in low or "datasheet" in low or "/wh40k" in low:
            score += 2
        candidates.append((score, urljoin(page_url, src)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    store = get_store()
    faction_ids = args or [f["id"] for f in store.faction_list()]

    done = 0
    for fid in faction_ids:
        sheets = [d for d in store.ds_by_faction.get(fid, []) if not d["virtual_bool"]]
        slug = ""
        if sheets and sheets[0].get("link"):
            m = re.search(r"/factions/([^/]+)/", sheets[0]["link"])
            slug = m.group(1) if m else ""
        print(f"\n[{fid}] {len(sheets)} units (slug: {slug or '?'})")
        for d in sheets:
            if limit is not None and done >= limit:
                print("reached --limit"); return
            did, link = d["id"], d.get("link", "")
            if cached(did):
                continue
            if not link:
                print(f"  - {d['name']}: no link, skipped"); continue
            try:
                html = fetch(link)
                img_url = pick_image(html, link, slug)
                if not img_url:
                    print(f"  ? {d['name']}: no image found"); continue
                data = fetch(img_url, binary=True)
                ext = os.path.splitext(img_url.split("?")[0])[1].lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                    ext = ".jpg"
                with open(os.path.join(CACHE_DIR, did + ext), "wb") as fh:
                    fh.write(data)
                done += 1
                print(f"  + {d['name']}  ({len(data)//1024} KB)")
                time.sleep(0.8)  # be polite
            except Exception as e:
                print(f"  ! {d['name']}: {e}")
    print(f"\nDone. {done} images fetched into {CACHE_DIR}")


if __name__ == "__main__":
    main()
