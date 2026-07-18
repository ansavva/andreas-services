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

  it('requests account deletion with DELETE /me and tolerates an empty 204 body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(api.deleteAccount('access-token')).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toBe('/api/me');
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE');
  });

  it('clears my own wishlist and address for a group', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ member_id: 'm', display_name: 'Alex', is_organizer: false, is_participating: true, wishlist: '', avoidances: '' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    await api.clearMyGroupData('token', 'group');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/groups/group/members/me/private-data');
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE');
  });
});
