"""Cloudinary URL-based image format transformations.

Generates transformed URLs for predefined image formats (L, S, P, 2_1, 3_2)
with optional scale multipliers (1x, 2x, 4x).
Uses c_fill + g_auto so images fill exact dimensions with smart cropping.
"""

import re

# Base dimensions for each format
IMAGE_FORMATS: dict[str, tuple[int, int]] = {
    "L": (500, 113),       # Landscape banner strip   (≈4.4:1)
    "S": (250, 250),       # Square thumbnail
    "P": (240, 320),       # Portrait card
    "2_1": (220, 110),     # 2:1 ratio widget
    "3_2": (270, 180),     # 3:2 ratio card
}

SCALE_MULTIPLIERS: dict[str, int] = {
    "1x": 1,
    "2x": 2,
    "4x": 4,
}

# Matches the /upload/ segment in a Cloudinary URL (with or without existing transforms)
_CLOUDINARY_UPLOAD_RE = re.compile(
    r"(https?://res\.cloudinary\.com/[^/]+/image/upload/)(v\d+/.+)"
)


def get_format_dimensions(fmt: str, scale: str = "1x") -> tuple[int, int]:
    """Return (width, height) for a format at a given scale."""
    base_w, base_h = IMAGE_FORMATS[fmt]
    multiplier = SCALE_MULTIPLIERS.get(scale, 1)
    return base_w * multiplier, base_h * multiplier


def transform_cloudinary_url(
    url: str, width: int, height: int, quality: int = 90
) -> str:
    """Insert Cloudinary transformation params into a URL.

    Uses c_fill + g_auto (smart gravity) so the image fills exact dimensions
    by intelligently cropping to focus on the important part of the image.
    """
    m = _CLOUDINARY_UPLOAD_RE.match(url)
    if not m:
        # Not a Cloudinary URL — return as-is
        return url
    base, path = m.group(1), m.group(2)
    transform = f"c_fill,g_auto,w_{width},h_{height},f_webp,q_{quality}"
    return f"{base}{transform}/{path}"


def get_all_format_urls(
    original_url: str,
    formats: list[str] | None = None,
    scale: str = "1x",
) -> dict[str, str]:
    """Return {format_name: transformed_url} for the requested formats."""
    if formats is None:
        formats = list(IMAGE_FORMATS.keys())
    result = {}
    for fmt in formats:
        if fmt not in IMAGE_FORMATS:
            continue
        w, h = get_format_dimensions(fmt, scale)
        result[fmt] = transform_cloudinary_url(original_url, w, h)
    return result
