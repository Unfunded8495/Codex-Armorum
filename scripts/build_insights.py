"""Build the Rules Insights dataset for the /rules/insights page.

Parses the curated community articles in data/rules/insights/*.md (produced
once by scripts/import_insight_docx.py, then hand-maintained) into
data/rules/insights.json:

- one entry per article, rendered to HTML, grouped by series
- every heading gets a stable anchor for deep links and the sidebar TOC
- rule references (13.01, 13.11.01) and [ABILITY] tags link into /rules,
  using the anchors already built into data/rules/core_rules.json
- images resolve through data/rules/insights_images.json for width/height
- the build FAILS if any external http(s) link survives curation: article
  links must point inside the codex or be unwrapped to plain text

Run order: after editing insights markdown run this, then
scripts/build_rules.py (which links commentary sources to these articles).

Usage:  python scripts/build_insights.py
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_DIR = ROOT / "data" / "rules" / "insights"
RULES_PATH = ROOT / "data" / "rules" / "core_rules.json"
MANIFEST_PATH = ROOT / "data" / "rules" / "insights_images.json"
OUT_PATH = ROOT / "data" / "rules" / "insights.json"
IMG_URL = "/static/images/insights"

SERIES = [
    {"id": "rules-deep-dive", "title": "Rules Deep Dive",
     "blurb": "A guided tour of the 11th Edition rules, phase by phase: "
              "what changed, why it matters, and how it plays."},
    {"id": "ruleshammer", "title": "Ruleshammer",
     "blurb": "Close readings of specific rules interactions, with worked "
              "diagrams and edge cases."},
    {"id": "hammer-of-math", "title": "Hammer of Math",
     "blurb": "The probability behind the rules changes: what the numbers "
              "actually say."},
]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def unescape_md(text: str) -> str:
    return re.sub(r"\\([\\*_\[\]])", r"\1", text)


# ---------------------------------------------------------- rules anchors

class RulesIndex:
    """Anchor lookups into the already-built core rules dataset."""

    def __init__(self, payload: dict):
        self.aids = set(payload.get("titles", {}))
        self.aids.update(s["id"] for s in payload.get("sections", []))
        self.abilities: dict[str, str] = {}
        for aid, title in payload.get("titles", {}).items():
            m = re.match(r"^\[(.+)\]$", title)
            if m:
                self.abilities[m.group(1).upper()] = aid

    def ref_aid(self, ref: str) -> str | None:
        """'13.01' / '13.00' -> anchor id in /rules, else None."""
        m = re.match(r"^(\d\d)\.(\d\d)$", ref)
        if not m:
            return None
        aid = f"s{m.group(1)}" if m.group(2) == "00" else \
              f"r{m.group(1)}-{m.group(2)}"
        return aid if aid in self.aids else None

    def ability_aid(self, inner: str) -> str | None:
        word = inner.split(" ")[0].rstrip("-")
        for cand in (inner, word, inner.rsplit(" ", 1)[0]):
            aid = self.abilities.get(cand.upper())
            if aid:
                return aid
        return None


# ---------------------------------------------------------- inline render

RE_LINK = re.compile(r"(?<!\\)(?<!!)\[((?:\\.|[^\]\\])*)\]\(([^)\s]+)\)")
RE_EMPH = re.compile(
    r"\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|(?<!\*)\*([^*]+)\*(?!\*)")
RE_ABILITY = re.compile(r"\[([A-Z][A-Z0-9+'’ \-]{2,})\]")
RE_REF = re.compile(r"\b(\d\d\.\d\d)(\.\d\d)?\b")


class Inline:
    def __init__(self, rules: RulesIndex):
        self.rules = rules
        self.anchor_ok: set[str] = set()      # filled before render pass
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.article = "?"

    def render(self, text: str) -> str:
        out, pos = [], 0
        for m in RE_LINK.finditer(text):
            out.append(self.emphasis(text[pos:m.start()]))
            out.append(self.link(unescape_md(m.group(1)), m.group(2)))
            pos = m.end()
        out.append(self.emphasis(text[pos:]))
        return "".join(out)

    def link(self, label: str, target: str) -> str:
        body = self.emphasis(label)
        if re.match(r"^https?://", target):
            self.errors.append(
                f"[{self.article}] external link survived curation: {target}")
            return body
        if target.startswith("#"):
            if target[1:] not in self.anchor_ok:
                self.errors.append(
                    f"[{self.article}] unknown internal anchor: {target}")
                return body
            return f'<a class="ins-xref" href="{target}">{body}</a>'
        if target.startswith("/rules#"):
            aid = target.split("#", 1)[1]
            if aid not in self.rules.aids:
                self.errors.append(
                    f"[{self.article}] unknown /rules anchor: {target}")
                return body
            return (f'<a class="rt-ref ins-rule-link" data-a="{aid}" '
                    f'href="{target}">{body}</a>')
        self.errors.append(f"[{self.article}] unsupported link target: {target}")
        return body

    def emphasis(self, text: str) -> str:
        out, pos = [], 0
        for m in RE_EMPH.finditer(text):
            out.append(self.plain(text[pos:m.start()]))
            if m.group(1) is not None:
                out.append(f"<strong><em>{self.plain(m.group(1))}</em></strong>")
            elif m.group(2) is not None:
                out.append(f"<strong>{self.plain(m.group(2))}</strong>")
            else:
                out.append(f"<em>{self.plain(m.group(3))}</em>")
            pos = m.end()
        out.append(self.plain(text[pos:]))
        return "".join(out)

    def plain(self, text: str) -> str:
        if not text:
            return ""
        text = esc(unescape_md(text))
        segs, pos = [], 0
        for m in RE_ABILITY.finditer(text):
            segs.append(self.refs(text[pos:m.start()]))
            aid = self.rules.ability_aid(m.group(1))
            if aid:
                segs.append(f'<a class="rt-ability" data-a="{aid}" '
                            f'href="/rules#{aid}">[{m.group(1)}]</a>')
            else:
                segs.append(f'<span class="rt-ability-plain">[{m.group(1)}]</span>')
            pos = m.end()
        segs.append(self.refs(text[pos:]))
        return "".join(segs)

    def refs(self, text: str) -> str:
        def repl(m: re.Match) -> str:
            aid = self.rules.ref_aid(m.group(1))
            if aid is None:
                return m.group(0)
            return (f'<a class="rt-ref" data-a="{aid}" '
                    f'href="/rules#{aid}">{m.group(0)}</a>')
        return RE_REF.sub(repl, text)


# ------------------------------------------------------------ block model

RE_META = re.compile(r"^([A-Za-z-]+):\s*(.+)$")
RE_HEAD = re.compile(r"^##\s+(.*)$")
RE_IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")
RE_ITEM = re.compile(r"^(\s*)(-|1\.)\s+(.*)$")
RE_CREDIT = re.compile(r"Credit:", re.I)
RE_HEAD_REF = re.compile(r"^(.*?)\s*(\d\d\.\d\d(?:\.\d\d)?)?\s*$")


def parse_article(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# "):
        raise SystemExit(f"{path.name}: first line must be '# Title'")
    art = {"title": lines[0][2:].strip(), "meta": {}, "blocks": []}
    i = 1
    while i < len(lines) and (m := RE_META.match(lines[i])):
        art["meta"][m.group(1).lower()] = m.group(2).strip()
        i += 1

    blocks = art["blocks"]
    para: list[str] = []

    def flush():
        if para:
            blocks.append({"t": "p", "text": " ".join(para)})
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        i += 1
        if not s:
            flush()
            continue
        if m := RE_HEAD.match(s):
            flush()
            blocks.append({"t": "h", "text": m.group(1).strip()})
            continue
        if m := RE_IMAGE.match(s):
            flush()
            blocks.append({"t": "img", "alt": m.group(1), "file": m.group(2)})
            continue
        if s.startswith(">"):
            flush()
            if not blocks or blocks[-1]["t"] != "quote":
                blocks.append({"t": "quote", "lines": []})
            blocks[-1]["lines"].append(s[1:].lstrip())
            continue
        if s.startswith("|"):
            flush()
            if not blocks or blocks[-1]["t"] != "table":
                blocks.append({"t": "table", "rows": []})
            blocks[-1]["rows"].append(s)
            continue
        if m := RE_ITEM.match(line):
            flush()
            if not blocks or blocks[-1]["t"] != "list":
                blocks.append({"t": "list", "items": []})
            blocks[-1]["items"].append({
                "level": min(len(m.group(1)) // 2, 3),
                "ordered": m.group(2) != "-",
                "text": m.group(3).strip(),
            })
            continue
        para.append(s)
    flush()
    return art


# ------------------------------------------------------------ block render

def render_list(items: list[dict], rend: Inline) -> str:
    out: list[str] = []
    stack: list[str] = []

    def open_at(level: int, ordered: bool):
        while len(stack) > level + 1:
            out.append(f"</{stack.pop()}>")
        while len(stack) < level + 1:
            tag = "ol" if ordered else "ul"
            out.append(f'<{tag} class="rt-list">')
            stack.append(tag)

    for it in items:
        open_at(it["level"], it["ordered"])
        out.append(f"<li>{rend.render(it['text'])}</li>")
    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


def render_table(rows: list[str], rend: Inline) -> str:
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


def render_quote(qlines: list[str], rend: Inline) -> str:
    out = ['<blockquote class="ins-quote">']
    items: list[dict] = []

    def flush_items():
        if items:
            out.append(render_list(items, rend))
            items.clear()

    for q in qlines:
        m = RE_ITEM.match(q)
        if m:
            items.append({"level": 0, "ordered": m.group(2) != "-",
                          "text": m.group(3).strip()})
        else:
            flush_items()
            out.append(f"<p>{rend.render(q)}</p>")
    flush_items()
    out.append("</blockquote>")
    return "".join(out)


def render_article(art: dict, rend: Inline, manifest: dict) -> None:
    slug = art["meta"]["slug"]
    rend.article = slug
    out: list[str] = []
    toc: list[dict] = []
    first_para = True

    blocks = art["blocks"]
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b["t"] == "h":
            m = RE_HEAD_REF.match(b["text"])
            title, ref = m.group(1).strip(), m.group(2)
            hid = b["hid"]
            refspan = ""
            if ref:
                aid = rend.rules.ref_aid(ref[:5])
                refspan = (f'<a class="rt-ref ins-head-ref" data-a="{aid}" '
                           f'href="/rules#{aid}">{ref}</a>') if aid else \
                          f'<span class="rt-refnum">{ref}</span>'
            out.append(f'<h3 class="rt-rule" id="{hid}">'
                       f"<span>{rend.emphasis(title)}</span>{refspan}"
                       f'<a class="rt-anchor" href="#{hid}" '
                       f'title="Link to this section">&#167;</a></h3>')
            toc.append({"id": hid, "title": re.sub(r"\*", "", title),
                        "ref": ref or None})
            first_para = False
            i += 1
            continue
        if b["t"] == "img":
            entry = manifest.get(b["file"])
            if entry is None:
                rend.errors.append(f"[{slug}] image missing from manifest: {b['file']}")
                i += 1
                continue
            caption = ""
            if (i + 1 < len(blocks) and blocks[i + 1]["t"] == "p"
                    and len(blocks[i + 1]["text"]) < 160
                    and RE_CREDIT.search(blocks[i + 1]["text"])):
                caption = (f'<figcaption class="ins-fig-credit">'
                           f'{rend.render(blocks[i + 1]["text"])}</figcaption>')
                i += 1
            alt = b["alt"] or re.sub(r"-\d+$", "", Path(b["file"]).stem)
            out.append(f'<figure class="ins-figure">'
                       f'<img loading="lazy" src="{IMG_URL}/{b["file"]}" '
                       f'width="{entry["width"]}" height="{entry["height"]}" '
                       f'alt="{esc(alt)}">{caption}</figure>')
            i += 1
            continue
        if b["t"] == "p":
            cls = "rt-p"
            if first_para and re.match(r"^\*[^*].*\*$", b["text"]):
                cls = "rt-p ins-lede"
            first_para = False
            out.append(f'<p class="{cls}">{rend.render(b["text"])}</p>')
            i += 1
            continue
        if b["t"] == "quote":
            out.append(render_quote(b["lines"], rend))
            i += 1
            continue
        if b["t"] == "list":
            out.append(render_list(b["items"], rend))
            i += 1
            continue
        if b["t"] == "table":
            out.append(render_table(b["rows"], rend))
            i += 1
            continue
        i += 1

    art["html"] = "".join(out)
    art["toc"] = toc


# -------------------------------------------------------------------- main

def main() -> int:
    if not RULES_PATH.exists():
        print("core_rules.json missing: run scripts/build_rules.py first")
        return 1
    rules = RulesIndex(json.loads(RULES_PATH.read_text(encoding="utf-8")))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rend = Inline(rules)

    articles = [parse_article(p) for p in sorted(MD_DIR.glob("*.md"))]
    if not articles:
        print(f"no articles under {MD_DIR}")
        return 1

    # first pass: register heading + article anchors so links can validate
    for art in articles:
        meta = art["meta"]
        for key in ("slug", "series", "order"):
            if key not in meta:
                raise SystemExit(f"{art['title']}: missing '{key.title()}:' line")
        rend.anchor_ok.add(meta["slug"])
        seen: set[str] = set()
        for b in art["blocks"]:
            if b["t"] != "h":
                continue
            m = RE_HEAD_REF.match(b["text"])
            hid = f"{meta['slug']}--{slugify(re.sub(r'[*]', '', m.group(1)))}"
            while hid in seen:
                hid += "-x"
            seen.add(hid)
            b["hid"] = hid
            rend.anchor_ok.add(hid)

    for art in articles:
        render_article(art, rend, manifest)

    if rend.errors:
        for e in rend.errors:
            print("ERROR:", e)
        return 1

    articles.sort(key=lambda a: (int(a["meta"]["order"]), a["title"]))
    known_series = {s["id"] for s in SERIES}
    payload = {
        "meta": {
            "title": "Rules Insights",
            "generated": date.today().isoformat(),
            "source": "data/rules/insights/*.md",
            "articles": len(articles),
        },
        "series": SERIES,
        "articles": [{
            "slug": a["meta"]["slug"],
            "title": a["title"],
            "series": a["meta"]["series"],
            "seriesId": slugify(a["meta"]["series"]),
            "words": len(re.sub(r"<[^>]+>", " ", a["html"]).split()),
            "html": a["html"],
            "toc": a["toc"],
        } for a in articles],
    }
    for a in payload["articles"]:
        if a["seriesId"] not in known_series:
            print(f"WARN: article {a['slug']} has unlisted series "
                  f"{a['series']!r}; it will render under its own group")
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8")
    total_words = sum(a["words"] for a in payload["articles"])
    print(f"articles: {len(articles)}  headings: "
          f"{sum(len(a['toc']) for a in payload['articles'])}  "
          f"words: {total_words}")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")
    for w in rend.warnings:
        print("WARN:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
