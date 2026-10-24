"""File attachments and snippets on local disk (spec 1.13, 1.14). S3 comes with slice B3."""

import mimetypes
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from api import config
from api.access import can_access
from api.errors import ApiError, forbidden, invalid
from api.models import Conversation, File, User
from api.serializers import thumbnail_path
from api.services.common import get_or_404
from api.services.conversations import require_member

MAX_BYTES = 25 * 1024 * 1024
THUMBNAIL_PX = 320


def path_of(f: File) -> Path:
    return config.FILES_DIR / f.storage_key


def upload(db: Session, user: User, upload: UploadFile, conversation_id: uuid.UUID | None, kind: str,
           name: str | None, language: str | None) -> File:
    if kind != "avatar":
        if conversation_id is None:
            raise invalid("conversation_id", "Attachments belong to a conversation.")
        require_member(db, user, get_or_404(db, Conversation, conversation_id, "Conversation"))
    data = upload.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ApiError(413, "too_large", "Files are limited to 25 MB.")
    filename = Path(name or upload.filename or "file").name
    mime = upload.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if kind == "file" and mime.startswith("image/"):
        kind = "image"
    file_id = uuid.uuid4()
    f = File(id=file_id, uploader_id=user.id, conversation_id=None if kind == "avatar" else conversation_id,
             kind=kind, name=filename, mime=mime, size=len(data), storage_key=f"{file_id}/{filename}",
             language=language if kind == "snippet" else None)
    target = path_of(f)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    if kind in ("image", "avatar"):
        _thumbnail(target, file_id)
    db.add(f)
    db.flush()
    return f


def _thumbnail(source: Path, file_id: uuid.UUID) -> None:
    try:
        with Image.open(source) as img:
            img.thumbnail((THUMBNAIL_PX, THUMBNAIL_PX))
            out = thumbnail_path(file_id)
            out.parent.mkdir(parents=True, exist_ok=True)
            img.save(out, "PNG")
    except (OSError, ValueError):
        pass  # not an image Pillow can read: no thumbnail, the file is still stored


def readable(db: Session, user: User, file_id: uuid.UUID) -> File:
    """Avatars are visible to everyone; unattached uploads to their uploader; the rest per `can_access`."""
    f = get_or_404(db, File, file_id, "File")
    if f.kind == "avatar":
        return f
    if f.message_id is None and f.uploader_id != user.id:
        raise forbidden()
    if not can_access(db, user, db.get(Conversation, f.conversation_id), at=f.created_at):
        raise forbidden()
    return f


def preview(f: File, lines: int) -> tuple[str, bool]:
    if f.kind != "snippet" and not f.mime.startswith("text/"):
        raise invalid("file_id", "Only snippets and text files have a preview.")
    content = path_of(f).read_text(errors="replace").splitlines()
    return "\n".join(content[:lines]), len(content) > lines
