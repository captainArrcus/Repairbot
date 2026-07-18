import uuid
from typing import Annotated

from fastapi import APIRouter, Header
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
def create_presigned_upload(
    req: UploadUrlRequest,
    x_tenant_id: Annotated[str, Header()] = "dev",  # auth fills this later (spec 2.5 D6)
) -> UploadUrlResponse:
    # media_key = "<tenant>/<uuid>" (1.2 forward pointer, landed in 2.5): every
    # S3 key is tenant-prefixed. filename/purpose accepted per API contract,
    # not persisted — no media table exists yet.
    media_key = f"{x_tenant_id}/{uuid.uuid4()}"
    return UploadUrlResponse(
        upload_url=generate_presigned_put(media_key, req.content_type),
        media_key=media_key,
    )
