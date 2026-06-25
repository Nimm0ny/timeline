from fastapi import APIRouter, Depends

from backend.app.models.entities import User
from backend.app.services.auth import get_admin_user
from backend.app.services.timeline import get_theme_vars, list_themes, update_theme_vars

router = APIRouter(tags=["themes"])


@router.get("/api/themes")
def get_themes():
    return list_themes()


@router.get("/api/themes/{name}/vars")
def get_theme_variables(name: str):
    return get_theme_vars(name)


@router.put("/api/themes/{name}/vars")
def put_theme_variables(name: str, payload: dict, _: User = Depends(get_admin_user)):
    return update_theme_vars(name, payload)
