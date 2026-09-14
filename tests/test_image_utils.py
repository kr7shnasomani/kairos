"""Service-free: the one shared downscale helper for NIM inline images (Backlog #16).

OCR and P&ID used to carry separate copies. They now share `services/image_utils`, and these tests pin
the two behaviours the merge had to preserve: an image is never resized when re-encoding alone fits,
and an image already under the ceiling is sent untouched with its original type.
"""

import base64
import io
import os

from PIL import Image

from api.services import image_utils
from api.services.image_utils import _NIM_IMAGE_SIZE_LIMIT, shrink_image_for_nim, shrink_image_for_nim_b64
from api.services.ocr import OCRService
from api.services.pid import PIDService


def _encode(img: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _smooth_bmp(size: int = 900) -> bytes:
    """A scan-like image: huge uncompressed, tiny as JPEG."""
    img = Image.linear_gradient("L").resize((size, size)).convert("RGB")
    return _encode(img, "BMP")


def _noise_png(size: int) -> bytes:
    return _encode(Image.frombytes("RGB", (size, size), os.urandom(size * size * 3)), "PNG")


def test_an_image_that_fits_after_re_encoding_keeps_its_full_resolution():
    raw = _smooth_bmp()
    assert len(base64.b64encode(raw)) > _NIM_IMAGE_SIZE_LIMIT

    data, mime = shrink_image_for_nim(raw)

    assert mime == "image/jpeg"
    assert len(base64.b64encode(data)) <= _NIM_IMAGE_SIZE_LIMIT
    assert Image.open(io.BytesIO(data)).size == (900, 900)


def test_an_image_already_under_the_ceiling_is_sent_untouched():
    small = _encode(Image.new("RGB", (40, 40), "white"), "PNG")

    b64, mime = shrink_image_for_nim_b64(small, "image/png")

    assert base64.b64decode(b64) == small
    assert mime == "image/png"


def test_an_image_no_step_can_fit_returns_none_rather_than_a_truncated_payload(monkeypatch):
    # A tiny ceiling makes "nothing fits" cheap to reach: incompressible noise at the smallest step
    # (0.25x) still encodes to a few KB.
    monkeypatch.setattr(image_utils, "_NIM_IMAGE_SIZE_LIMIT", 1000)
    assert shrink_image_for_nim(_noise_png(200)) is None


def test_ocr_and_pid_share_the_helper_and_keep_their_return_shapes():
    raw = _smooth_bmp()

    ocr_bytes, _ = OCRService._shrink_for_inline(raw)
    pid_b64, _ = PIDService._fit_b64(raw, "image/bmp")

    assert isinstance(ocr_bytes, bytes)
    assert base64.b64decode(pid_b64) == ocr_bytes
