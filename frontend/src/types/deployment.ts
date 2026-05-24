/** Deployment runs and lifecycle returned by deploy/destroy APIs. */

export type DeploymentStatus =
  | 'pending'
  | 'deploying'
  | 'succeeded'
  | 'failed'
  | 'stopping'
  | 'stopped';

export type DeploymentEventLevel = 'debug' | 'info' | 'warning' | 'error';

export interface DeploymentEventResponse {
  id: string;
  deployment_id: string;
  level: DeploymentEventLevel;
  message: string;
  created_at: string;
}

export interface DeploymentResponse {
  id: string;
  topology_id: string;
  status: DeploymentStatus;
  runtime_target: string;
  topology_version_id?: string | null;
  deployment_profile_id?: string | null;
  effective_config_json?: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  events: DeploymentEventResponse[];
}
