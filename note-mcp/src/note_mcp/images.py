"""Image upload (eyecatch + body)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from note_mcp.client import NoteAPIError, NoteClient

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_SIZE = 10 * 1024 * 1024
CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _validate(path: Path) -> None:
    if not path.exists():
        raise NoteAPIError(0, "file not found", str(path))
    if path.suffix.lower() not in ALLOWED_EXTS:
        raise NoteAPIError(0, f"unsupported extension {path.suffix}", str(path))
    size = path.stat().st_size
    if size > MAX_SIZE:
        raise NoteAPIError(0, f"file too large ({size} bytes, max {MAX_SIZE})", str(path))


async def _resolve_numeric_id(client: NoteClient, article_id: str) -> str:
    if article_id.isdigit():
        return article_id
    response = await client.get(f"/v3/notes/{article_id}")
    numeric = response.get("data", {}).get("id")
    if not numeric:
        raise NoteAPIError(0, "could not resolve numeric id", article_id)
    return str(numeric)


async def upload_eyecatch(file_path: str, article_id: str) -> dict[str, Any]:
    """Upload an eyecatch image. note.com requires aspect ratio 1280:670 strict."""
    path = Path(file_path)
    _validate(path)
    content_type = CONTENT_TYPES[path.suffix.lower()]
    file_bytes = path.read_bytes()

    async with NoteClient() as client:
        numeric = await _resolve_numeric_id(client, article_id)
        files = {"file": (path.name, file_bytes, content_type)}
        data = {"note_id": numeric}
        response = await client.post(
            "/v1/image_upload/note_eyecatch",
            data=data,
            files=files,
        )

    image = response.get("data", {})
    url = image.get("url")
    if not url:
        raise NoteAPIError(
            0,
            "API returned no url. Most often this means the image is not 1280:670.",
            str(response)[:300],
        )
    return {
        "url": url,
        "key": image.get("key"),
        "size_bytes": len(file_bytes),
    }


async def upload_body_image(file_path: str) -> dict[str, Any]:
    """Upload a body (inline) image via S3 presigned POST."""
    path = Path(file_path)
    _validate(path)
    content_type = CONTENT_TYPES[path.suffix.lower()]
    file_bytes = path.read_bytes()

    async with NoteClient() as client:
        # Step 1: get presigned post target
        presign = await client.post(
            "/v3/images/upload/presigned_post",
            data={"filename": path.name},
        )
        d = presign.get("data", {})
        action = d.get("action")
        url = d.get("url")
        post = d.get("post") or {}
        if not action or not url or not post:
            raise NoteAPIError(0, "presigned_post returned incomplete payload", str(presign)[:300])

        # Step 2: upload to S3
        s3_response = await client.post_absolute(
            action,
            data=post,
            files={"file": (path.name, file_bytes, content_type)},
        )
        if not s3_response.is_success:
            raise NoteAPIError(s3_response.status_code, "S3 upload failed", s3_response.text[:300])

    return {"url": url, "size_bytes": len(file_bytes)}
