"""Build the data-update changelog for the /changelog page.

Parses the per-update records in docs/data_updates/*.md into
data/changelog.json:

- one entry per file, rendered to HTML, newest first
- every ## heading gets a stable anchor for deep links and the sidebar TOC
- each file starts with '# Title' followed by meta lines:
      Date: 2026-07-15        (or 2026-07 when only the month is known)
      Kind: data update | migration | tooling
      Versions: 886 -> 895    (optional; shown on the entry plate)
      Summary: one-line hook shown under the entry title (optional)

The markdown subset matches how the records are written: ##/### headings,
paragraphs, -/1. lists (nested by two-space indent), | tables, **bold**,
*italic* and `inline code`. External links are left as plain text; these
records are self-contained.

Run after adding or editing a record: python scripts/build_changelog.py
(then reload /changelog). The runbook's Step 6 makes a record per refresh.

Usage:  python scripts/build_changelog.py
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD_DIR = ROOT / "docs" / "data_updates"
OUT_PATH = ROOT / "data" / "changelog.json"

KINDS = {"data update", "migration", "tooling"}

RE_META = re.compile(r"^([A-Za-z-]+):\s*(.+)$")
RE_HEAD = re.compile(r"^(##+)\s+(.*)$")
RE_ITEM = re.compile(r"^(\s*)(-|\d+\.)\s+(.*)$")
RE_EMPH = re.compile(
    r"\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|(?<!\*)\*([^*]+)\*(?!\*)")
RE_CODE = re.compile(r"`([^`]+)`")
RE_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def inline(text: str) -> str:
    """bold / italic / inline code; everything else is escaped text."""
    out, pos = [], 0
    for m in RE_CODE.finditer(text):
        out.append(emphasis(text[pos:m.start()]))
        out.append(f"<code>{esc(m.group(1))}</code>")
        pos = m.end()
    out.append(emphasis(text[pos:]))
    return "".join(out)


def emphasis(text: str) -> str:
    out, pos = [], 0
    for m in RE_EMPH.finditer(text):
        out.append(esc(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append(f"<strong><em>{esc(m.group(1))}</em></strong>")
        elif m.group(2) is not None:
            out.append(f"<strong>{esc(m.group(2))}</strong>")
        else:
            out.append(f"<em>{esc(m.group(3))}</em>")
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def date_label(iso: str) -> str:
    parts = iso.split("-")
    if len(parts) == 3:
        return f"{int(parts[2])} {MONTHS[int(parts[1]) - 1]} {parts[0]}"
    return f"{MONTHS[int(parts[1]) - 1]} {parts[0]}"


# ------------------------------------------------------------ block parsing

def parse_record(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# "):
        raise SystemExit(f"{path.name}: first line must be '# Title'")
    rec = {"file": path.name, "title": lines[0][2:].strip(),
           "meta": {}, "blocks": []}
    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines) and (m := RE_META.match(lines[i])):
        rec["meta"][m.group(1).lower()] = m.group(2).strip()
        i += 1

    blocks = rec["blocks"]
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
            blocks.append({"t": "h", "level": len(m.group(1)),
                           "text": m.group(2).strip()})
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
        # continuation of a wrapped list item (indented plain line)
        if line.startswith("  ") and blocks and blocks[-1]["t"] == "list":
            blocks[-1]["items"][-1]["text"] += " " + s
            continue
        para.append(s)
    flush()
    return rec


# ---------------------------------------------------------- block rendering

def render_list(items: list[dict]) -> str:
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
        out.append(f"<li>{inline(it['text'])}</li>")
    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


def render_table(rows: list[str]) -> str:
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
    out += [f"<th>{inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for cells in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells)
                   + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def render_record(rec: dict) -> None:
    slug = rec["slug"]
    out: list[str] = []
    toc: list[dict] = []
    seen: set[str] = set()
    for b in rec["blocks"]:
        if b["t"] == "h":
            if b["level"] == 2:
                hid = f"{slug}--{slugify(b['text'])}"
                while hid in seen:
                    hid += "-x"
                seen.add(hid)
                out.append(f'<h3 class="rt-rule" id="{hid}">'
                           f"<span>{inline(b['text'])}</span>"
                           f'<a class="rt-anchor" href="#{hid}" '
                           f'title="Link to this section">&#167;</a></h3>')
                toc.append({"id": hid, "title": re.sub(r"[`*]", "", b["text"])})
            else:
                out.append(f'<h4 class="cl-subhead">{inline(b["text"])}</h4>')
        elif b["t"] == "p":
            out.append(f'<p class="rt-p">{inline(b["text"])}</p>')
        elif b["t"] == "list":
            out.append(render_list(b["items"]))
        elif b["t"] == "table":
            out.append(render_table(b["rows"]))
    rec["html"] = "".join(out)
    rec["toc"] = toc


# -------------------------------------------------------------------- main

def main() -> int:
    records = [parse_record(p) for p in sorted(MD_DIR.glob("*.md"))]
    if not records:
        print(f"no records under {MD_DIR}")
        return 1

    errors: list[str] = []
    for rec in records:
        meta = rec["meta"]
        for key in ("date", "kind"):
            if key not in meta:
                errors.append(f"{rec['file']}: missing '{key.title()}:' line")
        if "date" in meta and not RE_DATE.match(meta["date"]):
            errors.append(f"{rec['file']}: Date must be YYYY-MM-DD or YYYY-MM")
        if meta.get("kind") and meta["kind"] not in KINDS:
            errors.append(f"{rec['file']}: Kind must be one of "
                          f"{sorted(KINDS)}, got {meta['kind']!r}")
        rec["slug"] = slugify(Path(rec["file"]).stem)
    if errors:
        for e in errors:
            print("ERROR:", e)
        return 1

    for rec in records:
        render_record(rec)

    # newest first; full dates sort after month-only dates in the same month
    records.sort(key=lambda r: r["meta"]["date"], reverse=True)
    payload = {
        "meta": {
            "title": "Changelog",
            "generated": date.today().isoformat(),
            "source": "docs/data_updates/*.md",
            "entries": len(records),
        },
        "entries": [{
            "slug": r["slug"],
            "title": r["title"],
            "date": r["meta"]["date"],
            "dateLabel": date_label(r["meta"]["date"]),
            "kind": r["meta"]["kind"],
            "versions": r["meta"].get("versions"),
            "summary": r["meta"].get("summary"),
            "html": r["html"],
            "toc": r["toc"],
        } for r in records],
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8")
    print(f"entries: {len(records)}  sections: "
          f"{sum(len(r['toc']) for r in records)}")
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
