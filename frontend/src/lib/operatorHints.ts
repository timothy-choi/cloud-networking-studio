import { ApiError } from '../api/client';

export interface OperatorErrorPresentation {
  /** Human-readable primary message */
  headline: string;
  /** Optional short next step */
  suggestion: string | null;
  /** Raw detail for expandable JSON/text */
  raw: string;
}

function stringifyDetail(detail: unknown): string {
  if (detail == null) return '';
  if (typeof detail === 'string') return detail;
  try {
    return JSON.stringify(detail, null, 2);
  } catch {
    return String(detail);
  }
}

function extractFastApiDetail(detail: unknown): string | null {
  if (detail == null) return null;
  if (typeof detail === 'object' && detail !== null && 'detail' in detail) {
    const inner = (detail as { detail: unknown }).detail;
    if (typeof inner === 'string') return inner;
    if (Array.isArray(inner)) {
      return inner.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join('; ');
    }
    if (inner != null) return stringifyDetail(inner);
  }
  if (typeof detail === 'string') return detail;
  return null;
}

function suggestionForText(status: number, text: string): string | null {
  const t = text.toLowerCase();
  if (status === 409 || /active deployment already exists|destroy it before/.test(t)) {
    return 'Open Runtime actions → Destroy deployment, wait until status is stopped, then deploy again.';
  }
  if (status === 400 && /validation failed/.test(t)) {
    return 'Fix topology validation issues (nodes, links, addressing), save, then retry deploy.';
  }
  if (status === 404) {
    return 'Refresh the page — the topology or deployment may have been removed.';
  }
  if (status === 500 && /docker|container|image/.test(t)) {
    return 'Check Docker daemon on the API host, disk space, and image pulls; review deployment events for the exact provider error.';
  }
  if (/traffic|ping|http/.test(t) && /failed|error|non-zero/.test(t)) {
    return 'Confirm the deployment succeeded and routes exist between source and target nodes; run reconcile then retry the traffic test.';
  }
  return null;
}

/** Turn API errors into operator-friendly copy with optional remediation hint. */
export function formatOperatorError(err: unknown): OperatorErrorPresentation {
  if (err instanceof ApiError) {
    const parsed = extractFastApiDetail(err.detail) ?? err.message;
    const suggestion = suggestionForText(err.status, parsed);
    return {
      headline: parsed || err.message,
      suggestion,
      raw: stringifyDetail(err.detail) || err.message,
    };
  }
  if (err instanceof Error) {
    return { headline: err.message, suggestion: null, raw: err.stack ?? err.message };
  }
  return { headline: String(err), suggestion: null, raw: String(err) };
}
