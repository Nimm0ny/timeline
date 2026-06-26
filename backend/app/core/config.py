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
    "media": dict(MEDIA_DEFAULT_CONFIG),
}


def encode_config_value(value) -> str:
    if isinstance(value, (dict, list, bool, int, float)) or value is None:
        return json.dumps(value, ensure_ascii=False)
    return str(value)
