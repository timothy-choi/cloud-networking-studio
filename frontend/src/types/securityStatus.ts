export interface SecurityStatusResponse {
  auth_secret_configured: boolean;
  auth_secret_strong: boolean;
  cors_strict: boolean;
  api_token_scopes_enabled: boolean;
  audit_logging_enabled: boolean;
  runtime_provider_access_configured: boolean;
  auth_require_login: boolean;
  environment: string;
  warnings: string[];
}

export const API_TOKEN_SCOPES = [
  { scope: 'read:projects', label: 'Read projects, topologies, and deployments' },
  { scope: 'write:topologies', label: 'Create and edit topologies' },
  { scope: 'deploy:deployments', label: 'Deploy and destroy workloads' },
  { scope: 'runtime:operate', label: 'Terminal, exec, restart, and expose' },
  { scope: 'exports:read', label: 'Download integration outputs and exports' },
  { scope: 'admin:project', label: 'Manage project members and settings' },
] as const;
