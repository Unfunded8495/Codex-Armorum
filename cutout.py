#!/usr/bin/env python3
"""
cutout.py  —  batch background remover for the Codex Armorum model photos.

Most catalogue photos are a miniature on a near-white studio sweep. This script
removes that background and writes a transparent WebP, so the redesigned faction
tiles can sit the model in a dark "display niche" instead of a white box.

Algorithm (matches the redesign mockups):
  1. Flood-fill from the image border, 8-connected, clearing near-white pixels.
     This removes the open background but leaves white *pockets* trapped between
     bases / limbs untouched.
  2. A global pass then clears any remaining near-pure studio white anywhere,
     which catches those enclosed pockets. The threshold here is strict enough
     to spare off-white painted details (scrolls, purity seals) on the model.
  3. A 1px fringe softening pass feathers the cut edge.

Output goes to  cache/images/cutouts/<catalogue_model_id>.webp
The app.py patch serves these when a tile requests `?cut=1`; if a cutout is
missing the app falls back to the original photo automatically, so you can run
this incrementally and nothing breaks in the meantime.

Usage:
    python cutout.py                 # process every catalogue image (skip done)
    python cutout.py --force         # re-process even if a cutout exists
    python cutout.py --id MD-50635   # just one model
    python cutout.py --max-width 480 # output longest-edge cap (default 480)

Requires Pillow:  pip install Pillow
"""

import argparse
import json
import os
from collections import deque

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
CATALOGUE_DIR = os.path.join(BASE, "cache", "images", "catalogue")
CUTOUT_DIR = os.path.join(BASE, "cache", "images", "cutouts")
IMAGES_JSON = os.path.join(BASE, "data", "model_catalogue_images.json")

# --- tuning ----------------------------------------------------------------
FLOOD_MIN = 206      # flood-fill: channel floor for "background" (lenient, bridges soft shadow)
FLOOD_SAT = 34       # flood-fill: max saturation (max-min channel) to count as background
GLOBAL_MIN = 225     # global pass: channel floor for pure studio white (strict)
GLOBAL_SAT = 20      # global pass: max saturation
FRINGE_MIN = 208     # fringe: light-pixel floor to feather when touching transparency
FRINGE_SAT = 30
FRINGE_ALPHA = 80    # alpha to leave feathered fringe pixels at


def _sat(r, g, b):
    return max(r, g, b) - min(r, g, b)


def cut_image(src_path, dest_path, max_width=480, quality=86):
    img = Image.open(src_path).convert("RGBA")
    w, h = img.size
    if w > max_width:
        scale = max_width / w
        img = img.resize((max_width, round(h * scale)), Image.LANCZOS)
        w, h = img.size

    px = bytearray(img.tobytes())  # RGBA, row-major
    n = w * h

    def idx(i):
        return i * 4

    # 1) edge flood fill, 8-connected
    visited = bytearray(n)
    q = deque()
    for x in range(w):
        q.append(x)
        q.append((h - 1) * w + x)
    for y in range(h):
        q.append(y * w)
        q.append(y * w + w - 1)
    while q:
        p = q.popleft()
        if visited[p]:
            continue
        visited[p] = 1
        i = idx(p)
        r, g, b = px[i], px[i + 1], px[i + 2]
        if not (r > FLOOD_MIN and g > FLOOD_MIN and b > FLOOD_MIN and _sat(r, g, b) < FLOOD_SAT):
            continue
        px[i + 3] = 0
        x, y = p % w, p // w
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                np_ = ny * w + nx
                if not visited[np_]:
                    q.append(np_)

    # 2) global near-pure-white removal (enclosed pockets)
    for p in range(n):
        i = idx(p)
        if px[i + 3] == 0:
            continue
        r, g, b = px[i], px[i + 1], px[i + 2]
        if r > GLOBAL_MIN and g > GLOBAL_MIN and b > GLOBAL_MIN and _sat(r, g, b) < GLOBAL_SAT:
            px[i + 3] = 0

    # 3) fringe softening
    alpha0 = bytes(px[idx(p) + 3] for p in range(n))
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            p = y * w + x
            if alpha0[p] == 0:
                continue
            i = idx(p)
            r, g, b = px[i], px[i + 1], px[i + 2]
            if r > FRINGE_MIN and g > FRINGE_MIN and b > FRINGE_MIN and _sat(r, g, b) < FRINGE_SAT:
                if (alpha0[p - 1] == 0 or alpha0[p + 1] == 0
                        or alpha0[p - w] == 0 or alpha0[p + w] == 0):
                    px[i + 3] = FRINGE_ALPHA

    out = Image.frombytes("RGBA", (w, h), bytes(px))
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    out.save(dest_path, "WEBP", quality=quality, method=6)
    return out.size


def iter_catalogue_ids(only_id=None):
    """Yield (catalogue_model_id, source_path) for every catalogue image on disk."""
    if only_id:
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            # files are stored as <id>-<hash><ext>; match by prefix
            for name in os.listdir(CATALOGUE_DIR):
                if name.startswith(only_id) and name.lower().endswith(ext):
                    yield only_id, os.path.join(CATALOGUE_DIR, name)
                    return
        return
    # map id -> local_path via the images json (authoritative), fall back to dir scan
    if os.path.exists(IMAGES_JSON):
        data = json.load(open(IMAGES_JSON, encoding="utf-8"))
        for row in data.get("images", []):
            cid = row.get("catalogue_model_id")
            lp = row.get("local_path")
            if not cid or not lp:
                continue
            src = os.path.join(BASE, lp)
            if os.path.exists(src):
                yield cid, src
    else:
        for name in sorted(os.listdir(CATALOGUE_DIR)):
            if name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                cid = name.split("-")[0] if "-" in name else os.path.splitext(name)[0]
                yield cid, os.path.join(CATALOGUE_DIR, name)


def main():
    ap = argparse.ArgumentParser(description="Batch background remover for model photos.")
    ap.add_argument("--force", action="store_true", help="re-process even if a cutout exists")
    ap.add_argument("--id", help="process a single catalogue_model_id")
    ap.add_argument("--max-width", type=int, default=480, help="output longest-edge cap (px)")
    ap.add_argument("--quality", type=int, default=86, help="WebP quality (1-100)")
    args = ap.parse_args()

    if not os.path.isdir(CATALOGUE_DIR):
        raise SystemExit(f"Catalogue image dir not found: {CATALOGUE_DIR}")

    done = skipped = failed = 0
    for cid, src in iter_catalogue_ids(args.id):
        dest = os.path.join(CUTOUT_DIR, f"{cid}.webp")
        if os.path.exists(dest) and not args.force:
            skipped += 1
            continue
        try:
            size = cut_image(src, dest, args.max_width, args.quality)
            done += 1
            print(f"  cut {cid}  -> {size[0]}x{size[1]}")
        except Exception as e:  # noqa: BLE001 — keep going on a bad file
            failed += 1
            print(f"  FAIL {cid}: {e}")

    print(f"\nDone. {done} cut, {skipped} already present, {failed} failed.")
    print(f"Cutouts in: {CUTOUT_DIR}")


if __name__ == "__main__":
    main()
