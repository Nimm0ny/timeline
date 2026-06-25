from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
FRONTEND_DIR = ROOT_DIR / "frontend"
THEME_DIR = ROOT_DIR / "theme"
CONFIG_FILE = DATA_DIR / "config.json"
DB_FILE = DATA_DIR / "timeline.db"

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
}
