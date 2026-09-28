"""Turn the user-provided artwork into reproducible Windows and web icons."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packaging" / "assets" / "source-icon.png"
WINDOWS_PNG = ROOT / "packaging" / "assets" / "guixu-icon.png"
WINDOWS_ICO = ROOT / "packaging" / "assets" / "guixu.ico"
WEB_ICON = ROOT / "frontend" / "public" / "app-icon.png"
FAVICON = ROOT / "frontend" / "public" / "favicon.png"


def main() -> None:
    source = Image.open(SOURCE).convert("RGB")
    pixels = np.asarray(source)
    gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
    _, foreground = cv2.threshold(gray, 225, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < source.width * source.height * 0.3:
        raise ValueError("Artwork foreground could not be identified")

    silhouette = np.zeros_like(gray)
    cv2.drawContours(silhouette, [contour], -1, 255, thickness=cv2.FILLED)
    x, y, width, height = cv2.boundingRect(contour)
    padding = 12
    side = max(width, height) + padding * 2
    left = max(0, x - (side - width) // 2)
    top = max(0, y - (side - height) // 2)
    box = (left, top, min(source.width, left + side), min(source.height, top + side))

    cropped = source.crop(box).convert("RGBA")
    alpha = Image.fromarray(silhouette).crop(box).filter(ImageFilter.GaussianBlur(0.8))
    cropped.putalpha(alpha)
    artwork = cropped.resize((1024, 1024), Image.Resampling.LANCZOS)
    artwork.save(WINDOWS_PNG, optimize=True)
    artwork.save(WINDOWS_ICO, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    artwork.resize((256, 256), Image.Resampling.LANCZOS).save(WEB_ICON, optimize=True)
    artwork.resize((64, 64), Image.Resampling.LANCZOS).save(FAVICON, optimize=True)
    print(f"Generated app icons from {SOURCE.name}; foreground box={(x, y, width, height)}")


if __name__ == "__main__":
    main()
