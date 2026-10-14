"""Animal photos: validate, normalise and store uploaded images."""

import os
import uuid

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PHOTOS = 2
FULL_SIZE = (1600, 1600)
THUMB_SIZE = (400, 400)


class PhotoError(Exception):
    pass


def folder():
    return current_app.config["UPLOAD_FOLDER"]


def thumb_name(filename):
    stem, ext = os.path.splitext(filename)
    return f"{stem}_thumb{ext}"


def save(file_storage):
    """Store an uploaded image as JPEG plus a thumbnail. Returns the file name.

    The image is turned upright from its EXIF orientation and re-encoded, which
    also drops EXIF data such as the GPS position from phone photos.
    """
    try:
        with Image.open(file_storage.stream) as image:
            image.load()
            image = ImageOps.exif_transpose(image)
            if image.mode != "RGB":
                image = image.convert("RGB")
            filename = f"{uuid.uuid4().hex}.jpg"
            full = image.copy()
            full.thumbnail(FULL_SIZE)
            full.save(os.path.join(folder(), filename), "JPEG", quality=85, optimize=True)
            image.thumbnail(THUMB_SIZE)
            image.save(os.path.join(folder(), thumb_name(filename)), "JPEG", quality=80, optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise PhotoError(
            f"{file_storage.filename or 'Filen'} kunde inte läsas som en bild. "
            "Använd JPEG, PNG eller WebP."
        ) from exc
    return filename


def delete_files(filename):
    for name in (filename, thumb_name(filename)):
        try:
            os.remove(os.path.join(folder(), name))
        except FileNotFoundError:
            pass
