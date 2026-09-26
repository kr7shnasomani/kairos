#!/usr/bin/env bash
# Build the deck. Output is Kairos_Deck.pdf; everything else lands in build/.
#
#   ./build.sh            rebuild the deck
#   ./build.sh --assets   also regenerate the gradients, diagram and logo
#
# assets/ is committed, so the plain form needs only `npm install`, not
# mermaid-cli's Chromium. See README.md before the first run on a new machine.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "--assets" || ! -f assets/lp_media_cover.jpg ]]; then
  python3 assets.py
fi

node build_deck.js      # -> build/Kairos_Deck.pptx
python3 finalize.py     # theme fonts, ea/cs mirror, geometry audit
python3 export.py       # -> Kairos_Deck.pdf
