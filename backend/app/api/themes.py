from fastapi import APIRouter

from backend.app.core.api_errors import API_ERROR_RESPONSES
from backend.app.schemas.common import OkOut
from backend.app.services.timeline import get_theme_vars, list_themes, update_theme_vars


router = APIRouter(
    tags=["themes"],
    responses={422: API_ERROR_RESPONSES[422], 500: API_ERROR_RESPONSES[500]},
)


@router.get(
    "/api/themes",
    response_model=list[str],
    operation_id="themes_list",
    responses={500: API_ERROR_RESPONSES[500]},
)
def get_themes():
    return list_themes()


@router.get(
    "/api/themes/{name}/vars",
    response_model=dict[str, str],
    operation_id="themes_vars_get",
    responses={404: API_ERROR_RESPONSES[404]},
)
def get_theme_variables(name: str):
    return get_theme_vars(name)


@router.put(
    "/api/themes/{name}/vars",
    response_model=OkOut,
    operation_id="themes_vars_update",
    responses={404: API_ERROR_RESPONSES[404], 422: API_ERROR_RESPONSES[422]},
)
def put_theme_variables(name: str, payload: dict[str, str]):
    return update_theme_vars(name, payload)
