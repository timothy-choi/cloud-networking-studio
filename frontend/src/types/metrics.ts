import type { DeploymentEventLevel } from './deployment';

export interface MetricsLatestEvent {
  id: string;
  source: 'deployment_event';
  topology_id: string;
  deployment_id: string;
  level: DeploymentEventLevel;
  message: string;
  created_at: string;
}

export interface MetricsSummaryResponse {
  total_topologies: number;
  total_deployments: number;
  active_deployments: number;
  failed_deployments: number;
  total_traffic_tests: number;
  failed_traffic_tests: number;
  total_failure_injections: number;
  failed_failure_injections: number;
  latest_events: MetricsLatestEvent[];
}
