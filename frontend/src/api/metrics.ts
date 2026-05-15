import { apiFetch } from './client';
import type { MetricsSummaryResponse } from '../types/metrics';

export async function getMetricsSummary(): Promise<MetricsSummaryResponse> {
  return apiFetch<MetricsSummaryResponse>('/metrics/summary');
}
