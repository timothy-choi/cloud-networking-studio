import { apiFetch } from './client';
import type { TopologyResponse } from '../types/topology';

export interface RuntimeTemplateSummary {
  id: string;
  name: string;
  description: string | null;
  category: string;
  tags: string[];
  owner_user_id: string | null;
  project_id: string | null;
  visibility: string;
  source_topology_id: string | null;
  slug: string | null;
  created_at: string;
  updated_at: string;
  can_delete: boolean;
}

export interface RuntimeTemplateDetail extends RuntimeTemplateSummary {
  topology_snapshot: Record<string, unknown>;
}

export async function listTemplates(params?: {
  project_id?: string;
  category?: string;
  q?: string;
}): Promise<RuntimeTemplateSummary[]> {
  const q = new URLSearchParams();
  if (params?.project_id) q.set('project_id', params.project_id);
  if (params?.category) q.set('category', params.category);
  if (params?.q) q.set('q', params.q);
  const suffix = q.toString() ? `?${q}` : '';
  return apiFetch<RuntimeTemplateSummary[]>(`/templates${suffix}`);
}

export async function getTemplate(templateId: string): Promise<RuntimeTemplateDetail> {
  return apiFetch<RuntimeTemplateDetail>(`/templates/${templateId}`);
}

export async function createTemplateFromTopology(
  topologyId: string,
  body: {
    name: string;
    description?: string | null;
    category?: string;
    tags?: string[];
    visibility: 'private' | 'project';
  },
): Promise<RuntimeTemplateDetail> {
  return apiFetch<RuntimeTemplateDetail>(`/templates/from-topology/${topologyId}`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function cloneTemplate(
  templateId: string,
  body: { name?: string | null; project_id?: string | null },
): Promise<TopologyResponse> {
  return apiFetch<TopologyResponse>(`/templates/${templateId}/clone`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function deleteTemplate(templateId: string): Promise<void> {
  await apiFetch<void>(`/templates/${templateId}`, { method: 'DELETE' });
}
