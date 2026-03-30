import logging

import cloudinary
import cloudinary.uploader
from fastapi import UploadFile

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _configure() -> None:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


async def upload_profile_picture(file: UploadFile, user_id: str) -> str:
    if file.content_type not in ALLOWED_TYPES:
        raise ValueError(f"File type '{file.content_type}' not allowed. Use JPEG, PNG, WebP, or GIF.")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise ValueError("File size exceeds 5 MB limit.")

    _configure()

    result = cloudinary.uploader.upload(
        contents,
        folder="rayna/profile_pictures",
        public_id=user_id,
        overwrite=True,
        transformation=[
            {"width": 400, "height": 400, "crop": "fill", "gravity": "face"},
            {"quality": "auto", "fetch_format": "auto"},
        ],
        resource_type="image",
    )

    return result["secure_url"]


async def delete_profile_picture(user_id: str) -> None:
    _configure()
    public_id = f"rayna/profile_pictures/{user_id}"
    cloudinary.uploader.destroy(public_id, resource_type="image")
