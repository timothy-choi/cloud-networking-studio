import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ApiError, formatApiError, parseStructuredError } from '../../api/client';
import { ApiErrorDisplay } from './ApiErrorDisplay';

describe('parseStructuredError', () => {
  it('extracts code message and request_id', () => {
    const parsed = parseStructuredError({
      detail: 'Not found',
      error: {
        code: 'NOT_FOUND',
        message: 'Not found',
        details: {},
        request_id: 'abc123',
      },
    });
    expect(parsed?.code).toBe('NOT_FOUND');
    expect(parsed?.request_id).toBe('abc123');
  });
});

describe('ApiErrorDisplay', () => {
  it('shows request_id for structured errors', () => {
    const err = new ApiError(404, 'Not Found', {
      detail: 'Not found',
      error: {
        code: 'NOT_FOUND',
        message: 'Not found',
        details: {},
        request_id: 'req-xyz',
      },
    });
    const html = renderToStaticMarkup(<ApiErrorDisplay error={err} />);
    expect(html).toContain('request_id: req-xyz');
  });

  it('shows endpoint and http status for ApiError', () => {
    const err = new ApiError(
      409,
      'Conflict',
      { detail: { message: 'Cannot confirm apply while status is pending.' } },
      'req-abc',
      'https://api-staging.cloudnetstudio.com/api/infrastructure-deployments/dep-1/confirm',
    );
    const html = renderToStaticMarkup(<ApiErrorDisplay error={err} />);
    expect(html).toContain('endpoint: https://api-staging.cloudnetstudio.com/api/infrastructure-deployments/dep-1/confirm');
    expect(html).toContain('http: 409 Conflict');
    expect(html).toContain('Response body');
  });
});

describe('formatApiError', () => {
  it('includes endpoint and status for HTTP errors instead of generic fetch message', () => {
    const err = new ApiError(
      409,
      'Conflict',
      { detail: { message: 'Cannot confirm apply while status is pending.' } },
      null,
      'https://api.example.com/api/infrastructure-deployments/dep-1/confirm',
    );
    const message = formatApiError(err);
    expect(message).toContain('HTTP 409 Conflict');
    expect(message).toContain('Endpoint: https://api.example.com/api/infrastructure-deployments/dep-1/confirm');
    expect(message).not.toContain('cannot reach');
  });
});
