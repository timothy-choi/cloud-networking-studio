import { apiFetch } from './client';

export interface ApiTokenRow {
  id: string;
  name: string;
  token_hint: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiTokenCreated extends ApiTokenRow {
  token: string;
}

export async function listApiTokens(): Promise<ApiTokenRow[]> {
  return apiFetch<ApiTokenRow[]>('/api-tokens');
}

export async function createApiToken(body: { name: string }): Promise<ApiTokenCreated> {
  return apiFetch<ApiTokenCreated>('/api-tokens', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function revokeApiToken(tokenId: string): Promise<void> {
  await apiFetch<void>(`/api-tokens/${tokenId}`, { method: 'DELETE' });
}
