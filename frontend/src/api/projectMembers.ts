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

export async function listProjectMembers(projectId: string): Promise<ProjectMemberResponse[]> {
  return apiFetch<ProjectMemberResponse[]>(`/projects/${projectId}/members`);
}

export async function inviteProjectMember(
  projectId: string,
  body: { email: string; role: 'member' | 'viewer' },
): Promise<ProjectMemberResponse> {
  return apiFetch<ProjectMemberResponse>(`/projects/${projectId}/members/invite`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
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

export async function removeProjectMember(projectId: string, memberId: string): Promise<void> {
  await apiFetch<void>(`/projects/${projectId}/members/${memberId}`, { method: 'DELETE' });
}
