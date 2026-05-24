"""Project invitations and collaboration hardening (Step 54B)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.topology import NodeType


def _register(client, prefix: str = "u") -> tuple[str, str, dict[str, str], str]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    user_id = client.get("/auth/me", headers=headers).json()["user"]["id"]
    return email, tok, headers, user_id


def _invite(client, owner_h, pid, email, role="member"):
    return client.post(
        f"/projects/{pid}/invitations",
        headers=owner_h,
        json={"email": email, "role": role},
    )


def _invite_and_accept(client, owner_h, pid, invitee_email, invitee_h, role="member"):
    inv = _invite(client, owner_h, pid, invitee_email, role)
    assert inv.status_code == 201, inv.text
    token = inv.json()["accept_token"]
    acc = client.post(f"/invitations/{token}/accept", headers=invitee_h)
    assert acc.status_code == 200, acc.text
    return inv.json(), acc.json()


def test_invite_existing_user_and_accept(client_strict, monkeypatch):
    captured: list[dict[str, str]] = []

    def fake_send(settings, *, to_email, subject, body_text, body_html=None):
        captured.append({"to": to_email, "body": body_text})
        return True

    monkeypatch.setattr("app.services.project_invitation_service.send_email", fake_send)
    _, _, ha, _ = _register(client_strict, "ie")
    eb, _, hb, _ = _register(client_strict, "ib")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    inv, _ = _invite_and_accept(client_strict, ha, pid, eb, hb, "member")
    assert inv["status"] == "pending" or inv["email"] == eb
    assert captured
    assert captured[0]["to"] == eb
    assert "Accept invitation" in captured[0]["body"]
    assert client_strict.get(f"/projects/{pid}", headers=hb).status_code == 200


def test_invite_non_existing_email(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, _ = _register(client_strict, "ne")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    ghost = f"ghost-{uuid.uuid4().hex[:6]}@example.com"
    inv = _invite(client_strict, ha, pid, ghost)
    assert inv.status_code == 201, inv.text
    assert inv.json()["email"] == ghost
    lst = client_strict.get(f"/projects/{pid}/invitations", headers=ha)
    assert lst.status_code == 200
    assert any(x["email"] == ghost and x["status"] == "pending" for x in lst.json())


def test_invite_existing_user_creates_notification(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, _ = _register(client_strict, "nt")
    eb, _, hb, _ = _register(client_strict, "nu")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert _invite(client_strict, ha, pid, eb).status_code == 201
    notes = client_strict.get("/notifications", headers=hb)
    assert notes.status_code == 200
    assert any(n.get("type") == "project.invitation" for n in notes.json())


def test_duplicate_pending_invite_blocked(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, _ = _register(client_strict, "dp")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    em = f"dup-{uuid.uuid4().hex[:6]}@example.com"
    assert _invite(client_strict, ha, pid, em).status_code == 201
    dup = _invite(client_strict, ha, pid, em)
    assert dup.status_code == 409


def test_decline_invite(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, _ = _register(client_strict, "de")
    eb, _, hb, _ = _register(client_strict, "df")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    inv = _invite(client_strict, ha, pid, eb).json()
    token = inv["accept_token"]
    dec = client_strict.post(f"/invitations/{token}/decline", headers=hb)
    assert dec.status_code == 200
    lst = client_strict.get(f"/projects/{pid}/invitations", headers=ha).json()
    assert any(x["id"] == inv["id"] and x["status"] == "declined" for x in lst)


def test_revoke_invite(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, _ = _register(client_strict, "rv")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    em = f"rev-{uuid.uuid4().hex[:6]}@example.com"
    inv = _invite(client_strict, ha, pid, em).json()
    rv = client_strict.post(
        f"/projects/{pid}/invitations/{inv['id']}/revoke",
        headers=ha,
    )
    assert rv.status_code == 200
    assert rv.json()["status"] == "revoked"


def test_expired_invite_rejected(client_strict, engine_db, monkeypatch):
    from app.db.session import SessionLocal
    from app.models.project_invitation import ProjectInvitation
    from app.core.security import hash_api_token_secret
    import secrets

    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, owner_id = _register(client_strict, "ex")
    eb, _, hb, invitee_id = _register(client_strict, "ey")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    secret = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        row = ProjectInvitation(
            project_id=uuid.UUID(pid),
            email=eb,
            role="viewer",
            token_hash=hash_api_token_secret(secret),
            status="pending",
            invited_by_user_id=uuid.UUID(owner_id),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        db.add(row)
        db.commit()
        iid = row.id
    token = f"{iid}.{secret}"
    r = client_strict.post(f"/invitations/{token}/accept", headers=hb)
    assert r.status_code == 400
    assert "expired" in r.json()["detail"].lower()


def test_ownership_transfer(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, _ = _register(client_strict, "ot")
    eb, _, hb, _ = _register(client_strict, "om")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    _invite_and_accept(client_strict, ha, pid, eb, hb, "member")
    members = client_strict.get(f"/projects/{pid}/members", headers=ha).json()
    mid = next(m["id"] for m in members if m["email"] == eb)
    tr = client_strict.post(f"/projects/{pid}/members/{mid}/transfer-ownership", headers=ha)
    assert tr.status_code == 200, tr.text
    assert tr.json()["role"] == "owner"
    proj = client_strict.get(f"/projects/{pid}", headers=hb).json()
    assert proj["my_role"] == "owner"


def test_last_owner_cannot_be_removed_or_demoted(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, uid = _register(client_strict, "lo")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    members = client_strict.get(f"/projects/{pid}/members", headers=ha).json()
    mid = next(m["id"] for m in members if m["user_id"] == uid)
    rm = client_strict.delete(f"/projects/{pid}/members/{mid}", headers=ha)
    assert rm.status_code == 400
    dem = client_strict.patch(
        f"/projects/{pid}/members/{mid}",
        headers=ha,
        json={"role": "member"},
    )
    assert dem.status_code == 400


def test_viewer_member_owner_permissions(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, _ = _register(client_strict, "pm")
    ev, _, hv, _ = _register(client_strict, "pv")
    em, _, hm, _ = _register(client_strict, "pmm")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    _invite_and_accept(client_strict, ha, pid, ev, hv, "viewer")
    _invite_and_accept(client_strict, ha, pid, em, hm, "member")

    assert (
        client_strict.post(
            "/topologies",
            headers=hv,
            json={
                "name": "blocked",
                "project_id": pid,
                "runtime_target": "docker",
                "networking_mode": "docker_bridge",
            },
        ).status_code
        == 403
    )
    assert (
        client_strict.post(
            "/topologies",
            headers=hm,
            json={
                "name": "ok",
                "project_id": pid,
                "runtime_target": "docker",
                "networking_mode": "docker_bridge",
            },
        ).status_code
        == 201
    )
    assert client_strict.delete(f"/projects/{pid}", headers=hm).status_code == 403


def test_invite_creates_audit_log(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, _ = _register(client_strict, "au")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    em = f"audit-{uuid.uuid4().hex[:6]}@example.com"
    assert _invite(client_strict, ha, pid, em).status_code == 201
    logs = client_strict.get(f"/projects/{pid}/audit-logs", headers=ha)
    assert logs.status_code == 200
    assert any(x.get("action") == "project.invite.sent" for x in logs.json()["items"])


def test_list_invitations_never_exposes_token_hash(client_strict, monkeypatch):
    monkeypatch.setattr(
        "app.services.project_invitation_service.send_email",
        lambda *a, **k: True,
    )
    _, _, ha, _ = _register(client_strict, "sec")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    inv = _invite(client_strict, ha, pid, f"sec-{uuid.uuid4().hex[:6]}@example.com").json()
    lst = client_strict.get(f"/projects/{pid}/invitations", headers=ha).json()
    blob = str(lst)
    assert "token_hash" not in blob
    assert inv["accept_token"] not in blob
