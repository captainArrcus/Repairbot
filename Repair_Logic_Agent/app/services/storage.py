"""Presigned S3 uploads (Feature 1.2). Signing is local — no S3 round-trip."""

import boto3
from botocore.config import Config

from app import config

PRESIGN_EXPIRY_S = 900

# ponytail: module-level client (thread-safe per boto3 docs); wrap in a factory
# only when tests need to fake it
_s3 = boto3.client(
    "s3",
    endpoint_url=config.S3_ENDPOINT_URL,
    aws_access_key_id=config.S3_ACCESS_KEY,
    aws_secret_access_key=config.S3_SECRET_KEY,
    region_name="us-east-1",
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)


def get_object(media_key: str) -> tuple[bytes, str]:
    """Fetch an uploaded object. Returns (bytes, content_type) — the stored
    MIME is trustworthy because the presign signs it (Feature 1.2)."""
    obj = _s3.get_object(Bucket=config.S3_BUCKET, Key=media_key)
    return obj["Body"].read(), obj.get("ContentType", "")


def put_object(key: str, data: bytes, content_type: str) -> None:
    """Store an agent-generated asset (e.g. annotated image, Feature 2.3)."""
    _s3.put_object(Bucket=config.S3_BUCKET, Key=key, Body=data, ContentType=content_type)


def generate_presigned_put(media_key: str, content_type: str) -> str:
    """URL for a direct client PUT. Object key == media_key (retrieval invariant).

    ContentType is part of the signature: the client must send the same
    Content-Type header, so stored MIME is trustworthy for vision/STT later.
    """
    return _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": config.S3_BUCKET, "Key": media_key, "ContentType": content_type},
        ExpiresIn=PRESIGN_EXPIRY_S,
    )
