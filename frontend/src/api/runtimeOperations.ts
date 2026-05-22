import { apiFetch } from './client';

export interface RuntimeOperationsLogsPayload {
  deployment_id: string;
  service_id?: string | null;
  logs: string;
  items: unknown[];
  runtime_provider: string;
}

export interface RuntimeOperationsHealthPayload {
  status: string;
  target: string;
  latency_ms?: number | null;
  message: string;
}

export interface RuntimeOperationsTrafficPayload {
  status: string;
  source: string;
  target: string;
  protocol: string;
  output: string;
  latency_ms?: number | null;
}

export async function fetchRuntimeDeploymentLogs(
  deploymentId: string,
  tail = 100,
): Promise<RuntimeOperationsLogsPayload> {
  const q = new URLSearchParams({ tail: String(tail) });
  return apiFetch<RuntimeOperationsLogsPayload>(`/deployments/${deploymentId}/runtime/logs?${q}`);
}

export async function fetchRuntimeServiceLogs(
  deploymentId: string,
  runtimeServiceResourceId: string,
  tail = 100,
): Promise<RuntimeOperationsLogsPayload> {
  const q = new URLSearchParams({ tail: String(tail) });
  return apiFetch<RuntimeOperationsLogsPayload>(
    `/deployments/${deploymentId}/runtime/services/${runtimeServiceResourceId}/logs?${q}`,
  );
}

export async function postRuntimeServiceHealth(
  deploymentId: string,
  runtimeServiceResourceId: string,
): Promise<RuntimeOperationsHealthPayload> {
  return apiFetch<RuntimeOperationsHealthPayload>(
    `/deployments/${deploymentId}/runtime/services/${runtimeServiceResourceId}/health-check`,
    { method: 'POST', body: '{}' },
  );
}

export type TrafficProtocol = 'http' | 'ping' | 'tcp' | 'dns' | 'command';

export async function postRuntimeTrafficTest(
  deploymentId: string,
  body: {
    source_runtime_resource_id: string;
    target: string;
    protocol: TrafficProtocol;
    port?: number;
    path?: string;
    command?: string[];
  },
): Promise<RuntimeOperationsTrafficPayload> {
  return apiFetch<RuntimeOperationsTrafficPayload>(
    `/deployments/${deploymentId}/runtime/traffic-tests`,
    { method: 'POST', body: JSON.stringify(body) },
  );
}
