import { afterEach, describe, expect, it, vi } from 'vitest';

import { api } from './client';

describe('API client', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends the Cognito access token as a bearer token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await api.listGroups('access-token');
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer access-token');
  });

  it('surfaces the stable API error message and code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'conflict', message: 'Draw is impossible.' } }), { status: 409 })));
    await expect(api.draw('token', 'group')).rejects.toMatchObject({ status: 409, code: 'conflict', message: 'Draw is impossible.' });
  });
});
