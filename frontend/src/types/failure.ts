/** Failure injection records. */

export type FailureInjectionFailureType = 'stop_container' | 'restart_container' | 'kill_container';

export type FailureInjectionStatus = 'pending' | 'running' | 'succeeded' | 'failed';

export interface FailureInjectionResponse {
  id: string;
  topology_id: string;
  deployment_id: string | null;
  target_node_id: string;
  failure_type: FailureInjectionFailureType;
  status: FailureInjectionStatus;
  description: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result_message: string | null;
}
