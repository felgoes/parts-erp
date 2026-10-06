from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings

MAX_USER_AVATAR_BYTES = 5 * 1024 * 1024
MAX_USER_AVATAR_PIXELS = 20_000_000


def store_user_avatar(contents: bytes) -> str:
    if not contents or len(contents) > MAX_USER_AVATAR_BYTES:
        raise ValueError("A foto deve ter até 5 MB")
    try:
        with Image.open(BytesIO(contents)) as probe:
            if probe.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Formato inválido. Use JPG, PNG ou WebP")
            if probe.width * probe.height > MAX_USER_AVATAR_PIXELS:
                raise ValueError("A imagem excede o limite de resolução permitido")
            probe.verify()
        with Image.open(BytesIO(contents)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image = ImageOps.fit(image, (512, 512), method=Image.Resampling.LANCZOS)
            filename = f"{uuid4().hex}.jpg"
            directory = Path(get_settings().product_images_dir).resolve() / "avatars"
            directory.mkdir(parents=True, exist_ok=True)
            image.save(directory / filename, format="JPEG", quality=86, optimize=True)
            return filename
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Não foi possível ler a imagem. Envie um JPG, PNG ou WebP válido") from exc


def user_avatar_path(filename: str) -> Path:
    directory = Path(get_settings().product_images_dir).resolve() / "avatars"
    target = (directory / filename).resolve()
    if target.parent != directory or Path(filename).name != filename or not filename.endswith(".jpg"):
        raise ValueError("Foto de perfil inválida")
    return target
