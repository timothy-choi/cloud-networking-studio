"""Simple email templates (Step 54A)."""

from __future__ import annotations


def deployment_failed(*, topology_name: str, deployment_id: str, reason: str) -> tuple[str, str, str]:
    subject = f"Deployment failed: {topology_name}"
    text = (
        f"Your deployment for topology \"{topology_name}\" failed.\n\n"
        f"Deployment ID: {deployment_id}\n"
        f"Reason: {reason}\n"
    )
    html = (
        f"<p>Your deployment for topology <strong>{topology_name}</strong> failed.</p>"
        f"<p><strong>Deployment ID:</strong> {deployment_id}<br/>"
        f"<strong>Reason:</strong> {reason}</p>"
    )
    return subject, text, html


def deployment_succeeded(*, topology_name: str, deployment_id: str) -> tuple[str, str, str]:
    subject = f"Deployment succeeded: {topology_name}"
    text = f"Deployment for \"{topology_name}\" completed successfully.\nDeployment ID: {deployment_id}\n"
    html = (
        f"<p>Deployment for <strong>{topology_name}</strong> completed successfully.</p>"
        f"<p><strong>Deployment ID:</strong> {deployment_id}</p>"
    )
    return subject, text, html


def quota_exceeded(*, quota: str, message: str) -> tuple[str, str, str]:
    subject = f"Quota exceeded: {quota}"
    text = f"{message}\n\nQuota: {quota}\n"
    html = f"<p>{message}</p><p><strong>Quota:</strong> {quota}</p>"
    return subject, text, html


def api_token_created(*, token_name: str) -> tuple[str, str, str]:
    subject = f"API token created: {token_name}"
    text = f"A new API token \"{token_name}\" was created on your account.\n"
    html = f"<p>A new API token <strong>{token_name}</strong> was created on your account.</p>"
    return subject, text, html


def api_token_revoked(*, token_name: str) -> tuple[str, str, str]:
    subject = f"API token revoked: {token_name}"
    text = f"API token \"{token_name}\" was revoked on your account.\n"
    html = f"<p>API token <strong>{token_name}</strong> was revoked on your account.</p>"
    return subject, text, html


def project_invitation(
    *,
    project_name: str,
    inviter: str,
    role: str,
    accept_url: str,
    expires_at,
) -> tuple[str, str, str]:
    exp = expires_at.strftime("%Y-%m-%d %H:%M UTC") if hasattr(expires_at, "strftime") else str(expires_at)
    subject = f"You're invited to {project_name} on Cloud Networking Studio"
    text = (
        f"{inviter} invited you to join project \"{project_name}\" as {role}.\n\n"
        f"Accept invitation:\n{accept_url}\n\n"
        f"This link expires on {exp}.\n"
    )
    html = (
        f"<p><strong>{inviter}</strong> invited you to join project "
        f"<strong>{project_name}</strong> as <strong>{role}</strong>.</p>"
        f'<p><a href="{accept_url}">Accept invitation</a></p>'
        f"<p><small>Expires {exp}</small></p>"
    )
    return subject, text, html


def project_invitation_placeholder(*, project_name: str, inviter: str) -> tuple[str, str, str]:
    subject = f"Project invitation (preview): {project_name}"
    text = (
        f"{inviter} invited you to join project \"{project_name}\".\n"
        "Team invitations are not enabled yet — this is a placeholder template.\n"
    )
    html = (
        f"<p><strong>{inviter}</strong> invited you to join project "
        f"<strong>{project_name}</strong>.</p>"
        "<p><em>Team invitations are not enabled yet — placeholder template.</em></p>"
    )
    return subject, text, html


def cleanup_completed(*, deployment_id: str) -> tuple[str, str, str]:
    subject = "Deployment cleanup completed"
    text = f"Runtime cleanup completed for deployment {deployment_id}.\n"
    html = f"<p>Runtime cleanup completed for deployment <strong>{deployment_id}</strong>.</p>"
    return subject, text, html


def export_completed(*, export_type: str, topology_name: str) -> tuple[str, str, str]:
    subject = f"Export ready: {export_type}"
    text = f"Your {export_type} export for \"{topology_name}\" is ready.\n"
    html = f"<p>Your <strong>{export_type}</strong> export for \"{topology_name}\" is ready.</p>"
    return subject, text, html
