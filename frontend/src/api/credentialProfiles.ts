import { apiFetch } from './client';

export type CredentialProvider = 'gcp' | 'aws' | 'azure';

export type CredentialValidationStatus = 'pending' | 'valid' | 'invalid';

export interface CredentialProfile {
  id: string;
  project_id: string;
  owner_id: string;
  name: string;
  provider: CredentialProvider;
  credential_type: string;
  metadata_json: Record<string, unknown>;
  validation_status: CredentialValidationStatus;
  validation_message: string | null;
  last_validated_at: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
  credentials_ref: string;
}

export interface CredentialProfileListResponse {
  items: CredentialProfile[];
}

export interface CredentialProfileValidateResponse {
  id: string;
  validation_status: CredentialValidationStatus;
  validation_message: string | null;
  last_validated_at: string | null;
}

export const CREDENTIAL_TYPE_BY_PROVIDER: Record<CredentialProvider, string> = {
  gcp: 'gcp_service_account_json',
  aws: 'aws_access_key',
  azure: 'azure_service_principal',
};

export function secretPlaceholder(provider: CredentialProvider): string {
  if (provider === 'gcp') {
    return '{"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}';
  }
  if (provider === 'aws') {
    return '{"access_key_id":"AKIA...","secret_access_key":"...","region":"us-east-1"}';
  }
  return '{"client_id":"...","client_secret":"...","tenant_id":"...","subscription_id":"..."}';
}

export async function listCredentialProfiles(projectId: string): Promise<CredentialProfile[]> {
  const res = await apiFetch<CredentialProfileListResponse>(
    `/projects/${projectId}/credential-profiles`,
  );
  return res.items;
}

export async function getCredentialProfile(profileId: string): Promise<CredentialProfile> {
  return apiFetch<CredentialProfile>(`/credential-profiles/${profileId}`);
}

export async function createCredentialProfile(
  projectId: string,
  body: {
    name: string;
    provider: CredentialProvider;
    credential_type: string;
    secret: string;
    metadata?: Record<string, unknown>;
  },
): Promise<CredentialProfile> {
  return apiFetch<CredentialProfile>(`/projects/${projectId}/credential-profiles`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function updateCredentialProfile(
  profileId: string,
  body: {
    name?: string;
    secret?: string;
    metadata?: Record<string, unknown>;
  },
): Promise<CredentialProfile> {
  return apiFetch<CredentialProfile>(`/credential-profiles/${profileId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteCredentialProfile(profileId: string): Promise<void> {
  await apiFetch<void>(`/credential-profiles/${profileId}`, { method: 'DELETE' });
}

export async function validateCredentialProfile(
  profileId: string,
): Promise<CredentialProfileValidateResponse> {
  return apiFetch<CredentialProfileValidateResponse>(`/credential-profiles/${profileId}/validate`, {
    method: 'POST',
  });
}
