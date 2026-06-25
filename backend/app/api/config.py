from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.timeline import get_app_config, update_app_config

router = APIRouter(tags=["config"])


@router.get("/api/config")
def get_config(db: Session = Depends(get_db)):
    return get_app_config(db)


@router.put("/api/config")
def put_config(payload: dict, db: Session = Depends(get_db)):
    return update_app_config(db, payload)
