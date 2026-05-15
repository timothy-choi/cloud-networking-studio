import { apiFetch, setStoredAccessToken } from './client';
import type { UserPublic } from '../types/auth';

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserPublic;
}

export interface MeResponse {
  user: UserPublic;
}

export async function registerUser(body: {
  email: string;
  password: string;
  display_name: string;
}): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function loginUser(body: { email: string; password: string }): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function fetchMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>('/auth/me');
}

export async function logoutApi(): Promise<void> {
  try {
    await apiFetch('/auth/logout', { method: 'POST' });
  } finally {
    setStoredAccessToken(null);
  }
}
