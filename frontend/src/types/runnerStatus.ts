export type LastRuntimeErrorDetail = {
  operation: string;
  message: string;
  request_id?: string | null;
  status_code?: number | null;
  timestamp: string;
  historical?: boolean;
};

export type RunnerStatusDetail = {
  runner_reachable: boolean;
  runtime_executor: string;
  runner_status?: string | null;
  status?: string | null;
  runtime_provider?: string | null;
  docker_reachable?: boolean | null;
  kubernetes_reachable?: boolean | null;
  current_context?: string | null;
  version?: string | null;
  git_sha?: string | null;
  build_time?: string | null;
  supported_operations?: string[];
  last_runtime_error?: LastRuntimeErrorDetail | null;
  message?: string | null;
  checked_at?: string;
};

export type RunnerOperationRecord = {
  operation: string;
  provider: string;
  status: string;
  duration_ms: number;
  request_id?: string | null;
  deployment_id?: string | null;
  topology_id?: string | null;
  error_message?: string | null;
  status_code?: number | null;
  created_at: string;
};

export type RecentRunnerOperationsResponse = {
  operations: RunnerOperationRecord[];
  count: number;
};

export type RuntimeStatusResponse = {
  backend_status?: string;
  status?: string;
  runtime_executor?: string;
  runtime_provider?: string;
  runner_reachable?: boolean;
  docker_reachable?: boolean;
  kubernetes_reachable?: boolean;
  current_context?: string;
  kubeconfig_source?: string;
  kubernetes_init_error?: string;
  message?: string;
  last_runtime_error?: LastRuntimeErrorDetail | null;
  environment?: string;
  checked_at?: string;
  runner?: RunnerStatusDetail;
  supported_operations?: string[];
  version?: string;
  git_sha?: string;
  build_time?: string;
};

export function formatLastRuntimeError(detail: LastRuntimeErrorDetail | null | undefined): string | null {
  if (!detail?.operation) return null;
  const parts = [`Last failed operation: ${detail.operation}`];
  if (detail.status_code != null) {
    parts.push(`returned ${detail.status_code}`);
  }
  if (detail.message) {
    parts.push(`— ${detail.message}`);
  }
  if (detail.request_id) {
    parts.push(`— request_id ${detail.request_id}`);
  }
  if (detail.timestamp) {
    parts.push(`(${new Date(detail.timestamp).toLocaleString()})`);
  }
  if (detail.historical) {
    parts.push('(historical)');
  }
  return parts.join(' ');
}

export function pickActiveRuntimeError(
  runnerStatus: RunnerStatusDetail | null | undefined,
  runtimeStatus: RuntimeStatusResponse | null | undefined,
): LastRuntimeErrorDetail | null {
  const candidates = [
    runnerStatus?.last_runtime_error,
    runtimeStatus?.last_runtime_error,
    runtimeStatus?.runner?.last_runtime_error,
  ];
  for (const err of candidates) {
    if (err && !err.historical) {
      return err;
    }
  }
  return null;
}
