import { apiFetch } from './client';
import type { SecurityStatusResponse } from '../types/securityStatus';

export async function getSecurityStatus(): Promise<SecurityStatusResponse> {
  return apiFetch<SecurityStatusResponse>('/platform/security-status');
}
