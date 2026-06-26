import hashlib
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.config import router as config_router
from backend.app.api.frontend import router as frontend_router
from backend.app.api.media import router as media_router
from backend.app.api.themes import router as themes_router
from backend.app.api.topics import router as topics_router
from backend.app.core.config import IMAGES_DIR, THEME_DIR
from backend.app.db.session import SessionLocal
from backend.app.services.legacy_migration import init_database, migrate_legacy_files
from backend.app.services.timeline import rebuild_search_index


MEDIA_CACHE_CONTROL = "public, max-age=31536000, immutable"
HASHED_MEDIA_NAME = re.compile(r"^[a-f0-9]{16}(?:\.thumb|\.orig)?\.[A-Za-z0-9]+$")


def _safe_image_path(filename: str) -> Path:
    root = IMAGES_DIR.resolve()
    requested = (root / filename).resolve()
    try:
        requested.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image not found") from exc
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return requested


def _media_etag(path: Path) -> str:
    name = path.name
    if HASHED_MEDIA_NAME.fullmatch(name):
        return name.split(".", 1)[0]
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def image_response(filename: str):
    path = _safe_image_path(filename)
    return FileResponse(
        path,
        headers={
            "Cache-Control": MEDIA_CACHE_CONTROL,
            "ETag": f'"{_media_etag(path)}"',
        },
    )


def create_app() -> FastAPI:
    app = FastAPI(title="历史长河 API")

    @app.on_event("startup")
    def on_startup():
        init_database()
        db = SessionLocal()
        try:
            migrate_legacy_files(db)
            rebuild_search_index(db)
            db.commit()
        finally:
            db.close()

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    THEME_DIR.mkdir(parents=True, exist_ok=True)
    app.add_api_route("/images/{filename:path}", image_response, methods=["GET"], name="images")
    app.mount("/theme", StaticFiles(directory=str(THEME_DIR)), name="theme")

    app.include_router(config_router)
    app.include_router(topics_router)
    app.include_router(media_router)
    app.include_router(themes_router)
    app.include_router(frontend_router)
    return app


app = create_app()
