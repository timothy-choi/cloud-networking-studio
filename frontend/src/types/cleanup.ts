export interface DeploymentCleanupStatusResponse {
  deployment_id: string;
  status: string;
  eligible_for_cleanup: boolean;
  reasons: string[];
  runtime_resources_count: number;
  stale_terminal_sessions: number;
  expires_at: string | null;
  expired: boolean;
  deployment_ttl_hours: number;
  last_cleanup_at: string | null;
  topology_id: string | null;
  project_id: string | null;
}

export interface DeploymentCleanupResponse {
  ok: boolean;
  deployment_id: string;
  events: Array<{ message: string }>;
}
