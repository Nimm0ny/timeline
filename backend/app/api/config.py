import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.timeline import get_app_config, update_app_config

router = APIRouter(tags=["config"])


def database_identity(db: Session) -> str:
    database = Path(str(db.get_bind().url.database)).resolve()
    return hashlib.sha256(str(database).encode("utf-8")).hexdigest()


@router.get("/api/config")
def get_config(db: Session = Depends(get_db)):
    return get_app_config(db)


@router.put("/api/config")
def put_config(payload: dict, db: Session = Depends(get_db)):
    return update_app_config(db, payload)


@router.get("/api/runtime/identity")
def get_runtime_identity(db: Session = Depends(get_db)):
    return {"databaseIdentity": database_identity(db)}
