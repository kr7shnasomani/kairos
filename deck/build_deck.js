/* Kairos pitch deck.
   Type and colour come from the landing page (frontend/src/app/globals.css
   --lp-* tokens, Instrument Sans 500 display / DM Sans body). Eleven slides:
   a cover plus the nine elements an idea round asks for, with Innovation,
   Feasibility and Scalability added because they are named evaluation criteria.
   Only the cover names a domain or theme; nothing else is event-specific. */
const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.layout = "LAYOUT_WIDE";                     // 13.333 x 7.5
p.author = "Deterium"; p.title = "Kairos";

const W = 13.333, H = 7.5, M = 0.62, CW = W - M * 2;
const C = {
  dark:"0A0A0A", darkCard:"141414", darkLine:"333333", darkLineMid:"4A4A4A",
  white:"FFFFFF", band:"F8F8F8", line:"E5E3DF", lineMid:"CFCBC4", blockIdle:"EBE8E2",
  ink:"0B1015", body:"3F3F3F", muted:"6F6F6F",
  onDark:"F5F5F4", onDarkMuted:"A3A09B",
  accent:"D93400", accentText:"CC3100", accentBright:"FF3C00",
  accentSoft:"FFF0EB", charcoal:"2E2E2E", barIdle:"3A3A3A", tabIdle:"6F6F6F"
};
const F = { h:"Instrument Sans", b:"DM Sans" };
const T = (o) => Object.assign({ isTextBox:true, margin:0 }, o);
const MK = require("./mocks.js")(p, C, F, T);
const path = require("path"), fs = require("fs");
const A = (f) => path.join(__dirname, "assets", f);
const OUT = path.join(__dirname, "build", "Kairos_Deck.pptx");

/* ---------- shared chrome ---------- */
function ground(s, kind) {                     // "white" | "band" | "dark"
  s.background = { color: kind === "dark" ? C.dark : kind === "band" ? C.band : C.white };
  return kind === "dark";
}
function rails(s, dark, stopAt) {
  const lc = dark ? C.darkLine : C.line, h = stopAt || H;
  s.addShape(p.ShapeType.rect, { x:0.34,  y:0, w:0.015, h:h, fill:{ color:lc } });
  s.addShape(p.ShapeType.rect, { x:12.99, y:0, w:0.015, h:h, fill:{ color:lc } });
  const tk = dark ? C.accentBright : C.accent;
  s.addShape(p.ShapeType.rect, { x:0.2825, y:0.30, w:0.125, h:0.125, fill:{ color:tk } });
  if (!stopAt) s.addShape(p.ShapeType.rect, { x:12.9325, y:7.07, w:0.125, h:0.125,
    fill:{ color:tk } });
}
function head(s, num, label, titleText, dark, x, w, th) {
  x = x === undefined ? M : x; w = w === undefined ? CW : w; th = th || 0.78;
  s.addShape(p.ShapeType.rect, { x:x, y:0.36, w:0.4, h:0.4,
    fill:{ color: dark ? C.accentBright : C.accent } });
  s.addText(num, T({ x:x, y:0.36, w:0.4, h:0.4, align:"center", valign:"middle",
    fontFace:F.b, fontSize:13, bold:true, color: dark ? C.dark : C.white }));
  s.addText(label.toUpperCase(), T({ x:x+0.56, y:0.36, w:w-0.56, h:0.4, valign:"middle",
    fontFace:F.b, fontSize:11, bold:true, charSpacing:0.95,
    color: dark ? C.onDarkMuted : C.muted }));
  s.addText(titleText, T({ x:x, y:0.94, w:w, h:th, valign:"top",
    fontFace:F.h, fontSize:32, charSpacing:-1.6, lineSpacing:34,
    color: dark ? C.white : C.ink }));
}
function rule(s, x, y, w, dark, kind) {
  const col = kind === "accent" ? (dark ? C.accentBright : C.accent)
            : kind === "mid"    ? (dark ? C.darkLineMid : C.lineMid)
            :                     (dark ? C.darkLine : C.line);
  s.addShape(p.ShapeType.rect, { x:x, y:y, w:w, h: kind === "mid" ? 0.022 : 0.012,
    fill:{ color:col } });
}
function vrule(s, x, y, h, dark, kind) {
  const col = kind === "mid" ? (dark ? C.darkLineMid : C.lineMid) : (dark ? C.darkLine : C.line);
  s.addShape(p.ShapeType.rect, { x:x, y:y, w: kind === "mid" ? 0.022 : 0.012, h:h,
    fill:{ color:col } });
}
function tick(s, x, y, dark, size) {
  const d = size || 0.115;
  s.addShape(p.ShapeType.rect, { x:x, y:y, w:d, h:d,
    fill:{ color: dark ? C.accentBright : C.accent } });
}
function eyebrow(s, t, x, y, w, dark, col) {
  s.addText(t.toUpperCase(), T({ x:x, y:y, w:w, h:0.24, fontFace:F.b, fontSize:9.5,
    bold:true, charSpacing:0.8, color: col || (dark ? C.onDarkMuted : C.muted) }));
}
function steps(s, items, o) {
  const gap = 0.1, rh = (o.h - gap * (items.length - 1)) / items.length;
  items.forEach((t, i) => {
    const y = o.y + i * (rh + gap);
    s.addShape(p.ShapeType.ellipse, { x:o.x, y:y + rh/2 - 0.145, w:0.29, h:0.29,
      fill:{ color:o.numFill } });
    s.addText(String(o.start + i), T({ x:o.x, y:y + rh/2 - 0.145, w:0.29, h:0.29,
      align:"center", valign:"middle", fontFace:F.b, fontSize:10.5, bold:true,
      color:o.numColor }));
    s.addText(t, T({ x:o.x+0.44, y:y, w:o.w-0.44, h:rh, valign:"middle",
      fontFace:F.b, fontSize:12.5, color:o.textColor, lineSpacing:15 }));
  });
}

/* ============================================ 00  cover */
{
  const s = p.addSlide(); ground(s, "dark");
  s.addImage({ path:A("lp_media_cover.jpg"), x:0, y:0, w:W, h:H });
  const fx = 0.34;
  s.addShape(p.ShapeType.rect, { x:fx, y:fx, w:W - fx*2, h:H - fx*2, fill:{ type:"none" },
    line:{ color:"FFFFFF", width:0.75, transparency:62 } });

  const X = 1.02;
  s.addImage({ path:A("logo_mark.png"), x:X, y:1.28, w:0.7, h:0.7 });
  s.addText("Kairos", T({ x:X, y:2.10, w:8, h:1.24, valign:"middle",
    fontFace:F.h, fontSize:74, charSpacing:-3.6, color:C.white }));
  s.addText("Knowledge that arrives before you ask for it.",
    T({ x:X, y:3.42, w:8.4, h:0.44, fontFace:F.h, fontSize:21, charSpacing:-0.8,
        color:"FFE4D8" }));

  eyebrow(s, "Problem statement", X, 4.16, 8, true, "FFD9CC");
  s.addText("Industrial knowledge that never reaches the point of decision.",
    T({ x:X, y:4.42, w:8.6, h:0.48, fontFace:F.h, fontSize:19, charSpacing:-0.7,
        color:C.white }));

  let cx = X;
  ["Artificial Intelligence & Machine Learning", "Computer Vision", "Generative AI"]
    .forEach((label) => {
      const cw = 0.3 + label.length * 0.077;
      s.addShape(p.ShapeType.rect, { x:cx, y:5.14, w:cw, h:0.34, fill:{ type:"none" },
        line:{ color:"FFFFFF", width:0.75, transparency:52 } });
      s.addText(label, T({ x:cx, y:5.14, w:cw, h:0.34, align:"center", valign:"middle",
        fontFace:F.b, fontSize:10, color:"FFE4D8" }));
      cx += cw + 0.16;
    });

  const SY = 6.08, SX = fx + 0.34, SW = W - (fx + 0.34) * 2;
  MK.slab(s, SX, SY, SW, 0.86, 46);
  const field = [
    ["Team", "Deterium"],
    ["Presented by", "Krishna Somani"],
    ["Institution", "SRM Institute of Science and Technology, Kattankulathur"],
    ["Domain", "AI & ML · Software Development"]
  ];
  const fw = (SW - 0.68) / 4;
  field.forEach((f, i) => {
    const x = SX + 0.34 + i * fw;
    s.addText(f[0].toUpperCase(), T({ x:x, y:SY + 0.12, w:fw - 0.3, h:0.22,
      fontFace:F.b, fontSize:8.5, bold:true, charSpacing:0.8, color:"FFC9B4" }));
    s.addText(f[1], T({ x:x, y:SY + 0.37, w:fw - 0.3, h:0.46, valign:"top",
      fontFace:F.b, fontSize:11.5, color:C.white, lineSpacing:14 }));
    if (i > 0) s.addShape(p.ShapeType.rect, { x:x - 0.17, y:SY + 0.14, w:0.01, h:0.58,
      fill:{ color:"FFFFFF", transparency:66 } });
  });
  s.addNotes("Cover. The problem title, the domain chips and the Domain field are the only event-specific lines on the whole deck; swap them per brief. Nothing anywhere names an organiser or competition.");
}

/* ============================================ 01  problem: hero over a media band */
{
  const s = p.addSlide(); const d = ground(s, "white"); rails(s, d, 3.94);
  s.addShape(p.ShapeType.rect, { x:M, y:0.36, w:0.4, h:0.4, fill:{ color:C.accent } });
  s.addText("01", T({ x:M, y:0.36, w:0.4, h:0.4, align:"center", valign:"middle",
    fontFace:F.b, fontSize:13, bold:true, color:C.white }));
  s.addText("PROBLEM STATEMENT", T({ x:M+0.56, y:0.36, w:6, h:0.4, valign:"middle",
    fontFace:F.b, fontSize:11, bold:true, charSpacing:0.95, color:C.muted }));

  s.addText([
    { text:"The plant\nalready knows.\n", options:{ color:C.ink } },
    { text:"Nobody can find it\nin time.", options:{ color:C.accent } }
  ], T({ x:M, y:1.02, w:6.5, h:2.6, valign:"top",
         fontFace:F.h, fontSize:40, charSpacing:-2.0, lineSpacing:43 }));

  const RX = 7.5, RW = W - RX - M;
  s.addText("At 2:40 a.m. a technician signs a permit to open a feed pump. The approved procedure in front of him is current, correct, and wrong for this pump. The bulletin that lowered the limit is in the building, in another system, under another name for the same equipment.",
    T({ x:RX, y:1.12, w:RW, h:1.5, valign:"top", fontFace:F.b, fontSize:13,
        color:C.body, lineSpacing:19 }));
  rule(s, RX, 2.78, RW, d, "mid");
  s.addText("He did not fail to find it. He failed to know it existed.",
    T({ x:RX, y:2.96, w:RW, h:0.6, valign:"top", fontFace:F.h, fontSize:19,
        charSpacing:-0.8, lineSpacing:23, color:C.accentText }));

  const BY = 3.94;
  MK.mediaFrame(s, A("lp_media_band.jpg"), 0, BY, W, H - BY, 0.3);
  s.addText("Over 90%", T({ x:1.0, y:4.44, w:4.2, h:0.9, valign:"middle",
    fontFace:F.h, fontSize:46, charSpacing:-2.2, color:C.white }));
  s.addText("of the serious incidents the US Chemical Safety Board analysed involved hazards already documented in publicly available literature.",
    T({ x:1.0, y:5.4, w:4.3, h:0.9, valign:"top", fontFace:F.b, fontSize:11.5,
        color:"FFE4D8", lineSpacing:15 }));
  s.addText("Incident Data: Reactive Hazard Investigation, No. 2003-15-D. 167 US incidents, 1980 to 2001.",
    T({ x:1.0, y:6.42, w:4.3, h:0.4, fontFace:F.b, fontSize:8.5, color:"FFC9B4",
        lineSpacing:11 }));

  MK.slab(s, 6.4, 4.44, 5.95, 2.4, 52);
  eyebrow(s, "Hit by an unplanned outage at least monthly", 6.72, 4.7, 5.4, true, "FFD9CC");
  const BW = 3.5;
  [["India", 88, 0], ["Global", 69, 62]].forEach((r, i) => {
    const y = 5.08 + i * 0.6;
    s.addText(r[0], T({ x:6.72, y:y, w:0.86, h:0.34, valign:"middle",
      fontFace:F.b, fontSize:11, color:"FFD9CC" }));
    s.addShape(p.ShapeType.rect, { x:7.6, y:y, w:BW * r[1] / 100, h:0.34,
      fill:{ color:"FFFFFF", transparency:r[2] } });
    s.addText(r[1] + "%", T({ x:7.68 + BW * r[1] / 100, y:y, w:0.7, h:0.34, valign:"middle",
      fontFace:F.h, fontSize:14, charSpacing:-0.4, color:C.white }));
  });
  s.addText("Unplanned downtime also costs ₹70 lakh an hour in India, against ₹1.03 crore globally.  ABB Value of Reliability, Sapio Research, July 2023, n=3,215.",
    T({ x:6.72, y:6.28, w:5.35, h:0.7, valign:"top", fontFace:F.b, fontSize:8.5,
        color:"FFD9CC", lineSpacing:11 }));
  s.addNotes("Open on the scenario, then the 90 percent: the knowledge was already reachable and did not arrive. Both figures are sourced on the slide.");
}

/* ============================================ 02  solution: flow on a spine */
{
  const s = p.addSlide(); const d = ground(s, "white"); rails(s, d);
  head(s, "02", "Proposed Solution", "Events trigger the knowledge, not questions", d);

  eyebrow(s, "Every system before this", M, 2.0, 5.5, d);
  s.addText("Knowledge exists  →  someone forms a query  →  results come back",
    T({ x:M, y:2.26, w:5.5, h:0.8, valign:"top", fontFace:F.b, fontSize:12.5,
        color:C.muted, lineSpacing:18 }));
  vrule(s, 6.52, 1.98, 1.16, d, "mid");
  eyebrow(s, "Kairos", 6.98, 2.0, 5.7, d, C.accentText);
  s.addText("An event happens  →  the system reads it against everything the plant knows  →  the brief arrives, unasked",
    T({ x:6.98, y:2.26, w:5.72, h:0.8, valign:"top", fontFace:F.b, fontSize:12.5,
        color:C.ink, lineSpacing:18 }));

  rule(s, M, 3.3, CW, d);
  s.addText("Nobody types anything. A work order opening, a permit raised, a shift handing over, equipment isolated: each is a trigger.",
    T({ x:M, y:3.48, w:CW, h:0.34, fontFace:F.b, fontSize:12.5, color:C.body }));

  const SY = 4.42;
  rule(s, M, SY, CW, d, "mid");
  const stage = [
    ["Sources", "Drawings, work orders, manuals, email, voice, live sensor values"],
    ["Perception", "A specialised model per document type"],
    ["Governed graph", "Every claim carries when, who, how sure, and its original"],
    ["Trigger engine", "Decides what matters, and how often to interrupt"],
    ["Point of action", "A phone, at the permit, before work starts"]
  ];
  const gw = CW / 5;
  stage.forEach((st, i) => {
    const x = M + i * gw;
    tick(s, x, SY - 0.047, d, 0.115);
    s.addText(st[0], T({ x:x, y:SY + 0.3, w:gw - 0.4, h:0.34,
      fontFace:F.h, fontSize:16, charSpacing:-0.5, color:C.ink }));
    s.addText(st[1], T({ x:x, y:SY + 0.72, w:gw - 0.45, h:0.9, valign:"top",
      fontFace:F.b, fontSize:11, color:C.muted, lineSpacing:14 }));
    if (i < 4) s.addText("→", T({ x:x + gw - 0.44, y:SY + 0.28, w:0.38, h:0.32,
      align:"center", fontFace:F.b, fontSize:14, color:C.lineMid }));
  });

  s.addText("A system that pushes must not become noise, so interruptions are capped at the process industry's own alarm benchmark: fewer than six per operator per hour (EEMUA 191, ANSI/ISA-18.2, IEC 62682).",
    T({ x:M, y:6.44, w:CW, h:0.5, valign:"top", fontFace:F.b, fontSize:11,
        color:C.muted, lineSpacing:14 }));
  s.addNotes("Five blocks is the whole architecture at this altitude. The alarm cap answers the obvious objection before a judge raises it.");
}

/* ============================================ 03  key features */
{
  const s = p.addSlide(); const d = ground(s, "white"); rails(s, d);
  head(s, "03", "Key Features", "Six things it does that a search box cannot", d);

  const feat = [
    ["Briefs that arrive unasked",
     "A work order opening, a permit raised, a shift handing over: each is a trigger. Nobody searches."],
    ["Every answer carries its evidence",
     "Source document, authority level, confidence score, and a link to the original file, on every claim."],
    ["A refusal instead of a guess",
     "Below the evidence threshold on a safety question it states what is missing, never a hedged answer."],
    ["Time travel over the record",
     "Ask what the plant knew on the day of the incident, not what it knows after the investigation."],
    ["Conflict detection and blast radius",
     "When a source is superseded, everything downstream of it is traced and flagged for re-review."],
    ["Compliance gaps by clause",
     "Each regulatory clause checked against the documents actually linked to that asset, and the gaps listed."]
  ];
  const top = 1.98, rh = 0.74;
  rule(s, M, top, CW, d, "mid");
  feat.forEach((f, i) => {
    const y = top + 0.16 + i * rh;
    tick(s, M, y + 0.16, d, 0.115);
    s.addText(f[0], T({ x:M + 0.36, y:y, w:3.9, h:0.5, valign:"middle",
      fontFace:F.h, fontSize:16, charSpacing:-0.55, lineSpacing:19, color:C.ink }));
    s.addText(f[1], T({ x:M + 4.5, y:y, w:CW - 4.5, h:0.5, valign:"middle",
      fontFace:F.b, fontSize:12, color:C.body, lineSpacing:16 }));
    if (i < 5) rule(s, M, y + 0.6, CW, d);
  });

  rule(s, M, 6.56, CW, d, "mid");
  s.addText([
    { text:"The first three are the product.  ", options:{ color:C.ink } },
    { text:"Delivery without governance is a confident guess; governance without delivery is a better document store.", options:{ color:C.muted } }
  ], T({ x:M, y:6.74, w:CW, h:0.42, valign:"top", fontFace:F.b, fontSize:12,
         lineSpacing:16 }));
  s.addNotes("Kept to six so each one is a sentence a judge can repeat. The full feature set also covers P&ID topology extraction, multilingual and mixed-script field records, voice capture, and cross-site pattern detection.");
}

/* ============================================ 04  innovation, beside the product */
{
  const s = p.addSlide(); const d = ground(s, "dark"); rails(s, d);
  head(s, "04", "Innovation and Uniqueness", "Two claims, and the four mechanisms underneath", d);

  const LW = 6.5;
  s.addText([
    { text:"The inversion.  ", options:{ color:C.accentBright } },
    { text:"Every prior approach optimises retrieval, and every one assumes somebody knows what to ask. The most dangerous gaps are the ones nobody thinks to query.", options:{ color:C.white } }
  ], T({ x:M, y:1.9, w:LW, h:1.0, valign:"top", fontFace:F.h, fontSize:16,
         charSpacing:-0.5, lineSpacing:22 }));

  const mech = [
    ["01","Every fact knows when it stopped being true"],
    ["02","A regulation outranks a field note"],
    ["03","Every answer points at the original file"],
    ["04","It is built to refuse"]
  ];
  rule(s, M, 3.06, LW, d, "mid");
  mech.forEach((m, i) => {
    const y = 3.24 + i * 0.78;
    s.addText(m[0], T({ x:M, y:y, w:0.8, h:0.5, valign:"middle",
      fontFace:F.h, fontSize:24, charSpacing:-1.0, color:C.accentBright }));
    s.addText(m[1], T({ x:M + 0.86, y:y, w:LW - 0.86, h:0.5, valign:"middle",
      fontFace:F.h, fontSize:15.5, charSpacing:-0.5, color:C.white }));
    if (i < 3) rule(s, M, y + 0.62, LW, d);
  });

  const PX = 7.42, PW = W - PX - M;
  MK.mediaFrame(s, A("lp_media_mock.jpg"), PX, 1.86, PW, 4.72, 0.24);
  MK.copilotMock(s, PX + 0.52, 2.24, PW - 1.04);

  rule(s, M, 6.52, CW, d);
  s.addText("Without proactive delivery this is a better document store. Without governed accuracy it is a confident hallucination machine pointed at a refinery.",
    T({ x:M, y:6.72, w:CW, h:0.52, valign:"top", fontFace:F.h, fontSize:15,
        charSpacing:-0.5, lineSpacing:19, color:C.accentBright }));
  s.addNotes("The mock is the real interface: source chips, authority, a confidence meter, and the refusal path beside it.");
}

/* ============================================ 05  target users */
{
  const s = p.addSlide(); const d = ground(s, "white"); rails(s, d);
  head(s, "05", "Target Users", "Five roles, each reached at one moment", d);

  const role = [
    ["Field technician", "At the permit, on a phone, one tap to acknowledge. Never opens a search box."],
    ["Reliability engineer", "At the failure, with the equipment's history already assembled."],
    ["Shift lead", "At handover, inheriting a structured brief instead of what someone remembered."],
    ["Compliance officer", "Before an audit, with evidence organised by the clause it answers to."],
    ["Plant head", "Across sites, where a failure at one plant warns the other five."]
  ];
  const gw = CW / 5, top = 2.1;
  rule(s, M, top, CW, d, "mid");
  role.forEach((r, i) => {
    const x = M + i * gw;
    tick(s, x, top + 0.34, d, 0.1);
    s.addText(r[0], T({ x:x, y:top + 0.66, w:gw - 0.4, h:0.72, valign:"top",
      fontFace:F.h, fontSize:17, charSpacing:-0.6, lineSpacing:20, color:C.ink }));
    s.addText(r[1], T({ x:x, y:top + 1.44, w:gw - 0.45, h:1.3, valign:"top",
      fontFace:F.b, fontSize:11.5, color:C.muted, lineSpacing:15 }));
    if (i > 0) vrule(s, x - 0.22, top + 0.3, 2.62, d, "mid");
  });

  rule(s, M, 5.34, CW, d);
  s.addText([
    { text:"Bought by ", options:{ color:C.muted } },
    { text:"plant operations and reliability leadership", options:{ color:C.ink } },
    { text:", who carry both the downtime budget and the safety accountability. Deployed first in Indian heavy industry, where multilingual and mixed-script field records are the norm rather than an edge case.", options:{ color:C.muted } }
  ], T({ x:M, y:5.56, w:CW, h:0.6, valign:"top", fontFace:F.b, fontSize:12.5,
         lineSpacing:17 }));
  s.addNotes("A list of moments, not a persona table. The structure argues this is point-of-action, not a portal people must remember to visit.");
}

/* ============================================ 06  expected impact */
{
  const s = p.addSlide(); const d = ground(s, "band"); rails(s, d);
  head(s, "06", "Expected Impact", "What we will measure, not what we will claim", d);

  s.addText("We will not project a percentage we cannot yet evidence.",
    T({ x:M, y:2.1, w:4.5, h:1.5, valign:"top", fontFace:F.h, fontSize:27,
        charSpacing:-1.1, lineSpacing:30, color:C.ink }));
  s.addText("The binding constraint was never search speed. It is that the right knowledge does not reach the right person at the moment of the decision: the permit, the work order, the handover.",
    T({ x:M, y:3.74, w:4.5, h:1.4, valign:"top", fontFace:F.b, fontSize:12.5,
        color:C.body, lineSpacing:17 }));

  vrule(s, 5.62, 2.06, 3.6, d, "mid");
  eyebrow(s, "Four instruments, built alongside the system", 6.1, 2.06, 6.6, d);
  const inst = [
    "Answer correctness against a fixed expert question set with a written answer key",
    "Time to a trusted answer, against plain keyword search on the same corpus",
    "Compliance gap detection, scored on recall first: a missed gap is a liability, a false alarm a nuisance",
    "Proactive brief relevance, against what the receiving role actually needed"
  ];
  inst.forEach((t, i) => {
    const y = 2.44 + i * 0.84;
    rule(s, 6.1, y, 6.6, d);
    s.addText("0" + (i + 1), T({ x:6.1, y:y + 0.16, w:0.6, h:0.4,
      fontFace:F.h, fontSize:18, charSpacing:-0.6, color:C.accentText }));
    s.addText(t, T({ x:6.76, y:y + 0.14, w:5.94, h:0.6, valign:"top",
      fontFace:F.b, fontSize:12, color:C.body, lineSpacing:16 }));
  });

  s.addShape(p.ShapeType.rect, { x:M, y:6.16, w:CW, h:0.72, fill:{ color:C.accent } });
  s.addText("Graded deterministically against a written key. Never one model scoring another model's output.",
    T({ x:M + 0.34, y:6.16, w:CW - 0.68, h:0.72, valign:"middle",
        fontFace:F.h, fontSize:16, charSpacing:-0.5, color:C.white }));
  s.addNotes("Deliberately not an ROI claim. A model judging its own family's answers measures agreement, not correctness, and saying so signals you know how these systems get evaluated dishonestly.");
}

/* ============================================ 07  technology: the repo's diagram */
{
  const s = p.addSlide(); const d = ground(s, "white"); rails(s, d);
  head(s, "07", "Proposed Technology Stack", "A store per job, a model per task", d);

  s.addText("Every box is a decision, not a vendor list: a graph store because the queries are multi-hop traversals filtered by time and authority, exact search alongside semantic because equipment tags must match exactly, and a specialist model per document type because one generalist degrades on all of them.",
    T({ x:M, y:1.82, w:CW, h:0.76, valign:"top", fontFace:F.b, fontSize:12.5,
        color:C.body, lineSpacing:17 }));

  const DW = CW, DH = DW * 806 / 2600;
  s.addImage({ path:A("dia_overview_lr.png"), x:M, y:2.54, w:DW, h:DH });

  const key = [
    ["FFF1EA", "D93400", "Human touch"],
    ["F6F5F3", "0B1015", "Request path"],
    ["FDF4E6", "A66A00", "Model reasoning"],
    ["EDF1F4", "3E5C6B", "Persistent state"],
    ["E9F2EC", "2F6B3E", "Human authority gate"],
    ["F5E1DC", "9A3324", "Refusal or hard gate"]
  ];
  const kw = CW / 6, ky = 6.24;
  rule(s, M, 6.06, CW, d);
  key.forEach((k, i) => {
    const x = M + i * kw;
    s.addShape(p.ShapeType.rect, { x:x, y:ky + 0.04, w:0.24, h:0.19,
      fill:{ color:k[0] }, line:{ color:k[1], width:1 } });
    s.addText(k[2], T({ x:x + 0.36, y:ky, w:kw - 0.46, h:0.28, valign:"middle",
      fontFace:F.b, fontSize:10.5, color:C.body }));
  });
  s.addText("Green and brick appear only on the human gate and the refusal path: the two places the system declines to act on its own. All inference runs on hosted APIs, so there is no GPU procurement, no training run and no labelled dataset on the critical path.",
    T({ x:M, y:6.72, w:CW, h:0.44, valign:"top", fontFace:F.b, fontSize:11,
        color:C.muted, lineSpacing:14 }));
  s.addNotes("This is the project's own architecture diagram, generated from the mermaid source in docs/DIAGRAMS.md and re-rendered in the deck's typeface.");
}

/* ============================================ 08  feasibility beyond the event */
{
  const s = p.addSlide(); const d = ground(s, "white"); rails(s, d);
  head(s, "08", "Feasibility", "Built to survive contact with a real plant", d);

  s.addText("The question is not whether a demo can be assembled. It is whether this can be implemented beyond the hackathon, inside a brownfield plant that will not stop running while you install it.",
    T({ x:M, y:1.86, w:CW, h:0.52, valign:"top", fontFace:F.b, fontSize:13,
        color:C.body, lineSpacing:18 }));

  eyebrow(s, "Why it is implementable", M, 2.58, 7.4, d, C.accentText);
  const yes = [
    "All inference runs on hosted APIs: no GPU procurement, no training run, no labelled dataset",
    "Brownfield entry. It reads the systems a plant already runs; nothing is ripped out or replaced",
    "Value lands before the graph does. Month one is search across everything ingested",
    "The human gate lets it enter a safety-critical environment without waiting for perfect extraction",
    "Every store is a managed or containerised service with a well-understood operating model"
  ];
  yes.forEach((t, i) => {
    const y = 2.96 + i * 0.62;
    tick(s, M, y + 0.1, d, 0.115);
    s.addText(t, T({ x:M + 0.36, y:y, w:7.0, h:0.52, valign:"top",
      fontFace:F.b, fontSize:13, color:C.ink, lineSpacing:17 }));
  });

  vrule(s, 8.3, 2.54, 3.5, d, "mid");
  eyebrow(s, "Constraints we are not hiding", 8.74, 2.58, 3.98, d);
  const no = [
    "Graph query performance as the graph grows. Index design is a workstream from month two, not late hardening",
    "Drawing extraction is candidate, not canonical, until an engineer verifies it element by element",
    "Benchmark figures will characterise a seeded corpus, not a production archive",
    "Compliance output is audit preparation with human sign-off, never automated compliance"
  ];
  no.forEach((t, i) => {
    s.addText(t, T({ x:8.74, y:2.96 + i * 0.78, w:3.98, h:0.72, valign:"top",
      fontFace:F.b, fontSize:11.5, color:C.tabIdle, lineSpacing:15 }));
  });

  rule(s, M, 6.36, CW, d, "mid");
  s.addText([
    { text:"For the prototype round: ", options:{ color:C.ink } },
    { text:"one vertical slice end to end, ingest through to a cited answer and one proactive brief, measured against a written answer key. A prototype that does one thing all the way through beats five that stop at the seam.", options:{ color:C.muted } }
  ], T({ x:M, y:6.56, w:CW, h:0.6, valign:"top", fontFace:F.b, fontSize:12.5,
         lineSpacing:17 }));
  s.addNotes("This slide answers the stated criterion: can the solution realistically be implemented beyond the hackathon. Naming the constraints is what makes the rest of it credible.");
}

/* ============================================ 09  scalability */
{
  const s = p.addSlide(); const d = ground(s, "white"); rails(s, d);
  head(s, "09", "Scalability", "One plant, then every plant, then every sector", d);

  const BASE = 5.10;
  const phase = [
    ["Month 1", "One plant", "Everything ingested is searchable in one place, before any graph exists", 0.70],
    ["Month 2", "Asset-linked", "Every document reachable by the equipment it concerns, under all its names", 1.25],
    ["Month 3", "Proactive", "Push switches on only after interruption volume holds inside the alarm benchmark", 1.80],
    ["Then", "Site by site", "A control plane for identity and cross-site patterns; each plant keeps its data plane", 2.35]
  ];
  const gw = CW / 4;
  rule(s, M, BASE, CW, d, "mid");
  phase.forEach((ph, i) => {
    const x = M + i * gw, h = ph[3], bw = gw - 0.5;
    s.addShape(p.ShapeType.rect, { x:x, y:BASE - h, w:bw, h:h,
      fill:{ color: i === 3 ? C.accent : C.blockIdle } });
    s.addText(ph[1], T({ x:x + 0.22, y:BASE - h + 0.18, w:bw - 0.44, h:0.36,
      fontFace:F.h, fontSize:15, charSpacing:-0.5, color: i === 3 ? C.white : C.ink }));
    eyebrow(s, ph[0], x, BASE + 0.16, bw, d, i === 3 ? C.accentText : C.muted);
    s.addText(ph[2], T({ x:x, y:BASE + 0.44, w:bw, h:0.86, valign:"top",
      fontFace:F.b, fontSize:10.5, color:C.muted, lineSpacing:13 }));
  });

  rule(s, M, 6.52, CW, d);
  s.addText([
    { text:"Data stays inside the plant.  ", options:{ color:C.ink } },
    { text:"Only an anonymised technical pattern crosses a site boundary, with personnel names stripped. Across sectors the architecture is identical: regulations, drawing conventions and vocabulary are configuration.", options:{ color:C.muted } }
  ], T({ x:M, y:6.70, w:CW, h:0.56, valign:"top", fontFace:F.b, fontSize:12,
         lineSpacing:16 }));
  s.addNotes("The phases are a deployment gate, not a release schedule: trust in a safety-critical system is earned by demonstrated accuracy.");
}

/* ============================================ 10  implementation approach */
{
  const s = p.addSlide(); const d = ground(s, "dark"); rails(s, d, 5.16);
  head(s, "10", "Initial Implementation Approach", "One event, traced end to end", d);

  s.addText("A manufacturer's bulletin arrives lowering a pressure limit.",
    T({ x:M, y:1.82, w:CW, h:0.32, fontFace:F.b, fontSize:13, color:C.onDark }));

  const step = [
    "Stored unchanged, hashed and timestamped",
    "New limit and equipment extracted, with confidence",
    "Linked to the asset, or quarantined rather than guessed",
    "Conflict classified as safety-critical",
    "The old claim's window closes, nothing is deleted",
    "Blast radius traced and flagged for re-review",
    "The technician on that permit is told, before he starts"
  ];
  const nw = (CW - 3 * 0.34) / 4, nh = 1.0;
  step.forEach((t, i) => {
    const row = i < 4 ? 0 : 1, col = i < 4 ? i : i - 4;
    const x = M + col * (nw + 0.34), y = 2.36 + row * (nh + 0.5), last = i === 6;
    s.addShape(p.ShapeType.rect, { x:x, y:y, w:nw, h:nh,
      fill:{ color: last ? C.accent : C.darkCard } });
    s.addText(String(i + 1), T({ x:x + 0.2, y:y + 0.14, w:0.5, h:0.26,
      fontFace:F.b, fontSize:10.5, bold:true, color: last ? "FFD9CC" : C.accentBright }));
    s.addText(t, T({ x:x + 0.2, y:y + 0.42, w:nw - 0.4, h:0.5, valign:"top",
      fontFace:F.b, fontSize:11, color: last ? C.white : C.onDark, lineSpacing:14 }));
    if (i < 6 && col < 3) s.addText("→", T({ x:x + nw, y:y + 0.34, w:0.34, h:0.3,
      align:"center", fontFace:F.b, fontSize:13, color:C.darkLine }));
  });

  // Closing panel, framed like the band on slide 01 rather than left as a bleed
  const BY = 5.16;
  MK.mediaFrame(s, A("lp_media_strip.jpg"), 0, BY, W, H - BY, 0.3);
  s.addImage({ path:A("logo_mark.png"), x:W - M - 0.52, y:5.66, w:0.52, h:0.52 });
  s.addText("Step 7 is the product. Steps 1 to 6 are why step 7 can be trusted.",
    T({ x:M, y:5.64, w:11.3, h:0.5, valign:"middle", fontFace:F.h, fontSize:19,
        charSpacing:-0.8, color:C.white }));
  s.addText("Phase 1 corpus, storage, ingestion   ·   Phase 2 graph and retrieval   ·   Phase 3 synthesis, refusal gate, trigger   ·   Phase 4 field view, evaluation, documentation",
    T({ x:M, y:6.24, w:12.0, h:0.38, fontFace:F.b, fontSize:11, color:"FFE4D8" }));
  s.addText("Evaluation is built in phase 1, not phase 4. A measured result is the deliverable, not a demonstration.",
    T({ x:M, y:6.66, w:11.6, h:0.34, fontFace:F.b, fontSize:11.5, bold:true,
        color:C.white }));

  s.addNotes("With nothing built, a traced flow is the proof of engineering thought. Phases rather than days, so the plan does not assume a particular build window.");
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
p.writeFile({ fileName: OUT }).then(() =>
  console.log("wrote", path.relative(__dirname, OUT)));
