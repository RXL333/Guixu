from __future__ import annotations

import base64
import io
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


def image_part(path: Path) -> dict[str, object]:
    """Make a bounded, metadata-free visual input for an explicitly selected image."""
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        raise ValueError("CHAT_IMAGE_UNSUPPORTED")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as original:
                image = ImageOps.exif_transpose(original)
                image.thumbnail((1024, 1024))
                output = io.BytesIO()
                image.convert("RGB").save(output, format="JPEG", quality=82, optimize=True)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("CHAT_IMAGE_INVALID") from exc
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}}
