"""Patch and check the built pptx.

Two things pptxgenjs cannot do, then one verification pass. Run after
build_deck.js and before export.py. Exits non-zero if the audit finds anything,
so build.sh stops rather than exporting a broken deck.
"""
import math, os, re, sys, zipfile
import defusedxml.ElementTree as ET

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
EMU, SW, SH, MARGIN, GLYPH = 914400.0, 13.333, 7.5, 0.5, 0.49
MAJOR, MINOR = "Instrument Sans", "DM Sans"
LATIN = re.compile(r'<a:latin typeface="([^"]+)"([^/]*)/>')


def harden(path):
    """Close every font-fallback path.

    1. Theme scheme. pptxgenjs leaves it on Office defaults, so any text box
       added later in PowerPoint inherits Calibri instead of the brand faces.
    2. A run resolves its face from <a:latin> only for text PowerPoint treats as
       Latin; anything it reads as East-Asian or complex-script uses <a:ea> or
       <a:cs>, which pptxgenjs never writes. Those inherit the theme, and that
       is where a stray Calibri gets back in.
    """
    zf = zipfile.ZipFile(path)
    data = {n: zf.read(n) for n in zf.namelist()}
    zf.close()

    runs = 0
    for name in list(data):
        if not name.endswith(".xml"):
            continue
        if not name.startswith(("ppt/slides/", "ppt/slideMasters/", "ppt/slideLayouts/")):
            continue
        x = data[name].decode("utf8")
        runs += len(LATIN.findall(x))
        data[name] = LATIN.sub(
            lambda m: m.group(0) if "<a:ea" in x[m.end():m.end() + 12] else
            '<a:latin typeface="%s"%s/><a:ea typeface="%s"%s/><a:cs typeface="%s"%s/>'
            % ((m.group(1), m.group(2)) * 3), x).encode("utf8")

    th = data["ppt/theme/theme1.xml"].decode("utf8")
    for tag, face in (("majorFont", MAJOR), ("minorFont", MINOR)):
        th = re.sub(r'(<a:%s>)<a:latin typeface="[^"]*"[^/]*/>'
                    r'(?:<a:ea typeface="[^"]*"/>)?(?:<a:cs typeface="[^"]*"/>)?' % tag,
                    r'\1<a:latin typeface="%s"/><a:ea typeface="%s"/><a:cs typeface="%s"/>'
                    % (face, face, face), th, count=1)
    data["ppt/theme/theme1.xml"] = th.encode("utf8")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in data.items():
            z.writestr(n, b)
    print("theme -> %s / %s; latin mirrored to ea/cs on %d runs" % (MAJOR, MINOR, runs))


def audit(path):
    """Geometry and text fit, read back off the package rather than the source.

    Catches the three defects a renderer would show: anything outside the slide
    or inside the margin, a text box that cannot hold its text, and text
    overlapping other text. Cards carry no text, so card-over-card overlap is by
    design and is not reported.
    """
    z = zipfile.ZipFile(path)
    slides = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                    key=lambda n: int(re.search(r"(\d+)", n.split("/")[-1]).group(1)))
    issues = []
    for si, name in enumerate(slides):
        shapes = []
        for sp in ET.fromstring(z.read(name)).iter(P + "sp"):
            xfrm = sp.find(".//" + A + "xfrm")
            if xfrm is None:
                continue
            off, ext = xfrm.find(A + "off"), xfrm.find(A + "ext")
            if off is None or ext is None:
                continue
            szs = [int(r.get("sz")) / 100 for r in sp.iter(A + "rPr") if r.get("sz")]
            lns = [int(l.get("val")) / 100 for l in sp.iter(A + "spcPts")]
            shapes.append(dict(x=int(off.get("x")) / EMU, y=int(off.get("y")) / EMU,
                               w=int(ext.get("cx")) / EMU, h=int(ext.get("cy")) / EMU,
                               t="".join(t.text or "" for t in sp.iter(A + "t")),
                               sz=max(szs) if szs else 12, ln=max(lns) if lns else 0))
        for s in shapes:
            tag = "s%02d" % si
            if (s["x"] < -.01 or s["y"] < -.01
                    or s["x"] + s["w"] > SW + .01 or s["y"] + s["h"] > SH + .01):
                issues.append((tag, "OUT OF BOUNDS", round(s["x"], 2), round(s["y"], 2),
                               s["t"][:45]))
            if s["t"] and (s["x"] < MARGIN - .01 or s["x"] + s["w"] > SW - MARGIN + .01):
                issues.append((tag, "MARGIN", round(s["x"], 2), round(s["x"] + s["w"], 2),
                               s["t"][:45]))
            if s["t"]:
                cpl = max(1, int(s["w"] * 72 / (s["sz"] * GLYPH)))
                lines = sum(max(1, math.ceil(len(seg) / cpl)) for seg in s["t"].split("\n"))
                need = lines * ((s["ln"] or s["sz"] * 1.22) / 72.0)
                if need > s["h"] + 0.04:
                    issues.append((tag, "TEXT OVERFLOW", round(need, 2), "vs",
                                   round(s["h"], 2), "%dpt" % s["sz"], s["t"][:55]))
        txts = [s for s in shapes if s["t"].strip()]
        for i in range(len(txts)):
            for j in range(i + 1, len(txts)):
                a, b = txts[i], txts[j]
                ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
                oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
                if ox > 0.05 and oy > 0.05:
                    issues.append(("s%02d" % si, "TEXT OVERLAP", round(ox, 2), round(oy, 2),
                                   a["t"][:26], "||", b["t"][:26]))
    print("audit: %d slides, %d issues" % (len(slides), len(issues)))
    for i in issues:
        print("  " + " ".join(str(x) for x in i))
    return len(issues)


if __name__ == "__main__":
    pptx = sys.argv[1] if len(sys.argv) > 1 else "build/Kairos_Deck.pptx"
    harden(pptx)
    sys.exit(1 if audit(pptx) else 0)
