import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ApiError, parseStructuredError } from '../../api/client';
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
});
