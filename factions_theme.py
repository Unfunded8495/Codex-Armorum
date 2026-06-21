"""Per-faction colour schemes and placeholder SVG generation."""

import re as _re

# The *primary* (first value) is the official Games Workshop faction colour and
# is the base colour used for that faction everywhere in the app. The *accent*
# (second value) is a complementary trim used for borders, glow, glyph tint and
# title ink; the *glyph* key selects the placeholder mark. Lookups are normalised
# (case, straight/curly apostrophes, spacing) by theme_for(), so "T'au Empire",
# "T’au Empire" and "tau empire" all resolve to the same theme.
THEME = {
    # ── Official GW faction colours (the 25 playable factions) ──────────────────
    "Adepta Sororitas":     ("#5d0301", "#d9c08a", "skull"),
    "Adeptus Custodes":     ("#755d44", "#d4af37", "aquila"),
    "Adeptus Mechanicus":   ("#9f352b", "#c79a3a", "gear"),
    "Aeldari":              ("#19767f", "#eef3f2", "blade"),
    "Astra Militarum":      ("#32513f", "#c7b27a", "aquila"),
    "Black Templars":       ("#221f21", "#c79a3a", "aquila"),
    "Blood Angels":         ("#921315", "#c79a3a", "aquila"),
    "Chaos Knights":        ("#256551", "#9c2a2a", "star"),
    "Chaos Space Marines":  ("#1b3038", "#b88a3a", "star"),
    "Dark Angels":          ("#004b21", "#c79a3a", "aquila"),
    "Death Guard":          ("#566010", "#c8b44a", "triskull"),
    "Drukhari":             ("#005b5b", "#d9cdb0", "blade"),
    "Emperor's Children":   ("#814a60", "#e9c6dd", "star"),
    "Genestealer Cults":    ("#3e1532", "#caa23a", "claw"),
    "Grey Knights":         ("#486571", "#cdd6dd", "skull"),
    "Imperial Agents":      ("#055374", "#c79a3a", "skull"),
    "Imperial Knights":     ("#004961", "#c79a3a", "aquila"),
    "Leagues of Votann":    ("#3d544c", "#d8a33a", "hex"),
    "Necrons":              ("#00592f", "#4dcc6e", "ankh"),
    "Orks":                 ("#63711f", "#9c2a2a", "jaw"),
    "Space Marines":        ("#516765", "#c79a3a", "aquila"),
    "Space Wolves":         ("#3f676f", "#c7b27a", "skull"),
    "T'au Empire":          ("#006d9c", "#d68a2a", "hex"),
    "Thousand Sons":        ("#004e5f", "#c79a3a", "star"),
    "Tyranids":             ("#462e64", "#d9cdb0", "claw"),
    "World Eaters":         ("#521618", "#b88a3a", "skull"),

    # "Agents of the Imperium" is the cross-faction keyword form of the Imperial
    # Agents faction (used on shared Space Marine datasheets and the catalogue
    # drill-in); share its colours so neither surface falls back to grey.
    "Agents of the Imperium": ("#055374", "#c79a3a", "skull"),

    # ── Space Marine chapters outside GW's faction-colour list ──────────────────
    # Kept thematic so chapter rollups stay visually distinct from one another.
    "Deathwatch":       ("#0d0d0d", "#9c9c9c", "skull"),
    "Imperial Fists":   ("#c8a432", "#0d0d0d", "aquila"),
    "Iron Hands":       ("#1a1a1a", "#707070", "gear"),
    "Raven Guard":      ("#0d0d0d", "#d0d0d0", "blade"),
    "Salamanders":      ("#1a4a28", "#c79a3a", "aquila"),
    "Ultramarines":     ("#1f3d6e", "#c79a3a", "aquila"),
    "White Scars":      ("#c8c8d0", "#8a1818", "aquila"),

    # ── Other sub-factions / unaligned ──────────────────────────────────────────
    "Chaos Daemons":    ("#7a1030", "#caa1d6", "star"),
    "Ynnari":           ("#5a2d6e", "#d9cdb0", "blade"),
    "Unaligned Forces": ("#4a4a4a", "#cccccc", "skull"),
}

DEFAULT = ("#4a4a4a", "#cccccc", "skull")


def _norm(name):
    """Normalise a faction name for lookup: drop apostrophes (straight or curly),
    collapse whitespace and lowercase. Mirrors the client-side facKey()."""
    s = (name or "").replace("’", "").replace("‘", "").replace("'", "")
    return _re.sub(r"\s+", " ", s).strip().lower()


_THEME_NORM = {_norm(k): v for k, v in THEME.items()}


def theme_for(name):
    """Return (primary, accent, glyph) for a faction name.

    Accepts:
      - Display name:      "Space Marines"
      - Full BSData name:  "Imperium - Adeptus Astartes - Space Marines"
    Tolerant of casing and straight vs curly apostrophes, so "T'au Empire",
    "T’au Empire" and "Imperial Agents" all resolve rather than falling to grey.
    """
    if name in THEME:
        return THEME[name]
    norm = _norm(name)
    if norm in _THEME_NORM:
        return _THEME_NORM[norm]
    # Strip BSData/keyword prefix hierarchy — match on the trailing segment.
    if name and " - " in name:
        tail = _norm(name.rsplit(" - ", 1)[-1])
        if tail in _THEME_NORM:
            return _THEME_NORM[tail]
    return DEFAULT


def _glyph(key, accent):
    a = accent
    if key == "skull":
        return f'''
        <path fill="{a}" d="M50 22c-15 0-25 11-25 26 0 9 4 14 8 18l-1 9 8-3 3 5 4-6 4 6 3-5 8 3-1-9c4-4 8-9 8-18 0-15-10-26-25-26z"/>
        <circle cx="40" cy="48" r="6" fill="#0d0d0d"/><circle cx="60" cy="48" r="6" fill="#0d0d0d"/>
        <path d="M50 56l-4 9h8z" fill="#0d0d0d"/>'''
    if key == "aquila":
        return f'''
        <path fill="{a}" d="M50 30c-3 0-5 2-5 6v30h10V36c0-4-2-6-5-6z"/>
        <path fill="{a}" d="M48 40C36 36 24 38 16 46c10-1 18 2 24 8l8-6zM52 40c12-4 24-2 32 6-10-1-18 2-24 8l-8-6z"/>'''
    if key == "gear":
        teeth = ""
        import math
        for i in range(12):
            ang = math.radians(i * 30)
            x = 50 + 34 * math.cos(ang)
            y = 50 + 34 * math.sin(ang)
            teeth += f'<rect x="{x-4:.1f}" y="{y-4:.1f}" width="8" height="8" fill="{a}" transform="rotate({i*30} {x:.1f} {y:.1f})"/>'
        return f'{teeth}<circle cx="50" cy="50" r="26" fill="{a}"/><circle cx="50" cy="50" r="13" fill="#0d0d0d"/>'
    if key == "blade":
        return f'<path fill="{a}" d="M50 18c8 18 8 46 0 64-8-18-8-46 0-64z"/><path fill="{a}" d="M30 40c12 6 28 6 40 0-12 10-28 10-40 0z" opacity="0.85"/>'
    if key == "star":  # 8-pointed mark
        import math
        pts = []
        for i in range(16):
            r = 36 if i % 2 == 0 else 13
            ang = math.radians(i * 22.5 - 90)
            pts.append(f"{50 + r*math.cos(ang):.1f},{50 + r*math.sin(ang):.1f}")
        return f'<polygon points="{" ".join(pts)}" fill="{a}"/>'
    if key == "triskull":
        return f'''<circle cx="50" cy="36" r="11" fill="{a}"/>
        <circle cx="36" cy="60" r="11" fill="{a}"/><circle cx="64" cy="60" r="11" fill="{a}"/>
        <circle cx="50" cy="36" r="4" fill="#0d0d0d"/><circle cx="36" cy="60" r="4" fill="#0d0d0d"/><circle cx="64" cy="60" r="4" fill="#0d0d0d"/>'''
    if key == "claw":
        return f'''<path fill="{a}" d="M40 20c-6 14-6 30 2 46 3 6 8 10 14 14-4-8-6-16-6-26 6 8 10 16 12 26 2-12 0-24-6-36-5-10-10-18-16-24z"/>'''
    if key == "hex":
        import math
        pts = [f"{50 + 34*math.cos(math.radians(60*i-30)):.1f},{50 + 34*math.sin(math.radians(60*i-30)):.1f}" for i in range(6)]
        inner = [f"{50 + 16*math.cos(math.radians(60*i-30)):.1f},{50 + 16*math.sin(math.radians(60*i-30)):.1f}" for i in range(6)]
        return f'<polygon points="{" ".join(pts)}" fill="{a}"/><polygon points="{" ".join(inner)}" fill="#0d0d0d"/>'
    if key == "ankh":
        return f'<circle cx="50" cy="34" r="14" fill="none" stroke="{a}" stroke-width="7"/><rect x="46" y="44" width="8" height="34" fill="{a}"/><rect x="34" y="56" width="32" height="8" fill="{a}"/>'
    if key == "jaw":
        return f'''<path fill="{a}" d="M30 40h40v10c0 12-9 22-20 22S30 62 30 50z"/>
        <path fill="#0d0d0d" d="M38 52l4 10 4-10 4 10 4-10 4 10 4-10"/>
        <path fill="{a}" d="M34 36l6-10 6 8 4-10 4 10 6-8 6 10z"/>'''
    return ""


def _lighten(hex_color, amount=0.22):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def placeholder_svg(faction_name, unit_name, did, size=600):
    """Reference-image fallback: a faction-coloured plate with the unit name."""
    primary, accent, glyph = theme_for(faction_name)
    inner = _glyph(glyph, accent)
    safe = (unit_name or "").replace("&", "&amp;").replace("<", "&lt;")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="{size}" height="{size}">
  <defs>
    <linearGradient id="p{did}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{_lighten(primary,0.12)}"/>
      <stop offset="100%" stop-color="#0d0d0d"/>
    </linearGradient>
    <pattern id="grid{did}" width="20" height="20" patternUnits="userSpaceOnUse">
      <path d="M20 0H0V20" fill="none" stroke="{accent}" stroke-width="0.5" opacity="0.12"/>
    </pattern>
  </defs>
  <rect width="400" height="400" fill="url(#p{did})"/>
  <rect width="400" height="400" fill="url(#grid{did})"/>
  <g transform="translate(150 90) scale(1.0)" opacity="0.9">{inner}</g>
  <rect x="0" y="300" width="400" height="100" fill="#0d0d0d" opacity="0.55"/>
  <text x="200" y="332" text-anchor="middle" fill="{accent}" font-family="Georgia, serif" font-size="11" letter-spacing="3" opacity="0.8">REFERENCE IMAGE</text>
  <text x="200" y="362" text-anchor="middle" fill="#f2ead8" font-family="Georgia, serif" font-size="20" font-weight="bold">{_wrap(safe)}</text>
</svg>'''


def _wrap(text, limit=26):
    if len(text) <= limit:
        return text
    words, line, out = text.split(), "", []
    for w in words:
        if len(line + " " + w) > limit:
            out.append(line.strip())
            line = w
        else:
            line += " " + w
    out.append(line.strip())
    return out[0] + ("…" if len(out) > 1 else "")
