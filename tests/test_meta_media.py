"""Tests for local Meta image validation and sandboxing."""

from pathlib import Path
from unittest.mock import patch

import pytest

from burnr8.meta.media import validate_local_image


def _write_png(path: Path, width: int = 1080, height: int = 1920) -> Path:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )
    return path


def test_validates_vertical_png(tmp_path):
    photo = _write_png(tmp_path / "reel.png")
    with patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}):
        result = validate_local_image(str(photo))

    assert result.content_type == "image/png"
    assert (result.width, result.height) == (1080, 1920)
    assert result.reels_warning is None


def test_warns_for_non_vertical_image(tmp_path):
    _write_png(tmp_path / "square.png", 1080, 1080)
    with patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}):
        result = validate_local_image("square.png")

    assert "recommended 9:16" in (result.reels_warning or "")


def test_rejects_path_outside_media_root(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    outside = _write_png(tmp_path / "outside.png")
    with (
        patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(media_root)}),
        pytest.raises(ValueError, match="outside BURNR8_MEDIA_ROOT"),
    ):
        validate_local_image(str(outside))


def test_rejects_symlink(tmp_path):
    photo = _write_png(tmp_path / "photo.png")
    link = tmp_path / "link.png"
    link.symlink_to(photo)
    with (
        patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}),
        pytest.raises(ValueError, match="symbolic links"),
    ):
        validate_local_image(str(link))


def test_rejects_mismatched_extension(tmp_path):
    photo = _write_png(tmp_path / "photo.jpg")
    with (
        patch.dict("os.environ", {"BURNR8_MEDIA_ROOT": str(tmp_path)}),
        pytest.raises(ValueError, match="must end in .png"),
    ):
        validate_local_image(str(photo))
