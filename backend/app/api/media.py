from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.services.timeline import delete_image_by_filename, store_uploaded_image

router = APIRouter(tags=["media"])


@router.post("/api/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return await store_uploaded_image(db, file)


@router.delete("/api/media/by-filename/{filename}")
def delete_media_by_filename(
    filename: str,
    db: Session = Depends(get_db),
):
    return delete_image_by_filename(db, filename)
