"""Import Lexicanum miniature gallery images for the local model catalogue.

Lexicanum blocks the normal MediaWiki API, but miniature pages expose raw wiki
markup with ``?action=raw``. This script parses gallery rows, matches them to
resolved catalogue model releases, and downloads thumbnails into the local cache.
It is resumable and intentionally slow by default because Lexicanum's robots.txt
declares a crawl delay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from difflib import SequenceMatcher


BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")
CACHE_DIR = os.path.join(BASE, "cache", "images", "catalogue")
CATALOGUE_PATH = os.path.join(DATA_DIR, "model_catalogue_manual.json")
RESOLUTIONS_PATH = os.path.join(DATA_DIR, "model_catalogue_resolutions.json")
IMAGES_PATH = os.path.join(DATA_DIR, "model_catalogue_images.json")
LEX_BASE = "https://wh40k.lexicanum.com"
USER_AGENT = "Warhammer-Catalogue local image cache/0.1"


LEXICANUM_PAGES = {
    "Adepta Sororitas": "Miniatures: Adepta Sororitas",
    "Adeptus Custodes": "Miniatures: Adeptus Custodes (Warhammer 40,000)",
    "Adeptus Mechanicus": "Miniatures: Adeptus Mechanicus",
    "Astra Militarum": "Miniatures: Astra Militarum",
    "Blood Angels": "Miniatures: Blood Angels",
    "Chaos Daemons": "Miniatures: Chaos Daemons",
    "Chaos Knights": "Miniatures: Chaos Knights",
    "Chaos Space Marines": "Miniatures: Chaos Space Marines",
    "Craftworlds": "Miniatures: Eldar",
    "Dark Angels": "Miniatures: Dark Angels",
    "Death Guard": "Miniatures: Death Guard",
    "Deathwatch": "Miniatures: Deathwatch",
    "Drukhari": "Miniatures: Dark Eldar",
    "Genestealer Cult": "Miniatures: Genestealer Cults",
    "Grey Knights": "Miniatures: Grey Knights",
    "Harlequins": "Miniatures: Harlequins",
    "Imperial Assassins": "Miniatures: Imperial Forces",
    "Imperial Knights": "Miniatures: Imperial Knights",
    "Inquisition": "Miniatures: Imperial Forces",
    "Necrons": "Miniatures: Necrons",
    "Orks": "Miniatures: Orks",
    "Space Marines": "Miniatures: Space Marines",
    "Space Wolves": "Miniatures: Space Wolves",
    "Tau Empire": "Miniatures: Tau",
    "Thousand Sons": "Miniatures: Thousand Sons",
    "Tyranids": "Miniatures: Tyranids",
    "Ynnari": "Miniatures: Eldar",
}


last_request_at = 0.0


def load_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return fallback


def write_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def request_url(url, crawl_delay):
    global last_request_at
    wait = crawl_delay - (time.time() - last_request_at)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = resp.read()
        content_type = resp.headers.get("content-type", "")
    last_request_at = time.time()
    return body, content_type


def wiki_url(title, raw=False):
    title = title.replace(" ", "_")
    url = f"{LEX_BASE}/wiki/{urllib.parse.quote(title, safe=':_()')}"
    if raw:
        url += "?action=raw"
    return url


def normalise_name(value):
    text = str(value or "").lower()
    text = text.replace("\u2019", "'").replace("\ufffd", "")
    text = text.replace("t'au", "tau").replace("t\u2019au", "tau")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    drop = {"a", "an", "and", "kit", "model", "models", "of", "or", "set", "the", "with"}
    words = []
    for word in text.split():
        if word in drop:
            continue
        if len(word) > 3 and word.endswith("s"):
            word = word[:-1]
        words.append(word)
    return " ".join(words)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "image"


def clean_caption(text):
    text = re.sub(r"\{\{Fn\|[^}]+\}\}", " ", text)
    text = re.sub(r"\{\{[^}]+\}\}", " ", text)
    text = re.sub(r"'''? ?", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def linked_names(caption):
    names = []
    for body in re.findall(r"\[\[([^\]]+)\]\]", caption):
        parts = body.split("|")
        names.append(parts[-1].strip())
    plain = clean_caption(re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", caption))
    plain = clean_caption(re.sub(r"\[\[([^\]]+)\]\]", r"\1", plain))
    if plain:
        names.append(plain)
    return [n for n in names if n]


def image_key(filename):
    value = filename.strip()
    value = re.sub(r"^(Image|File):", "", value, flags=re.I)
    value = value.replace(" ", "_")
    return urllib.parse.unquote(value)


def parse_gallery_entries(raw, page_title):
    entries = []
    current_year = None
    in_gallery = False
    for line in raw.splitlines():
        year_match = re.match(r"^;\s*((?:19|20)\d{2})", line)
        if year_match:
            current_year = int(year_match.group(1))
        if "<gallery" in line:
            in_gallery = True
            continue
        if "</gallery" in line:
            in_gallery = False
            continue
        if not in_gallery or "|" not in line:
            continue
        image_part, caption = line.split("|", 1)
        image_part = image_part.strip()
        if not re.search(r"\.(jpe?g|png|gif|webp)$", image_part, re.I):
            continue
        filename = image_key(image_part)
        entries.append({
            "page_title": page_title,
            "page_url": wiki_url(page_title),
            "release_year": current_year,
            "filename": filename,
            "file_page_url": f"{LEX_BASE}/wiki/File:{urllib.parse.quote(filename, safe='._-')}",
            "caption": clean_caption(caption),
            "names": linked_names(caption),
        })
    return entries


def image_src_map(html):
    out = {}
    for tag in re.findall(r"<img\b[^>]+>", html, re.I):
        src_match = re.search(r'\bsrc="([^"]+)"', tag)
        if not src_match:
            continue
        src = src_match.group(1)
        parts = urllib.parse.unquote(src).split("/")
        filename = ""
        if "/thumb/" in src and len(parts) >= 2:
            filename = parts[-2]
        elif parts:
            filename = parts[-1]
        if filename:
            out[filename] = urllib.parse.urljoin(LEX_BASE, src)
    return out


def original_image_url(thumbnail_url):
    """Convert a MediaWiki thumbnail URL to the original file URL when possible."""
    if not thumbnail_url:
        return ""
    parsed = urllib.parse.urlparse(thumbnail_url)
    path = urllib.parse.unquote(parsed.path)
    marker = "/mediawiki/images/thumb/"
    if marker not in path:
        return thumbnail_url
    tail = path.split(marker, 1)[1].split("/")
    if len(tail) < 3:
        return thumbnail_url
    original_path = "/mediawiki/images/" + "/".join(tail[:3])
    return urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        urllib.parse.quote(original_path, safe="/._-"),
        "",
        "",
        "",
    ))


def resolved_catalogue_items():
    catalogue = load_json(CATALOGUE_PATH, {"model_releases": []})
    resolutions = {
        r.get("catalogue_model_id"): r
        for r in load_json(RESOLUTIONS_PATH, {"resolutions": []}).get("resolutions", [])
    }
    items = []
    for record in catalogue.get("model_releases", []):
        resolution = resolutions.get(record.get("id"), {})
        if resolution.get("action") in {"exclude", "mark_accessory", "mark_box_product"}:
            continue
        items.append({
            "id": record.get("id", ""),
            "name": record.get("name", ""),
            "faction_label": record.get("faction_label", ""),
            "release_year": record.get("release_year"),
            "note": record.get("note", ""),
            "datasheet_names": [
                link.get("datasheet_name", "")
                for link in record.get("datasheet_links", [])
            ],
        })
    return items


def match_score(item, entry):
    names = [item["name"], *item.get("datasheet_names", [])]
    best = 0.0
    for left in names:
        left_norm = normalise_name(left)
        if not left_norm:
            continue
        for right in entry.get("names", []) + [entry.get("caption", "")]:
            right_norm = normalise_name(right)
            if not right_norm:
                continue
            if left_norm == right_norm:
                score = 1.0
            else:
                left_tokens = set(left_norm.split())
                right_tokens = set(right_norm.split())
                token_score = 0.0
                if left_tokens and right_tokens:
                    token_score = 2 * len(left_tokens & right_tokens) / (len(left_tokens) + len(right_tokens))
                score = max(token_score, SequenceMatcher(None, left_norm, right_norm).ratio())
            best = max(best, score)
    if entry.get("release_year") == item.get("release_year"):
        best += 0.15
    elif entry.get("release_year") and item.get("release_year") and abs(entry["release_year"] - item["release_year"]) <= 1:
        best += 0.05
    return min(best, 1.0)


def load_existing_images():
    data = load_json(IMAGES_PATH, {"images": []})
    return data, {row.get("catalogue_model_id"): row for row in data.get("images", [])}


def extension_from_url(url, content_type):
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        if path.endswith(ext) or f"{ext}/" in path:
            return ".jpg" if ext == ".jpeg" else ext
    if "png" in content_type:
        return ".png"
    if "gif" in content_type:
        return ".gif"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def local_filename(item_id, source_filename, ext):
    digest = hashlib.sha1(source_filename.encode("utf-8")).hexdigest()[:8]
    return f"{slug(item_id)}-{digest}{ext}"


def import_images(args):
    os.makedirs(CACHE_DIR, exist_ok=True)
    items = resolved_catalogue_items()
    pages_needed = sorted({LEXICANUM_PAGES.get(item["faction_label"]) for item in items})
    pages_needed = [p for p in pages_needed if p]
    if args.army:
        labels = {a.strip() for a in args.army.split(",") if a.strip()}
        pages_needed = sorted({LEXICANUM_PAGES.get(label) for label in labels if LEXICANUM_PAGES.get(label)})
        items = [item for item in items if item["faction_label"] in labels]

    entries_by_page = {}
    src_by_page = {}
    skipped_pages = []
    for page in pages_needed:
        try:
            raw_bytes, _ = request_url(wiki_url(page, raw=True), args.crawl_delay)
            html_bytes, _ = request_url(wiki_url(page), args.crawl_delay)
        except urllib.error.HTTPError as exc:
            skipped_pages.append({"page": page, "status": exc.code})
            print(f"skipped {page}: HTTP {exc.code}")
            continue
        except urllib.error.URLError as exc:
            skipped_pages.append({"page": page, "status": str(exc.reason)})
            print(f"skipped {page}: {exc.reason}")
            continue
        raw = raw_bytes.decode("utf-8", "replace")
        html = html_bytes.decode("utf-8", "replace")
        entries = parse_gallery_entries(raw, page)
        src_map = image_src_map(html)
        for entry in entries:
            entry["thumbnail_url"] = src_map.get(entry["filename"], "")
        entries_by_page[page] = entries
        src_by_page[page] = src_map
        print(f"{page}: {len(entries)} gallery entries")

    image_doc, image_by_id = load_existing_images()
    rows = [row for row in image_doc.get("images", [])]
    row_by_id = {row.get("catalogue_model_id"): row for row in rows}
    downloads = 0
    matched = 0

    for item in items:
        existing_row = row_by_id.get(item["id"], {})
        if (args.skip_existing and existing_row.get("local_path") and
                existing_row.get("image_url")):
            continue
        page = LEXICANUM_PAGES.get(item["faction_label"])
        if not page:
            continue
        best_entry = None
        best_score = 0.0
        for entry in entries_by_page.get(page, []):
            score = match_score(item, entry)
            if score > best_score:
                best_score = score
                best_entry = entry
        if not best_entry or best_score < args.min_score:
            continue
        matched += 1
        thumbnail_url = best_entry.get("thumbnail_url")
        original_url = original_image_url(thumbnail_url)
        if not original_url:
            continue

        existing = row_by_id.get(item["id"])
        local_path = existing.get("local_path") if existing else ""
        existing_source = existing.get("image_url") or existing.get("thumbnail_url") if existing else ""
        needs_original = existing_source and "/mediawiki/images/thumb/" in existing_source
        if (not local_path or needs_original or
                not os.path.exists(os.path.join(BASE, local_path))):
            if args.metadata_only:
                local_path = ""
            else:
                if args.limit and downloads >= args.limit:
                    continue
                body, content_type = request_url(original_url, args.crawl_delay)
                ext = extension_from_url(original_url, content_type)
                filename = local_filename(item["id"], best_entry["filename"], ext)
                abs_path = os.path.join(CACHE_DIR, filename)
                with open(abs_path, "wb") as fh:
                    fh.write(body)
                local_path = os.path.relpath(abs_path, BASE).replace("\\", "/")
                downloads += 1
                print(f"downloaded {downloads}: {item['name']} -> {local_path}")

        row = {
            "catalogue_model_id": item["id"],
            "model_name": item["name"],
            "faction_label": item["faction_label"],
            "release_year": item["release_year"],
            "match_confidence": round(best_score, 3),
            "caption": best_entry.get("caption", ""),
            "caption_names": best_entry.get("names", []),
            "lexicanum_page": best_entry.get("page_url", ""),
            "lexicanum_file": best_entry.get("filename", ""),
            "file_page_url": best_entry.get("file_page_url", ""),
            "thumbnail_url": thumbnail_url,
            "image_url": original_url,
            "local_path": local_path,
            "source": "Lexicanum miniature gallery",
        }
        row_by_id[item["id"]] = row

    merged = sorted(row_by_id.values(), key=lambda row: (row.get("faction_label", ""), row.get("model_name", ""), row.get("catalogue_model_id", "")))
    write_json(IMAGES_PATH, {
        "schema_version": 1,
        "source": {
            "site": "Lexicanum",
            "base_url": LEX_BASE,
            "crawl_delay_seconds": args.crawl_delay,
        },
        "summary": {
            "image_records": len(merged),
            "matched_this_run": matched,
            "downloaded_this_run": downloads,
            "skipped_pages_this_run": skipped_pages,
        },
        "images": merged,
    })
    print(f"Wrote {len(merged)} image records to {IMAGES_PATH}")
    print(f"Downloaded {downloads} images this run")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--army", help="Comma-separated catalogue faction labels, e.g. 'Tau Empire,Space Marines'")
    parser.add_argument("--limit", type=int, default=25, help="Maximum image downloads this run. 0 means no limit.")
    parser.add_argument("--crawl-delay", type=float, default=5.0)
    parser.add_argument("--min-score", type=float, default=0.82)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    args = parser.parse_args()
    import_images(args)


if __name__ == "__main__":
    main()
