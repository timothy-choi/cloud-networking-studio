import { apiFetch } from './client';

export interface RuntimeExecResultPayload {
  id: string;
  deployment_id: string;
  service_id: string | null;
  command: string;
  status: string;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  started_at: string | null;
  finished_at: string | null;
  runtime_provider: string;
  message?: string | null;
}

export interface RuntimeExecResultListPayload {
  deployment_id: string;
  items: RuntimeExecResultPayload[];
}

export interface RuntimeRestartPayload {
  status: string;
  message: string;
  runtime_provider: string;
}

export async function postRuntimeServiceExec(
  deploymentId: string,
  runtimeServiceResourceId: string,
  body: { command: string; timeout_seconds?: number },
): Promise<RuntimeExecResultPayload> {
  return apiFetch<RuntimeExecResultPayload>(
    `/deployments/${deploymentId}/runtime/services/${runtimeServiceResourceId}/exec`,
    {
      method: 'POST',
      body: JSON.stringify({
        command: body.command,
        timeout_seconds: body.timeout_seconds ?? 10,
      }),
    },
  );
}

export async function fetchRuntimeExecResults(
  deploymentId: string,
  limit = 50,
): Promise<RuntimeExecResultListPayload> {
  const q = new URLSearchParams({ limit: String(limit) });
  return apiFetch<RuntimeExecResultListPayload>(
    `/deployments/${deploymentId}/runtime/exec-results?${q}`,
  );
}

export async function fetchRuntimeExecResult(
  deploymentId: string,
  execResultId: string,
): Promise<RuntimeExecResultPayload> {
  return apiFetch<RuntimeExecResultPayload>(
    `/deployments/${deploymentId}/runtime/exec-results/${execResultId}`,
  );
}

export async function postRuntimeServiceRestart(
  deploymentId: string,
  runtimeServiceResourceId: string,
): Promise<RuntimeRestartPayload> {
  return apiFetch<RuntimeRestartPayload>(
    `/deployments/${deploymentId}/runtime/services/${runtimeServiceResourceId}/restart`,
    { method: 'POST' },
  );
}
