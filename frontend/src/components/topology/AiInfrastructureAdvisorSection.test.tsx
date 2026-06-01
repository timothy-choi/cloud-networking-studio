import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { AiInfrastructureAdvice } from '../../api/topologyPlacement';
import { AiInfrastructureAdvisorSection } from './AiInfrastructureAdvisorSection';

const sampleAdvice: AiInfrastructureAdvice = {
  summary: 'Topology fits on one e2-micro host with docker-vm strategy.',
  risks: ['Public workload requires exposed ports: 8080.'],
  suggestions: ['[Cost] Utilization is low — a smaller machine type may reduce cost.'],
  recommended_overrides: {
    machine_type: 'e2-micro',
    strategy: 'docker-vm',
    machine_type_valid: true,
    strategy_valid: true,
  },
  explanation: 'The planner bin-packed your nodes onto one host.',
  advisor_mode: 'heuristic',
  advisory_only: true,
};

describe('AiInfrastructureAdvisorSection', () => {
  it('renders advice summary, risks, and suggested overrides', () => {
    const html = renderToStaticMarkup(
      <AiInfrastructureAdvisorSection
        advice={sampleAdvice}
        loading={false}
        error={null}
        onRequestAdvice={() => {}}
        onApplyMachineType={() => {}}
      />,
    );
    expect(html).toContain('AI advisor');
    expect(html).toContain('Advisory only');
    expect(html).toContain('Topology fits on one e2-micro host');
    expect(html).toContain('Public workload requires exposed ports');
    expect(html).toContain('machine_type: e2-micro');
    expect(html).toContain('Apply suggested machine type');
  });

  it('shows apply button only when machine type override is valid', () => {
    const invalidAdvice: AiInfrastructureAdvice = {
      ...sampleAdvice,
      recommended_overrides: {
        machine_type: 'e2-micro',
        strategy: 'docker-vm',
        machine_type_valid: false,
        strategy_valid: true,
      },
    };
    const html = renderToStaticMarkup(
      <AiInfrastructureAdvisorSection
        advice={invalidAdvice}
        loading={false}
        error={null}
        onRequestAdvice={() => {}}
        onApplyMachineType={() => {}}
      />,
    );
    expect(html).not.toContain('Apply suggested machine type');
    expect(html).toContain('not allowed by planner');
  });
});
