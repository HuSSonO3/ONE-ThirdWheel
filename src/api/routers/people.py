"""auth, users, departments (spec 1.1–1.4, 2.4)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response

from api import auth, serializers
from api.auth import DB, Admin, CurrentUser
from api.models import Department, User
from api.schemas import contract as c
from api.services import tasks, users
from api.services.common import get_or_404

router = APIRouter()
Statuses = Annotated[list[Literal["open", "in_progress", "done", "cancelled"]] | None, Query()]


@router.post("/auth/login", response_model=c.User, tags=["auth"])
def login(body: c.LoginRequest, response: Response, db: DB):
    return serializers.user(db, auth.login(db, response, body.email, body.password))


@router.post("/auth/logout", status_code=204, tags=["auth"])
def logout(request: Request, response: Response, db: DB) -> Response:
    auth.logout(db, response, request.cookies.get(auth.COOKIE))
    response.status_code = 204
    return response


@router.get("/auth/me", response_model=c.User, tags=["auth"])
def me(user: CurrentUser, db: DB):
    return serializers.user(db, user)


@router.get("/users", response_model=list[c.User], tags=["users"])
def list_users(user: CurrentUser, db: DB, q: str | None = None, department_id: uuid.UUID | None = None,
               include_inactive: bool = False):
    return serializers.users(db, users.list_users(db, q, department_id, include_inactive))


@router.post("/users", response_model=c.User, status_code=201, tags=["users", "admin"])
def create_user(body: c.UserCreate, admin: Admin, db: DB):
    return serializers.user(db, users.create(db, admin, body))


@router.get("/users/{user_id}", response_model=c.UserProfile, tags=["users"])
def get_user(user_id: uuid.UUID, user: CurrentUser, db: DB):
    return serializers.user_profile(db, get_or_404(db, User, user_id, "User"))


@router.patch("/users/{user_id}", response_model=c.User, tags=["users"])
def update_user(user_id: uuid.UUID, body: c.UserUpdate, user: CurrentUser, db: DB):
    target = get_or_404(db, User, user_id, "User")
    return serializers.user(db, users.update(db, user, target, body))


@router.get("/users/{user_id}/tasks", response_model=list[c.Task], tags=["tasks", "users"])
def user_tasks(user_id: uuid.UUID, user: CurrentUser, db: DB, project: str | None = None, status: Statuses = None):
    return serializers.tasks(db, tasks.for_user(db, user, user_id, project, status))


@router.get("/me/subordinates", response_model=list[c.UserSummary], tags=["users"])
def my_subordinates(user: CurrentUser, db: DB):
    return [serializers.user_summary(u) for u in users.subordinates(db, user)]


@router.get("/departments", response_model=list[c.Department], tags=["departments"])
def list_departments(user: CurrentUser, db: DB):
    from sqlalchemy import select

    return serializers.departments(db, list(db.scalars(select(Department).order_by(Department.name))))


@router.post("/departments", response_model=c.Department, status_code=201, tags=["departments", "admin"])
def create_department(body: c.DepartmentWrite, admin: Admin, db: DB):
    return serializers.departments(db, [users.create_department(db, admin, body.name)])[0]


@router.get("/departments/{department_id}", response_model=c.DepartmentDetail, tags=["departments"])
def get_department(department_id: uuid.UUID, user: CurrentUser, db: DB):
    dept = get_or_404(db, Department, department_id, "Department")
    members = [serializers.user_summary(u) for u in users.department_members(db, dept)]
    return {**serializers.departments(db, [dept])[0], "members": members}


@router.patch("/departments/{department_id}", response_model=c.Department, tags=["departments", "admin"])
def update_department(department_id: uuid.UUID, body: c.DepartmentWrite, admin: Admin, db: DB):
    dept = get_or_404(db, Department, department_id, "Department")
    return serializers.departments(db, [users.rename_department(db, admin, dept, body.name)])[0]
