"""Image upload service using Cloudflare R2 (S3-compatible).

Handles:
- Listing photo uploads (max 5 per listing, 5MB each)
- Image resizing/optimization via Pillow
- R2 bucket management
"""

# import boto3
# from config import get_settings
# settings = get_settings()


async def upload_image(file_bytes: bytes, filename: str, content_type: str = "image/jpeg") -> str:
    """Upload image to R2 and return public URL."""
    # s3 = boto3.client(
    #     "s3",
    #     endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
    #     aws_access_key_id=settings.r2_access_key_id,
    #     aws_secret_access_key=settings.r2_secret_access_key,
    # )
    # key = f"listings/{filename}"
    # s3.put_object(Bucket=settings.r2_bucket_name, Key=key, Body=file_bytes, ContentType=content_type)
    # return f"{settings.r2_public_url}/{key}"
    return f"https://placeholder.r2.dev/listings/{filename}"


async def delete_image(image_url: str) -> None:
    """Delete image from R2."""
    pass


async def optimize_image(file_bytes: bytes, max_width: int = 1200, quality: int = 85) -> bytes:
    """Resize and compress image for web."""
    # from PIL import Image
    # import io
    # img = Image.open(io.BytesIO(file_bytes))
    # if img.width > max_width:
    #     ratio = max_width / img.width
    #     img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
    # buffer = io.BytesIO()
    # img.save(buffer, format="JPEG", quality=quality, optimize=True)
    # return buffer.getvalue()
    return file_bytes
