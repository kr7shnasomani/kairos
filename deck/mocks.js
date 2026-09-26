/* Product mockups lifted from the landing page (page.tsx CopilotMock).
   Drawn as shapes rather than images so they stay crisp and editable. */
module.exports = function (p, C, F, T) {

  // .lp-media panel with the inner hairline frame the hero uses
  function mediaFrame(s, img, x, y, w, h, pad) {
    pad = pad === undefined ? 0.26 : pad;
    s.addImage({ path: img, x: x, y: y, w: w, h: h });
    s.addShape(p.ShapeType.rect, { x: x + pad, y: y + pad, w: w - pad * 2, h: h - pad * 2,
      fill: { type: "none" }, line: { color: "FFFFFF", width: 0.75, transparency: 65 } });
  }

  // translucent slab, as the page puts over its media panels (bg-black/45)
  function slab(s, x, y, w, h, alpha) {
    s.addShape(p.ShapeType.rect, { x: x, y: y, w: w, h: h,
      fill: { color: "000000", transparency: alpha === undefined ? 45 : alpha } });
  }

  function bar(s, x, y, w, h, pct, fg, bg) {
    s.addShape(p.ShapeType.rect, { x: x, y: y, w: w, h: h, fill: { color: bg } });
    s.addShape(p.ShapeType.rect, { x: x, y: y, w: w * pct, h: h, fill: { color: fg } });
  }

  function chip(s, x, y, label, filled) {
    const w = 0.17 + label.length * 0.062;
    s.addShape(p.ShapeType.rect, { x: x, y: y, w: w, h: 0.28,
      fill: filled ? { color: C.accent } : { color: "FFFFFF" },
      line: filled ? null : { color: C.line, width: 1 } });
    s.addText(label, T({ x: x, y: y, w: w, h: 0.28, align: "center", valign: "middle",
      fontFace: F.b, fontSize: 9, color: filled ? "FFFFFF" : C.muted }));
    return w;
  }

  /* The copilot exchange: a question, a governed answer with its evidence, and
     the refusal path beside it. Mirrors CopilotMock in page.tsx. */
  function copilotMock(s, x, y, w) {
    const qw = w * 0.86;
    slab(s, x + w - qw, y, qw, 0.42, 45);
    s.addText("What changed on P-101 since the last turnaround?",
      T({ x: x + w - qw + 0.16, y: y, w: qw - 0.32, h: 0.42, valign: "middle",
          fontFace: F.b, fontSize: 10.5, color: "FFFFFF" }));

    const cy = y + 0.58, cw = w * 0.94, ch = 2.16;
    s.addShape(p.ShapeType.rect, { x: x, y: cy, w: cw, h: ch, fill: { color: "FFFFFF" } });
    s.addShape(p.ShapeType.rect, { x: x, y: cy, w: 0.032, h: ch, fill: { color: C.accent } });

    const px = x + 0.24;
    s.addText("CHECKED ANSWER", T({ x: px, y: cy + 0.18, w: cw - 0.48, h: 0.2,
      fontFace: F.b, fontSize: 8, bold: true, charSpacing: 0.7, color: C.accentText }));
    s.addText("The pressure limit dropped to 16.2 bar on 14 May.",
      T({ x: px, y: cy + 0.44, w: cw - 0.48, h: 0.24,
          fontFace: F.b, fontSize: 10.5, color: C.ink }));
    [1.0, 0.83, 0.66].forEach((f, i) =>
      s.addShape(p.ShapeType.rect, { x: px, y: cy + 0.76 + i * 0.15, w: (cw - 0.48) * f,
        h: 0.075, fill: { color: C.band } }));

    let chx = px;
    chx += chip(s, chx, cy + 1.26, "3 sources", true) + 0.1;
    chip(s, chx, cy + 1.26, "Authority: regulation", false);

    s.addText("Confidence", T({ x: px, y: cy + 1.66, w: 1.4, h: 0.2,
      fontFace: F.b, fontSize: 9, color: C.muted }));
    s.addText("0.91", T({ x: px + cw - 1.12, y: cy + 1.66, w: 0.64, h: 0.2, align: "right",
      fontFace: F.b, fontSize: 9, bold: true, color: C.ink }));
    bar(s, px, cy + 1.9, cw - 0.48, 0.08, 0.91, C.accent, C.band);

    const ry = cy + ch + 0.2;
    s.addShape(p.ShapeType.rect, { x: x, y: ry, w: w, h: 0.56, fill: { type: "none" },
      line: { color: "FFFFFF", width: 1, dashType: "dash", transparency: 45 } });
    s.addShape(p.ShapeType.rect, { x: x + 0.18, y: ry + 0.22, w: 0.1, h: 0.1,
      fill: { color: "FFFFFF" } });
    s.addText([
      { text: "Thin evidence on a safety question returns a ", options: { color: "FFFFFF" } },
      { text: "refusal card", options: { color: "FFFFFF", bold: true } },
      { text: ", with its sources, never a hedge.", options: { color: "FFFFFF" } }
    ], T({ x: x + 0.38, y: ry, w: w - 0.56, h: 0.56, valign: "middle",
           fontFace: F.b, fontSize: 10, lineSpacing: 13 }));
  }

  return { mediaFrame, slab, bar, chip, copilotMock };
};
