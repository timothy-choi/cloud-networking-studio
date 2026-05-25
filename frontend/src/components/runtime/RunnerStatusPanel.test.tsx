import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { RunnerStatusContent, RunnerStatusPanel } from './RunnerStatusPanel';
import { formatLastRuntimeError, pickActiveRuntimeError } from '../../types/runnerStatus';

describe('RunnerStatusPanel', () => {
  it('renders loading shell', () => {
    const html = renderToStaticMarkup(<RunnerStatusPanel />);
    expect(html).toContain('Loading runtime provider status');
  });

  it('renders runner details when reachable', () => {
    const html = renderToStaticMarkup(
      <RunnerStatusContent
        runtimeStatus={{ backend_status: 'ok', runtime_executor: 'go', status: 'ok' }}
        runnerStatus={{
          runner_reachable: true,
          runtime_executor: 'go',
          runner_status: 'ok',
          runtime_provider: 'docker',
          docker_reachable: true,
          version: 'dev',
          supported_operations: ['deploy', 'destroy'],
        }}
        operations={[]}
      />,
    );
    expect(html).toContain('Go runner');
    expect(html).toContain('deploy');
  });

  it('shows friendly message when runner unreachable', () => {
    const html = renderToStaticMarkup(
      <RunnerStatusContent
        runtimeStatus={{ runtime_executor: 'go' }}
        runnerStatus={{
          runner_reachable: false,
          runtime_executor: 'go',
          message: 'Go runner unavailable',
        }}
        operations={[]}
      />,
    );
    expect(html).toContain('Go runner is not reachable');
    expect(html).toContain('Go runner unavailable');
  });

  it('renders active error with operation status and request_id', () => {
    const html = renderToStaticMarkup(
      <RunnerStatusContent
        runtimeStatus={{
          runtime_executor: 'go',
          status: 'ok',
          last_runtime_error: {
            operation: 'deploy',
            status_code: 400,
            message: 'topology has no links',
            request_id: 'req-abc',
            timestamp: '2026-05-18T12:00:00Z',
            historical: false,
          },
        }}
        runnerStatus={null}
        operations={[]}
      />,
    );
    expect(html).toContain('Last failed operation: deploy');
    expect(html).toContain('returned 400');
    expect(html).toContain('topology has no links');
    expect(html).toContain('request_id req-abc');
  });

  it('does not show warning banner for historical errors', () => {
    const err = {
      operation: 'deploy',
      status_code: 400,
      message: 'old failure',
      request_id: 'req-old',
      timestamp: '2026-05-18T10:00:00Z',
      historical: true,
    };
    expect(pickActiveRuntimeError(null, { last_runtime_error: err })).toBeNull();
    const html = renderToStaticMarkup(
      <RunnerStatusContent
        runtimeStatus={{ runtime_executor: 'go', status: 'ok', last_runtime_error: err }}
        runnerStatus={null}
        operations={[]}
      />,
    );
    expect(html).not.toContain('Last failed operation');
  });

  it('renders failed operations in recent table', () => {
    const html = renderToStaticMarkup(
      <RunnerStatusContent
        runtimeStatus={{ runtime_executor: 'go', status: 'ok' }}
        runnerStatus={{ runner_reachable: true, runtime_executor: 'go' }}
        operations={[
          {
            operation: 'deploy',
            provider: 'docker',
            status: 'error',
            duration_ms: 42,
            request_id: 'req-fail',
            error_message: 'invalid topology',
            status_code: 400,
            created_at: '2026-05-18T12:00:00Z',
          },
        ]}
      />,
    );
    expect(html).toContain('Recent runner operations');
    expect(html).toContain('invalid topology');
    expect(html).toContain('req-fail');
    expect(html).toContain('error (400)');
  });

  it('formats structured runtime error text', () => {
    expect(
      formatLastRuntimeError({
        operation: 'deploy',
        status_code: 400,
        message: 'boom',
        request_id: 'rid-1',
        timestamp: '2026-05-18T12:00:00Z',
      }),
    ).toContain('Last failed operation: deploy returned 400 — boom — request_id rid-1');
  });
});
