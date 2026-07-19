import uuid
from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.storage import generate_presigned_put
from app.tools import stt

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


class TranscribeResponse(BaseModel):
    transcript: str
    confidence: float


# Feature 2.10: standalone STT so the app can echo the transcript BEFORE send.
# :path converter — media_keys are tenant-prefixed and contain a slash (2.5 D6).
@router.post("/{media_key:path}/transcribe")
def transcribe_media(
    media_key: str,
    x_tenant_id: Annotated[str, Header()] = "dev",
) -> TranscribeResponse:
    # same trust boundary as the turn pipeline (2.5 D6): foreign tenant → 404,
    # existence of the key is not revealed
    if not media_key.startswith(f"{x_tenant_id}/"):
        raise HTTPException(404, "media not found")
    try:
        result = stt.transcribe(media_key)
    except ValueError as exc:  # stored object is not audio
        raise HTTPException(422, str(exc)) from exc
    except ClientError as exc:  # object missing in S3
        raise HTTPException(404, "media not found") from exc
    except Exception as exc:  # ffmpeg/model failure — app degrades to 2.4 inline STT
        raise HTTPException(502, "Transkription fehlgeschlagen") from exc
    return TranscribeResponse(
        transcript=result["transcript"], confidence=result["confidence"]
    )
