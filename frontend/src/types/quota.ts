export interface ProjectQuotaResponse {
  project_id: string;
  limits: {
    max_active_deployments_per_project: number;
    max_nodes_per_topology: number;
    max_services_per_deployment: number;
    max_terminal_sessions_per_user: number;
    max_api_tokens_per_user: number;
  };
  usage: {
    active_deployments: number;
    terminal_sessions: number;
    api_tokens: number;
  };
  remaining: {
    active_deployments: number;
    terminal_sessions: number;
    api_tokens: number;
  };
}
