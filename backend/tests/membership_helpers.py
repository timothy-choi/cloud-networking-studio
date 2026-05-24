"""Shared helpers for invitation-based project membership in tests."""

from __future__ import annotations


def invite_and_accept(client, owner_h, project_id: str, invitee_email: str, invitee_h, role: str = "member"):
    inv = client.post(
        f"/projects/{project_id}/invitations",
        headers=owner_h,
        json={"email": invitee_email, "role": role},
    )
    assert inv.status_code == 201, inv.text
    token = inv.json()["accept_token"]
    acc = client.post(f"/invitations/{token}/accept", headers=invitee_h)
    assert acc.status_code == 200, acc.text
