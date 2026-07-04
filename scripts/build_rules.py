"""Build the Core Rules dataset for the /rules page.

Parses data/rules/wh40k_core_rules_combined.md (the merged app + PDF core
rules for 11th edition) into data/rules/core_rules.json:

- sections grouped into the printed book's five parts, each rendered to HTML
- every numbered rule (NN.NN) gets a stable anchor for deep links
- cross-references like "(03.03)" become in-page links
- defined game terms become tooltip links pointing at the defining rule
  (tooltip text is auto-extracted from that rule, so it never drifts)
- diagram headings are matched to the optimised images in
  static/images/rules/ via data/rules/images_manifest.json

Run after changing the source markdown:  python scripts/build_rules.py
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "rules"
MD_PATH = DATA / "wh40k_core_rules_combined.md"
MANIFEST_PATH = DATA / "images_manifest.json"
FLAVOUR_PATH = DATA / "flavour.json"
COMMENTARY_PATH = DATA / "commentary.md"
OUT_PATH = DATA / "core_rules.json"
IMG_URL = "/static/images/rules"

PART_TITLES = {
    "Basic Rules",
    "The Battle Round",
    "Battlefields and Tactics",
    "Advanced Rules",
    "Reference",
}

# ---------------------------------------------------------------- utilities

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def unescape_md(text: str) -> str:
    """The exporter backslash-escapes markdown punctuation; undo it."""
    return re.sub(r"\\([\[\].#*'\-])", r"\1", text)


SMALL_WORDS = {"and", "or", "of", "the", "to", "a", "an", "in", "on", "with",
               "for", "but", "at", "by", "from", "not", "be", "as"}
KEEP_UPPER = {"CP", "OC", "FAQ", "D6", "D3", "BS", "WS", "AP"}


def smart_title(text: str) -> str:
    """Title-case ALL-CAPS headings from the PDF; leave mixed case alone.
    Bracketed ability names ([ANTI] etc.) keep their official capitals."""
    if text != text.upper() or text.startswith("["):
        return text
    if text.upper() == "FAQS":
        return "FAQs"

    def cap(word: str, first: bool) -> str:
        if word.upper() in KEEP_UPPER:
            return word.upper()
        low = word.lower()
        if not first and low in SMALL_WORDS:
            return low
        return "-".join(p[:1].upper() + p[1:] for p in low.split("-"))

    words = text.split(" ")
    return " ".join(cap(w, i == 0) for i, w in enumerate(words))


# ---------------------------------------------------------------- line scan

RE_H1 = re.compile(r"^#\s+(.*)$")
RE_H2 = re.compile(r"^##\s+(.*)$")
RE_H3 = re.compile(r"^###\s+(.*)$")
RE_PAGEMARK = re.compile(r"^\*Page (\d+)[^*]*\*$")
RE_SEP = re.compile(r"^\\?---+$")
RE_FLAVOUR = re.compile(r"^\*\+\+\s*(.+?)\s*\+\+\*$")
RE_BULLET = re.compile(r"^([*\-•▪▫])\s+(.*)$")
RE_NUMBERED = re.compile(r"^(\d+)\\?\.\s+(.*)$")
RE_ILLUSTRATION = re.compile(r"^\\?\[.*\]$")
RE_RULE_HEAD = re.compile(
    r"^(.*?)\s*\((\d\d\.\d\d)\)(?:\s*[-–]\s*(\d+\s*CP))?$"
)
RE_HEAD_PREFIX = re.compile(r"^\d+\\?\.\s*")


def parse_blocks(lines: list[str]) -> list[dict]:
    """Turn a page chunk's body lines into typed blocks.

    The exporter leaks list indentation onto whole pages, so headings,
    separators and paragraphs can carry arbitrary leading whitespace;
    everything is classified on the stripped line, and bullet nesting is
    inferred from indent depth.
    """
    blocks: list[dict] = []
    para: list[str] = []
    open_list: dict | None = None

    def flush_para():
        nonlocal para
        if para:
            blocks.append({"t": "p", "text": " ".join(para)})
            para = []

    def close_list():
        nonlocal open_list
        open_list = None

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        indent = len(raw) - len(raw.lstrip(" "))
        i += 1

        if not line:
            flush_para()
            continue
        if RE_PAGEMARK.match(line) or RE_ILLUSTRATION.match(line):
            flush_para()
            close_list()
            continue
        if RE_SEP.match(line):
            flush_para()
            close_list()
            blocks.append({"t": "hr"})
            continue
        m = RE_FLAVOUR.match(line)
        if m:
            flush_para()
            close_list()
            blocks.append({"t": "flavour", "text": m.group(1)})
            continue
        m = RE_H3.match(line)
        if m:
            flush_para()
            close_list()
            blocks.append({"t": "h3", "text": m.group(1).strip()})
            continue
        m = RE_H2.match(line)
        if m:
            flush_para()
            close_list()
            blocks.append({"t": "h2", "text": m.group(1).strip()})
            continue
        if line.startswith("|"):
            flush_para()
            close_list()
            rows = [line]
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            blocks.append({"t": "table", "rows": rows})
            continue

        mb = RE_BULLET.match(line)
        mn = RE_NUMBERED.match(line) if not mb else None
        if mb or mn:
            flush_para()
            level = min(indent // 2, 3)
            item = {
                "level": level,
                "ordered": bool(mn),
                "text": (mb or mn).group(2).strip(),
                "extra": [],
            }
            if open_list is None:
                open_list = {"t": "list", "items": []}
                blocks.append(open_list)
            open_list["items"].append(item)
            continue

        # Plain text. Indented text while a numbered list is open is a
        # continuation paragraph of the last item; otherwise a paragraph.
        if open_list and indent >= 3 and open_list["items"] and (
            open_list["items"][-1]["ordered"]
        ):
            if para:
                open_list["items"][-1]["extra"].append(" ".join(para))
                para = []
            open_list["items"][-1]["extra"].append(line)
            continue
        if open_list and not para:
            close_list()
        para.append(line)

    flush_para()
    return blocks


# ------------------------------------------------------------ page chunking

def chunk_pages(text: str) -> list[dict]:
    chunks: list[dict] = []
    cur: dict | None = None
    for raw in text.splitlines():
        m = RE_H1.match(raw.strip())
        if m:
            cur = {"title": unescape_md(m.group(1)).strip(), "lines": []}
            chunks.append(cur)
            continue
        if cur is not None:
            cur["lines"].append(raw)
    return chunks


def base_section(title: str) -> tuple[str | None, str]:
    """('01', 'Core Concepts') for numbered sections, (None, name) otherwise.
    Trailing parentheticals such as '(continued)' are dropped."""
    t = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
    m = re.match(r"^(\d\d)\.\s*(.*)$", t)
    if m:
        return m.group(1), m.group(2).strip()
    return None, t


# ---------------------------------------------------------------- documents


class Doc:
    """Accumulates parsed sections, anchors and tooltip text."""

    def __init__(self, manifest: dict):
        self.sections: list[dict] = []   # {id,num,title,part,blocks}
        self.parts: list[dict] = []      # {id,title,blurb}
        self.anchors: dict[str, str] = {}   # "01.02" -> anchor id
        self.anchor_titles: dict[str, str] = {}
        self.tips: dict[str, str] = {}       # anchor id -> plain text tip
        self.images: dict[str, dict] = {}    # slug -> manifest entry
        for src, entry in manifest.items():
            self.images[slugify(re.sub(r"(\.(png|jpe?g))+$", "", src, flags=re.I))] = entry
        self.warnings: list[str] = []

    def image_for(self, title: str) -> dict | None:
        slug = slugify(title)
        hit = self.images.get(slug)
        if hit:
            return hit
        # fall back to a separator-free comparison (e.g. the BOYZ datasheet
        # image was named ExampleDatasheetBoyz with no separators)
        squash = slug.replace("-", "")
        for key, entry in self.images.items():
            if key.replace("-", "") == squash:
                return entry
        return None


def collect_sections(chunks: list[dict], doc: Doc) -> None:
    epigraph = None
    intro: dict | None = None
    current_part: dict | None = None
    sec_by_key: dict[str, dict] = {}

    for chunk in chunks:
        title = chunk["title"]
        num, name = base_section(title)
        blocks = parse_blocks(chunk["lines"])

        if title == "Core Rules":
            texts = [b["text"] for b in blocks if b["t"] == "p"]
            epigraph = " / ".join(texts[1:]) if len(texts) > 1 else None
            doc.epigraph_lead = texts[0] if texts else None
            continue
        if title == "Contents" or re.match(r"^Page \d+$", title):
            continue
        if num is None and name in PART_TITLES:
            blurb = next((b["text"] for b in blocks if b["t"] == "p"), "")
            current_part = {"id": slugify(name), "title": name, "blurb": blurb}
            doc.parts.append(current_part)
            continue
        if num is None and name == "Introduction":
            if intro is None:
                intro = {
                    "id": "intro", "num": None, "title": "Introduction",
                    "part": None, "blocks": [],
                }
                doc.sections.append(intro)
            intro["blocks"].extend(blocks)
            continue
        if num is None and name == "Rules Appendix":
            key = "appendix"
            sec = sec_by_key.get(key)
            if sec is None:
                sec = {
                    "id": "appendix", "num": None, "title": "Rules Appendix",
                    "part": current_part["id"] if current_part else None,
                    "blocks": [],
                }
                sec_by_key[key] = sec
                doc.sections.append(sec)
            sec["blocks"].extend(blocks)
            continue
        if num is None:
            doc.warnings.append(f"unrecognised page chunk: {title!r}")
            continue

        sec = sec_by_key.get(num)
        if sec is None:
            sec = {
                "id": f"s{num}", "num": num, "title": name,
                "part": current_part["id"] if current_part else None,
                "blocks": [],
            }
            sec_by_key[num] = sec
            doc.sections.append(sec)
        sec["blocks"].extend(blocks)

    doc.epigraph = epigraph


# ------------------------------------------------------- anchor registration

def register_anchors(doc: Doc) -> None:
    seen_refs: dict[str, dict] = {}
    for sec in doc.sections:
        if sec["num"]:
            doc.anchors[f"{sec['num']}.00"] = sec["id"]
            doc.anchor_titles[sec["id"]] = sec["title"]
        for b in sec["blocks"]:
            if b["t"] not in ("h2", "h3"):
                continue
            text = unescape_md(b["text"])
            m = RE_RULE_HEAD.match(text)
            if b["t"] == "h3":
                # a handful of numbered rules are nested one level deeper
                # (e.g. NORMAL FIGHT (12.05)); give them anchors too — but
                # not combined cross-reference headings such as
                # "LEADER (24.22) / SUPPORT (24.34)"
                if m and m.group(2) and not re.search(r"\(\d\d\.\d\d\)", m.group(1)):
                    ref = m.group(2)
                    aid = "r" + ref.replace(".", "-")
                    b["ref"], b["aid"] = ref, aid
                    b["clean"] = RE_HEAD_PREFIX.sub("", m.group(1)).strip()
                    doc.anchors[ref] = aid
                    doc.anchor_titles[aid] = b["clean"]
                continue
            if m and m.group(2) and not re.search(r"\(\d\d\.\d\d\)", m.group(1)):
                ref = m.group(2)
                aid = "r" + ref.replace(".", "-")
                b["ref"], b["aid"] = ref, aid
                b["cp"] = (m.group(3) or "").replace(" ", "") or None
                b["clean"] = RE_HEAD_PREFIX.sub("", m.group(1)).strip()
                prev = seen_refs.get(ref)
                if prev is not None:
                    # the book prints some rules twice (e.g. Heroic
                    # Intervention appears as the worked example and in the
                    # core stratagem list); the earlier copy becomes an
                    # unanchored worked example, the later one is canonical
                    prev["aid"] = "eg-" + slugify(prev["clean"])
                    prev["dup"] = True
                    doc.anchor_titles[prev["aid"]] = prev["clean"]
                seen_refs[ref] = b
                doc.anchors[ref] = aid
                doc.anchor_titles[aid] = b["clean"]
            else:
                clean = RE_HEAD_PREFIX.sub("", text).strip()
                b["clean"] = clean
                if clean.lower().startswith(("diagram:", "example datasheet:",
                                             "example action:")):
                    b["aid"] = "dg-" + slugify(clean.split(":", 1)[1])
                else:
                    b["aid"] = f"{sec['id']}-{slugify(clean)}"
                b["ref"] = None
                doc.anchor_titles[b["aid"]] = clean


# ------------------------------------------------------------ glossary terms

# term (lower-case) -> rule ref ("NN.NN"), section ref ("NN.00") or anchor id.
ALIASES: dict[str, str] = {
    "engaged": "03.04", "unengaged": "03.04", "engagement": "03.04",
    "coherency": "03.03",
    "visible": "06.01", "fully visible": "06.01",
    "battle-shocked": "01.07", "battle-shock roll": "01.07",
    "leadership roll": "01.06",
    "mortal wound": "06.02", "mortal wounds": "06.02",
    "hazard roll": "06.03", "hazard rolls": "06.03",
    "hit roll": "05.01", "critical hit": "05.01",
    "wound roll": "05.02", "critical wound": "05.02",
    "save roll": "05.03", "saving throw": "05.03",
    "invulnerable saving throw": "05.03", "invulnerable save": "05.03",
    "attack dice": "04.03", "identical attacks": "04.03",
    "maximum distance": "03.01", "set-up distance": "03.01",
    "move type": "03.01", "move types": "03.01",
    "remain stationary": "09.04", "remained stationary": "09.04",
    "normal move": "09.05",
    "advance move": "09.06", "advance roll": "09.06", "advance": "09.06",
    "fall-back move": "09.07", "fall back": "09.07",
    "eligible to shoot": "10.02", "shoot": "10.02",
    "normal shooting": "10.04", "assault shooting": "10.05",
    "close-quarters shooting": "10.06", "indirect shooting": "10.07",
    "charge": "11.02", "charge roll": "11.02", "charge targets": "11.02",
    "charge target": "11.02", "eligible to declare a charge": "11.02",
    "charge move": "11.04",
    "eligible to fight": "12.04", "selected to fight": "12.04",
    "select to fight": "12.04", "fight": "12.04", "fights": "12.04",
    "pile-in move": "12.03", "pile in": "12.03", "pile-in": "12.03",
    "normal fight": "12.05", "overrun fight": "12.06",
    "consolidation move": "12.08", "consolidation": "12.08",
    "stratagem": "15.01", "stratagems": "15.01", "core stratagems": "15.01",
    "action": "16.01", "actions": "16.01",
    "eligible to start an action": "16.01",
    "objective": "14.01", "objectives": "14.01",
    "terrain objective": "14.01", "terrain objectives": "14.01",
    "level of control": "14.02", "secured": "14.03",
    "terrain feature": "13.01", "terrain features": "13.01",
    "terrain area": "13.01", "terrain areas": "13.01",
    "terrain category": "13.02", "terrain categories": "13.02",
    "exposed": "13.03", "light": "13.04", "dense": "13.05",
    "strategic reserves": "20.00", "ingress move": "20.04",
    "surge move": "21.02", "surge moves": "21.02",
    "plunging fire": "22.05", "aura": "22.01",
    "deep strike": "24.09", "scout move": "24.32",
    "firing deck": "24.14",
    "embark": "18.00", "embarked": "18.00", "disembark": "18.00",
    "disembark move": "18.04", "emergency disembark move": "18.05",
    "transport capacity": "18.00",
    "gain core cp": "08.02",
    "starting strength": "appendix-starting-strength-and-half-strength",
    "below starting strength": "appendix-starting-strength-and-half-strength",
    "half-strength": "appendix-starting-strength-and-half-strength",
    "below half-strength": "appendix-starting-strength-and-half-strength",
    "destroyed": "appendix-destroyed",
    "revived": "appendix-revived",
    "objective marker": "appendix-objectives-not-within-a-terrain-area",
    "objective markers": "appendix-objectives-not-within-a-terrain-area",
}

# Terms too generic to auto-link outside their own bolded, exact usage.
STOP_TERMS = {"light", "exposed", "dense", "shoot", "fight", "charge",
              "advance", "action", "actions", "objective", "objectives"}


def build_glossary(doc: Doc) -> dict[str, str]:
    """lower-case term -> anchor id."""
    glossary: dict[str, str] = {}

    def anchor_of(target: str) -> str | None:
        if re.match(r"^\d\d\.\d\d$", target):
            return doc.anchors.get(target)
        return target if target in doc.anchor_titles else None

    # every numbered rule heading is linkable by its name
    for ref, aid in doc.anchors.items():
        title = doc.anchor_titles.get(aid, "")
        term = title.lower().strip()
        term = re.sub(r"^\[|\]$", "", term)
        if len(term) >= 4 and not term.startswith("diagram"):
            glossary.setdefault(term, aid)

    for term, target in ALIASES.items():
        aid = anchor_of(target)
        if aid is None:
            doc.warnings.append(f"glossary alias target missing: {term} -> {target}")
            continue
        glossary[term] = aid
    return glossary


def extract_tips(doc: Doc) -> None:
    """Plain-text definition snippets for every anchor, for tooltips."""
    def clip(text: str, limit: int = 300) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return text
        cut = text[:limit]
        cut = cut[: cut.rfind(" ")]
        return cut.rstrip(",;: ") + "…"

    def plain(md_text: str) -> str:
        t = unescape_md(md_text)
        t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
        t = re.sub(r"\*(.+?)\*", r"\1", t)
        t = re.sub(r"\((\d\d\.\d\d)\)", "", t)
        return t

    for sec in doc.sections:
        cur: str | None = sec["id"]
        buf: list[str] = []
        first = True

        def commit():
            if cur and buf and cur not in doc.tips:
                doc.tips[cur] = clip(" ".join(buf))

        for b in sec["blocks"]:
            if b["t"] == "h2":
                commit()
                cur, buf, first = b.get("aid"), [], True
            elif b["t"] == "h3":
                commit()
                cur = None
            elif b["t"] == "hr":
                commit()
                cur = None
            elif cur and b["t"] == "p":
                text = b["text"]
                if RE_FLAVOUR.match(text.strip()):
                    continue
                # skip pure-flavour italic openers under ability headings
                if first and re.match(r"^\*[^*].*\*$", text.strip()):
                    first = False
                    continue
                first = False
                if text.startswith("**Example"):
                    commit()
                    cur = None
                    continue
                buf.append(plain(text))
                if sum(len(x) for x in buf) > 360:
                    commit()
                    cur = None
            elif cur and b["t"] == "list" and buf:
                # include top-level items compactly if the intro is short
                items = [plain(it["text"]) for it in b["items"] if it["level"] == 0]
                buf.append(" • ".join(items[:6]))
                commit()
                cur = None
        commit()


# ------------------------------------------------------------ inline render

ABILITY_WORDS = {}  # filled at build: "ANTI" -> anchor id


def esc(text: str) -> str:
    return html.escape(text, quote=False)


class InlineRenderer:
    def __init__(self, doc: Doc, glossary: dict[str, str]):
        self.doc = doc
        self.glossary = glossary
        self.context_aid: str | None = None
        self.link_terms = True

    # -- helpers -----------------------------------------------------------
    def term_link(self, term: str, label_html: str) -> str | None:
        key = term.lower().strip()
        aid = self.glossary.get(key)
        if aid is None and key.endswith("s"):
            aid = self.glossary.get(key[:-1])
        if aid is None or aid == self.context_aid:
            return None
        return f'<a class="rt-term" href="#{aid}" data-a="{aid}">{label_html}</a>'

    def ability_link(self, inner: str) -> str | None:
        base = re.match(r"^([A-Z][A-Z' \-]*?)(?:[ \-]\d.*|[ ]?[A-Z]*\s*\d\+)?$", inner)
        word = inner.split(" ")[0].rstrip("-")
        for cand in (inner, word, inner.rsplit(" ", 1)[0]):
            aid = ABILITY_WORDS.get(cand.upper())
            if aid:
                if aid == self.context_aid:
                    return None
                return (f'<a class="rt-ability" href="#{aid}" data-a="{aid}">'
                        f"[{esc(inner)}]</a>")
        return None

    def render_brackets(self, text: str) -> str:
        def sub(m: re.Match) -> str:
            inner = m.group(1)
            link = self.ability_link(inner)
            return link if link else f'<span class="rt-ability-plain">[{esc(inner)}]</span>'
        return re.sub(r"\[([A-Z][A-Z0-9+' \-]{2,})\]", sub, text)

    def render_refs(self, text: str) -> str:
        def repl(m: re.Match) -> str:
            ref = m.group(1)
            aid = self.doc.anchors.get(ref)
            if aid is None and ref.endswith(".00"):
                aid = self.doc.anchors.get(ref)
            if aid is None:
                m2 = re.match(r"^(\d\d)$", ref)
                if m2:
                    aid = self.doc.anchors.get(f"{ref}.00")
            if aid:
                return f'<a class="rt-ref" href="#{aid}" data-a="{aid}">{ref}</a>'
            return ref
        text = re.sub(r"\b(\d\d\.\d\d)\b", repl, text)
        text = re.sub(r"\((\d\d)\)", lambda m: "(" + repl(m) + ")"
                      if self.doc.anchors.get(m.group(1) + ".00") else m.group(0),
                      text)
        return text

    # -- main entry --------------------------------------------------------
    def render(self, raw: str) -> str:
        text = unescape_md(raw)
        out: list[str] = []
        pos = 0
        # split on **bold** / *italic* spans, preserving order
        token = re.compile(r"\*\*(.+?)\*\*|(?<!\*)\*([^*]+)\*(?!\*)")
        for m in token.finditer(text):
            out.append(self.plain_segment(text[pos:m.start()]))
            if m.group(1) is not None:
                out.append(self.render_bold(m.group(1)))
            else:
                out.append(f"<em>{self.plain_segment(m.group(2))}</em>")
            pos = m.end()
        out.append(self.plain_segment(text[pos:]))
        return "".join(out)

    def plain_segment(self, text: str) -> str:
        if not text:
            return ""
        segs: list[str] = []
        pos = 0
        for m in re.finditer(r"\[([A-Z][A-Z0-9+' \-]{2,})\]", text):
            segs.append(self.render_refs(esc(text[pos:m.start()])))
            link = self.ability_link(m.group(1))
            segs.append(link if link else
                        f'<span class="rt-ability-plain">[{esc(m.group(1))}]</span>')
            pos = m.end()
        segs.append(self.render_refs(esc(text[pos:])))
        return "".join(segs)

    def render_bold(self, inner: str) -> str:
        stripped = inner.strip()
        # bracketed ability inside bold: [ASSAULT]
        m = re.match(r"^\[([A-Z][A-Z0-9+' \-]{2,})\]$", stripped)
        if m:
            link = self.ability_link(m.group(1))
            return link if link else (
                f'<span class="rt-ability-plain">[{esc(m.group(1))}]</span>')
        # ALL-CAPS keyword chips (INFANTRY, MONSTER/VEHICLE ...)
        if re.match(r"^[A-Z][A-Z0-9/'’ \-]*$", stripped) and len(stripped) >= 2 \
                and not stripped.endswith(":"):
            if self.link_terms:
                link = self.term_link(stripped, esc(stripped))
                if link and stripped.lower() not in STOP_TERMS:
                    return f'<span class="rt-kw">{link}</span>'
            return f'<span class="rt-kw">{esc(stripped)}</span>'
        # defined game term?
        if self.link_terms:
            link = self.term_link(stripped, esc(stripped))
            if link and (stripped.lower() not in STOP_TERMS):
                return link
        return f"<strong>{self.plain_segment(inner)}</strong>"


# ------------------------------------------------------------- block render

def render_list(items: list[dict], rend: InlineRenderer) -> str:
    out: list[str] = []
    stack: list[str] = []  # open tags: "ul"/"ol"

    def open_at(level: int, ordered: bool):
        while len(stack) > level + 1:
            out.append(f"</{stack.pop()}>")
        while len(stack) < level + 1:
            tag = "ol" if ordered else "ul"
            out.append(f'<{tag} class="rt-list">')
            stack.append(tag)

    for it in items:
        open_at(it["level"], it["ordered"])
        body = rend.render(it["text"])
        for extra in it["extra"]:
            body += f'<div class="rt-li-more">{rend.render(extra)}</div>'
        out.append(f"<li>{body}</li>")
    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


def render_table(rows: list[str], rend: InlineRenderer) -> str:
    parsed = []
    for r in rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if all(re.match(r"^:?-+:?$", c or "-") for c in cells):
            continue
        parsed.append(cells)
    if not parsed:
        return ""
    head, *body = parsed
    out = ['<table class="rt-table"><thead><tr>']
    out += [f"<th>{rend.render(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for cells in body:
        out.append("<tr>" + "".join(f"<td>{rend.render(c)}</td>" for c in cells)
                   + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


BADGE_RE = re.compile(r"^\*\*([A-Z][A-Z ()/\-]+)\*\*$")


def render_section(sec: dict, doc: Doc, rend: InlineRenderer) -> str:
    """Render one section's block stream to HTML, handling boxes/cards."""
    blocks = sec["blocks"]
    out: list[str] = []
    toc: list[dict] = []
    i = 0
    n = len(blocks)
    card_open = False
    fig_open = False
    commentary = getattr(doc, "commentary", {})
    sec_cmt_flushed = False

    def flush_commentary(aid: str | None):
        """Emit commentary blocks attached to the rule that just ended."""
        nonlocal sec_cmt_flushed
        if aid and aid in commentary:
            out.extend(commentary.pop(aid))

    def flush_section_commentary():
        nonlocal sec_cmt_flushed
        if not sec_cmt_flushed:
            sec_cmt_flushed = True
            if sec["id"] in commentary:
                out.extend(commentary.pop(sec["id"]))

    def close_card():
        nonlocal card_open
        if card_open:
            out.append("</div>")
            card_open = False

    def close_fig():
        nonlocal fig_open
        if fig_open:
            out.append("</div></figure>")
            fig_open = False

    while i < n:
        b = blocks[i]
        t = b["t"]

        if t == "h2":
            close_fig()
            close_card()
            flush_commentary(rend.context_aid)
            flush_section_commentary()
            rend.context_aid = b.get("aid")
            clean = b.get("clean", b["text"])
            low = clean.lower()
            if low.startswith("diagram:") or low.startswith("example datasheet:"):
                kind, _, label = clean.partition(":")
                label = smart_title(label.strip())
                img = doc.image_for(label) or doc.image_for(f"{kind} {label}")
                out.append(f'<figure class="rt-figure" id="{b["aid"]}">')
                out.append(f'<figcaption class="rt-fig-title">'
                           f'<span class="rt-fig-kind">{esc(kind)}</span> '
                           f"{esc(label)}</figcaption>")
                if img:
                    out.append(
                        f'<img loading="lazy" src="{IMG_URL}/{img["file"]}" '
                        f'width="{img["width"]}" height="{img["height"]}" '
                        f'alt="{esc(clean)}">')
                else:
                    doc.warnings.append(f"no image for: {clean!r}")
                    out.append('<div class="rt-fig-missing">Image not available'
                               " — caption below describes the diagram.</div>")
                out.append('<div class="rt-fig-captions">')
                fig_open = True
                i += 1
                continue
            # stratagem / action card?
            badge = None
            if i + 1 < n and blocks[i + 1]["t"] == "p":
                mb = BADGE_RE.match(blocks[i + 1]["text"].strip())
                if mb and ("STRATAGEM" in mb.group(1) or "ACTION" in mb.group(1)):
                    badge = mb.group(1)
            ref = b.get("ref")
            refspan = f'<span class="rt-refnum">{ref}</span>' if ref else ""
            cp = b.get("cp")
            if badge or cp:
                out.append(f'<div class="rt-card" id="{b["aid"]}">')
                card_open = True
                cphtml = f'<span class="rt-cp">{cp}</span>' if cp else ""
                bhtml = (f'<span class="rt-badge">{esc(smart_title(badge))}</span>'
                         if badge else "")
                if b.get("dup"):
                    bhtml += '<span class="rt-badge">Worked Example</span>'
                title = ": ".join(smart_title(p.strip())
                                  for p in clean.split(":"))
                out.append(f'<h3 class="rt-card-title">{esc(title)}{cphtml}'
                           f"{refspan}{bhtml}</h3>")
                if badge:
                    i += 2
                else:
                    i += 1
                if ref and not b.get("dup"):
                    toc.append({"ref": ref, "id": b["aid"],
                                "title": smart_title(clean)})
                continue
            out.append(f'<h3 class="rt-rule" id="{b["aid"]}">'
                       f"<span>{esc(smart_title(clean))}</span>{refspan}"
                       f'<a class="rt-anchor" href="#{b["aid"]}" title="Link to this rule">&#167;</a></h3>')
            if ref and not b.get("dup"):
                toc.append({"ref": ref, "id": b["aid"],
                            "title": smart_title(clean)})
            i += 1
            continue

        if t == "h3":
            if b.get("ref"):
                close_fig()
                close_card()
                flush_commentary(rend.context_aid)
                rend.context_aid = b["aid"]
                refspan = f'<span class="rt-refnum">{b["ref"]}</span>'
                out.append(f'<h3 class="rt-rule" id="{b["aid"]}">'
                           f'<span>{esc(smart_title(b["clean"]))}</span>{refspan}'
                           f'<a class="rt-anchor" href="#{b["aid"]}" '
                           f'title="Link to this rule">&#167;</a></h3>')
                toc.append({"ref": b["ref"], "id": b["aid"],
                            "title": smart_title(b["clean"])})
                i += 1
                continue
            if not fig_open:
                close_card()  # keep sub-heads inside figures/cards otherwise
            out.append(f'<h4 class="rt-subrule">'
                       f'{rend.plain_segment(smart_title(unescape_md(b["text"])))}</h4>')
            i += 1
            continue

        if t == "hr":
            close_fig()
            close_card()
            # look ahead: See-also box or note box?
            seg = []
            j = i + 1
            while j < n and blocks[j]["t"] not in ("hr", "h2"):
                seg.append(blocks[j])
                j += 1
            first_p = next((x for x in seg if x["t"] == "p"), None)
            if first_p and first_p["text"].strip() in ("**See also**", "See also"):
                out.append(render_seealso(seg, rend))
                i = j
                continue
            if first_p and BOLD_TITLE_RE.match(first_p["text"].strip()):
                out.append(render_notes(seg, rend))
                i = j
                continue
            i += 1
            continue

        if t == "flavour":
            close_fig()
            close_card()
            out.append(f'<p class="rt-quote">++ {rend.render(b["text"])} ++</p>')
            i += 1
            continue

        if t == "p":
            text = b["text"].strip()
            if text.startswith("**Example:**"):
                body = text[len("**Example:**"):].strip()
                out.append(f'<div class="rt-example"><span>Example</span> '
                           f"{rend.render(body)}</div>")
            elif re.match(r"^\*\*Q:", text):
                # FAQ pair
                q = re.sub(r"^\*\*Q:\s*(.*?)\*\*$", r"\1", text)
                a = ""
                if i + 1 < n and blocks[i + 1]["t"] == "p" \
                        and re.match(r"^\*A:", blocks[i + 1]["text"].strip()):
                    a = re.sub(r"^\*A:\s*(.*?)\*$", r"\1",
                               blocks[i + 1]["text"].strip())
                    i += 1
                out.append('<div class="rt-faq">'
                           f'<p class="rt-faq-q">Q: {rend.render(q)}</p>'
                           f'<p class="rt-faq-a">A: {rend.render(a)}</p></div>')
            else:
                cls = "rt-cap" if fig_open else "rt-p"
                out.append(f'<p class="{cls}">{rend.render(text)}</p>')
            i += 1
            continue

        if t == "list":
            out.append(render_list(b["items"], rend))
            i += 1
            continue

        if t == "table":
            close_fig()
            out.append(render_table(b["rows"], rend))
            i += 1
            continue

        i += 1

    close_fig()
    close_card()
    flush_commentary(rend.context_aid)
    flush_section_commentary()
    rend.context_aid = None
    sec["toc"] = toc
    return "".join(out)


BOLD_TITLE_RE = re.compile(r"^\*\*[^*]+\*\*$")


def render_notes(seg: list[dict], rend: InlineRenderer) -> str:
    """Designer's-note style side boxes: bold title lines + italic bodies."""
    out = ['<aside class="rt-note">']
    for b in seg:
        if b["t"] == "p":
            text = b["text"].strip()
            if BOLD_TITLE_RE.match(text):
                out.append(f"<h5>{esc(unescape_md(text.strip('*')))}</h5>")
            elif RE_FLAVOUR.match(text):
                out.append(f'<p class="rt-quote">++ '
                           f'{rend.render(RE_FLAVOUR.match(text).group(1))} ++</p>')
            else:
                out.append(f"<p>{rend.render(text)}</p>")
        elif b["t"] == "list":
            out.append(render_list(b["items"], rend))
        elif b["t"] == "table":
            out.append(render_table(b["rows"], rend))
    out.append("</aside>")
    return "".join(out)


def render_seealso(seg: list[dict], rend: InlineRenderer) -> str:
    out = ['<aside class="rt-seealso"><h5>See also</h5>']
    for b in seg:
        if b["t"] == "p":
            text = b["text"].strip()
            if text in ("**See also**", "See also"):
                continue
            out.append(f'<p class="rt-seealso-group">'
                       f'{rend.render(smart_title(text))}</p>')
        elif b["t"] == "list":
            out.append(render_list(b["items"], rend))
    out.append("</aside>")
    return "".join(out)


# -------------------------------------------------------------- commentary

RE_CMT_HEAD = re.compile(r"^##\s+@(\S+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*$")


def load_commentary(doc: Doc, rend: InlineRenderer) -> int:
    """Parse data/rules/commentary.md (community insight, kept separate from
    the official rules text) into doc.commentary: anchor id -> [html]."""
    doc.commentary = {}
    if not COMMENTARY_PATH.exists():
        return 0

    entries: list[dict] = []
    cur: dict | None = None
    for raw in COMMENTARY_PATH.read_text(encoding="utf-8").splitlines():
        # match at column 0 only, so the indented format example in the
        # file's preamble is not treated as an entry
        m = RE_CMT_HEAD.match(raw)
        if m:
            cur = {"target": m.group(1), "title": m.group(2),
                   "source": m.group(3), "lines": []}
            entries.append(cur)
        elif cur is not None:
            cur["lines"].append(raw)

    count = 0
    for e in entries:
        target = e["target"]
        if re.match(r"^\d\d\.\d\d$", target):
            aid = doc.anchors.get(target)
        elif target in ("intro", "appendix") or re.match(r"^s\d\d$", target):
            aid = target if any(s["id"] == target for s in doc.sections) else None
        else:
            aid = target if target in doc.anchor_titles else None
        if aid is None:
            doc.warnings.append(f"commentary target not found: @{target} "
                                f"({e['title']!r})")
            continue

        rend.context_aid = aid if aid.startswith("r") else None
        body: list[str] = []
        for b in parse_blocks(e["lines"]):
            if b["t"] == "p":
                body.append(f'<p class="rt-p">{rend.render(b["text"])}</p>')
            elif b["t"] == "list":
                body.append(render_list(b["items"], rend))
            elif b["t"] == "table":
                body.append(render_table(b["rows"], rend))
        html_block = (
            '<aside class="rt-commentary">'
            '<div class="rt-cmt-head">'
            '<span class="rt-cmt-badge">Commentary</span>'
            f'<span class="rt-cmt-title">{esc(e["title"])}</span>'
            f'<span class="rt-cmt-src">{esc(e["source"])}</span></div>'
            f'<div class="rt-cmt-body">{"".join(body)}</div></aside>')
        doc.commentary.setdefault(aid, []).append(html_block)
        count += 1
    return count


# ----------------------------------------------------------------- flavour

def check_flavour(doc: Doc, md_text: str) -> None:
    if not FLAVOUR_PATH.exists():
        return
    entries = json.loads(FLAVOUR_PATH.read_text(encoding="utf-8"))
    flat = re.sub(r"\s+", " ", unescape_md(md_text))
    missing = [e["ref"] + " " + e["title"] for e in entries.values()
               if re.sub(r"\s+", " ", e["flavour"]) not in flat]
    if missing:
        doc.warnings.append("flavour.json lines NOT found in markdown: "
                            + ", ".join(missing))


# -------------------------------------------------------------------- main

def main() -> int:
    md_text = MD_PATH.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    doc = Doc(manifest)

    chunks = chunk_pages(md_text)
    collect_sections(chunks, doc)
    register_anchors(doc)

    # ability anchors: [WORD] -> 24.xx rule anchors
    for ref, aid in doc.anchors.items():
        title = doc.anchor_titles.get(aid, "")
        m = re.match(r"^\[(.+)\]$", title)
        if m:
            ABILITY_WORDS[m.group(1).upper()] = aid
    # non-bracket core abilities usable in [X] form never appear; also allow
    # ANTI-X and BLAST X style prefixes via first-word lookup in ability_link.

    glossary = build_glossary(doc)
    extract_tips(doc)
    check_flavour(doc, md_text)

    rend = InlineRenderer(doc, glossary)
    cmt_count = load_commentary(doc, rend)
    for sec in doc.sections:
        sec["html"] = render_section(sec, doc, rend)
        del sec["blocks"]

    parts_out = []
    for part in doc.parts:
        part["sections"] = [s["id"] for s in doc.sections if s["part"] == part["id"]]
        parts_out.append(part)

    leftover = {aid: len(v) for aid, v in getattr(doc, "commentary", {}).items() if v}
    if leftover:
        doc.warnings.append(f"commentary never flushed (bad targets?): {leftover}")

    payload = {
        "meta": {
            "title": "Warhammer 40,000 Core Rules — 11th Edition",
            "generated": date.today().isoformat(),
            "source": MD_PATH.name,
            "commentary": cmt_count,
        },
        "epigraph": getattr(doc, "epigraph", None),
        "epigraph_lead": getattr(doc, "epigraph_lead", None),
        "parts": parts_out,
        "sections": [
            {k: sec[k] for k in ("id", "num", "title", "part", "html", "toc")}
            for sec in doc.sections
        ],
        "tips": doc.tips,
        "titles": {k: smart_title(v) for k, v in doc.anchor_titles.items()},
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print(f"sections: {len(doc.sections)}  anchors: {len(doc.anchors)}  "
          f"tips: {len(doc.tips)}  glossary terms: {len(glossary)}  "
          f"commentary: {cmt_count}")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")
    for w in doc.warnings:
        print("WARN:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
