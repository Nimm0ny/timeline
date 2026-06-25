from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import User
from backend.app.services.auth import get_admin_user, get_current_user
from backend.app.services.timeline import (
    create_event,
    create_topic,
    delete_image_by_filename,
    delete_topic,
    export_topic_data,
    get_topic_meta,
    import_topic_data,
    list_topic_events,
    list_topics,
    parse_query_date_key,
    get_topic_or_404,
    update_topic_meta,
)

router = APIRouter(tags=["compat"])


def require_topic_id(topic_id: int | None) -> int:
    if not topic_id:
        raise HTTPException(status_code=400, detail="topicId is required")
    return topic_id


@router.get("/api/data-files")
def compat_list_topics(db: Session = Depends(get_db)):
    return list_topics(db)


@router.post("/api/data-files")
def compat_create_topic(payload: dict, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return create_topic(db, payload.get("name", ""))


@router.delete("/api/data-files/{topic_id}")
def compat_delete_topic(topic_id: int, db: Session = Depends(get_db), _: User = Depends(get_admin_user)):
    return delete_topic(db, topic_id)


@router.get("/api/events")
def compat_get_events(topicId: int = Query(...), db: Session = Depends(get_db)):
    return list_topic_events(db, topicId, legacy=True)


@router.post("/api/events")
def compat_create_event(
    payload: dict,
    topicId: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return create_event(db, topicId, payload, user, legacy=True)


@router.get("/api/data-meta")
def compat_get_meta(topicId: int = Query(...), db: Session = Depends(get_db)):
    return get_topic_meta(db, topicId)


@router.put("/api/data-meta")
def compat_put_meta(
    payload: dict,
    topicId: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return update_topic_meta(db, topicId, payload)


@router.get("/api/export")
def compat_export(
    topicId: int = Query(...),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    content, headers = export_topic_data(
        db,
        topicId,
        from_key=parse_query_date_key(from_date),
        to_key=parse_query_date_key(to_date, is_end=True),
    )
    return JSONResponse(content=content, media_type="application/json", headers=headers)


@router.delete("/api/images/{filename}")
def compat_delete_image(filename: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return delete_image_by_filename(db, filename)
