import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./client', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from './client';
import { confirmInfrastructureDeployment } from './infrastructureDeployments';

describe('confirmInfrastructureDeployment', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('posts to confirm endpoint with JSON body', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ id: 'dep-1', status: 'succeeded' });
    await confirmInfrastructureDeployment('dep-1');
    expect(apiFetch).toHaveBeenCalledWith('/infrastructure-deployments/dep-1/confirm', {
      method: 'POST',
      body: JSON.stringify({ confirm: true }),
    });
  });
});
