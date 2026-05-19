import { apiFetch, getApiBase, getStoredAccessToken } from './client';

export type TerminalSessionCreateResponse = {
  session_id: string;
  deployment_id: string;
  service_id: string;
  status: string;
  websocket_path: string;
  expires_at: string;
  max_duration_seconds: number;
  idle_timeout_seconds: number;
  runtime_provider: string;
  message?: string | null;
};

export function createTerminalSession(deploymentId: string, serviceId: string) {
  return apiFetch<TerminalSessionCreateResponse>(
    `/deployments/${deploymentId}/runtime/services/${serviceId}/terminal`,
    { method: 'POST' },
  );
}

export function closeTerminalSession(sessionId: string) {
  return apiFetch<{ session_id: string; status: string; close_reason?: string | null }>(
    `/terminal-sessions/${sessionId}`,
    { method: 'DELETE' },
  );
}

export function terminalWebSocketUrl(websocketPath: string): string {
  const base = getApiBase().replace(/\/$/, '');
  const wsBase = base.replace(/^http/, 'ws');
  const path = websocketPath.startsWith('/') ? websocketPath : `/${websocketPath}`;
  const token = getStoredAccessToken();
  const q = token ? `?token=${encodeURIComponent(token)}` : '';
  return `${wsBase}${path}${q}`;
}
