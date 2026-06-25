from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.app.core.config import FRONTEND_DIR

router = APIRouter(tags=["frontend"])


def ensure_frontend_path(path: str) -> Path:
    file_path = (FRONTEND_DIR / path).resolve()
    frontend_root = FRONTEND_DIR.resolve()
    if frontend_root not in file_path.parents and file_path != frontend_root:
        raise HTTPException(status_code=404, detail="Frontend asset not found")
    return file_path


def _serve_frontend_asset(path: str) -> FileResponse:
    file_path = ensure_frontend_path(path)
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Frontend asset not found")


@router.get("/")
def serve_frontend_index():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=503, detail="Frontend has not been built yet")
    return FileResponse(index_file)


@router.get("/{full_path:path}")
def serve_frontend(full_path: str):
    if full_path.startswith(("api/", "images/", "theme/")):
        raise HTTPException(status_code=404, detail="Not found")

    if "." in Path(full_path).name:
        return _serve_frontend_asset(full_path)

    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=503, detail="Frontend has not been built yet")
    return FileResponse(index_file)
