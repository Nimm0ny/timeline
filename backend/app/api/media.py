from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import User
from backend.app.services.auth import get_current_user
from backend.app.services.timeline import delete_image_by_filename, store_uploaded_image

router = APIRouter(tags=["media"])


@router.post("/api/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await store_uploaded_image(db, file, user.id)


@router.delete("/api/media/by-filename/{filename}")
def delete_media_by_filename(
    filename: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return delete_image_by_filename(db, filename)
