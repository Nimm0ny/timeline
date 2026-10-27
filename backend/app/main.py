import hashlib
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.bookshelves import router as bookshelves_router
from backend.app.api.config import router as config_router
from backend.app.api.features import router as features_router
from backend.app.api.frontend import router as frontend_router
from backend.app.api.media import router as media_router
from backend.app.api.themes import router as themes_router
from backend.app.api.topics import router as topics_router
from backend.app.core.config import DB_FILE, IMAGES_DIR, THEME_DIR
from backend.app.core.api_errors import API_ERROR_RESPONSES, install_api_error_handlers
from backend.app.db.session import Base, SessionLocal, engine
from backend.app.services.timeline import ensure_search_schema


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


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    if not DB_FILE.exists():
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            ensure_search_schema(db)
            db.commit()
        finally:
            db.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="编年 API", lifespan=app_lifespan)
    install_api_error_handlers(app)

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    THEME_DIR.mkdir(parents=True, exist_ok=True)
    app.add_api_route("/images/{filename:path}", image_response, methods=["GET"], name="images")
    app.add_api_route(
        "/api/media/by-filename/{filename}",
        image_response,
        methods=["GET"],
        name="media_read",
        operation_id="media_read",
        response_class=FileResponse,
        responses={
            200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}},
            404: API_ERROR_RESPONSES[404],
        },
    )
    app.mount("/theme", StaticFiles(directory=str(THEME_DIR)), name="theme")

    app.include_router(config_router)
    app.include_router(features_router)
    app.include_router(bookshelves_router)
    app.include_router(topics_router)
    app.include_router(media_router)
    app.include_router(themes_router)
    app.include_router(frontend_router)
    return app


app = create_app()
