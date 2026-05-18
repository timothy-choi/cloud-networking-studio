"""Bootstrap dev user, default project, and backfill topology.project_id after schema changes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.project import Project
from app.models.project_membership import ProjectMembership
from app.models.topology import Topology
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

DEV_USER_EMAIL = "cns-dev@localhost"
DEV_USER_DISPLAY = "Local Dev"
DEFAULT_PROJECT_NAME = "Default workspace"
# Short placeholder only (bcrypt 72-byte limit); dev user is not meant for password login.
_DEV_PLACEHOLDER_PASSWORD = "n0pe-dev"


def _ensure_owner_membership(db: Session, *, project_id, user_id) -> None:
    m = db.scalar(
        select(ProjectMembership.id).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
        )
    )
    if m is None:
        db.add(
            ProjectMembership(
                project_id=project_id,
                user_id=user_id,
                role="owner",
            )
        )


def ensure_dev_user_and_project(db: Session) -> tuple[User, Project]:
    """Guarantee the implicit dev operator and a default project exist (AUTH_REQUIRE_LOGIN=false)."""
    user = db.scalars(select(User).where(User.email == DEV_USER_EMAIL)).first()
    if user is None:
        user = User(
            email=DEV_USER_EMAIL,
            password_hash=hash_password(_DEV_PLACEHOLDER_PASSWORD),
            display_name=DEV_USER_DISPLAY,
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            # Concurrent startup (e.g. parallel pytest workers sharing one Postgres) can
            # pass the initial SELECT before another process inserts the same dev email.
            db.rollback()
            user = db.scalars(select(User).where(User.email == DEV_USER_EMAIL)).first()
            if user is None:
                raise

    proj = db.scalars(
        select(Project)
        .where(Project.owner_user_id == user.id, Project.name == DEFAULT_PROJECT_NAME)
        .limit(1)
    ).first()
    if proj is None:
        proj = Project(
            owner_user_id=user.id,
            name=DEFAULT_PROJECT_NAME,
            description="Auto-created for local single-user flows.",
        )
        db.add(proj)
        db.flush()

    _ensure_owner_membership(db, project_id=proj.id, user_id=user.id)

    db.commit()
    db.refresh(user)
    db.refresh(proj)
    return user, proj


def get_or_create_dev_user(db: Session) -> User:
    """Return the implicit dev user (creates row + default project if missing)."""
    user, _ = ensure_dev_user_and_project(db)
    return user


def run_startup_datafixes(engine: Engine) -> None:
    """Backfill topology.project_id and project owner memberships."""
    from app.db.seed_runtime_templates import ensure_starter_runtime_templates

    with Session(engine) as db:
        _, proj = ensure_dev_user_and_project(db)
        db.execute(
            update(Topology)
            .where(Topology.project_id.is_(None))
            .values(project_id=proj.id)
        )
        for row in db.scalars(select(Project)).all():
            _ensure_owner_membership(db, project_id=row.id, user_id=row.owner_user_id)
        db.commit()
        ensure_starter_runtime_templates(db)
