import { apiFetch } from './client';
import type {
  RecentRunnerOperationsResponse,
  RunnerStatusDetail,
  RuntimeStatusResponse,
} from '../types/runnerStatus';

export function getRuntimeStatus(): Promise<RuntimeStatusResponse> {
  return apiFetch<RuntimeStatusResponse>('/runtime/status');
}

export function getRunnerStatus(): Promise<RunnerStatusDetail> {
  return apiFetch<RunnerStatusDetail>('/runtime/runner-status');
}

export function getRecentRunnerOperations(limit = 20): Promise<RecentRunnerOperationsResponse> {
  return apiFetch<RecentRunnerOperationsResponse>(`/runtime/operations/recent?limit=${limit}`);
}
