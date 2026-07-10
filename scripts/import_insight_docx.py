"""One-off importer: community rules articles (.docx) -> insights markdown.

Converts a folder of saved article documents (the "11th Rules Insight" pack:
Rules Deep Dive, Ruleshammer and Hammer of Math series) into:

- data/rules/insights/<slug>.md        hand-maintained article source
- static/images/insights/<name>        optimised article images (Pillow)
- data/rules/insights_images.json     image manifest {file: {width, height}}

The markdown then gets curated by hand (link remapping, cruft removal) and
built into data/rules/insights.json by scripts/build_insights.py. Re-running
the importer OVERWRITES the markdown, so only re-run it for a genuinely new
document drop, never to "refresh" curated articles.

Usage:  python scripts/import_insight_docx.py <folder-with-docx>

Needs Pillow (same optional dev dependency cutout.py uses); the app itself
never imports this.

Conversion notes, discovered from the pack itself:
- The docx are web clips with NO paragraph styles: headings are simply
  whole-paragraph bold runs, so heading detection is heuristic (all runs
  bold, shortish, not a list item).
- "(back to top)" navigation links are site cruft and are dropped here;
  every other hyperlink is kept verbatim for the curation pass.
- Em dashes are replaced per the project-wide ban.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from PIL import Image
except ImportError:  # pragma: no cover - dev tooling guard
    print("This importer needs Pillow (pip install Pillow); the app itself does not.")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
MD_DIR = ROOT / "data" / "rules" / "insights"
IMG_DIR = ROOT / "static" / "images" / "insights"
MANIFEST_PATH = ROOT / "data" / "rules" / "insights_images.json"

MAX_IMG_WIDTH = 1400
JPEG_QUALITY = 85

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
V = "{urn:schemas-microsoft-com:vml}"

# preferred page order: Deep Dive in game-flow order, then Ruleshammer
# deep dives, then the maths articles. Unlisted slugs sort by title at 90.
ARTICLE_ORDER = {
    "rules-deep-dive-core-concepts": 10,
    "rules-deep-dive-command-phase": 11,
    "rules-deep-dive-moving-and-the-movement-phase": 12,
    "rules-deep-dive-attacks-and-the-shooting-phase": 13,
    "rules-deep-dive-the-charge-and-fight-phases": 14,
    "rules-deep-dive-terrain-and-objectives": 15,
    "rules-deep-dive-special-unit-types": 16,
    "rules-deep-dive-core-stratagems-and-abilities": 17,
    "ruleshammer-shooting-range-line-of-sight-and-visibility": 30,
    "ruleshammer-charge-phase": 31,
    "ruleshammer-fight-phase": 32,
    "ruleshammer-save-groups-precision-and-feel-no-pain": 33,
    "ruleshammer-terrain-guide": 34,
    "ruleshammer-hidden-and-gone-to-ground-guide": 35,
    "hammer-of-math-the-benefit-of-cover": 50,
    "hammer-of-math-coherency-circles-and-triangles": 51,
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def clean_text(text: str) -> str:
    """Normalise a docx text node for markdown."""
    text = text.replace("—", " - ")     # em dash: banned project-wide
    text = text.replace(" ", " ")            # nbsp
    text = re.sub(r"[​‎‏﻿]", "", text)
    return text


def md_escape(text: str) -> str:
    """Escape characters markdown would misread mid-sentence."""
    return re.sub(r"([\\*_\[\]])", r"\\\1", text)


# ------------------------------------------------------------ title parsing

SERIES_PREFIXES = [
    ("11th Edition Rules Deep Dive", "Rules Deep Dive"),
    ("Ruleshammer 11th Edition", "Ruleshammer"),
    ("Ruleshammer", "Ruleshammer"),
    ("Hammer of Math 11th Edition", "Hammer of Math"),
    ("Hammer of Math", "Hammer of Math"),
]


def parse_name(stem: str) -> tuple[str, str, str]:
    """filename stem -> (series, topic, slug)."""
    series, rest = None, stem
    for prefix, name in SERIES_PREFIXES:
        if stem.lower().startswith(prefix.lower()):
            series, rest = name, stem[len(prefix):]
            break
    if series is None:
        series, rest = "Insight", stem
    rest = rest.strip(" -")
    rest = re.sub(r"^11th Edition\s*", "", rest, flags=re.I).strip(" -")
    rest = re.sub(r"\s*in 11th Edition$", "", rest, flags=re.I).strip()
    slug = slugify(f"{series} {rest}")
    return series, rest, slug


# ------------------------------------------------------------- docx parsing

class DocxDoc:
    def __init__(self, path: Path):
        self.zip = zipfile.ZipFile(path)
        self.body = ET.fromstring(self.zip.read("word/document.xml")).find(W + "body")
        rels = ET.fromstring(self.zip.read("word/_rels/document.xml.rels"))
        self.rels = {rel.get("Id"): rel.get("Target") for rel in rels}
        self.ordered_nums = self._ordered_num_ids()

    def _ordered_num_ids(self) -> set[str]:
        """numId values whose level-0 format is a numbered (not bullet) list."""
        try:
            numbering = ET.fromstring(self.zip.read("word/numbering.xml"))
        except KeyError:
            return set()
        fmt_by_abstract: dict[str, str] = {}
        for an in numbering.findall(W + "abstractNum"):
            lvl0 = an.find(f"{W}lvl[@{W}ilvl='0']")
            fmt = lvl0.find(W + "numFmt") if lvl0 is not None else None
            fmt_by_abstract[an.get(W + "abstractNumId")] = (
                fmt.get(W + "val") if fmt is not None else "bullet")
        ordered = set()
        for num in numbering.findall(W + "num"):
            ref = num.find(W + "abstractNumId")
            if ref is not None and fmt_by_abstract.get(ref.get(W + "val")) not in (
                    "bullet", None):
                ordered.add(num.get(W + "numId"))
        return ordered

    def media_bytes(self, rid: str) -> tuple[str, bytes] | None:
        target = self.rels.get(rid)
        if not target:
            return None
        name = "word/" + target.lstrip("/")
        try:
            return target.rsplit("/", 1)[-1], self.zip.read(name)
        except KeyError:
            return None


class ImageStore:
    """Optimises and dedupes article images across the whole import run."""

    def __init__(self):
        IMG_DIR.mkdir(parents=True, exist_ok=True)
        self.by_hash: dict[str, str] = {}      # sha1 -> final filename
        # merge into the existing manifest so importing a single new article
        # does not drop the entries for every article already converted
        self.manifest: dict[str, dict] = {}    # filename -> {width, height}
        if MANIFEST_PATH.exists():
            self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.counters: dict[str, int] = {}
        self.warnings: list[str] = []

    def add(self, slug: str, raw: bytes, src_name: str) -> str | None:
        digest = hashlib.sha1(raw).hexdigest()
        if digest in self.by_hash:
            return self.by_hash[digest]
        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
        except Exception as exc:
            self.warnings.append(f"unreadable image {src_name} in {slug}: {exc}")
            return None
        if img.width > MAX_IMG_WIDTH:
            img = img.resize(
                (MAX_IMG_WIDTH, round(img.height * MAX_IMG_WIDTH / img.width)),
                Image.LANCZOS)
        alpha = "A" in img.getbands() and img.getchannel("A").getextrema()[0] < 255
        self.counters[slug] = self.counters.get(slug, 0) + 1
        base = f"{slug}-{self.counters[slug]:02d}"
        if alpha:
            name = base + ".png"
            img.save(IMG_DIR / name, "PNG", optimize=True)
        else:
            name = base + ".jpg"
            img.convert("RGB").save(IMG_DIR / name, "JPEG",
                                    quality=JPEG_QUALITY, optimize=True)
        self.by_hash[digest] = name
        self.manifest[name] = {"width": img.width, "height": img.height}
        return name


# ------------------------------------------------------- paragraph -> lines

BACK_TO_TOP = re.compile(r"^\s*\(?\s*back to top\s*\)?\s*$", re.I)


def run_pieces(doc: DocxDoc, node, link: str | None, out: list[dict]):
    """Walk inline content in document order, collecting text/image pieces."""
    for child in node:
        tag = child.tag
        if tag == W + "hyperlink":
            rid = child.get(R + "id")
            anchor = child.get(W + "anchor")
            target = doc.rels.get(rid) if rid else (f"#{anchor}" if anchor else None)
            run_pieces(doc, child, target or link, out)
        elif tag == W + "r":
            rpr = child.find(W + "rPr")
            bold = rpr is not None and rpr.find(W + "b") is not None
            italic = rpr is not None and rpr.find(W + "i") is not None
            for el in child:
                if el.tag == W + "t":
                    out.append({"kind": "text", "text": clean_text(el.text or ""),
                                "bold": bold, "italic": italic, "link": link})
                elif el.tag in (W + "br", W + "tab", W + "cr"):
                    out.append({"kind": "text", "text": " ", "bold": False,
                                "italic": False, "link": link})
                elif el.tag == W + "drawing":
                    blip = el.find(f".//{A}blip")
                    if blip is not None:
                        alt = ""
                        for pr in el.iter():
                            if pr.tag.endswith("}docPr"):
                                alt = pr.get("descr") or ""
                                break
                        out.append({"kind": "image",
                                    "rid": blip.get(R + "embed"), "alt": alt})
                elif el.tag == W + "pict":
                    data = el.find(f".//{V}imagedata")
                    if data is not None:
                        out.append({"kind": "image",
                                    "rid": data.get(R + "id"), "alt": ""})
        else:
            run_pieces(doc, child, link, out)


def pieces_to_md(pieces: list[dict]) -> str:
    """Merge adjacent same-format text pieces and emit inline markdown."""
    merged: list[dict] = []
    for p in pieces:
        if (merged and p["kind"] == "text" and merged[-1]["kind"] == "text"
                and all(merged[-1][k] == p[k] for k in ("bold", "italic", "link"))):
            merged[-1]["text"] += p["text"]
        else:
            merged.append(dict(p))
    out = []
    for p in merged:
        if p["kind"] != "text":
            continue
        text = p["text"]
        if not text:
            continue
        lead = " " if text != text.lstrip() else ""
        trail = " " if text != text.rstrip() and text.strip() else ""
        body = md_escape(text.strip())
        if not body:
            out.append(" ")
            continue
        if p["bold"] and p["italic"]:
            body = f"***{body}***"
        elif p["bold"]:
            body = f"**{body}**"
        elif p["italic"]:
            body = f"*{body}*"
        if p["link"]:
            if BACK_TO_TOP.match(text):
                body = ""            # site navigation cruft, drop entirely
            else:
                body = f"[{body}]({p['link']})"
        out.append(lead + body + trail)
    text = "".join(out)
    text = re.sub(r"  +", " ", text).strip()
    text = re.sub(r"\s*\(\s*\)\s*$", "", text)   # empty () left by dropped links
    return text


def para_meta(doc: DocxDoc, p) -> dict:
    ppr = p.find(W + "pPr")
    meta = {"list": None, "level": 0, "ordered": False}
    if ppr is not None:
        numpr = ppr.find(W + "numPr")
        if numpr is not None:
            ilvl = numpr.find(W + "ilvl")
            numid = numpr.find(W + "numId")
            meta["list"] = True
            meta["level"] = int(ilvl.get(W + "val")) if ilvl is not None else 0
            meta["ordered"] = (numid is not None
                               and numid.get(W + "val") in doc.ordered_nums)
    return meta


def is_heading(pieces: list[dict], meta: dict, text: str) -> bool:
    if meta["list"] or not text or len(text) > 120:
        return False
    has_text = False
    for p in pieces:
        if p["kind"] == "text" and p["text"].strip():
            has_text = True
            if not p["bold"]:
                return False
    return has_text


def table_to_md(doc: DocxDoc, tbl) -> list[str]:
    rows = []
    for tr in tbl.findall(W + "tr"):
        cells = []
        for tc in tr.findall(W + "tc"):
            parts = []
            for p in tc.findall(W + "p"):
                pieces: list[dict] = []
                run_pieces(doc, p, None, pieces)
                t = pieces_to_md(pieces)
                if t:
                    parts.append(t)
            cells.append(" ".join(parts) or " ")
        rows.append(cells)
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [" "] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |",
           "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return out


def convert(path: Path, store: ImageStore) -> dict:
    series, topic, slug = parse_name(path.stem)
    doc = DocxDoc(path)
    lines: list[str] = []
    links: list[tuple[str, str]] = []

    for block in doc.body:
        if block.tag == W + "tbl":
            lines += [""] + table_to_md(doc, block) + [""]
            continue
        if block.tag != W + "p":
            continue
        pieces: list[dict] = []
        run_pieces(doc, block, None, pieces)
        meta = para_meta(doc, block)

        # images first: emit each on its own line, in place
        text_pieces = []
        for p in pieces:
            if p["kind"] == "image":
                media = doc.media_bytes(p["rid"])
                if media is None:
                    store.warnings.append(f"missing media rel {p['rid']} in {slug}")
                    continue
                name = store.add(slug, media[1], media[0])
                if name:
                    lines += ["", f"![{p['alt']}]({name})", ""]
            else:
                text_pieces.append(p)

        text = pieces_to_md(text_pieces)
        if not text:
            continue
        for m in re.finditer(r"\[([^\]]*)\]\(([^)]+)\)", text):
            links.append((m.group(1), m.group(2)))

        if is_heading(text_pieces, meta, text):
            head = re.sub(r"^\*\*(.*)\*\*$", r"\1", text)
            head = re.sub(r"\s*\\?\[?\(?back to top\)?\\?\]?.*$", "", head,
                          flags=re.I).strip()
            lines += ["", f"## {head}", ""]
        elif meta["list"]:
            marker = "1." if meta["ordered"] else "-"
            lines.append("  " * meta["level"] + f"{marker} {text}")
        else:
            lines += [text, ""]

    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    order = ARTICLE_ORDER.get(slug, 90)
    md = (f"# {series}: {topic}\n"
          f"Series: {series}\n"
          f"Slug: {slug}\n"
          f"Order: {order}\n"
          f"Source-Doc: {path.name}\n\n"
          f"{body}\n")
    MD_DIR.mkdir(parents=True, exist_ok=True)
    (MD_DIR / f"{slug}.md").write_text(md, encoding="utf-8")
    return {"slug": slug, "title": f"{series}: {topic}", "links": links,
            "words": len(body.split())}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    files = sorted(src.glob("*.docx"))
    if not files:
        print(f"no .docx files under {src}")
        return 2
    store = ImageStore()
    all_links: list[tuple[str, str, str]] = []
    for f in files:
        info = convert(f, store)
        print(f"{info['slug']:58s} {info['words']:>6} words")
        all_links += [(info["slug"], t, u) for t, u in info["links"]]
    MANIFEST_PATH.write_text(
        json.dumps(store.manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(store.manifest)} images -> {IMG_DIR}")
    print(f"manifest -> {MANIFEST_PATH}")
    if all_links:
        print(f"\n{len(all_links)} hyperlinks kept for curation:")
        for slug, text, url in all_links:
            print(f"  [{slug}] {text!r} -> {url}")
    for wmsg in store.warnings:
        print("WARN:", wmsg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
