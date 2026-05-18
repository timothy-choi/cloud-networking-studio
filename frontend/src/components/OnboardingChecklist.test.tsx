import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { OnboardingChecklist } from './OnboardingChecklist';

const sampleSteps = [
  {
    id: 'project',
    title: 'Create or select a project',
    description: 'd1',
    completed: true,
    auto_detected: true,
  },
  {
    id: 'topology',
    title: 'Create a topology',
    description: 'd2',
    completed: false,
    auto_detected: false,
  },
];

describe('OnboardingChecklist', () => {
  it('renders checklist headings and demo button', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <OnboardingChecklist
          steps={sampleSteps}
          hasSeenOnboarding={false}
          firstTopologyId={null}
          selectedProjectId="p1"
          onOpenCreateProject={vi.fn()}
          onRefresh={vi.fn().mockResolvedValue(undefined)}
          demoBusy={false}
          onStartDemo={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(html).toContain('Guided path: first deploy in minutes');
    expect(html).toContain('Start demo (optional)');
    expect(html).toContain('Create a topology');
  });
});
