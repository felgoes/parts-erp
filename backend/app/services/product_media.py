from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000


def store_product_image(contents: bytes) -> tuple[str, int, int]:
    if not contents or len(contents) > MAX_IMAGE_BYTES:
        raise ValueError("Cada foto deve ter até 10 MB")
    try:
        with Image.open(BytesIO(contents)) as probe:
            if probe.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Formato inválido. Use JPG, PNG ou WebP")
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise ValueError("A foto excede o limite de 25 megapixels")
            probe.verify()
        with Image.open(BytesIO(contents)) as source:
            image = ImageOps.exif_transpose(source)
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            filename = f"{uuid4().hex}.jpg"
            directory = Path(get_settings().product_images_dir).resolve()
            directory.mkdir(parents=True, exist_ok=True)
            image.save(directory / filename, format="JPEG", quality=88, optimize=True)
            return filename, image.width, image.height
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(
            "Não consegui ler essa imagem. Selecione um JPG, PNG ou WebP válido"
        ) from exc


def product_image_path(filename: str) -> Path:
    directory = Path(get_settings().product_images_dir).resolve()
    target = (directory / filename).resolve()
    if target.parent != directory or not filename.endswith(".jpg"):
        raise ValueError("Imagem inválida")
    return target
