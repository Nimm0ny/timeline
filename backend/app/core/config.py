import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
FRONTEND_DIR = ROOT_DIR / "frontend"
THEME_DIR = ROOT_DIR / "theme"
CONFIG_FILE = DATA_DIR / "config.json"
DB_FILE = DATA_DIR / "timeline.db"

MEDIA_DEFAULT_CONFIG = {
    "compress": True,
    "keepOriginal": False,
    "quality": 80,
    "maxEdge": 1920,
    "thumbEdge": 400,
}

DEFAULT_CONFIG = {
    "brandName": "历史长河",
    "heroTitle": "历史长河",
    "heroSubtitle": "滚动浏览 · 悬停探索 · 纵览千年",
    "brandFontSize": "",
    "brandColor": "",
    "titleFontSize": "",
    "titleColor": "",
    "subtitleFontSize": "",
    "subtitleColor": "",
    "layout": "horizontal",
    # Desktop three-column layout: which outer edge the function sidebar sits on
    # ("left" | "right"). feed stays centered; the detail pane takes the opposite
    # outer edge (docs/layout-swap-design.md). Global (not per-notebook), cross-device.
    "navPosition": "left",
    # Whether the detail pane sits on an outer edge ("edge", default) or swaps with
    # the feed into the center track ("center") — docs/layout-swap-design.md §7.
    # Global, cross-device; the frontend normalizes invalid values back to "edge".
    "detailPosition": "edge",
    # The cross-notebook favorites view has no owning notebook, so its sort levels
    # live in app config (cross-device synced) rather than a Topic column. Default =
    # most-recently-favorited first (docs/center-sort-design.md §12).
    "favoritesSort": [{"field": "favorited", "dir": -1}],
    # Left-tree ordering applied client-side to both bookshelves and the notebooks
    # inside each shelf. Canonical "mode:dir" — mode ("default" = backend creation
    # order | "name" | "count" | "updated"), dir (1 asc / -1 desc). Legacy bare "mode"
    # values are tolerated by the front-end. Global (not per-shelf), cross-device;
    # era sub-lists stay time-sorted. Stored/decoded as a plain string (no whitelist).
    "sidebarSort": "default:1",
    "media": dict(MEDIA_DEFAULT_CONFIG),
}


def encode_config_value(value) -> str:
    if isinstance(value, (dict, list, bool, int, float)) or value is None:
        return json.dumps(value, ensure_ascii=False)
    return str(value)
