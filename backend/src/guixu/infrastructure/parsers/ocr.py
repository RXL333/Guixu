from __future__ import annotations

import hashlib
import importlib.metadata
from functools import lru_cache
from pathlib import Path
from typing import Any


RAPIDOCR_VERSION = "3.9.2"
MODEL_HASHES = {
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    "PP-OCRv6_det_small.onnx": "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    "PP-OCRv6_rec_small.onnx": "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def rapidocr_status() -> tuple[bool, str]:
    try:
        if importlib.metadata.version("rapidocr") != RAPIDOCR_VERSION:
            return False, "OCR_VERSION_UNVERIFIED"
        import rapidocr
        model_root = Path(rapidocr.__file__).parent / "models"
        for name, expected in MODEL_HASHES.items():
            model = model_root / name
            if not model.is_file() or _digest(model) != expected:
                return False, "OCR_RESOURCE_HASH_MISMATCH"
        importlib.metadata.version("onnxruntime")
    except (ImportError, importlib.metadata.PackageNotFoundError, OSError):
        return False, "OCR_COMPONENT_MISSING"
    return True, "OCR_READY"


@lru_cache(maxsize=1)
def _engine():
    ready, reason = rapidocr_status()
    if not ready:
        raise RuntimeError(reason)
    from rapidocr import RapidOCR
    # All three model files are present and hash-verified before construction;
    # no URL or model alias is passed, so the bundled local resources are used.
    return RapidOCR()


def recognize(image: Any) -> tuple[list[tuple[str, float]], str | None]:
    ready, reason = rapidocr_status()
    if not ready:
        return [], reason
    try:
        output = _engine()(image)
    except Exception:
        return [], "OCR_FAILED"
    texts = [(str(text).strip(), float(score)) for text, score in zip(output.txts or (), output.scores or ()) if str(text).strip()]
    return texts, None
