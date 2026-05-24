import { apiFetch } from './client';

export type ProjectMemberRole = 'owner' | 'member' | 'viewer';

export interface ProjectMemberResponse {
  id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: ProjectMemberRole;
  created_at: string;
}

export type InvitationStatus = 'pending' | 'accepted' | 'declined' | 'expired' | 'revoked';

export interface ProjectInvitationResponse {
  id: string;
  project_id: string;
  email: string;
  role: 'member' | 'viewer';
  status: InvitationStatus;
  invited_by_user_id: string;
  accepted_by_user_id: string | null;
  expires_at: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectInvitationCreatedResponse extends ProjectInvitationResponse {
  accept_token: string;
}

export async function listProjectMembers(projectId: string): Promise<ProjectMemberResponse[]> {
  return apiFetch<ProjectMemberResponse[]>(`/projects/${projectId}/members`);
}

export async function listProjectInvitations(projectId: string): Promise<ProjectInvitationResponse[]> {
  return apiFetch<ProjectInvitationResponse[]>(`/projects/${projectId}/invitations`);
}

export async function createProjectInvitation(
  projectId: string,
  body: { email: string; role: 'member' | 'viewer' },
): Promise<ProjectInvitationCreatedResponse> {
  return apiFetch<ProjectInvitationCreatedResponse>(`/projects/${projectId}/invitations`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function revokeProjectInvitation(
  projectId: string,
  invitationId: string,
): Promise<ProjectInvitationResponse> {
  return apiFetch<ProjectInvitationResponse>(
    `/projects/${projectId}/invitations/${invitationId}/revoke`,
    { method: 'POST' },
  );
}

export async function acceptInvitation(token: string): Promise<{ status: string; message: string; project_id?: string }> {
  return apiFetch(`/invitations/${encodeURIComponent(token)}/accept`, { method: 'POST' });
}

export async function declineInvitation(token: string): Promise<{ status: string; message: string }> {
  return apiFetch(`/invitations/${encodeURIComponent(token)}/decline`, { method: 'POST' });
}

export async function patchProjectMemberRole(
  projectId: string,
  memberId: string,
  body: { role: ProjectMemberRole },
): Promise<ProjectMemberResponse> {
  return apiFetch<ProjectMemberResponse>(`/projects/${projectId}/members/${memberId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function transferProjectOwnership(
  projectId: string,
  memberId: string,
): Promise<ProjectMemberResponse> {
  return apiFetch<ProjectMemberResponse>(
    `/projects/${projectId}/members/${memberId}/transfer-ownership`,
    { method: 'POST' },
  );
}

export async function removeProjectMember(projectId: string, memberId: string): Promise<void> {
  await apiFetch<void>(`/projects/${projectId}/members/${memberId}`, { method: 'DELETE' });
}

/** @deprecated Use createProjectInvitation */
export async function inviteProjectMember(
  projectId: string,
  body: { email: string; role: 'member' | 'viewer' },
): Promise<ProjectInvitationCreatedResponse> {
  return createProjectInvitation(projectId, body);
}
