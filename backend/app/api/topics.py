import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.timeline import (
    build_timeline_index,
    create_event,
    create_topic,
    delete_event,
    delete_topic,
    export_topic_data,
    get_event_detail,
    get_topic_meta,
    get_topic_or_404,
    import_topic_data,
    list_topic_events,
    list_topics,
    parse_cursor_token,
    parse_query_date_key,
    query_topic_events,
    search_events,
    summarize_topic_events,
    topic_to_dict,
    update_event,
    update_topic_meta,
)

router = APIRouter(tags=["topics"])


@router.get("/api/topics")
def get_topics(db: Session = Depends(get_db)):
    return list_topics(db)


@router.get("/api/index")
def get_index(db: Session = Depends(get_db)):
    return build_timeline_index(db)


@router.get("/api/search")
def get_search(
    q: str = Query("", alias="q"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return search_events(db, q, limit)


@router.post("/api/topics")
def post_topic(payload: dict, db: Session = Depends(get_db)):
    return create_topic(db, payload.get("name", ""), payload.get("bookshelfId"))


@router.get("/api/topics/{topic_id}")
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    return topic_to_dict(get_topic_or_404(db, topic_id))


@router.delete("/api/topics/{topic_id}")
def remove_topic(topic_id: int, db: Session = Depends(get_db)):
    return delete_topic(db, topic_id)


@router.get("/api/topics/{topic_id}/meta")
def get_topic_meta_route(topic_id: int, db: Session = Depends(get_db)):
    return get_topic_meta(db, topic_id)


@router.put("/api/topics/{topic_id}/meta")
def put_topic_meta(topic_id: int, payload: dict, db: Session = Depends(get_db)):
    return update_topic_meta(db, topic_id, payload)


@router.get("/api/topics/{topic_id}/events")
def get_topic_events(
    topic_id: int,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    cursor: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    return query_topic_events(
        db,
        topic_id,
        from_key=parse_query_date_key(from_date),
        to_key=parse_query_date_key(to_date, is_end=True),
        cursor=parse_cursor_token(cursor) if cursor else None,
        limit=limit,
    )


@router.get("/api/topics/{topic_id}/summary")
def get_topic_summary(
    topic_id: int,
    group_by: str = Query(..., alias="groupBy"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    return summarize_topic_events(
        db,
        topic_id,
        group_by=group_by,
        from_key=parse_query_date_key(from_date),
        to_key=parse_query_date_key(to_date, is_end=True),
    )


@router.post("/api/topics/{topic_id}/events")
def create_topic_event(
    topic_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    return create_event(db, topic_id, payload)


@router.put("/api/events/{event_id}")
def put_event(event_id: int, payload: dict, db: Session = Depends(get_db)):
    return update_event(db, event_id, payload)


@router.get("/api/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    return get_event_detail(db, event_id)


@router.delete("/api/events/{event_id}")
def remove_event(
    event_id: int,
    permanent: bool = Query(False),
    db: Session = Depends(get_db),
):
    return delete_event(db, event_id, permanent=permanent)


@router.post("/api/topics/{topic_id}/import")
async def import_topic(
    topic_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        content = await file.read()
        parsed = json.loads(content.decode("utf-8"))
        return import_topic_data(db, topic_id, parsed)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/topics/{topic_id}/export")
def export_topic(
    topic_id: int,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    content, headers = export_topic_data(
        db,
        topic_id,
        from_key=parse_query_date_key(from_date),
        to_key=parse_query_date_key(to_date, is_end=True),
    )
    return JSONResponse(content=content, media_type="application/json", headers=headers)
