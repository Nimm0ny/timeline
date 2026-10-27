import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.api_errors import API_ERROR_RESPONSES
from backend.app.db.session import get_db
from backend.app.schemas.common import AppConfigOut, AppConfigUpdateIn, RuntimeIdentityOut, model_payload
from backend.app.services.timeline import get_app_config, update_app_config


router = APIRouter(
    tags=["config"],
    responses={422: API_ERROR_RESPONSES[422], 500: API_ERROR_RESPONSES[500]},
)


def database_identity(db: Session) -> str:
    database = Path(str(db.get_bind().url.database)).resolve()
    return hashlib.sha256(str(database).encode("utf-8")).hexdigest()


@router.get(
    "/api/config",
    response_model=AppConfigOut,
    operation_id="config_get",
    responses={500: API_ERROR_RESPONSES[500]},
)
def get_config(db: Session = Depends(get_db)):
    return get_app_config(db)


@router.put(
    "/api/config",
    response_model=AppConfigOut,
    operation_id="config_update",
    responses={422: API_ERROR_RESPONSES[422], 500: API_ERROR_RESPONSES[500]},
)
def put_config(payload: AppConfigUpdateIn, db: Session = Depends(get_db)):
    return update_app_config(db, model_payload(payload))


@router.get(
    "/api/runtime/identity",
    response_model=RuntimeIdentityOut,
    operation_id="runtime_identity",
    responses={500: API_ERROR_RESPONSES[500]},
)
def get_runtime_identity(db: Session = Depends(get_db)):
    return {"databaseIdentity": database_identity(db)}
