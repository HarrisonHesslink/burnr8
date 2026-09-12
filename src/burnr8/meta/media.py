"""Safe local image handling for Meta creative uploads."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MAX_IMAGE_BYTES = 30 * 1024 * 1024
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


@dataclass(frozen=True)
class ValidatedImage:
    path: Path
    filename: str
    content_type: str
    size_bytes: int
    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    @property
    def reels_warning(self) -> str | None:
        if abs(self.aspect_ratio - (9 / 16)) > 0.03:
            return (
                f"{self.filename} is {self.width}x{self.height} ({self.aspect_ratio:.3f}:1), "
                "not the recommended 9:16 Reels aspect ratio; Meta may crop or pad it."
            )
        return None

    def as_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": round(self.aspect_ratio, 4),
            "reels_warning": self.reels_warning,
        }


def get_media_root() -> Path:
    """Return the only directory from which Meta tools may read photos."""
    raw_root = os.environ.get("BURNR8_MEDIA_ROOT") or os.getcwd()
    root = Path(raw_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("BURNR8_MEDIA_ROOT must point to an existing directory.")
    return root


def validate_local_image(image_path: str) -> ValidatedImage:
    """Resolve and validate a JPEG/PNG beneath ``BURNR8_MEDIA_ROOT``."""
    if not isinstance(image_path, str) or not image_path.strip():
        raise ValueError("image_path must be a non-empty file path.")

    root = get_media_root()
    supplied = Path(image_path).expanduser()
    unresolved = supplied if supplied.is_absolute() else root / supplied
    try:
        resolved = unresolved.resolve(strict=True)
    except FileNotFoundError:
        raise ValueError(f"Image file does not exist: {supplied.name or image_path}") from None

    try:
        relative_parts = unresolved.absolute().relative_to(root).parts
    except ValueError:
        relative_parts = ()
    current = root
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Image paths may not contain symbolic links.")

    if not resolved.is_relative_to(root):
        raise ValueError("Image path is outside BURNR8_MEDIA_ROOT and cannot be read.")
    if not resolved.is_file():
        raise ValueError("image_path must point to a regular file.")

    size = resolved.stat().st_size
    if size <= 0:
        raise ValueError("Image file is empty.")
    if size > MAX_IMAGE_BYTES:
        raise ValueError(f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB upload limit.")

    data = resolved.read_bytes()
    suffix = resolved.suffix.lower()
    if data.startswith(_PNG_SIGNATURE):
        if suffix != ".png":
            raise ValueError("PNG image filename must end in .png.")
        width, height = _png_dimensions(data)
        content_type = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        if suffix not in {".jpg", ".jpeg"}:
            raise ValueError("JPEG image filename must end in .jpg or .jpeg.")
        width, height = _jpeg_dimensions(data)
        content_type = "image/jpeg"
    else:
        raise ValueError("Only valid JPEG and PNG image files are supported.")

    return ValidatedImage(
        path=resolved,
        filename=resolved.name,
        content_type=content_type,
        size_bytes=size,
        width=width,
        height=height,
    )


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise ValueError("PNG file has an invalid header.")
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        raise ValueError("PNG file has invalid dimensions.")
    return width, height


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    offset = 2
    while offset + 3 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            break
        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            break
        if marker in _JPEG_SOF_MARKERS:
            if segment_length < 7:
                break
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            if width <= 0 or height <= 0:
                break
            return width, height
        offset += segment_length
    raise ValueError("JPEG file has an invalid header or no readable dimensions.")
