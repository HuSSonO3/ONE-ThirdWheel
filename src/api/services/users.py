"""Users, departments and the org tree (spec 1.2–1.4, 2.1)."""

import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import events
from api.auth import hash_password
from api.errors import conflict, forbidden, invalid
from api.models import Conversation, Department, User, UserClosure
from api.models import Session as UserSession
from api.schemas import contract as c
from api.services.common import get_or_404
from api.services.conversations import add_member, close_member, department_conversation

SELF_FIELDS = {"name", "job_title", "avatar_file_id", "timezone"}
ADMIN_FIELDS = {"email", "password", "role", "department_id", "manager_id", "active"}


def list_users(db: Session, q: str | None, department_id: uuid.UUID | None, include_inactive: bool) -> list[User]:
    query = select(User)
    if q:
        like = f"{q.lower()}%"
        query = query.where(or_(func.lower(User.name).like(like), func.lower(User.email).like(like),
                                func.lower(User.name).like(f"% {q.lower()}%")))
    if department_id:
        query = query.where(User.department_id == department_id)
    if not include_inactive:
        query = query.where(User.active)
    return list(db.scalars(query.order_by(User.name)))


def subordinates(db: Session, me: User) -> list[User]:
    return list(db.scalars(
        select(User).join(UserClosure, UserClosure.descendant_id == User.id)
        .where(UserClosure.ancestor_id == me.id, UserClosure.depth > 0)
        .order_by(UserClosure.depth, User.name)))


def _check_manager(db: Session, target: User | None, manager_id: uuid.UUID | None) -> None:
    if manager_id is None:
        return
    get_or_404(db, User, manager_id, "Manager")
    if target and db.scalar(select(func.count()).select_from(UserClosure).where(
            UserClosure.ancestor_id == target.id, UserClosure.descendant_id == manager_id)):
        raise conflict("manager_cycle", "That manager reports to this person.")


def _move_department(db: Session, user: User, new: uuid.UUID | None, by: uuid.UUID) -> None:
    """Changing department moves the user between department channels (spec 1.4)."""
    if user.department_id == new:
        return
    if user.department_id:
        close_member(db, department_conversation(db, user.department_id), user.id, via="department_sync", by=by)
    if new:
        get_or_404(db, Department, new, "Department")
        add_member(db, department_conversation(db, new), user.id, via="department_sync", by=by)
    user.department_id = new


def create(db: Session, admin: User, body: c.UserCreate) -> User:
    if db.scalar(select(func.count()).select_from(User).where(func.lower(User.email) == body.email.lower())):
        raise conflict("email_taken", "That email is already in use.")
    _check_manager(db, None, body.manager_id)
    user = User(email=body.email, password_hash=hash_password(body.password), name=body.name,
                job_title=body.job_title, manager_id=body.manager_id, role=body.role or "member",
                timezone=body.timezone or "UTC")
    db.add(user)
    db.flush()
    if body.department_id:
        _move_department(db, user, body.department_id, admin.id)
    return user


def update(db: Session, actor: User, target: User, body: c.UserUpdate) -> User:
    fields = body.model_fields_set
    is_admin = actor.role == "admin"
    if actor.id != target.id and not is_admin:
        raise forbidden("You can only edit your own profile.")
    if fields & ADMIN_FIELDS and not is_admin:
        raise forbidden("Only an admin can change that.", code="admin_required")

    for field in fields & SELF_FIELDS:
        if field == "name" and not body.name:
            raise invalid("name", "Name can't be empty.")
        setattr(target, field, getattr(body, field))
    if "email" in fields and body.email.lower() != target.email.lower():
        if db.scalar(select(func.count()).select_from(User).where(func.lower(User.email) == body.email.lower())):
            raise conflict("email_taken", "That email is already in use.")
        target.email = body.email
    if "password" in fields:
        target.password_hash = hash_password(body.password)
    if "role" in fields and body.role:
        target.role = body.role
    if "manager_id" in fields and body.manager_id != target.manager_id:
        if body.manager_id == target.id:
            raise conflict("manager_cycle", "Nobody can manage themselves.")
        _check_manager(db, target, body.manager_id)
        target.manager_id = body.manager_id
        try:
            db.flush()  # the closure trigger runs here and is the last line against cycles
        except IntegrityError as exc:
            raise conflict("manager_cycle", "That manager reports to this person.") from exc
    if "department_id" in fields:
        _move_department(db, target, body.department_id, actor.id)
    if "active" in fields and body.active is not None:
        target.active = body.active
        if not body.active:
            db.execute(delete(UserSession).where(UserSession.user_id == target.id))
    db.flush()
    return target


# ---------------------------------------------------------------- departments

def create_department(db: Session, admin: User, name: str) -> Department:
    name = name.strip()
    if db.scalar(select(func.count()).select_from(Department).where(func.lower(Department.name) == name.lower())):
        raise conflict("conflict", "A department with that name exists.")
    dept = Department(name=name)
    db.add(dept)
    db.flush()
    db.add(Conversation(kind="department", name=name.lower(), description=f"{name} department",
                        department_id=dept.id, created_by=admin.id))
    db.flush()
    return dept


def rename_department(db: Session, admin: User, dept: Department, name: str) -> Department:
    name = name.strip()
    if name == dept.name:
        return dept
    if db.scalar(select(func.count()).select_from(Department).where(
            func.lower(Department.name) == name.lower(), Department.id != dept.id)):
        raise conflict("conflict", "A department with that name exists.")
    dept.name = name
    conv = department_conversation(db, dept.id)
    events.conversation_updated(db, conv.id, admin.id, {"name": [conv.name, name.lower()]})
    conv.name = name.lower()
    return dept


def department_members(db: Session, dept: Department) -> list[User]:
    return list(db.scalars(select(User).where(User.department_id == dept.id, User.active).order_by(User.name)))
