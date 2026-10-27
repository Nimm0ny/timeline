from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from backend.app.core.api_errors import API_ERROR_RESPONSES
from backend.app.db.session import get_db
from backend.app.schemas.common import ImageUploadOut, OkOut
from backend.app.services.timeline import delete_image_by_filename, store_uploaded_image


router = APIRouter(
    tags=["media"],
    responses={422: API_ERROR_RESPONSES[422], 500: API_ERROR_RESPONSES[500]},
)


@router.post(
    "/api/media/upload",
    response_model=ImageUploadOut,
    operation_id="media_upload",
    responses={400: API_ERROR_RESPONSES[400], 413: API_ERROR_RESPONSES[413]},
)
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return await store_uploaded_image(db, file)


@router.delete(
    "/api/media/by-filename/{filename}",
    response_model=OkOut,
    operation_id="media_delete",
    responses={404: API_ERROR_RESPONSES[404], 409: API_ERROR_RESPONSES[409]},
)
def delete_media_by_filename(
    filename: str,
    db: Session = Depends(get_db),
):
    return delete_image_by_filename(db, filename)
