import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from api.errors import not_found
from api.models import Base


def now() -> datetime:
    return datetime.now(UTC)


def get_or_404[M: Base](db: Session, model: type[M], ident: uuid.UUID, what: str, *, lock: bool = False) -> M:
    row = db.get(model, ident, with_for_update=lock)
    if row is None:
        raise not_found(what)
    return row
