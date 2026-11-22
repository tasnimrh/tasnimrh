"""Builds the artwork for the profile README.

Run:  pip install fonttools uharfbuzz brotli  &&  python tools/build_assets.py

GitHub shows README SVGs through an <img> tag, which cannot load web fonts, so every
piece of text is converted to vector outlines. Each asset is written in a light and a
dark version with a transparent background, so it sits on the page in either theme.

The order field and the review-budget chart are drawn from real results: the locked
final model from the Olist project, scored on the held-out test set (olist-curve.json,
olist_sample.json, exported from notebook 05).
"""
import json
import os
import urllib.request

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
OUT = os.path.join(HERE, "..", "assets")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

# Geist and Geist Mono (SIL Open Font License). Fetched once and cached, not committed,
# since only their outlines end up in the SVGs.
GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONT_URLS = {
    "Geist.ttf": GF + "geist/Geist%5Bwght%5D.ttf",
    "GeistMono.ttf": GF + "geistmono/GeistMono%5Bwght%5D.ttf",
}
for _name, _url in FONT_URLS.items():
    _path = os.path.join(CACHE, _name)
    if not os.path.exists(_path):
        urllib.request.urlretrieve(_url, _path)

CURVE = json.load(open(os.path.join(HERE, "olist-curve.json")))
SAMPLE = json.load(open(os.path.join(HERE, "olist_sample.json")))

W = 880  # close to the README column width on desktop, so type renders near 1:1

THEMES = {
    "dark": dict(ink="#E6EDF3", muted="#9198A1", dim="#6E7681", rule="#30363D", soft="#151B23",
                 accent="#7EE0C3", miss="#F08C8C", warn="#E3B46C", bg="#0D1117"),
    "light": dict(ink="#1F2328", muted="#59636E", dim="#818B98", rule="#D1D9E0", soft="#F6F8FA",
                  accent="#0F7B63", miss="#C8473F", warn="#9A6700", bg="#FFFFFF"),
}


class Face:
    """One static instance of a variable font, shaped with HarfBuzz."""

    def __init__(self, key, file, **axes):
        self.key = key
        path = os.path.join(CACHE, key + ".ttf")
        tt = instancer.instantiateVariableFont(TTFont(os.path.join(CACHE, file)), axes)
        tt.save(path)
        self.tt = TTFont(path)
        self.gs = self.tt.getGlyphSet()
        self.upm = self.tt["head"].unitsPerEm
        self.hb = hb.Font(hb.Face(hb.Blob.from_file_path(path)))

    def shape(self, text):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True})
        return [(i.codepoint, p.x_advance, p.x_offset, p.y_offset)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]


FACES = {
    "D": Face("D", "Geist.ttf", wght=500),       # name
    "H": Face("H", "Geist.ttf", wght=560),       # titles
    "L": Face("L", "Geist.ttf", wght=400),       # tagline and prose
    "S": Face("S", "Geist.ttf", wght=560),       # prose, strong
    "M": Face("M", "GeistMono.ttf", wght=400),   # data and labels
    "N": Face("N", "GeistMono.ttf", wght=560),   # data, strong
}


class Svg:
    def __init__(self, h, theme, title, desc, css=""):
        self.h, self.t, self.theme = h, THEMES[theme], theme
        self.title, self.desc, self.css = title, desc, css
        self.defs, self.used, self.body = [], set(), []

    def c(self, name):
        return self.t.get(name, name)

    def width(self, face, text, size, track=0.0):
        f = FACES[face]
        s = size / f.upm
        return sum(a for _, a, _, _ in f.shape(text)) * s + track * size * len(text)

    def text(self, face, text, x, y, size, color="ink", anchor="start", track=0.0, cls=None):
        f = FACES[face]
        s = size / f.upm
        if anchor != "start":
            w = self.width(face, text, size, track)
            x -= w if anchor == "end" else w / 2
        pen_x, uses = 0.0, []
        for gid, adv, xo, yo in f.shape(text):
            gname = f.tt.getGlyphName(gid)
            ref = f"{f.key}{gid}"
            if ref not in self.used:
                pen = SVGPathPen(f.gs, ntos=lambda v: str(int(round(v))))
                f.gs[gname].draw(pen)
                self.used.add(ref)
                self.defs.append(f'<path id="{ref}" d="{pen.getCommands()}"/>')
            if gname != "space":
                uses.append(f'<use href="#{ref}" x="{pen_x + xo:.0f}"' + (f' y="{yo}"' if yo else "") + "/>")
            pen_x += adv + track * f.upm
        k = f' class="{cls}"' if cls else ""
        self.body.append(f'<g{k} fill="{self.c(color)}" transform="translate({x:.1f} {y:.1f}) '
                         f'scale({s:.5f} {-s:.5f})">' + "".join(uses) + "</g>")
        return pen_x * s

    def raw(self, s):
        self.body.append(s)

    def line(self, x1, y1, x2, y2, color="rule", w=1, dash=None, cls=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        k = f' class="{cls}"' if cls else ""
        self.raw(f'<path{k} d="M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}" stroke="{self.c(color)}" '
                 f'stroke-width="{w}" fill="none" stroke-linecap="round"{d}/>')

    def rect(self, x, y, w, h, r=0, fill="soft", stroke=None, dash=None, cls=None):
        st = f' stroke="{self.c(stroke)}"' if stroke else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        k = f' class="{cls}"' if cls else ""
        self.raw(f'<rect{k} x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" '
                 f'fill="{self.c(fill)}"{st}{da}/>')

    def dot(self, cx, cy, r, color, hollow=False, cls=None):
        k = f' class="{cls}"' if cls else ""
        if hollow:
            self.raw(f'<circle{k} cx="{cx:.1f}" cy="{cy:.1f}" r="{r - 0.6:.2f}" fill="none" '
                     f'stroke="{self.c(color)}" stroke-width="1.2"/>')
        else:
            self.raw(f'<circle{k} cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.2f}" fill="{self.c(color)}"/>')

    def save(self, name):
        style = (f"<style>{self.css}@media (prefers-reduced-motion:reduce)"
                 f"{{*{{animation:none!important}}}}</style>") if self.css else ""
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {self.h}" width="{W}" '
               f'height="{self.h}" role="img" aria-labelledby="t d"><title id="t">{self.title}</title>'
               f'<desc id="d">{self.desc}</desc>{style}<defs>{"".join(self.defs)}</defs>'
               f'{"".join(self.body)}</svg>')
        with open(os.path.join(OUT, name), "w") as fh:
            fh.write(svg)
        return len(svg)


def label(s, x, y, text, color="dim"):
    s.text("M", text, x, y, 11, color)


# ---------------------------------------------------------------- hero

def hero(theme):
    h = 392
    rows, cols = 32, 50
    css = ("@keyframes f{from{opacity:0}to{opacity:1}}"
           "@keyframes b{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
           "@keyframes p{0%,100%{opacity:1}50%{opacity:.25}}"
           ".lv{animation:p 2.2s ease-in-out infinite}"
           f".bd{{stroke-dasharray:1;stroke-dashoffset:1;animation:b .9s ease-out {0.25 + rows * 0.03:.2f}s forwards}}")
    for r in range(rows):
        css += f".r{r}{{animation:f .35s ease-out {0.2 + r * 0.03:.2f}s both}}"
    s = Svg(h, theme, "Tasnim Hassan, analytics and AI",
            "Four years in corporate finance, now in analytics and AI. MMA candidate at McGill Desautels, "
            "GPA 4.0. Previously Informa, Assembly Global and KPMG in London. The panel shows 1,600 real orders "
            "from the Olist test set sorted by predicted late-delivery risk: reviewing the riskiest 10% catches "
            "23 of the 65 late orders in this sample.", css)

    # left column
    s.raw(f'<circle class="lv" cx="4" cy="22" r="3.5" fill="{s.c("accent")}"/>')
    s.text("M", "open to roles  /  montreal, canada", 16, 26, 11.5, "muted")
    s.text("D", "Tasnim Hassan", -3, 98, 58, track=-0.035)
    s.text("L", "Four years in corporate finance,", 0, 146, 23, track=-0.015)
    s.text("L", "now in analytics and AI.", 0, 175, 23, "muted", track=-0.015)
    s.text("L", "MMA candidate at McGill Desautels, GPA 4.0.", 0, 218, 14.5, "muted")
    s.text("L", "Previously Informa, Assembly Global and KPMG, London.", 0, 240, 14.5, "muted")

    # right column: the order field, real test-set orders sorted by predicted risk
    px, py, pw, ph = 556, 4, W - 556, 268
    s.rect(px, py, pw, ph, 10, "soft")
    label(s, px + 16, py + 24, "olist / test set / sorted by risk")
    cell = (pw - 32) / cols
    gx, gy = px + 16, py + 40
    order = sorted(range(len(SAMPLE["p"])), key=lambda i: -SAMPLE["p"][i])
    thr = SAMPLE["flagThreshold"]
    flagged = sum(1 for p in SAMPLE["p"] if p >= thr)
    rad = cell * 0.22
    for r in range(rows):
        s.raw(f'<g class="r{r}">')
        for c in range(cols):
            k = r * cols + c
            if k >= len(order):
                break
            i = order[k]
            x, y = gx + (c + 0.5) * cell, gy + (r + 0.5) * cell
            late, flag = SAMPLE["late"][i] == 1, SAMPLE["p"][i] >= thr
            if flag and late:
                s.dot(x, y, rad * 1.7, "accent")
            elif flag:
                s.dot(x, y, rad * 1.45, "accent", hollow=True)
            elif late:
                s.dot(x, y, rad * 1.45, "miss")
            else:
                op = 0.28 + SAMPLE["p"][i] * 0.4
                s.raw(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.2f}" fill="{s.c("dim")}" opacity="{op:.2f}"/>')
        s.raw("</g>")
    band_rows = -(-flagged // cols)
    s.raw(f'<rect class="bd" pathLength="1" x="{gx - 3:.1f}" y="{gy - 3:.1f}" width="{cols * cell + 6:.1f}" '
          f'height="{band_rows * cell + 6:.1f}" rx="3" fill="none" stroke="{s.c("accent")}" stroke-width="1"/>')
    late_n = sum(SAMPLE["late"])
    caught = sum(1 for i, p in enumerate(SAMPLE["p"]) if p >= thr and SAMPLE["late"][i])
    yb = gy + rows * cell + 22
    s.text("M", "riskiest 10%", gx, yb, 11, "accent")
    s.text("M", f"{caught} of {late_n} late orders caught", px + pw - 16, yb, 11, "muted", "end")

    # first-glance ledger
    y0 = 300
    s.line(0, y0, W, y0, "ink", 1.2)
    cols3 = (0, 300, 600)
    rows3 = [("NOW", "McGill MMA, GPA 4.0", "Team lead, Novartis capstone"),
             ("BEFORE", "Finance Analyst, Informa", "Assembly Global, KPMG UK"),
             ("FOCUS", "Data science, AI consulting", "Strategy, digital transformation")]
    for x, (k, a, b) in zip(cols3, rows3):
        label(s, x, y0 + 24, k)
        s.text("S", a, x, y0 + 48, 14.5)
        s.text("L", b, x, y0 + 69, 13.5, "muted")
    return s.save(f"hero-{theme}.svg")


# ---------------------------------------------------------------- project strips

def frame(s, idx, ctx, title, desc, facts, url):
    s.line(0, 1, W, 1, "rule", 1)
    label(s, 0, 30, f"{idx}  /  {ctx}")
    s.text("H", title, -1, 68, 30, track=-0.03)
    y = 100
    for ln in desc:
        s.text("L", ln, 0, y, 15)
        y += 22
    y += 14
    for k, v in facts:
        w = s.text("N", k, 0, y, 12, "accent" if k == facts[0][0] else "ink")
        s.text("M", v, max(w, 64) + 10, y, 12, "muted")
        y += 20
    s.text("M", url, 0, s.h - 14, 11, "dim")


def olist(theme):
    s = Svg(292, theme, "Late-delivery risk at order approval",
            "A model that ranks e-commerce orders by their risk of arriving late, using only what is known when "
            "the order is approved. On the held-out test set, reviewing the riskiest 10% of orders catches 36.1% "
            "of late deliveries, against 33.6% for a two-feature baseline and 10.2% for random review.",
            "@keyframes d{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
            ".dm{stroke-dasharray:1;stroke-dashoffset:1;animation:d 1.4s cubic-bezier(.3,.6,.2,1) .2s forwards}"
            "@keyframes f{from{opacity:0}to{opacity:1}}.fd{animation:f .5s ease-out 1.3s both}")
    frame(s, "01", "olist e-commerce, mcgill enterprise data science", "Late-delivery risk",
          ["Ranks orders by their risk of arriving late,",
           "using only what is known at approval, so",
           "operations review the right orders first."],
          [("36.1%", "of late orders caught at a 10% budget"),
           ("3.6x", "random review"),
           ("my part", "tuning, ensembles, final test")],
          "github.com/JustJay7/olist-late-delivery")
    # chart: share of late orders caught by review budget, test set
    L, R, T, B = 470, W - 14, 62, 238
    xs = lambda b: L + (b - 1) / 49 * (R - L)
    ys = lambda v: B - v * (B - T)
    label(s, 430, 30, "late orders caught, by review budget")
    for v in (0, 0.5, 1):
        s.line(L, ys(v), R, ys(v), "rule", 1, dash=None if v == 0 else "1 4")
        s.text("M", f"{int(v * 100)}%", L - 10, ys(v) + 4, 10.5, "dim", "end")
    for b in (1, 10, 25, 50):
        s.text("M", f"{b}%", xs(b), B + 20, 10.5, "dim", "end" if b == 50 else "middle")
    path = lambda ser: "M" + "L".join(f"{xs(i + 1):.1f} {ys(v):.1f}" for i, v in enumerate(ser))
    S = CURVE["series"]
    s.raw(f'<path d="{path(S["random"])}" fill="none" stroke="{s.c("dim")}" stroke-width="1.4" stroke-dasharray="2 4"/>')
    s.raw(f'<path d="{path(S["b1"])}" fill="none" stroke="{s.c("warn")}" stroke-width="1.4" stroke-dasharray="5 4"/>')
    s.raw(f'<path class="dm" pathLength="1" d="{path(S["model"])}" fill="none" stroke="{s.c("accent")}" '
          f'stroke-width="2.4" stroke-linejoin="round"/>')
    x10 = xs(10)
    s.line(x10, T - 6, x10, B, "muted", 1, dash="2 3")
    s.raw('<g class="fd">')
    for key, col in (("model", "accent"), ("b1", "warn"), ("random", "dim")):
        v = S[key][9]
        s.dot(x10, ys(v), 3.6 if key == "model" else 3, col)
    rows = [("final model", S["model"][9], "accent"), ("two-feature", S["b1"][9], "warn"),
            ("random", S["random"][9], "dim")]
    tx = x10 + 16
    for j, (name, v, col) in enumerate(rows):
        yy = 84 + j * 18
        s.text("N", f"{v * 100:.1f}%", tx, yy, 11.5, col)
        s.text("M", name, tx + 52, yy, 11, "muted")
    s.text("M", "at 10%", x10, T - 12, 10.5, "muted", "middle")
    s.raw("</g>")
    return s.save(f"olist-{theme}.svg")


def skillguard(theme):
    rows = [("Static scan, NVIDIA SkillSpector", "7 / 100", "rated safe", "warn"),
            ("Receipt tasks in sandbox", "12 / 12", "correct", "muted"),
            ("Private-file reads attempted", "13", "all denied", "miss"),
            ("Model reviewer", "allow", "overruled", "warn"),
            ("SkillGuard decision", "blocked", "not installed", "accent")]
    css = "@keyframes f{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}"
    for i in range(len(rows)):
        css += f".q{i}{{animation:f .35s ease-out {0.25 + i * 0.22:.2f}s both}}"
    s = Svg(292, theme, "SkillGuard",
            "Runs a skill an AI agent wrote for itself in a sandbox and blocks the install when it misbehaves. "
            "A static scanner scored an unsafe receipt skill 7 of 100 and rated it safe. In the sandbox it "
            "attempted 13 private-file reads, all denied, and SkillGuard blocked it. 821 model calls for $0.48.", css)
    frame(s, "02", "nebius x nvidia global ai hackathon", "SkillGuard",
          ["Runs a skill an AI agent wrote for itself in",
           "a sandbox, records what it actually does, and",
           "blocks the install when it misbehaves."],
          [("13/13", "private-file reads caught at runtime"),
           ("$0.48", "for 821 model calls, hard budget caps"),
           ("my part", "co-builder, cost control, model comparison")],
          "github.com/JustJay7/skillguard")
    L, R = 430, W
    s.rect(L, 14, R - L, 250, 10, "soft")
    label(s, L + 16, 38, "recorded run")
    s.text("M", "unsafe receipt skill", R - 16, 38, 11, "dim", "end")
    s.line(L, 52, R, 52, "rule", 1)
    for i, (k, v, st, col) in enumerate(rows):
        y = 86 + i * 38
        s.raw(f'<g class="q{i}">')
        kw = s.text("L", k, L + 16, y, 13.5, "ink")
        vw = s.width("N", v, 12)
        pw = s.width("M", st, 10.5) + 16
        px = R - 16 - pw
        vx = px - 12 - vw
        s.line(L + 16 + kw + 8, y - 4, vx - 8, y - 4, "rule", 1, dash="1 4")
        s.text("N", v, vx, y, 12, col if col in ("miss", "accent") else "ink")
        tint = {"warn": "warn", "miss": "miss", "accent": "accent"}.get(col)
        if tint:
            s.raw(f'<rect x="{px:.1f}" y="{y - 15:.1f}" width="{pw:.1f}" height="20" rx="4" '
                  f'fill="{s.c(tint)}" opacity=".14"/>')
        else:
            s.rect(px, y - 15, pw, 20, 4, "bg")
        s.text("M", st, px + 8, y, 10.5, tint or "muted")
        s.raw("</g>")
        if i < len(rows) - 1:
            s.line(L + 16, y + 16, R - 16, y + 16, "rule", 1)
    return s.save(f"skillguard-{theme}.svg")


# ---------------------------------------------------------------- toolkit

TOOLKIT = [
    ("Data and ML", ["Python", "pandas", "NumPy", "scikit-learn", "R", "SQL"]),
    ("Data platforms", ["Spark", "Kafka", "Databricks"]),
    ("BI and reporting", ["Power BI", "Tableau", "Advanced Excel"]),
    ("Finance systems", ["SAP", "TM1", "Salesforce", "Sage"]),
    ("Tooling", ["Docker", "Git", "Matplotlib", "Seaborn"]),
]


def toolkit(theme):
    n = max(len(v) for _, v in TOOLKIT)
    s = Svg(54 + n * 22, theme, "Toolkit", ". ".join(f"{k}: {', '.join(v)}" for k, v in TOOLKIT) + ".")
    cw = W / len(TOOLKIT)
    s.line(0, 1, W, 1, "rule", 1)
    for i, (head, items) in enumerate(TOOLKIT):
        x = i * cw
        s.text("S", head, x, 28, 14)
        for j, it in enumerate(items):
            s.text("M", it, x, 56 + j * 22, 12, "muted")
    return s.save(f"toolkit-{theme}.svg")


if __name__ == "__main__":
    for th in THEMES:
        for fn in (hero, olist, skillguard, toolkit):
            print(fn.__name__, th, fn(th), "bytes")
