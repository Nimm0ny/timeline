from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.auth import router as auth_router
from backend.app.api.compat import router as compat_router
from backend.app.api.config import router as config_router
from backend.app.api.frontend import router as frontend_router
from backend.app.api.media import router as media_router
from backend.app.api.themes import router as themes_router
from backend.app.api.topics import router as topics_router
from backend.app.core.config import IMAGES_DIR, THEME_DIR
from backend.app.db.session import SessionLocal
from backend.app.services.legacy_migration import init_database, migrate_legacy_files


def create_app() -> FastAPI:
    app = FastAPI(title="历史长河 API")

    @app.on_event("startup")
    def on_startup():
        init_database()
        db = SessionLocal()
        try:
            migrate_legacy_files(db)
        finally:
            db.close()

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    THEME_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")
    app.mount("/theme", StaticFiles(directory=str(THEME_DIR)), name="theme")

    app.include_router(auth_router)
    app.include_router(config_router)
    app.include_router(topics_router)
    app.include_router(media_router)
    app.include_router(themes_router)
    app.include_router(compat_router)
    app.include_router(frontend_router)
    return app


app = create_app()
