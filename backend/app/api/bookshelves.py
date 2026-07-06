from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.timeline import (
    create_bookshelf,
    delete_bookshelf,
    list_bookshelf_tree,
    list_bookshelves,
    update_bookshelf,
)

router = APIRouter(tags=["bookshelves"])


@router.get("/api/bookshelves")
def get_bookshelves(db: Session = Depends(get_db)):
    return list_bookshelves(db)


@router.get("/api/bookshelves/tree")
def get_bookshelf_tree(db: Session = Depends(get_db)):
    return list_bookshelf_tree(db)


@router.post("/api/bookshelves")
def post_bookshelf(payload: dict, db: Session = Depends(get_db)):
    return create_bookshelf(db, payload or {})


@router.put("/api/bookshelves/{bookshelf_id}")
def put_bookshelf(bookshelf_id: int, payload: dict, db: Session = Depends(get_db)):
    return update_bookshelf(db, bookshelf_id, payload or {})


@router.delete("/api/bookshelves/{bookshelf_id}")
def remove_bookshelf(bookshelf_id: int, db: Session = Depends(get_db)):
    return delete_bookshelf(db, bookshelf_id)
