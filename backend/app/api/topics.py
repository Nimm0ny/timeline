import json
from typing import Literal

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.core.api_errors import API_ERROR_RESPONSES
from backend.app.db.session import get_db
from backend.app.schemas.common import (
    DeleteOut,
    ImportOut,
    NoteIndexOut,
    NoteOut,
    NotePageOut,
    NoteListQuery,
    NoteSearchQuery,
    NoteSearchItem,
    NoteUpdateIn,
    NoteWriteIn,
    TopicCreateIn,
    TopicExportOut,
    TopicMetaUpdateIn,
    TopicOut,
    TopicSummaryOut,
    model_payload,
)
from backend.app.services.timeline import (
    build_timeline_index,
    create_note,
    create_topic,
    delete_note,
    delete_topic,
    export_topic_data,
    get_note_detail,
    get_topic_meta,
    get_topic_or_404,
    import_topic_data,
    list_topics,
    parse_cursor_token,
    parse_query_date_key,
    query_topic_notes,
    search_notes,
    summarize_topic_notes,
    topic_to_dict,
    update_note,
    update_topic_meta,
)


router = APIRouter(
    tags=["topics"],
    responses={422: API_ERROR_RESPONSES[422], 500: API_ERROR_RESPONSES[500]},
)


def _parse_if_match(value: str | None, resource_id: int) -> str | None:
    if value is None:
        return None
    token = value.strip()
    if len(token) >= 2 and token[0] == token[-1] == '"':
        token = token[1:-1]
    if not token or token == "*":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_version",
                "message": "If-Match 必须包含读取到的具体 updatedAt 版本。",
                "nextAction": "读取笔记详情，并将 updatedAt 原样放入 If-Match 请求头。",
                "details": {"resourceType": "note", "resourceId": resource_id},
            },
        )
    return token


def _set_note_etag(response: Response, payload: dict) -> None:
    version = payload.get("updatedAt")
    if version:
        response.headers["ETag"] = f'"{version}"'


@router.get(
    "/api/topics",
    response_model=list[TopicOut],
    operation_id="topics_list",
    responses={500: API_ERROR_RESPONSES[500]},
)
def get_topics(db: Session = Depends(get_db)):
    return list_topics(db)


@router.get(
    "/api/index",
    response_model=NoteIndexOut,
    operation_id="notes_index",
    responses={500: API_ERROR_RESPONSES[500]},
)
def get_index(db: Session = Depends(get_db)):
    return build_timeline_index(db)


@router.get(
    "/api/search",
    response_model=list[NoteSearchItem],
    operation_id="notes_search",
    responses={422: API_ERROR_RESPONSES[422], 500: API_ERROR_RESPONSES[500]},
)
def get_search(
    q: str = Query("", alias="q"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query = NoteSearchQuery(q=q, limit=limit)
    return search_notes(db, query.query, query.limit)


@router.post(
    "/api/topics",
    response_model=TopicOut,
    operation_id="topics_create",
    responses={400: API_ERROR_RESPONSES[400], 409: API_ERROR_RESPONSES[409], 422: API_ERROR_RESPONSES[422]},
)
def post_topic(payload: TopicCreateIn, db: Session = Depends(get_db)):
    return create_topic(db, payload.name, payload.bookshelfId)


@router.get(
    "/api/topics/{topic_id}",
    response_model=TopicOut,
    operation_id="topics_get",
    responses={404: API_ERROR_RESPONSES[404]},
)
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    return topic_to_dict(get_topic_or_404(db, topic_id))


@router.delete(
    "/api/topics/{topic_id}",
    response_model=DeleteOut,
    response_model_exclude_unset=True,
    operation_id="topics_delete",
    responses={404: API_ERROR_RESPONSES[404]},
)
def remove_topic(topic_id: int, db: Session = Depends(get_db)):
    return delete_topic(db, topic_id)


@router.get(
    "/api/topics/{topic_id}/meta",
    response_model=TopicOut,
    operation_id="topics_meta_get",
    responses={404: API_ERROR_RESPONSES[404]},
)
def get_topic_meta_route(topic_id: int, db: Session = Depends(get_db)):
    return get_topic_meta(db, topic_id)


@router.put(
    "/api/topics/{topic_id}/meta",
    response_model=TopicOut,
    operation_id="topics_meta_update",
    responses={400: API_ERROR_RESPONSES[400], 404: API_ERROR_RESPONSES[404], 422: API_ERROR_RESPONSES[422]},
)
def put_topic_meta(topic_id: int, payload: TopicMetaUpdateIn, db: Session = Depends(get_db)):
    return update_topic_meta(db, topic_id, model_payload(payload))


@router.get(
    "/api/topics/{topic_id}/notes",
    response_model=NotePageOut,
    operation_id="notes_list",
    responses={400: API_ERROR_RESPONSES[400], 404: API_ERROR_RESPONSES[404], 422: API_ERROR_RESPONSES[422]},
)
def get_topic_notes(
    topic_id: int,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    cursor: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    dir: int = Query(1, ge=-1, le=1),
    db: Session = Depends(get_db),
):
    query = NoteListQuery(
        **{"from": from_date, "to": to_date, "cursor": cursor, "limit": limit, "dir": dir}
    )
    return query_topic_notes(
        db,
        topic_id,
        from_key=parse_query_date_key(query.fromDate),
        to_key=parse_query_date_key(query.toDate, is_end=True),
        cursor=parse_cursor_token(query.cursor) if query.cursor else None,
        limit=query.limit,
        direction=-1 if query.direction < 0 else 1,
    )


@router.get(
    "/api/topics/{topic_id}/summary",
    response_model=TopicSummaryOut,
    operation_id="topics_summary",
    responses={400: API_ERROR_RESPONSES[400], 404: API_ERROR_RESPONSES[404], 422: API_ERROR_RESPONSES[422]},
)
def get_topic_summary(
    topic_id: int,
    group_by: Literal["year", "month"] = Query(..., alias="groupBy"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    return summarize_topic_notes(
        db,
        topic_id,
        group_by=group_by,
        from_key=parse_query_date_key(from_date),
        to_key=parse_query_date_key(to_date, is_end=True),
    )


@router.post(
    "/api/topics/{topic_id}/notes",
    response_model=NoteOut,
    operation_id="notes_create",
    responses={400: API_ERROR_RESPONSES[400], 404: API_ERROR_RESPONSES[404], 413: API_ERROR_RESPONSES[413], 422: API_ERROR_RESPONSES[422]},
)
def create_topic_note(
    topic_id: int,
    payload: NoteWriteIn,
    response: Response,
    db: Session = Depends(get_db),
):
    result = create_note(db, topic_id, model_payload(payload))
    _set_note_etag(response, result)
    return result


@router.put(
    "/api/notes/{note_id}",
    response_model=NoteOut,
    operation_id="notes_update",
    responses={
        400: API_ERROR_RESPONSES[400],
        404: API_ERROR_RESPONSES[404],
        409: API_ERROR_RESPONSES[409],
        413: API_ERROR_RESPONSES[413],
        422: API_ERROR_RESPONSES[422],
        428: API_ERROR_RESPONSES[428],
    },
)
def put_note(
    note_id: int,
    payload: NoteUpdateIn,
    response: Response,
    if_match: str = Header(..., alias="If-Match"),
    db: Session = Depends(get_db),
):
    result = update_note(
        db,
        note_id,
        model_payload(payload),
        expected_updated_at=_parse_if_match(if_match, note_id),
        require_version=True,
    )
    _set_note_etag(response, result)
    return result


@router.get(
    "/api/notes/{note_id}",
    response_model=NoteOut,
    operation_id="notes_get",
    responses={404: API_ERROR_RESPONSES[404]},
)
def get_note(note_id: int, response: Response, db: Session = Depends(get_db)):
    result = get_note_detail(db, note_id)
    _set_note_etag(response, result)
    return result


@router.delete(
    "/api/notes/{note_id}",
    response_model=DeleteOut,
    response_model_exclude_unset=True,
    operation_id="notes_delete",
    responses={404: API_ERROR_RESPONSES[404], 409: API_ERROR_RESPONSES[409], 422: API_ERROR_RESPONSES[422], 428: API_ERROR_RESPONSES[428]},
)
def remove_note(
    note_id: int,
    permanent: bool = Query(False),
    if_match: str = Header(..., alias="If-Match"),
    db: Session = Depends(get_db),
):
    return delete_note(
        db,
        note_id,
        permanent=permanent,
        expected_updated_at=_parse_if_match(if_match, note_id),
        require_version=True,
    )


@router.post(
    "/api/topics/{topic_id}/import",
    response_model=ImportOut,
    operation_id="topics_import",
    responses={400: API_ERROR_RESPONSES[400], 404: API_ERROR_RESPONSES[404], 413: API_ERROR_RESPONSES[413]},
)
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


@router.get(
    "/api/topics/{topic_id}/export",
    response_model=TopicExportOut,
    operation_id="topics_export",
    responses={400: API_ERROR_RESPONSES[400], 404: API_ERROR_RESPONSES[404]},
)
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
