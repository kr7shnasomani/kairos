"""Generate every raster the deck needs.

Three jobs, all writing into assets/:
  1. the landing page's .lp-media gradient panels
  2. the architecture diagram, re-rendered from ../docs/DIAGRAMS.md
  3. the logo, resized down from the one the app ships

Run it directly to make all of them. assets/ is committed, so a clone can
rebuild the deck without installing mermaid-cli and its Chromium.
"""
import io, os, re, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)                       # the deck lives inside the repo
DIAGRAMS = os.path.join(REPO, "docs/DIAGRAMS.md")
LOGO_SRC = os.path.join(REPO, "frontend/public/logo.png")
OUT = os.path.join(HERE, "assets")
BUILD = os.path.join(HERE, "build")


def _p(name):
    return os.path.join(OUT, name)


def save(im, path, quality=90):
    """Gradients ship as JPEG.

    They are continuous tone with fine film grain, the worst case for PNG:
    lossless coding cannot exploit a smooth ramp and the grain defeats it
    outright, so the PNG compresses to its own size inside the pptx zip. JPEG
    at 90 is visually identical here and roughly fifteen times smaller, and the
    grain dithers the ramp so there is no banding.
    """
    if path.lower().endswith((".jpg", ".jpeg")):
        im.convert("RGB").save(path, "JPEG", quality=quality, optimize=True,
                               progressive=True, subsampling=0)
    else:
        im.save(path, "PNG", optimize=True)
    print("  %-28s %-11s %6.2f MB" % (os.path.basename(path), "%dx%d" % im.size,
                                      os.path.getsize(path) / 1e6))


# ---------------------------------------------------------------- gradients
def hx(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def radial(shape, cx, cy, rx, ry, stop):
    h, w = shape
    y, x = np.mgrid[0:h, 0:w]
    dx, dy = (x / w - cx) / rx, (y / h - cy) / ry
    return np.clip(1.0 - np.sqrt(dx * dx + dy * dy) / stop, 0.0, 1.0)


def fractal_noise(shape, octaves=4, seed=7):
    """feTurbulence baseFrequency 0.8 over a 160px tile is ~1px grain, so the
    energy sits in the top octave rather than in blobs."""
    h, w = shape
    rng = np.random.default_rng(seed)
    out, amp, tot = np.zeros(shape, float), 1.0, 0.0
    for o in range(octaves):
        step = 2 ** o
        small = rng.random((max(2, h // step), max(2, w // step)))
        up = np.asarray(Image.fromarray((small * 255).astype(np.uint8))
                        .resize((w, h), Image.NEAREST if step == 1 else Image.BILINEAR),
                        float) / 255.0
        out += up * amp
        tot += amp
        amp *= 0.45
    return out / tot


def panel(w, h, path, scrim=0.0):
    """One .lp-media panel. Layer order and stops come from globals.css."""
    yy, xx = np.mgrid[0:h, 0:w][0] / h, np.mgrid[0:h, 0:w][1] / w

    ang = np.deg2rad(152.0)                        # linear-gradient(152deg, ...)
    t = xx * np.sin(ang) - yy * np.cos(ang)
    t = (t - t.min()) / (t.max() - t.min())
    img = np.zeros((h, w, 3), float)
    a, b, c = hx("170601"), hx("6b1902"), hx("d9490a")
    m = t <= 0.46
    img[m] = a + (b - a) * (t[m] / 0.46)[:, None]
    img[~m] = b + (c - b) * ((t[~m] - 0.46) / 0.54)[:, None]

    for col, cx, cy, rx, ry, stop in [       # bottom-most first; CSS lists the top first
        ("9c1c00", 0.48, 1.12, 1.35, 1.15, 0.64),
        ("f0570c", 0.86, 0.30, 0.95, 0.75, 0.58),
        ("ffa257", 0.79, 0.15, 0.58, 0.50, 0.62),
        ("150c06", 0.10, 0.04, 1.05, 0.80, 0.52),
    ]:
        al = radial((h, w), cx, cy, rx, ry, stop)[:, :, None]
        img = img * (1 - al) + hx(col)[None, None, :] * al

    g = fractal_noise((h, w))
    img = np.clip(img + ((g - g.mean()) * 255.0)[:, :, None] * 0.085, 0, 255)

    edge = np.minimum.reduce([xx, 1 - xx, yy, 1 - yy])   # inset 0 0 100px 26px
    v = np.clip(edge / 0.085, 0, 1) ** 0.85
    img = (img * v[:, :, None]
           + hx("0a0300")[None, None, :] * (1 - v)[:, :, None] * 0.42
           + img * (1 - v)[:, :, None] * 0.58)

    if scrim:                                  # so reversed-out copy keeps contrast
        img = img * (1 - scrim * (1 - np.clip(xx / 0.68, 0, 1) ** 0.9))[:, :, None]

    save(Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)), path)


def band(w, h, path, src_h=1600, top=0.47):
    """A wide band cut out of a correctly proportioned panel.

    Rendering straight onto a 6:1 canvas squashes the radial lights into
    horizontal smears and turns the inset vignette into dark bands, because both
    are placed in normalised coordinates. Crop instead, so the key light keeps
    its shape.
    """
    tmp = os.path.join(tempfile.gettempdir(), "_panel_src.jpg")
    panel(w, src_h, tmp)
    im = Image.open(tmp)
    y0 = int(src_h * top)
    save(im.crop((0, y0, w, y0 + h)), path)
    os.remove(tmp)


def gradients():
    print("gradients")
    panel(2000, 1125, _p("lp_media_cover.jpg"), scrim=0.58)   # 00 cover, 13.33 x 7.5in
    panel(2000, 534,  _p("lp_media_band.jpg"))                # 01 band,  13.33 x 3.56
    panel(900,  803,  _p("lp_media_mock.jpg"))                # 04 panel, 5.29 x 4.72
    band(2000, 351,   _p("lp_media_strip.jpg"))               # 10 band,  13.33 x 2.34


# ------------------------------------------------------------------- logo
def logo(size=240):
    """The app ships a 1254px square and the deck lands it at 0.7in. pptxgenjs
    embeds an image once per slide, so full size cost 1.8 MB for a small mark."""
    print("logo")
    im = Image.open(LOGO_SRC).convert("RGB").resize((size, size), Image.LANCZOS)
    save(im, _p("logo_mark.png"))


# ---------------------------------------------------------------- diagram
def diagram(name="overview"):
    """Re-render the architecture diagram in the deck's typeface.

    The committed SVGs in frontend/public/diagrams use "arial, sans-serif" per
    the repo's mermaid.config.json, which reads as foreign next to DM Sans.
    Restyling those SVGs does not work: mermaid lays flowchart labels out as
    foreignObject divs with white-space:nowrap and a fixed width measured
    against the font used at render time, so a wider face clips. The source has
    to go through mermaid again.

    It is also re-rendered left to right. The committed source is `flowchart TB`,
    which the current mermaid lays out at aspect 0.57; on a 16:9 slide that is a
    narrow column. LR gives 3.2:1 and runs full width. ../docs/DIAGRAMS.md is
    never modified.
    """
    print("diagram")
    os.makedirs(BUILD, exist_ok=True)
    md = io.open(DIAGRAMS, encoding="utf-8").read()
    m = re.search(r"##\s+`%s`[^\n]*\n(.*?)```mermaid\n(.*?)```" % name, md, re.S)
    if not m:
        raise SystemExit("no `%s` mermaid block in %s" % (name, DIAGRAMS))

    src = os.path.join(BUILD, "%s_lr.mmd" % name)
    io.open(src, "w", encoding="utf-8").write(m.group(2).replace("flowchart TB",
                                                                 "flowchart LR", 1))
    pconf = os.path.join(BUILD, "puppeteer.config.json")
    io.open(pconf, "w", encoding="utf-8").write(
        '{"args":["--no-sandbox","--disable-setuid-sandbox"]}')

    svg = os.path.join(BUILD, "%s_lr.svg" % name)
    subprocess.run([os.path.join(HERE, "node_modules/.bin/mmdc"), "-i", src, "-o", svg,
                    "-c", os.path.join(HERE, "mermaid.deck.json"), "-p", pconf,
                    "-b", "white"], check=True, capture_output=True)
    subprocess.run(["qlmanage", "-t", "-s", "2600", "-o", BUILD, svg], capture_output=True)

    im = Image.open(os.path.join(BUILD, "%s_lr.svg.png" % name)).convert("RGB")
    box = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()
    pad = 16
    box = (max(0, box[0] - pad), max(0, box[1] - pad),
           min(im.width, box[2] + pad), min(im.height, box[3] + pad))
    out = im.crop(box)
    save(out, _p("dia_%s_lr.png" % name))
    print("  aspect %.4f  (build_deck.js hardcodes this ratio)" % (out.width / out.height))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    want = sys.argv[1:] or ["gradients", "logo", "diagram"]
    if "gradients" in want: gradients()
    if "logo" in want: logo()
    if "diagram" in want: diagram()
