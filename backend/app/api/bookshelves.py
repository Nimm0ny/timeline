from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.api_errors import API_ERROR_RESPONSES
from backend.app.db.session import get_db
from backend.app.schemas.common import (
    BookshelfCreateIn,
    BookshelfOut,
    BookshelfTreeItem,
    BookshelfUpdateIn,
    DeleteOut,
    model_payload,
)
from backend.app.services.timeline import (
    create_bookshelf,
    delete_bookshelf,
    list_bookshelf_tree,
    list_bookshelves,
    update_bookshelf,
)


router = APIRouter(
    tags=["bookshelves"],
    responses={422: API_ERROR_RESPONSES[422], 500: API_ERROR_RESPONSES[500]},
)


@router.get(
    "/api/bookshelves",
    response_model=list[BookshelfOut],
    operation_id="bookshelves_list",
    responses={500: API_ERROR_RESPONSES[500]},
)
def get_bookshelves(db: Session = Depends(get_db)):
    return list_bookshelves(db)


@router.get(
    "/api/bookshelves/tree",
    response_model=list[BookshelfTreeItem],
    operation_id="bookshelves_tree",
    responses={500: API_ERROR_RESPONSES[500]},
)
def get_bookshelf_tree(db: Session = Depends(get_db)):
    return list_bookshelf_tree(db)


@router.post(
    "/api/bookshelves",
    response_model=BookshelfOut,
    operation_id="bookshelves_create",
    responses={400: API_ERROR_RESPONSES[400], 409: API_ERROR_RESPONSES[409], 422: API_ERROR_RESPONSES[422]},
)
def post_bookshelf(payload: BookshelfCreateIn, db: Session = Depends(get_db)):
    return create_bookshelf(db, model_payload(payload))


@router.put(
    "/api/bookshelves/{bookshelf_id}",
    response_model=BookshelfOut,
    operation_id="bookshelves_update",
    responses={400: API_ERROR_RESPONSES[400], 404: API_ERROR_RESPONSES[404], 422: API_ERROR_RESPONSES[422]},
)
def put_bookshelf(
    bookshelf_id: int,
    payload: BookshelfUpdateIn,
    db: Session = Depends(get_db),
):
    return update_bookshelf(db, bookshelf_id, model_payload(payload))


@router.delete(
    "/api/bookshelves/{bookshelf_id}",
    response_model=DeleteOut,
    response_model_exclude_unset=True,
    operation_id="bookshelves_delete",
    responses={404: API_ERROR_RESPONSES[404], 409: API_ERROR_RESPONSES[409]},
)
def remove_bookshelf(bookshelf_id: int, db: Session = Depends(get_db)):
    return delete_bookshelf(db, bookshelf_id)
