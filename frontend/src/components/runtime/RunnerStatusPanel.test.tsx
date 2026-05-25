import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { RunnerStatusContent, RunnerStatusPanel } from './RunnerStatusPanel';

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
});
