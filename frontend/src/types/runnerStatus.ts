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
  last_runtime_error?: string | null;
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
  last_runtime_error?: string | null;
  environment?: string;
  checked_at?: string;
  runner?: RunnerStatusDetail;
  supported_operations?: string[];
  version?: string;
  git_sha?: string;
  build_time?: string;
};
