"""Notifications and email (Step 54A)."""

from __future__ import annotations

import uuid

from app.services.notification_service import (
    create_notification,
    notify_user,
)
from app.services.email_service import ConsoleEmailProvider, get_email_provider, send_email
from app.core.config import Settings


def _reg(client_strict, prefix: str) -> tuple[dict[str, str], str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "N"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    pid = client_strict.get("/projects", headers=h).json()[0]["id"]
    return h, pid


def test_create_and_list_own_notifications(client_strict, engine_db):
    from app.db.session import SessionLocal

    h, _ = _reg(client_strict, "n1")
    uid = uuid.UUID(client_strict.get("/auth/me", headers=h).json()["user"]["id"])
    with SessionLocal() as db:
        notify_user(
            db,
            uid,
            type="test.info",
            title="Hello",
            message="World",
            severity="info",
        )
        db.commit()

    lst = client_strict.get("/notifications", headers=h)
    assert lst.status_code == 200
    body = lst.json()
    assert len(body) >= 1
    assert body[0]["title"] == "Hello"
    assert body[0]["status"] == "unread"


def test_unread_count_and_mark_read(client_strict, engine_db):
    from app.db.session import SessionLocal

    h, _ = _reg(client_strict, "n2")
    uid = uuid.UUID(client_strict.get("/auth/me", headers=h).json()["user"]["id"])
    with SessionLocal() as db:
        row = notify_user(db, uid, type="t", title="A", message="B")
        db.commit()
        nid = row.id

    c = client_strict.get("/notifications/unread-count", headers=h)
    assert c.status_code == 200
    assert c.json()["unread_count"] >= 1

    r = client_strict.post(f"/notifications/{nid}/read", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "read"

    c2 = client_strict.get("/notifications/unread-count", headers=h)
    assert c2.json()["unread_count"] == 0


def test_mark_all_read_and_archive(client_strict, engine_db):
    from app.db.session import SessionLocal

    h, _ = _reg(client_strict, "n3")
    uid = uuid.UUID(client_strict.get("/auth/me", headers=h).json()["user"]["id"])
    with SessionLocal() as db:
        n1 = notify_user(db, uid, type="t", title="1", message="a")
        n2 = notify_user(db, uid, type="t", title="2", message="b")
        n1_id = n1.id
        db.commit()

    all_read = client_strict.post("/notifications/read-all", headers=h)
    assert all_read.status_code == 200
    assert all_read.json()["marked_read"] >= 2

    ar = client_strict.post(f"/notifications/{n1_id}/archive", headers=h)
    assert ar.status_code == 200
    assert ar.json()["status"] == "archived"


def test_cannot_see_other_users_notifications(client_strict, engine_db):
    from app.db.session import SessionLocal

    ha, _ = _reg(client_strict, "na")
    hb, _ = _reg(client_strict, "nb")
    uid_a = uuid.UUID(client_strict.get("/auth/me", headers=ha).json()["user"]["id"])
    with SessionLocal() as db:
        row = notify_user(db, uid_a, type="private", title="Secret", message="x")
        db.commit()
        nid = row.id

    assert client_strict.post(f"/notifications/{nid}/read", headers=hb).status_code == 404
    lst_b = client_strict.get("/notifications", headers=hb).json()
    assert all(x["title"] != "Secret" for x in lst_b)


def test_project_broadcast_visible_to_members(client_strict, engine_db):
    from app.db.session import SessionLocal
    from app.models.project_membership import ProjectMembership

    ha, pid = _reg(client_strict, "pm")
    hb, _ = _reg(client_strict, "pm2")
    member_id = uuid.UUID(client_strict.get("/auth/me", headers=hb).json()["user"]["id"])
    with SessionLocal() as db:
        db.add(
            ProjectMembership(project_id=uuid.UUID(pid), user_id=member_id, role="viewer")
        )
        create_notification(
            db,
            user_id=None,
            project_id=uuid.UUID(pid),
            type="project.broadcast",
            title="Team note",
            message="For project members",
        )
        db.commit()

    lst = client_strict.get("/notifications", headers=hb)
    assert any(x["title"] == "Team note" for x in lst.json())


def test_console_email_provider(monkeypatch):
    from app.services import email_service as email_svc

    messages: list[str] = []

    def capture_info(msg, *args, **kwargs):
        messages.append(msg % args if args else str(msg))

    monkeypatch.setattr(email_svc._log, "info", capture_info)

    ok = ConsoleEmailProvider().send(
        to_email="user@example.com",
        subject="Test",
        body_text="Hello",
    )
    assert ok is True
    assert any("console email" in m for m in messages)


def test_smtp_disabled_does_not_crash(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "disabled")
    s = Settings()
    assert get_email_provider(s).send(
        to_email="a@b.com", subject="s", body_text="t"
    ) is False


def test_email_failure_does_not_break_notification(client_strict, engine_db, monkeypatch):
    from app.db.session import SessionLocal

    def boom(*args, **kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(
        "app.services.notification_service.send_email",
        boom,
    )
    h, _ = _reg(client_strict, "em")
    uid = uuid.UUID(client_strict.get("/auth/me", headers=h).json()["user"]["id"])
    with SessionLocal() as db:
        notify_user(
            db,
            uid,
            type="t",
            title="Still ok",
            message="m",
            send_email=True,
            email_subject="s",
            email_text="t",
        )
        db.commit()
    lst = client_strict.get("/notifications", headers=h)
    assert lst.status_code == 200
    assert any(x["title"] == "Still ok" for x in lst.json())


def test_api_token_create_emits_notification(client_strict):
    h, _ = _reg(client_strict, "tokn")
    cr = client_strict.post("/api-tokens", headers=h, json={"name": "ci-notify"})
    assert cr.status_code == 201
    lst = client_strict.get("/notifications", headers=h)
    assert any("API token" in x["title"] for x in lst.json())
