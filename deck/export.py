"""Produce the PDF. This is the only output that leaves the folder.

Preferred path is LibreOffice, which gives a real vector PDF: selectable text,
embedded fonts, crisp at any zoom, and a fraction of the size. The fallback
rasterises each slide through Quick Look and stitches the pictures together,
which has no text layer at all, so it is only used when LibreOffice is absent.

The pptx is an intermediate, not a deliverable. It stays in build/.
"""
import glob, json, os, re, shutil, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")

# Gradients hide JPEG artefacts well and the 150 dpi cap leaves diagram text
# crisp at 200 dpi, so 80 is safe here. Raise it if a slide ever carries fine
# line art at small size.
FILTER = "pdf:impress_pdf_Export:" + json.dumps({
    "UseLosslessCompression": {"type": "boolean", "value": "false"},
    "Quality":                {"type": "long",    "value": "80"},
    "ReduceImageResolution":  {"type": "boolean", "value": "true"},
    "MaxImageResolution":     {"type": "long",    "value": "150"},
}, separators=(",", ":"))

SOFFICE = ["/Applications/LibreOffice.app/Contents/MacOS/soffice",
           "/usr/bin/soffice", "/usr/local/bin/soffice"]


def soffice():
    for c in SOFFICE + [shutil.which("soffice") or "", shutil.which("libreoffice") or ""]:
        if c and os.path.exists(c):
            return c
    return None


def inspect(path):
    """Content streams are Flate-compressed, so grepping the raw bytes for a Tj
    finds nothing even in a proper vector PDF. Ask poppler instead."""
    d = open(path, "rb").read()
    pages = d.count(b"/Type /Page") - d.count(b"/Type /Pages")
    if pages <= 0:
        pages = len(re.findall(rb"/Type\s*/Page[^s]", d))
    try:
        words = len(subprocess.run(["pdftotext", path, "-"], capture_output=True,
                                   text=True).stdout.split())
    except FileNotFoundError:
        words = -1
    return dict(mb=len(d) / 1e6, pages=pages, words=words,
                fonts=len(re.findall(rb"/FontFile", d)),
                images=d.count(b"DCTDecode") + d.count(b"JPXDecode"))


def raster(src, out):
    """Fallback. Quick Look renders only a file's first slide, so the deck is
    split into one package per slide and the pictures are stitched together."""
    from PIL import Image
    print("LibreOffice not found. Falling back to a raster PDF with no text layer.")
    split, png = os.path.join(BUILD, "split"), os.path.join(BUILD, "png")
    for d in (split, png):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    zf = zipfile.ZipFile(src)
    data = {n: zf.read(n) for n in zf.namelist()}
    pres = data["ppt/presentation.xml"].decode("utf8")
    lst = re.search(r"<p:sldIdLst>.*?</p:sldIdLst>", pres, re.S).group(0)
    for i, sid in enumerate(re.findall(r"<p:sldId [^>]*/>", pres)):
        one = pres.replace(lst, "<p:sldIdLst>%s</p:sldIdLst>" % sid)
        with zipfile.ZipFile("%s/s%02d.pptx" % (split, i), "w", zipfile.ZIP_DEFLATED) as z:
            for n, b in data.items():
                z.writestr(n, one.encode("utf8") if n == "ppt/presentation.xml" else b)
    for f in sorted(glob.glob(split + "/*.pptx")):
        subprocess.run(["qlmanage", "-t", "-s", "2600", "-o", png, f], capture_output=True)
    imgs = [Image.open(f).convert("RGB") for f in sorted(glob.glob(png + "/*.png"))]
    imgs[0].save(out, "PDF", resolution=72.0, save_all=True, append_images=imgs[1:],
                 quality=85, optimize=True)


def main(src=None, out=None):
    src = src or os.path.join(BUILD, "Kairos_Deck.pptx")
    out = out or os.path.join(HERE, "Kairos_Deck.pdf")
    exe = soffice()

    if exe:
        work = os.path.join(BUILD, "pdf")
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        subprocess.run([exe, "--headless", "--norestore", "--convert-to", FILTER,
                        "--outdir", work, src], check=True, capture_output=True,
                       env=dict(os.environ, HOME=os.path.expanduser("~")))
        made = glob.glob(os.path.join(work, "*.pdf"))
        if not made:
            raise SystemExit("LibreOffice produced no PDF")
        shutil.copy(made[0], out)
    else:
        raster(src, out)

    i = inspect(out)
    print("%s  %.2f MB  %d pages  %d embedded fonts  %d words of live text  %d images"
          % (os.path.basename(out), i["mb"], i["pages"], i["fonts"], i["words"], i["images"]))
    if i["fonts"] == 0 or i["words"] == 0:
        print("WARNING: no text layer. This is a raster PDF, not a vector one.")
    bad = [f for f in ("LinuxLibertine", "FrankRuhl", "DejaVu", "Liberation")
           if f.encode() in open(out, "rb").read()]
    if bad:
        print("WARNING: substituted fonts in the PDF (%s). LibreOffice cannot see the "
              "brand faces. Copy fonts/*.ttf into\n"
              "         /Applications/LibreOffice.app/Contents/Resources/fonts/truetype/"
              % ", ".join(bad))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]) or 0)
