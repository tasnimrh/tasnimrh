"""Builds the artwork for the profile README.

Run:  pip install fonttools uharfbuzz brotli  &&  python tools/build_assets.py

GitHub shows README SVGs through an <img> tag, which cannot load web fonts, so every
piece of text is converted to vector outlines. Each asset is written in a light and a
dark version with a transparent background, so it sits on the page in either theme.

The review-budget chart is drawn from real results: the locked
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
    "InstrumentSerif.ttf": GF + "instrumentserif/InstrumentSerif-Regular.ttf",
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
        tt = TTFont(os.path.join(CACHE, file))
        if axes:
            tt = instancer.instantiateVariableFont(tt, axes)
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
    "D": Face("D", "InstrumentSerif.ttf"),       # name, matches the site
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
    h = 340
    # A rising dot series with a forecast tail; a brightness wave sweeps across the columns.
    cols, rows_n = 24, 11
    gx0, gx1, gy1 = 612, W - 4, 158
    sp = (gx1 - gx0) / (cols - 1)
    vals = [1.6 + c * 0.36 + 1.1 * __import__("math").sin(c / 2.4) for c in range(cols)]
    css = ("@keyframes p{0%,100%{opacity:1}50%{opacity:.25}}.lv{animation:p 2.2s ease-in-out infinite}"
           "@keyframes f{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}"
           ".a1{animation:f .6s ease-out .1s both}.a2{animation:f .6s ease-out .35s both}"
           ".a3{animation:f .6s ease-out .6s both}.a4{animation:f .6s ease-out .85s both}"
           "@keyframes w{0%,100%{opacity:.35}12%{opacity:1}30%{opacity:.35}}.w{animation:w 3.2s ease-in-out infinite}")
    s = Svg(h, theme, "Tasnim Hassan, data and AI",
            "Tasnim Hassan builds data and AI systems and tests them on real data, with four years on the business "
            "side of the numbers. 359,699 live posts streamed through Kafka and Databricks; 13 of 13 private-file "
            "reads by an AI skill caught at runtime; 3.5 times fewer reviews per late order caught than random; "
            "a 125 million pound plus revenue portfolio reported to a CFO. McGill MMA, Montreal.", css)
    s.raw(f'<circle class="lv" cx="4" cy="22" r="3.5" fill="{s.c("accent")}"/>')
    s.text("M", "building in montreal  /  mcgill mma, gpa 4.0", 16, 26, 11.5, "muted")
    s.raw('<g class="a1">')
    s.text("D", "Tasnim Hassan", -2, 120, 100, track=-0.02)
    s.raw('</g><g class="a2">')
    s.text("H", "Data and AI systems, tested on real data.", 0, 166, 24, track=-0.025)
    s.raw('</g><g class="a3">')
    s.text("L", "Built by someone who spent four years on the business side of the numbers.", 0, 194, 16, "muted",
           track=-0.01)
    s.raw("</g>")
    # signal: columns of dots, the last six a forecast
    for c in range(cols):
        x = gx0 + c * sp
        n = max(1, min(rows_n, round(vals[c])))
        fc = c >= cols - 6
        s.raw(f'<g class="w" style="animation-delay:{c * 0.09:.2f}s">')
        for r in range(n):
            y = gy1 - r * sp
            top = r == n - 1
            if fc:
                s.dot(x, y, 2.3 if top else 1.7, "accent", hollow=False)
            else:
                s.dot(x, y, 2.1 if top else 1.6, "ink" if top else "dim")
        s.raw("</g>")
    s.line(gx0 + (cols - 6.5) * sp, gy1 + 10, gx0 + (cols - 6.5) * sp, gy1 - rows_n * sp, "dim", 1, dash="2 3")
    s.text("M", "now", gx0 + (cols - 6.5) * sp, gy1 + 24, 10, "dim", "middle")

    # proof band
    y0 = 232
    s.line(0, y0, W, y0, "ink", 1.2)
    band = [("359,699", "live posts streamed through", "Kafka and Databricks"),
            ("13/13", "file reads an AI skill hid,", "caught at runtime"),
            ("3.5x", "fewer reviews per late order", "caught than at random"),
            ("£125M+", "revenue portfolio I reported", "on to a CFO")]
    cw = W / 4
    s.raw('<g class="a4">')
    for i, (v, l1, l2) in enumerate(band):
        x = i * cw + (0 if i == 0 else 18)
        if i:
            s.line(i * cw, y0 + 16, i * cw, h - 10, "rule", 1)
        s.text("N", v, x, y0 + 46, 27, "accent" if i == 0 else "ink", track=-0.03)
        s.text("L", l1, x, y0 + 74, 13, "muted")
        s.text("L", l2, x, y0 + 93, 13, "muted")
    s.raw("</g>")
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


def brandpulse(theme):
    css = ("@keyframes g{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
           ".bar{transform-box:fill-box;transform-origin:left center}"
           "@keyframes f{from{opacity:0}to{opacity:1}}")
    stages = [("matched a brand", 2668, "dim", "first run"),
              ("a link is not a mention", 1824, "ink", "-844"),
              ("bots and ads removed", 1521, "accent", "-303")]
    for i in range(len(stages)):
        css += f".b{i}{{animation:g .8s cubic-bezier(.2,.7,.2,1) {0.3 + i * 0.35:.2f}s both}}"
        css += f".t{i}{{animation:f .4s ease-out {0.5 + i * 0.35:.2f}s both}}"
    s = Svg(292, theme, "Brand Pulse",
            "Streams every public Bluesky post through Kafka into Databricks and flags brands having a bad day. "
            "In one evening, 359,699 posts produced 2,668 brand matches. Ignoring links cut that to 1,824 and "
            "removed a false alert; filtering bots and ads left 1,521 real mentions.", css)
    frame(s, "01", "personal project, live data", "Brand Pulse",
          ["Streams every public Bluesky post through Kafka",
           "into Databricks and flags brands having a bad day.",
           "Then live data broke it three ways. Each fix is measured."],
          [("359,699", "posts streamed live in one evening"),
           ("17%", "of brand mentions were bots or ads"),
           ("my part", "solo: producer, pipeline, detection, tests")],
          "github.com/tasnimrh/brand-pulse")
    L, R = 430, W
    s.rect(L, 14, R - L, 250, 10, "soft")
    label(s, L + 16, 38, "first live run")
    s.text("M", "bluesky to kafka to delta", R - 16, 38, 11, "dim", "end")
    s.line(L, 52, R, 52, "rule", 1)
    s.text("L", "posts streamed", L + 16, 80, 13.5)
    s.text("N", "359,699", R - 16, 80, 12, "ink", "end")
    bw = R - L - 32
    for i, (k, v, col, note) in enumerate(stages):
        y = 112 + i * 44
        s.raw(f'<g class="t{i}">')
        s.text("L", k, L + 16, y, 13.5, "ink" if i else "muted")
        s.text("N", f"{v:,}", R - 16, y, 12, "accent" if col == "accent" else "ink", "end")
        nw = s.width("N", f"{v:,}", 12)
        s.text("M", note, R - 16 - nw - 10, y, 10.5, "miss" if note.startswith("-") else "dim", "end")
        s.raw("</g>")
        s.raw(f'<rect class="bar b{i}" x="{L + 16}" y="{y + 9}" width="{bw * v / 2668:.1f}" height="6" rx="3" '
              f'fill="{s.c(col)}" opacity="{0.9 if col == "accent" else 0.55}"/>')
    s.line(L + 16, 238, R - 16, 238, "rule", 1)
    s.text("M", "false alerts after the link rule", L + 16, 256, 11, "muted")
    s.text("N", "1 to 0", R - 16, 256, 11.5, "accent", "end")
    return s.save(f"brandpulse-{theme}.svg")


def olist(theme):
    s = Svg(292, theme, "Late-delivery risk at order approval",
            "A model that ranks e-commerce orders by their risk of arriving late, using only what is known when "
            "the order is approved. On the held-out test set, reviewing the riskiest 10% of orders catches 36.1% "
            "of late deliveries. The panel shows 1,600 real test-set orders sorted by predicted risk.",
            "@keyframes f{from{opacity:0}to{opacity:1}}"
            + "".join(f".r{r}{{animation:f .35s ease-out {0.2 + r * 0.03:.2f}s both}}" for r in range(40)))
    frame(s, "03", "olist e-commerce, mcgill enterprise data science", "Late-delivery risk",
          ["Late orders earn 2.2 stars, on-time 4.3. Ranks",
           "orders by late risk at approval, so operations",
           "review the right ones before the customer is let down."],
          [("36.1%", "of late orders caught at a 10% budget"),
           ("6.8", "reviews per late order caught, 24 at random"),
           ("my part", "tuning, ensembles, final test")],
          "github.com/JustJay7/olist-late-delivery")
    # The order field: 1,600 real test-set orders sorted by predicted risk, riskiest first.
    L, R, T = 430, W, 14
    s.rect(L, T, R - L, 262, 10, "soft")
    label(s, L + 16, T + 24, "olist / test set / sorted by predicted risk")
    cols = 64
    cell = (R - L - 32) / cols
    gx, gy = L + 16, T + 40
    order = sorted(range(len(SAMPLE["p"])), key=lambda i: -SAMPLE["p"][i])
    thr = SAMPLE["flagThreshold"]
    rows = -(-len(order) // cols)
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
                s.raw(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.2f}" fill="{s.c("dim")}" opacity="{0.28 + SAMPLE["p"][i] * 0.4:.2f}"/>')
        s.raw("</g>")
    flagged = sum(1 for p in SAMPLE["p"] if p >= thr)
    band_rows = -(-flagged // cols)
    s.raw(f'<rect x="{gx - 3:.1f}" y="{gy - 3:.1f}" width="{cols * cell + 6:.1f}" height="{band_rows * cell + 6:.1f}" '
          f'rx="3" fill="none" stroke="{s.c("accent")}" stroke-width="1" stroke-dasharray="3 3"/>')
    late_n = sum(SAMPLE["late"])
    caught = sum(1 for i, p in enumerate(SAMPLE["p"]) if p >= thr and SAMPLE["late"][i])
    yb = gy + rows * cell + 22
    s.text("M", "boxed: riskiest 10%", gx, yb, 11, "accent")
    s.text("M", f"{caught} of {late_n} late orders caught", R - 16, yb, 11, "muted", "end")
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


def kafka(theme):
    rows = [("Spark batch write", "3 / 3", "landed", "muted"),
            ("Python producer, idempotent", "9 / 9", "landed", "muted"),
            ("Spark Structured Streaming", "20 / 20", "landed", "muted"),
            ("Duplicates by event id", "0", "pass", "accent"),
            ("End-to-end check", "32 / 32", "pass", "accent")]
    css = "@keyframes f{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}"
    for i in range(len(rows)):
        css += f".q{i}{{animation:f .35s ease-out {0.25 + i * 0.22:.2f}s both}}"
    s = Svg(292, theme, "Streaming pipeline: Kafka to Spark",
            "Rebuilt a 2022 Kafka and Spark course pipeline on Confluent Cloud and Databricks with a registered "
            "Avro schema. Three producers sent 32 events; all 32 landed in Delta with zero duplicates.", css)
    frame(s, "03", "mcgill enterprise ml in production, solo", "Kafka to Spark, verified",
          ["A 2022 pipeline no longer ran on 2026 platforms.",
           "Rebuilt it with an Avro contract and proved",
           "every event arrived exactly once."],
          [("32/32", "events landed from three producers"),
           ("0", "duplicates, checked by event id"),
           ("my part", "solo: code, cloud setup, verification")],
          "github.com/tasnimrh/kafka-spark-streaming")
    L, R = 430, W
    s.rect(L, 14, R - L, 250, 10, "soft")
    label(s, L + 16, 38, "verification run")
    s.text("M", "confluent cloud to delta", R - 16, 38, 11, "dim", "end")
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
        s.text("N", v, vx, y, 12, "accent" if col == "accent" else "ink")
        if col == "accent":
            s.raw(f'<rect x="{px:.1f}" y="{y - 15:.1f}" width="{pw:.1f}" height="20" rx="4" '
                  f'fill="{s.c("accent")}" opacity=".14"/>')
        else:
            s.rect(px, y - 15, pw, 20, 4, "bg")
        s.text("M", st, px + 8, y, 10.5, "accent" if col == "accent" else "muted")
        s.raw("</g>")
        if i < len(rows) - 1:
            s.line(L + 16, y + 16, R - 16, y + 16, "rule", 1)
    return s.save(f"kafka-{theme}.svg")


# ---------------------------------------------------------------- toolkit

TOOLKIT = [
    ("AI and ML", ["Python", "scikit-learn", "pandas", "NumPy", "LLM APIs", "R"]),
    ("Data engineering", ["Spark", "Kafka", "Databricks", "Delta Lake", "Avro", "SQL"]),
    ("Cloud and tooling", ["AWS", "Confluent Cloud", "Docker", "Git"]),
    ("Analytics and BI", ["Power BI", "Tableau", "Matplotlib", "Excel"]),
    ("Business systems", ["SAP", "TM1", "Salesforce"]),
]
CREDENTIALS = "Databricks Fundamentals  /  AWS Cloud Practitioner Essentials"


def toolkit(theme):
    n = max(len(v) for _, v in TOOLKIT)
    h = 54 + n * 22 + 44
    s = Svg(h, theme, "Toolkit",
            ". ".join(f"{k}: {', '.join(v)}" for k, v in TOOLKIT) + ". Credentials: " + CREDENTIALS + ".")
    cw = W / len(TOOLKIT)
    s.line(0, 1, W, 1, "rule", 1)
    for i, (head, items) in enumerate(TOOLKIT):
        x = i * cw
        s.text("S", head, x, 28, 14)
        for j, it in enumerate(items):
            s.text("M", it, x, 56 + j * 22, 12, "muted")
    y = 54 + n * 22 + 6
    s.line(0, y, W, y, "rule", 1)
    w = s.text("M", "credentials", 0, y + 26, 11, "dim")
    s.text("M", CREDENTIALS, w + 16, y + 26, 12, "ink")
    return s.save(f"toolkit-{theme}.svg")


if __name__ == "__main__":
    for th in THEMES:
        for fn in (hero, brandpulse, skillguard, olist, toolkit):
            print(fn.__name__, th, fn(th), "bytes")
