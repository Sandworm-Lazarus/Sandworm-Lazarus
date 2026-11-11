#!/usr/bin/env python3
"""Build the SVG assets for the Sandworm Lazarus GitHub profile README.

All text is converted to outlines (HarfBuzz shaping + font outlines), because
GitHub serves README images without web fonts. The fonts are the self-hosted
Chakra Petch / Anuphan / JetBrains Mono files of sandworm-lazarus.pages.dev
(SIL Open Font License); they are downloaded on first run.

Usage:  python -X utf8 build_assets.py
Needs:  fonttools, brotli, uharfbuzz
"""
import io
import math
import os
import urllib.request
from xml.sax.saxutils import escape

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
FONT_DIR = os.environ.get("SW_FONT_DIR") or os.path.join(os.environ.get("TEMP", HERE), "sw-fonts")
SITE = "https://sandworm-lazarus.pages.dev"
FONT_URL = SITE + "/assets/fonts/{}-normal.woff2"


# ---------------------------------------------------------------- palette ---
def oklch(L, C, h):
    """OKLCH -> sRGB hex (gamut-clipped), same tokens as the website CSS."""
    hr = math.radians(h)
    a, b = C * math.cos(hr), C * math.sin(hr)
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
           -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)

    def enc(x):
        x = min(1.0, max(0.0, x))
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
    return "#%02x%02x%02x" % tuple(round(enc(v) * 255) for v in rgb)


BG = oklch(0.145, 0.022, 240)
RAISE = oklch(0.185, 0.026, 238)
LINE = oklch(0.36, 0.04, 230)
SOFT = oklch(0.25, 0.03, 236)
INK = oklch(0.945, 0.012, 210)
INK2 = oklch(0.8, 0.028, 215)
INK3 = oklch(0.66, 0.034, 220)
THREAT = oklch(0.66, 0.225, 22)
THREAT_INK = oklch(0.77, 0.165, 22)
GUARD = oklch(0.86, 0.19, 152)
WARN = oklch(0.85, 0.15, 80)
DATA = oklch(0.83, 0.115, 215)


# ------------------------------------------------------------------ fonts ---
FAMILY = {
    "display": {500: ("chakra-petch-latin-500", "chakra-petch-thai-500"),
                600: ("chakra-petch-latin-600", "chakra-petch-thai-600"),
                700: ("chakra-petch-latin-700", "chakra-petch-thai-700")},
    "read": {400: ("anuphan-latin-400", "anuphan-thai-400"),
             500: ("anuphan-latin-500", "anuphan-thai-500"),
             600: ("anuphan-latin-600", "anuphan-thai-600")},
    # JetBrains Mono has no Thai: Thai inside mono labels uses Chakra Petch.
    "mono": {400: ("jetbrains-mono-latin-400", "chakra-petch-thai-500"),
             600: ("jetbrains-mono-latin-600", "chakra-petch-thai-600")},
}


class Face:
    def __init__(self, name):
        path = os.path.join(FONT_DIR, name + ".woff2")
        if not os.path.exists(path):
            os.makedirs(FONT_DIR, exist_ok=True)
            urllib.request.urlretrieve(FONT_URL.format(name), path)
        tt = TTFont(path)
        tt.flavor = None                      # woff2 -> sfnt bytes for HarfBuzz
        buf = io.BytesIO()
        tt.save(buf)
        data = buf.getvalue()
        self.name = name
        self.tt = TTFont(io.BytesIO(data))
        self.gs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.upem = self.tt["head"].unitsPerEm
        self.hb = hb.Font(hb.Face(hb.Blob(data)))


_faces = {}


def face(family, weight, thai):
    name = FAMILY[family][weight][1 if thai else 0]
    if name not in _faces:
        _faces[name] = Face(name)
    return _faces[name]


def is_thai(ch):
    return 0x0E01 <= ord(ch) <= 0x0E5B


def runs(text):
    out, cur, buf = [], None, ""
    for ch in text:
        t = is_thai(ch)
        if cur is None or t == cur:
            buf += ch
        else:
            out.append((cur, buf))
            buf = ch
        cur = t
    if buf:
        out.append((cur, buf))
    return out


def n1(v):
    s = "%.1f" % v
    s = s[:-2] if s.endswith(".0") else s
    return "0" if s == "-0" else s


def n2(v):
    s = ("%.2f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Text:
    """Shaped text: width is known before drawing, so layouts can align."""

    def __init__(self, s, family="read", weight=400, size=16, track=0.0):
        self.glyphs = []
        x = 0.0
        last_track = 0.0
        for thai, chunk in runs(s):
            f = face(family, weight, thai)
            sc = size / f.upem
            run_track = 0.0 if thai else track   # Thai is never letter-spaced
            buf = hb.Buffer()
            buf.add_str(chunk)
            buf.guess_segment_properties()
            hb.shape(f.hb, buf, {"kern": True})
            for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
                if info.codepoint == 0:
                    raise ValueError(f"missing glyph in {f.name} for {chunk!r}")
                self.glyphs.append((f, f.order[info.codepoint],
                                    x + pos.x_offset * sc, -pos.y_offset * sc, sc))
                x += pos.x_advance * sc
                if pos.x_advance:
                    x += run_track
                    last_track = run_track
        self.width = x - last_track

    def d(self, x, y, anchor="start"):
        if anchor == "middle":
            x -= self.width / 2
        elif anchor == "end":
            x -= self.width
        parts = []
        for f, name, gx, gy, sc in self.glyphs:
            pen = SVGPathPen(f.gs, ntos=n1)
            f.gs[name].draw(TransformPen(pen, (sc, 0, 0, -sc, x + gx, y + gy)))
            cmd = pen.getCommands()
            if cmd:
                parts.append(cmd)
        return "".join(parts)


def text(s, x, y, fill, family="read", weight=400, size=16, track=0.0,
         anchor="start", attrs=""):
    t = Text(s, family, weight, size, track)
    return f'<path d="{t.d(x, y, anchor)}" fill="{fill}"{attrs}/>', t.width


def t(*a, **k):
    return text(*a, **k)[0]


def seq(parts, x, y, family="mono", weight=600, size=11, track=0.0, anchor="start"):
    """Inline run of differently coloured pieces: parts = [(string, colour), ...]."""
    shaped = [(Text(s, family, weight, size, track), c) for s, c in parts]
    total = sum(sh.width for sh, _ in shaped) + track * (len(shaped) - 1)
    if anchor == "middle":
        x -= total / 2
    elif anchor == "end":
        x -= total
    out, cx = [], x
    for sh, c in shaped:
        out.append(f'<path d="{sh.d(cx, y)}" fill="{c}"/>')
        cx += sh.width + track
    return "".join(out), total


def fit(s, max_w, family, weight, size, min_size):
    while size >= min_size:
        if Text(s, family, weight, size).width <= max_w:
            return size
        size -= 0.5
    raise ValueError(f"text does not fit {max_w}px: {s!r}")


# ------------------------------------------------------------- primitives ---
def ch(x, y, w, h, c):
    """Chamfered box, corners cut top-right and bottom-left like the site mark."""
    return (f"M{n2(x)} {n2(y)}H{n2(x + w - c)}L{n2(x + w)} {n2(y + c)}"
            f"V{n2(y + h)}H{n2(x + c)}L{n2(x)} {n2(y + h - c)}Z")


def panel(w, h, c=16, fill=BG, stroke=SOFT):
    return f'<path d="{ch(0.5, 0.5, w - 1, h - 1, c)}" fill="{fill}" stroke="{stroke}"/>'


def arrow(x, y, color, size=10, width=1.8):
    k = size * 0.42
    return (f'<path d="M{n2(x - size)} {n2(y)}H{n2(x)}M{n2(x - k)} {n2(y - k)}L{n2(x)} {n2(y)}'
            f'L{n2(x - k)} {n2(y + k)}" stroke="{color}" stroke-width="{width}" '
            'stroke-linecap="round" stroke-linejoin="round" fill="none"/>')


def grid(pid, step=24, opacity=0.55):
    return (f'<pattern id="{pid}" width="{step}" height="{step}" patternUnits="userSpaceOnUse">'
            f'<path d="M{step} 0H0V{step}" stroke="{SOFT}" stroke-width="1" opacity="{opacity}"/>'
            '</pattern>')


def mark(x, y, size, cls="sq"):
    k = size / 32
    return (f'<g transform="translate({n2(x)} {n2(y)}) scale({n2(k)})">'
            f'<path d="M2 2H24L30 8V30H8L2 24Z" stroke="{THREAT}" stroke-width="2"/>'
            f'<path class="{cls}" d="M8 20c3-8 6 4 9-4s5 2 7-2" pathLength="100" stroke="{GUARD}" '
            'stroke-width="2.2" stroke-linecap="round"/></g>')


BASE_CSS = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
RISE_CSS = (".rise{animation:rise .8s cubic-bezier(.16,1,.3,1) both}"
            "@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}")
DRAW_CSS = (".sq{stroke-dasharray:100;animation:draw 6s ease-in-out infinite}"
            "@keyframes draw{0%{stroke-dashoffset:100}30%,80%{stroke-dashoffset:0}100%{stroke-dashoffset:-100}}")


def doc(w, h, title, body, css="", defs=""):
    label = escape(title, {'"': "&quot;"})
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" fill="none" role="img" aria-label="{label}">'
            f"<title>{escape(title)}</title><style>{BASE_CSS}{css}</style>"
            f"<defs>{defs}</defs>{body}</svg>")


# ------------------------------------------------------------------ hero ---
def hero():
    W, H = 840, 440
    defs = (grid("g") +
            f'<clipPath id="clip"><path d="{ch(0, 0, W, H, 20)}"/></clipPath>'
            '<radialGradient id="fade" cx=".72" cy=".28" r=".75"><stop offset="0" stop-color="#fff"/>'
            '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
            f'<mask id="gm"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>'
            f'<radialGradient id="gr" cx=".86" cy=".16" r=".5"><stop offset="0" stop-color="{THREAT}" stop-opacity=".18"/>'
            f'<stop offset="1" stop-color="{THREAT}" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="gb" cx=".08" cy=".96" r=".55"><stop offset="0" stop-color="{DATA}" stop-opacity=".11"/>'
            f'<stop offset="1" stop-color="{DATA}" stop-opacity="0"/></radialGradient>'
            f'<linearGradient id="sc" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{DATA}" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="{DATA}" stop-opacity=".08"/><stop offset="1" stop-color="{DATA}" stop-opacity="0"/></linearGradient>'
            '<filter id="glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="3" result="b"/>'
            '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
            '<clipPath id="band1"><rect x="0" y="160" width="840" height="16"/></clipPath>'
            '<clipPath id="band2"><rect x="0" y="184" width="840" height="12"/></clipPath>')
    css = (DRAW_CSS +
           ".scan{animation:scan 9s linear infinite}@keyframes scan{to{transform:translateY(540px)}}"
           ".gl{opacity:0}.g1{animation:g1 7s steps(1,end) infinite}.g2{animation:g2 7s steps(1,end) infinite}"
           "@keyframes g1{0%,88%{opacity:0;transform:none}89%{opacity:.8;transform:translate(-4px,0)}"
           "91%{opacity:.7;transform:translate(3px,0)}93%,100%{opacity:0;transform:none}}"
           "@keyframes g2{0%,88%{opacity:0;transform:none}89%{opacity:.7;transform:translate(4px,0)}"
           "91%{opacity:.6;transform:translate(-3px,0)}93%,100%{opacity:0;transform:none}}"
           ".stamp{transform-box:fill-box;transform-origin:center;animation:stamp .5s cubic-bezier(.2,1.6,.4,1) .9s both}"
           "@keyframes stamp{from{opacity:0;transform:scale(1.35)}to{opacity:1;transform:none}}"
           ".flow{stroke-dasharray:5 6;animation:flow .9s linear infinite}@keyframes flow{to{stroke-dashoffset:-11}}"
           ".dflow{stroke-dasharray:2 6;animation:dflow 2.4s linear infinite}@keyframes dflow{to{stroke-dashoffset:-16}}"
           ".pk{opacity:0;transform-box:fill-box;transform-origin:center;animation:pk 3.6s cubic-bezier(.45,0,.55,1) infinite}"
           "@keyframes pk{0%{opacity:0;transform:translateX(0)}6%{opacity:1}68%{opacity:1;transform:translateX(250px) scale(1)}"
           "76%,100%{opacity:0;transform:translateX(250px) scale(2.6)}}"
           ".rg{opacity:0;transform-box:fill-box;transform-origin:center;animation:rg 3.6s ease-out infinite}"
           "@keyframes rg{0%,66%{opacity:0;transform:scale(.3)}70%{opacity:1;transform:scale(.4)}100%{opacity:0;transform:scale(1.7)}}"
           ".bar{animation:bar 3.6s ease-out infinite}@keyframes bar{0%,66%,92%,100%{stroke-width:3.5}71%{stroke-width:7}}"
           ".live{animation:live 1.6s ease-in-out infinite}@keyframes live{50%{opacity:.25}}")
    b = [f'<path d="{ch(0, 0, W, H, 20)}" fill="{BG}"/>',
         '<g clip-path="url(#clip)">',
         f'<rect width="{W}" height="{H}" fill="url(#g)" mask="url(#gm)"/>',
         f'<rect width="{W}" height="{H}" fill="url(#gr)"/><rect width="{W}" height="{H}" fill="url(#gb)"/>',
         f'<rect class="scan" y="-90" width="{W}" height="90" fill="url(#sc)"/></g>',
         f'<path d="{ch(0.5, 0.5, W - 1, H - 1, 20)}" stroke="{SOFT}"/>',
         f'<path d="M24 48V24H48M816 392V416H792" stroke="{WARN}" stroke-width="2"/>']

    b.append(seq([("CASE LIBRARY", INK3), ("  ·  ", INK3), ("30 FILES", THREAT),
                  ("  ·  ", INK3), ("THAI-LANGUAGE", INK3)], 48, 66, size=12, track=2.4)[0])
    b.append(t("Sandworm", 44, 140, INK, "display", 700, 68))
    laz = Text("Lazarus", "display", 700, 68).d(44, 208)
    b.append(f'<path d="{laz}" fill="{THREAT}"/>')
    b.append(f'<g clip-path="url(#band1)"><path class="gl g1" d="{laz}" fill="{DATA}"/></g>')
    b.append(f'<g clip-path="url(#band2)"><path class="gl g2" d="{laz}" fill="{THREAT_INK}"/></g>')
    b.append(t("Cybersecurity, explained visually — step by step,", 46, 252, INK2, "read", 400, 20))
    b.append(t("from absolute zero to professional practice.", 46, 283, INK2, "read", 400, 20))

    b.append(mark(704, 46, 92))
    stamp_txt, _ = text("CASE OPEN", 745, 231, THREAT, "display", 600, 18, track=3.4, anchor="middle")
    b.append(f'<g transform="rotate(-7 745 224)"><g class="stamp">'
             f'<rect x="668" y="202" width="154" height="44" stroke="{THREAT}" stroke-width="2"/>{stamp_txt}</g></g>')

    # --- attack chain band
    b.append(f'<path d="M48 306H792" stroke="{SOFT}" stroke-dasharray="2 6"/>')
    b.append(seq([("ATTACK CHAIN", INK3), ("  ·  ", INK3), ("WHERE WE BREAK IT", INK3)],
                 48, 334, size=11, track=2)[0])
    live, lw = seq([("SIMULATION", INK3)], 792, 334, size=11, track=2, anchor="end")
    b.append(live + f'<circle class="live" cx="{n2(792 - lw - 12)}" cy="330" r="3.5" fill="{DATA}"/>')

    cy, bh, bw = 368, 40, 132
    xs = [48, 252, 456, 660]
    b.append(f'<path class="flow" d="M180 {cy}H252" stroke="{THREAT}" stroke-width="2"/>')
    b.append(f'<path class="flow" d="M384 {cy}H430" stroke="{THREAT}" stroke-width="2"/>')
    b.append(f'<path class="dflow" d="M588 {cy}H660" stroke="{DATA}" stroke-width="2" stroke-linecap="round"/>')
    b.append(f'<circle class="pk" cx="180" cy="{cy}" r="5" fill="{THREAT}" filter="url(#glow)"/>')
    nodes = [("Attacker", "sends a phishing link", THREAT_INK, THREAT),
             ("Risk point", "arrives via chat", WARN, WARN),
             ("Defense", "we don't click", GUARD, GUARD),
             ("Our data", "stays safe", DATA, DATA)]
    for x, (label, sub, ink, col) in zip(xs, nodes):
        y = cy - bh / 2
        b.append(f'<path d="{ch(x, y, bw, bh, 9)}" fill="{BG}"/>')
        b.append(f'<path d="{ch(x, y, bw, bh, 9)}" fill="{col}" fill-opacity=".12" stroke="{col}" stroke-opacity=".85" stroke-width="1.5"/>')
        b.append(t(label, x + bw / 2, cy + 6, ink, "display", 600, 16, anchor="middle"))
        b.append(t(sub, x + bw / 2, cy + 44, INK3, "mono", 400,
                   fit(sub, bw + 40, "mono", 400, 12, 10.5), anchor="middle"))
    b.append(f'<path d="M438 {cy}H456" stroke="{GUARD}" stroke-width="2"/>')
    b.append(f'<path class="bar" d="M438 {cy - 16}V{cy + 16}" stroke="{GUARD}" stroke-width="3.5" '
             'stroke-linecap="round" filter="url(#glow)"/>')
    b.append(f'<circle class="rg" cx="438" cy="{cy}" r="16" stroke="{GUARD}" stroke-width="2"/>')
    return doc(W, H, "Sandworm Lazarus — cybersecurity explained visually, step by step, "
               "from absolute zero to professional practice", "".join(b), css, defs)


# ------------------------------------------------------------------- CTA ---
def cta(label, color, primary=False):
    W, H = 272, 56
    fg = BG if primary else INK
    css = ""
    defs = f'<clipPath id="c"><path d="{ch(0, 0, W, H, 12)}"/></clipPath>'
    b = []
    if primary:
        defs += ('<linearGradient id="sh" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                 '<stop offset=".5" stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
        css = (".sh{transform:translateX(-120px) skewX(-20deg);animation:sh 5s ease-in-out 1.2s infinite}"
               "@keyframes sh{0%{transform:translateX(-120px) skewX(-20deg)}30%,100%{transform:translateX(360px) skewX(-20deg)}}")
        b.append(f'<path d="{ch(0, 0, W, H, 12)}" fill="{color}"/>')
        b.append(f'<g clip-path="url(#c)"><rect class="sh" x="0" y="-10" width="70" height="80" fill="url(#sh)"/></g>')
    else:
        b.append(f'<path d="{ch(0.75, 0.75, W - 1.5, H - 1.5, 12)}" fill="{BG}" stroke="{color}" stroke-width="1.5"/>')
    size = fit(label, 196, "display", 600, 17, 14)
    b.append(t(label, 22, 34, fg, "display", 600, size))
    b.append(arrow(250, 28, fg if primary else color, 12, 2))
    return doc(W, H, label, "".join(b), css, defs)


# ----------------------------------------------------------------- stats ---
def stats():
    W, H = 840, 108
    cells = [("LIBRARY", "30", "case files", THREAT), ("PRACTICE", "11", "hands-on labs", GUARD),
             ("CURRICULUM", "3", "core paths", DATA), ("SPECIALIZE", "6", "expert tracks", WARN)]
    b = [panel(W, H, 14)]
    for i, (code, num, th, col) in enumerate(cells):
        x0 = i * 210
        if i:
            b.append(f'<path d="M{x0}.5 22V86" stroke="{SOFT}"/>')
        g = [f'<path d="{ch(x0 + 28, 29, 9, 9, 3)}" fill="{col}"/>',
             t(code, x0 + 44, 38, INK3, "mono", 600, 11, track=2)]
        numsvg, nw = text(num, x0 + 27, 86, col, "display", 700, 42)
        g.append(numsvg)
        avail = 210 - 27 - nw - 10 - 14
        g.append(t(th, x0 + 27 + nw + 10, 83, INK2, "read", 500, fit(th, avail, "read", 500, 16, 13)))
        b.append(f'<g class="rise" style="animation-delay:{0.15 + i * 0.12:.2f}s">{"".join(g)}</g>')
    return doc(W, H, "30 case files · 11 hands-on labs · 3 core learning paths · 6 expert tracks",
               "".join(b), RISE_CSS)


# -------------------------------------------------------- section header ---
def section(idx, th, en):
    W, H = 840, 60
    b = [panel(W, H, 12),
         f'<path d="{ch(14, 13, 34, 34, 7)}" fill="{THREAT}" fill-opacity=".1" stroke="{THREAT}" stroke-opacity=".9"/>',
         t(idx, 31, 35, THREAT, "mono", 600, 13, anchor="middle")]
    title, tw = text(th, 62, 38, INK, "display", 600, 21)
    right, rw = seq([(en, INK3)], 816, 35, size=11, track=2.6, anchor="end")
    b += [title, right,
          f'<path d="M{n2(62 + tw + 18)} 31H{n2(816 - rw - 18)}" stroke="{SOFT}" stroke-dasharray="2 5"/>']
    return doc(W, H, f"{idx} {th}", "".join(b))


# ------------------------------------------------------------- path card ---
def path_card(i, title, sub, steps, hours, col):
    W, H = 272, 200
    css = ".seg{animation:seg 4.8s ease-in-out infinite}@keyframes seg{0%,100%{opacity:.22}12%,70%{opacity:1}}"
    b = [panel(W, H, 16),
         f'<path d="M0.5 0.5H110" stroke="{col}" stroke-width="2"/>',
         t(f"PATH 0{i}", 20, 36, INK3, "mono", 600, 11, track=2),
         f'<path d="{ch(236, 24, 14, 14, 4)}" stroke="{col}" stroke-width="1.5"/>',
         t(title, 20, 80, INK, "display", 600, fit(title, 232, "display", 600, 24, 18)),
         t(sub, 20, 106, INK2, "read", 400, fit(sub, 232, "read", 400, 14.5, 12))]
    gap = 3
    sw = (232 - gap * (steps - 1)) / steps
    for k in range(steps):
        x = 20 + k * (sw + gap)
        b.append(f'<rect class="seg" style="animation-delay:{k * 0.09:.2f}s" x="{n2(x)}" y="128" '
                 f'width="{n2(sw)}" height="6" rx="1" fill="{col}"/>')
    b.append(t(f"{steps} steps · ~{hours} hrs", 20, 174, INK3, "mono", 400, 12))
    go, gw = text("View path", 232, 174, col, "display", 600, 14, anchor="end")
    b.append(go + arrow(252, 169, col, 10, 1.8))
    return doc(W, H, f"{title}: {sub} · {steps} steps · about {hours} hours", "".join(b), css)


# ---------------------------------------------------------------- tracks ---
def icon(kind, cx, cy, col):
    s = f'stroke="{col}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
    if kind == "code":
        return (f'<path d="M{cx - 4} {cy - 6}L{cx - 10} {cy}L{cx - 4} {cy + 6}M{cx + 4} {cy - 6}L{cx + 10} {cy}'
                f'L{cx + 4} {cy + 6}M{cx + 2} {cy - 8}L{cx - 2} {cy + 8}" {s}/>')
    if kind == "cloud":
        return (f'<path d="M{cx - 7} {cy + 6}H{cx + 7}a5 5 0 0 0 0-10a7 7 0 0 0-13-1a5 5 0 0 0-1 11Z" {s}/>')
    if kind == "lens":
        return f'<circle cx="{cx - 2}" cy="{cy - 2}" r="6" {s}/><path d="M{cx + 2.5} {cy + 2.5}L{cx + 8} {cy + 8}" {s}/>'
    if kind == "radar":
        return (f'<circle cx="{cx}" cy="{cy}" r="2" fill="{col}"/>'
                f'<path d="M{cx - 6} {cy}a6 6 0 0 1 6-6M{cx - 10} {cy}a10 10 0 0 1 10-10M{cx} {cy}L{cx + 7} {cy - 7}" {s}/>')
    if kind == "chip":
        pins = "".join(f"M{cx + d} {cy - 10}V{cy - 7}M{cx + d} {cy + 7}V{cy + 10}M{cx - 10} {cy + d}H{cx - 7}M{cx + 7} {cy + d}H{cx + 10}"
                       for d in (-3, 3))
        return f'<rect x="{cx - 7}" y="{cy - 7}" width="14" height="14" rx="2" {s}/><path d="{pins}" {s}/><circle cx="{cx}" cy="{cy}" r="2" fill="{col}"/>'
    if kind == "gear":
        ticks = "".join(f"M{n2(cx + 6 * math.cos(a))} {n2(cy + 6 * math.sin(a))}L{n2(cx + 9 * math.cos(a))} {n2(cy + 9 * math.sin(a))}"
                        for a in [k * math.pi / 4 for k in range(8)])
        return f'<circle cx="{cx}" cy="{cy}" r="5" {s}/><path d="{ticks}" {s}/><circle cx="{cx}" cy="{cy}" r="1.6" fill="{col}"/>'
    raise ValueError(kind)


def tracks():
    W, H = 840, 196
    items = [("AppSec", "Threat modeling to code review", "code", THREAT_INK),
             ("Cloud", "Access, configuration and recovery", "cloud", DATA),
             ("DFIR", "Evidence, timelines and file triage", "lens", WARN),
             ("Detection", "Write the rule, then verify it", "radar", GUARD),
             ("AI Security", "Govern agent data and permissions", "chip", THREAT_INK),
             ("OT Safety", "Assess live impact before changes", "gear", WARN)]
    cw, chh, gap, pad = (W - 40 - 24) / 3, 72, 12, 20
    b = [panel(W, H, 16)]
    for k, (name, desc, ic, col) in enumerate(items):
        x = pad + (k % 3) * (cw + gap)
        y = pad + (k // 3) * (chh + gap)
        g = [f'<path d="{ch(x, y, cw, chh, 10)}" fill="{RAISE}" stroke="{SOFT}"/>',
             f'<path d="{ch(x + 14, y + 18, 36, 36, 7)}" fill="{col}" fill-opacity=".1" stroke="{col}" stroke-opacity=".8"/>',
             icon(ic, x + 32, y + 36, col),
             t(name, x + 64, y + 32, INK, "display", 600, 17),
             t(desc, x + 64, y + 54, INK3, "read", 400, fit(desc, cw - 76, "read", 400, 13.5, 11.5))]
        b.append(f'<g class="rise" style="animation-delay:{0.1 + k * 0.08:.2f}s">{"".join(g)}</g>')
    return doc(W, H, "Expert tracks: AppSec, Cloud, DFIR, Detection, AI Security, OT Safety",
               "".join(b), RISE_CSS)


# -------------------------------------------------------------- lab card ---
def lab():
    W, H = 840, 252
    defs = f'<clipPath id="c"><path d="{ch(0, 0, W, H, 16)}"/></clipPath>'
    b = [panel(W, H, 16),
         f'<g clip-path="url(#c)"><rect width="{W}" height="44" fill="{RAISE}"/></g>',
         f'<path d="M0.5 44.5H839.5" stroke="{SOFT}"/>']
    for k, col in enumerate((THREAT, WARN, GUARD)):
        b.append(f'<path d="{ch(24 + k * 16, 17, 10, 10, 3)}" fill="{col}"/>')
    b.append(seq([("HANDS-ON LAB", INK3), ("  ·  ", INK3), ("INCIDENT TRIAGE", INK2)], 84, 27, size=11, track=2)[0])
    b.append(seq([("11 LABS", GUARD), ("  ·  ", INK3), ("SIMULATED EVIDENCE", INK3)], 816, 27,
                 size=11, track=2, anchor="end")[0])
    lines = [[("›", GUARD), ("  open lab --triage", INK)],
             [("[ALERT]", WARN), ("     separate anomalies from what cannot be concluded yet", INK2)],
             [("[EVIDENCE]", DATA), ("  cite the evidence row behind every finding", INK2)],
             [("[REPORT]", GUARD), ("    timeline · evidence · response plan · limitations", INK2)],
             [("›", GUARD), ("  11 labs · simulated files · tasks · answer guides · rubrics", INK3)]]
    css = [".cur{animation:blink 1.1s steps(1,end) infinite}@keyframes blink{50%{opacity:0}}"]
    cycle = 14
    for i, parts in enumerate(lines):
        y = 84 + i * 34
        svg, w = seq(parts, 28, y, family="mono", weight=400, size=14)
        b.append(svg)
        cover_w = w + 6
        if i == len(lines) - 1:
            b.append(f'<rect class="cur" x="{n2(28 + w + 8)}" y="{y - 14}" width="8" height="17" fill="{GUARD}"/>')
            cover_w = w + 20
        t0, t1 = 3 + i * 13, 3 + i * 13 + 10
        chars = max(8, sum(len(s) for s, _ in parts))
        css.append(f".c{i}{{transform:scaleX(0);transform-box:fill-box;transform-origin:right center;"
                   f"animation:t{i} {cycle}s infinite}}"
                   f"@keyframes t{i}{{0%,{t0}%{{transform:scaleX(1);animation-timing-function:steps({chars},end)}}"
                   f"{t1}%,93%{{transform:scaleX(0)}}97%,100%{{transform:scaleX(1)}}}}")
        b.append(f'<rect class="c{i}" x="24" y="{y - 21}" width="{n2(cover_w + 6)}" height="30" fill="{BG}"/>')
    return doc(W, H, "Hands-on labs: 11 labs with simulated evidence, tasks, answer guides and grading rubrics",
               "".join(b), "".join(css), defs)


# --------------------------------------------------------- arsenal card ---
def arsenal():
    W, H = 840, 172
    defs = (grid("g", 20, 0.5) + f'<clipPath id="c"><path d="{ch(0, 0, W, H, 16)}"/></clipPath>'
            '<linearGradient id="f" x1="0" y1="0" x2="1" y2="0"><stop offset=".45" stop-color="#fff" stop-opacity="0"/>'
            '<stop offset="1" stop-color="#fff"/></linearGradient>'
            f'<mask id="m"><rect width="{W}" height="{H}" fill="url(#f)"/></mask>')
    b = [panel(W, H, 16),
         f'<g clip-path="url(#c)"><rect width="{W}" height="{H}" fill="url(#g)" mask="url(#m)"/></g>',
         f'<path d="{ch(0.5, 0.5, W - 1, H - 1, 16)}" stroke="{SOFT}"/>',
         seq([("REPOSITORY", INK3), ("  ·  ", INK3), ("PUBLIC", GUARD), ("  ·  ", INK3), ("MIT LICENSE", INK3)],
             28, 38, size=11, track=2)[0],
         seq([("sandworm-", INK), ("arsenal", THREAT)], 28, 84, family="display", weight=700, size=32)[0],
         t("A curated AI & cybersecurity skill arsenal — Thai + English guides, commit-pinned sources.",
           28, 114, INK2, "read", 400,
           fit("A curated AI & cybersecurity skill arsenal — Thai + English guides, commit-pinned sources.",
               784, "read", 400, 16, 13)),
         t("57 skill entries  ·  19 collections  ·  3 evaluation tools", 28, 146, INK3, "mono", 400, 12)]
    x = 812
    for topic in reversed(["agent-skills", "appsec", "llm", "thai"]):
        tw = Text(topic, "mono", 400, 11).width
        cw = tw + 18
        x -= cw
        b.append(f'<path d="{ch(x, 22, cw, 22, 5)}" fill="{BG}" stroke="{LINE}"/>')
        b.append(t(topic, x + 9, 37, INK2, "mono", 400, 11))
        x -= 8
    go, gw = text("View repository", 788, 146, THREAT, "display", 600, 15, anchor="end")
    b.append(go + arrow(810, 141, THREAT, 11, 2))
    return doc(W, H, "sandworm-arsenal — a curated AI and cybersecurity skill arsenal",
               "".join(b), "", defs)


# ---------------------------------------------------------------- footer ---
def footer():
    W, H = 840, 76
    b = [panel(W, H, 12), mark(24, 20, 36),
         t("CASE OPEN", 76, 34, THREAT, "mono", 600, 11, track=2.4),
         t("Thai-language library · anonymous author · every visual drawn in code", 76, 55, INK3, "mono", 400, 12)]
    url, uw = text("sandworm-lazarus.pages.dev", 790, 43, DATA, "mono", 600, 12, anchor="end")
    b.append(url + arrow(812, 39, DATA, 10, 1.8))
    return doc(W, H, "Sandworm Lazarus · Thai-language library · anonymous author", "".join(b), DRAW_CSS)


# ------------------------------------------------------------------ main ---
def main():
    os.makedirs(OUT, exist_ok=True)
    files = {
        "hero.svg": hero(),
        "cta-start.svg": cta("Start with CASE-001", THREAT, primary=True),
        "cta-paths.svg": cta("Choose a learning path", DATA),
        "cta-library.svg": cta("Browse the library", GUARD),
        "stats.svg": stats(),
        "h-paths.svg": section("01", "Learning paths", "3 PATHS · 32 STEPS"),
        "h-tracks.svg": section("02", "Expert tracks", "6 SPECIALIZATIONS"),
        "h-labs.svg": section("03", "Hands-on labs", "LEARN BY EVIDENCE"),
        "h-projects.svg": section("04", "Projects", "OPEN SOURCE"),
        "path-safety.svg": path_card(1, "Start from zero", "Staying safe in digital life", 6, "1.0", GUARD),
        "path-foundation.svg": path_card(2, "Tech foundations", "From systems to evidence", 12, "7.1", DATA),
        "path-soc.svg": path_card(3, "SOC analyst", "From alert to incident report", 14, "6.7", THREAT),
        "tracks.svg": tracks(),
        "lab.svg": lab(),
        "arsenal.svg": arsenal(),
        "footer.svg": footer(),
    }
    for name, svg in files.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(svg)
        print(f"{name:22s} {len(svg.encode('utf-8')) / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
