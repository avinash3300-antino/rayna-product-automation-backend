import logging

import cloudinary
import cloudinary.uploader

from app.core.config import settings
from app.integrations.freepik_client import freepik_client

logger = logging.getLogger(__name__)


def _configure_cloudinary() -> None:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


async def fetch_and_upload_images(
    activity_name: str,
    city: str,
    activity_id: str,
    num_images: int = 8,
) -> list[dict]:
    """Search Freepik → upload to Cloudinary → return image metadata.

    Returns list of {url, alt_text, size_variant} dicts.
    Sets cover_image_url from the first result.
    """
    try:
        results = await freepik_client.search_images(
            f"{activity_name} {city}", limit=num_images
        )
    except Exception as exc:
        logger.warning(
            "Freepik search failed for '%s %s': %s",
            activity_name,
            city,
            exc,
        )
        return []

    if not results:
        return []

    _configure_cloudinary()
    gallery: list[dict] = []

    for i, img in enumerate(results):
        image_url = img.get("url", "")
        if not image_url:
            continue

        try:
            # Upload original and let Cloudinary handle transformations
            upload_result = cloudinary.uploader.upload(
                image_url,
                folder=f"rayna/activities/{activity_id}",
                public_id=str(i),
                overwrite=True,
                transformation=[
                    {"width": 1200, "height": 800, "crop": "fill"},
                    {"quality": "auto", "fetch_format": "auto"},
                ],
                resource_type="image",
            )

            base_url = upload_result["secure_url"]
            public_id = upload_result["public_id"]

            gallery.append(
                {
                    "url": base_url,
                    "alt_text": f"{activity_name} - image {i + 1}",
                    "size_variant": "detail",
                    "cloudinary_id": public_id,
                }
            )
        except Exception as exc:
            logger.warning(
                "Cloudinary upload failed for image %d: %s", i, exc
            )
            continue

    return gallery
