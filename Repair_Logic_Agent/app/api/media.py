import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.storage import generate_presigned_put

router = APIRouter(prefix="/api/v1/media", tags=["media"])


class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str = Field(pattern=r"^(image|audio)/[\w.+-]+$")
    purpose: str = "turn_media"


class UploadUrlResponse(BaseModel):
    upload_url: str
    media_key: str


@router.post("/upload-url")
def create_presigned_upload(req: UploadUrlRequest) -> UploadUrlResponse:
    # ponytail: media_key = bare uuid; tenant prefix lands here when auth
    # introduces tenant context (Feature 2.5). filename/purpose accepted per
    # API contract, not persisted — no media table exists yet.
    media_key = str(uuid.uuid4())
    return UploadUrlResponse(
        upload_url=generate_presigned_put(media_key, req.content_type),
        media_key=media_key,
    )
