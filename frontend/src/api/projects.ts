import { apiFetch } from './client';

export interface ProjectResponse {
  id: string;
  owner_user_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export async function listProjects(): Promise<ProjectResponse[]> {
  return apiFetch<ProjectResponse[]>('/projects');
}

export async function createProject(body: {
  name: string;
  description?: string | null;
}): Promise<ProjectResponse> {
  return apiFetch<ProjectResponse>('/projects', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
