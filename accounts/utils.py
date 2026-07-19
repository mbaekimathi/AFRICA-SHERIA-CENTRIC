from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps


def optimize_profile_photo(uploaded_file, max_size=400, quality=72):
    """Compress and resize a profile photo for fast loading (WebP)."""
    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6)
    buffer.seek(0)

    base_name = uploaded_file.name.rsplit(".", 1)[0]
    return ContentFile(buffer.read(), name=f"{base_name}.webp")
