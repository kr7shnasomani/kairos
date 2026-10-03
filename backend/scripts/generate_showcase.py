"""
Write the showcase files into `dataset/` (`showcase_*` beside the golden files in the same six folders).

The generator (`scripts/showcase/spec|docs|history.py`) is how the files get made; the files are what the
loader, the redate and the reset read (`scripts/showcase/files.py`). Touches no store and writes only
showcase files (a test pins that none shares a name with a golden file). Overwrites them, so review the diff.

    make generate-showcase          # writes dataset/ (the dataset mount is read-only, so make adds /out)
    make generate-showcase ARGS=--now   # re-anchor the dates (rewrites every dated file)
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "/app")

from scripts.showcase import files
from scripts.showcase.docs import build_documents
from scripts.showcase.history import build_showcase
from scripts.showcase.spec import build_assets

PLACEHOLDER_USER = "00000000-0000-0000-0000-00000000de40"


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/out")
    # Keep the anchor the files were written at (dates are moved to load time on read, so it never needs to
    # move), which makes a regeneration reproduce unchanged files byte for byte. `--now` re-anchors.
    meta = out / files.META[0] / files.META[1]
    anchor = datetime.fromisoformat(json.loads(meta.read_text())["anchor"]) if meta.exists() and "--now" not in sys.argv else datetime.now(UTC)
    assets = build_assets()
    counts = files.write(out, assets, build_documents(assets, anchor), build_showcase(assets, anchor, PLACEHOLDER_USER),
                         demo_user_placeholder=PLACEHOLDER_USER)
    print("Wrote", out, counts)


if __name__ == "__main__":
    main()
