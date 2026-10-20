from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from app.services import product_media


def test_uploaded_product_image_keeps_original_dimensions(tmp_path, monkeypatch):
    buffer = BytesIO()
    Image.new("RGB", (2400, 1800), "white").save(buffer, format="JPEG")
    monkeypatch.setattr(
        product_media,
        "get_settings",
        lambda: SimpleNamespace(product_images_dir=str(tmp_path)),
    )

    filename, width, height = product_media.store_product_image(buffer.getvalue())

    assert filename.endswith(".jpg")
    assert (width, height) == (2400, 1800)
