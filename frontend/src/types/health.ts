/** API health and controller status. */

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}

export interface ControllerStatusResponse {
  controller_mode: string;
  managed_deployments_count: number;
  active_deployments_count: number;
  supported_providers: string[];
  last_run_timestamp: string | null;
  health_summary: string;
}
