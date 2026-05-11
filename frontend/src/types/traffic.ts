/** Traffic test records (ping / HTTP). */

export type TrafficTestType = 'ping' | 'http';

export interface TrafficTestResultResponse {
  exit_code: number;
  stdout: string;
  stderr: string;
  latency_ms: number | null;
  success: boolean;
}

export interface TrafficTestResponse {
  id: string;
  topology_id: string;
  deployment_id: string | null;
  source_node_id: string;
  target_node_id: string | null;
  test_type: TrafficTestType;
  status: string;
  command: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: (TrafficTestResultResponse & { id?: string; traffic_test_id?: string; created_at?: string }) | null;
}
