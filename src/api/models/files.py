import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, now_column, one_of, uuid_pk

FILE_KINDS = ("file", "image", "snippet", "avatar")


class File(Base):
    __tablename__ = "files"
    __table_args__ = (one_of("kind", FILE_KINDS),)

    id: Mapped[uuid.UUID] = uuid_pk()
    uploader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Access is checked against this conversation; null only for avatars.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(Text, server_default="file")
    name: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    language: Mapped[str | None] = mapped_column(Text)  # snippets only
    created_at: Mapped[datetime] = now_column()
