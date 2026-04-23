"""Unified image storage — supports S3 and Cloudinary.

Switch via IMAGE_STORAGE env var: "s3" or "cloudinary".
When you're ready for S3, just set IMAGE_STORAGE=s3 and fill in AWS creds.
"""

import asyncio
import io
import logging
import uuid
from urllib.parse import urlparse

import httpx
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

_USE_S3 = settings.IMAGE_STORAGE.lower() == "s3"

# ── S3 setup (lazy — only if IMAGE_STORAGE=s3) ──────────────────────────

if _USE_S3:
    import aioboto3

    _session = aioboto3.Session(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )

# ── Cloudinary setup (lazy — only if IMAGE_STORAGE=cloudinary) ───────────

if not _USE_S3:
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def _s3_public_url(key: str) -> str:
    return f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"


# ── Core upload functions ────────────────────────────────────────────────


async def upload_file(
    file_bytes: bytes,
    key: str,
    content_type: str = "image/webp",
) -> str:
    """Upload raw bytes and return the public URL."""
    if _USE_S3:
        async with _session.client("s3") as s3:
            await s3.put_object(
                Bucket=settings.AWS_S3_BUCKET,
                Key=key,
                Body=file_bytes,
                ContentType=content_type,
            )
        url = _s3_public_url(key)
        logger.info("Uploaded to S3: %s", key)
        return url
    else:
        # Cloudinary upload — run in thread to avoid blocking the event loop
        result = await asyncio.to_thread(
            cloudinary.uploader.upload,
            file_bytes,
            public_id=key.rsplit(".", 1)[0],
            folder="rayna",
            resource_type="image",
            format="webp",
            overwrite=True,
        )
        url = result["secure_url"]
        logger.info("Uploaded to Cloudinary: %s", key)
        return url


async def upload_from_url(
    source_url: str,
    key: str,
    resize: tuple[int, int] | None = None,
) -> str:
    """Download image from URL, optionally resize, upload."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        resp = await http.get(source_url)
        resp.raise_for_status()

    img_bytes = resp.content
    content_type = "image/webp"

    if resize:
        try:
            img = Image.open(io.BytesIO(img_bytes))
            img = img.convert("RGB")
            img = img.resize(resize, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=85)
            img_bytes = buf.getvalue()
        except Exception as exc:
            logger.warning("Image resize failed, uploading original: %s", exc)
            ct = resp.headers.get("content-type", "image/jpeg")
            content_type = ct.split(";")[0].strip()

    return await upload_file(img_bytes, key, content_type)


async def delete_file(key: str) -> None:
    """Delete a file."""
    if _USE_S3:
        async with _session.client("s3") as s3:
            await s3.delete_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
        logger.info("Deleted from S3: %s", key)
    else:
        public_id = f"rayna/{key.rsplit('.', 1)[0]}"
        await asyncio.to_thread(
            cloudinary.uploader.destroy, public_id, resource_type="image"
        )
        logger.info("Deleted from Cloudinary: %s", public_id)


# ── Profile picture helpers ──────────────────────────────────────────


async def upload_profile_picture(file, user_id: str) -> str:
    """Upload a user profile picture."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError(
            f"File type '{file.content_type}' not allowed. Use JPEG, PNG, WebP, or GIF."
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise ValueError("File size exceeds 5 MB limit.")

    try:
        img = Image.open(io.BytesIO(contents))
        img = img.convert("RGB")
        img = img.resize((400, 400), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=90)
        contents = buf.getvalue()
    except Exception as exc:
        logger.warning("Profile picture resize failed: %s", exc)

    key = f"profiles/{user_id}.webp"
    return await upload_file(contents, key, "image/webp")


async def delete_profile_picture(user_id: str) -> None:
    """Delete a user's profile picture."""
    key = f"profiles/{user_id}.webp"
    await delete_file(key)
