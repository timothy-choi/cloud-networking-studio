/** Platform observability metrics (Step 53C). */

export interface RuntimeProviderStatusMetrics {
  status: string;
  runtime_executor: string;
  runtime_provider?: string | null;
  runner_reachable?: boolean | null;
  docker_reachable?: boolean | null;
  kubernetes_reachable?: boolean | null;
  message?: string | null;
}

export interface QuotaUsageMetrics {
  active_deployments: number;
  terminal_sessions: number;
  api_tokens: number;
  limits: Record<string, number>;
}

export interface ApiRequestMetrics {
  total_requests: number;
  by_status: Record<string, number>;
}

export interface FailedOperationMetrics {
  action: string;
  resource_type: string;
  resource_id: string | null;
  status: string;
  message: string | null;
  request_id: string | null;
  created_at: string;
}

export interface CleanupStatusMetrics {
  eligible_deployments: number;
  deployments_with_runtime_resources: number;
  stale_terminal_sessions: number;
}

export interface DeploymentDurationMetrics {
  average_deploy_duration_seconds: number | null;
  sample_count: number;
}

export interface PlatformMetricsResponse {
  scope: string;
  active_deployments: number;
  deployment_success_count: number;
  deployment_failure_count: number;
  deploy_duration: DeploymentDurationMetrics;
  active_terminal_sessions: number;
  runtime_provider_status: RuntimeProviderStatusMetrics;
  quota_usage: QuotaUsageMetrics;
  recent_failed_operations: FailedOperationMetrics[];
  cleanup_status: CleanupStatusMetrics;
  api_requests: ApiRequestMetrics;
}

export interface ProjectMetricsResponse {
  scope: string;
  project_id: string;
  active_deployments: number;
  deployment_success_count: number;
  deployment_failure_count: number;
  deploy_duration: DeploymentDurationMetrics;
  active_terminal_sessions: number;
  quota_usage: QuotaUsageMetrics;
  recent_failed_operations: FailedOperationMetrics[];
  cleanup_status: CleanupStatusMetrics;
}

export interface DeploymentMetricsResponse {
  scope: string;
  deployment_id: string;
  topology_id: string;
  project_id: string | null;
  status: string;
  deploy_duration_seconds: number | null;
  runtime_resources_count: number;
  active_terminal_sessions: number;
  cleanup_status: CleanupStatusMetrics;
  recent_failed_operations: FailedOperationMetrics[];
}
