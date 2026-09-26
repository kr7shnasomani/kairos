# Kairos deck

Builds `Kairos_Deck.pdf`, the pitch deck. Eleven slides: a cover plus the nine
sections an idea round asks for, with Innovation, Feasibility and Scalability
added because they are named evaluation criteria.

```bash
npm install
./build.sh              # rebuild the deck
./build.sh --assets     # also regenerate gradients, diagram and logo
```

`assets/` is committed, so the plain form does not need mermaid-cli's Chromium.
The PDF is the only output; the pptx is an intermediate and stays in `build/`.

## First run on a new machine

Three things are not in this folder and the build is wrong without them.

1. **Install the fonts.** Double-click the four files in `fonts/`, or
   `cp fonts/*.ttf ~/Library/Fonts/`. Instrument Sans Regular is pinned to
   weight 500, which is the landing page's display weight, so the deck never
   asks for a bold it does not have.
2. **Install LibreOffice**, `brew install --cask libreoffice`. It is what turns
   the pptx into a vector PDF. Without it `export.py` falls back to stitching
   pictures together, and the PDF loses its text layer.
3. **Copy the fonts into LibreOffice too**:
   `cp fonts/*.ttf /Applications/LibreOffice.app/Contents/Resources/fonts/truetype/`

## Three traps, each of which cost an hour

**LibreOffice does not read `~/Library/Fonts`.** It silently substitutes Linux
Libertine, a serif, and exports with no error at all. The deck simply looks
wrong. Hence step 3 above. `export.py` greps the finished PDF for substituted
faces and warns, so this cannot ship quietly.

**The gradients must be JPEG, not PNG.** They are continuous tone with fine film
grain, the worst case for lossless coding: as PNG they compressed to their own
size inside the zip and the deck was 9.4 MB. As JPEG it is 1 MB, visually
identical, and the grain dithers the ramp so there is no banding.

**A rendered mermaid SVG cannot be restyled.** Mermaid lays flowchart labels out
as `foreignObject` divs with `white-space: nowrap` and a width measured against
the font used at render time. Swapping the font afterwards clips every label.
`assets.py` re-renders from `../docs/DIAGRAMS.md` instead. It also flips the
diagram to `flowchart LR`, because the committed `TB` lays out at aspect 0.57
and a 16:9 slide wants 3.2:1. The repo source is never modified.

## Files

| | |
|---|---|
| `build_deck.js` | The deck. Every slide is pptxgenjs calls with inch coordinates. |
| `mocks.js` | The copilot mockup, ported from the landing page's `CopilotMock`. |
| `assets.py` | Gradients, the mermaid diagram, and the logo. |
| `finalize.py` | Theme fonts, `a:latin` mirrored to `a:ea`/`a:cs`, geometry audit. |
| `export.py` | Vector PDF via LibreOffice, raster fallback without it. |
| `mermaid.deck.json` | Deck render config. DM Sans, against arial in the root one. |

`finalize.py` exits non-zero if the audit finds anything, so `build.sh` stops
rather than exporting a broken deck. It checks bounds, margins, whether any text
box can actually hold its text, and text overlapping other text.

## What reads the repo

Two files, both read-only: `../docs/DIAGRAMS.md` for the architecture diagram
and `../frontend/public/logo.png` for the mark. Nothing outside this folder is
written.

## Event-specific content

Only the cover: the problem title, the three domain chips and the Domain field.
Nothing anywhere names an organiser or an event, so the deck travels between
submissions with one slide edited.
