// Ported from the web app. The assertions that pinned `/api/...` now pin
// `API_BASE_URL + path` — the one real change to `client.ts` — so a regression
// that silently dropped the base URL would fail here rather than in production.
import { api, API_BASE_URL } from './client';

const realFetch = globalThis.fetch;

function stubFetch(response: Response) {
  const mock = jest.fn().mockResolvedValue(response);
  globalThis.fetch = mock as unknown as typeof fetch;
  return mock;
}

afterEach(() => {
  globalThis.fetch = realFetch;
  jest.clearAllMocks();
});

describe('API client', () => {
  it('sends the Cognito access token as a bearer token', async () => {
    const fetchMock = stubFetch(new Response(JSON.stringify([]), { status: 200 }));
    await api.listGroups('access-token');
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer access-token');
  });

  it('prefixes every path with the configured API origin', async () => {
    const fetchMock = stubFetch(new Response(JSON.stringify([]), { status: 200 }));
    await api.listGroups('access-token');
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE_URL}/groups`);
  });

  it('surfaces the stable API error message and code', async () => {
    stubFetch(
      new Response(JSON.stringify({ error: { code: 'conflict', message: 'Draw is impossible.' } }), {
        status: 409,
      }),
    );
    await expect(api.draw('token', 'group')).rejects.toMatchObject({
      status: 409,
      code: 'conflict',
      message: 'Draw is impossible.',
    });
  });

  it('requests account deletion with DELETE /me and tolerates an empty 204 body', async () => {
    const fetchMock = stubFetch(new Response(null, { status: 204 }));
    await expect(api.deleteAccount('access-token')).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE_URL}/me`);
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE');
  });

  it('exports my own data with GET /me/export', async () => {
    const fetchMock = stubFetch(
      new Response(
        JSON.stringify({
          metadata: { generated_at: 'now', format_version: '1.0', subject_user_id: 'u', notes: [] },
          profile: { user_id: 'u' },
          memberships: [],
        }),
        { status: 200 },
      ),
    );
    const result = await api.exportMyData('access-token');
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE_URL}/me/export`);
    expect(fetchMock.mock.calls[0][1].method ?? 'GET').toBe('GET');
    expect(result.profile.user_id).toBe('u');
  });

  it('clears my own wishlist and address for a group', async () => {
    const fetchMock = stubFetch(
      new Response(
        JSON.stringify({
          member_id: 'm',
          display_name: 'Alex',
          is_organizer: false,
          is_participating: true,
          wishlist: '',
          avoidances: '',
        }),
        { status: 200 },
      ),
    );
    await api.clearMyGroupData('token', 'group');
    expect(fetchMock.mock.calls[0][0]).toBe(`${API_BASE_URL}/groups/group/members/me/private-data`);
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE');
  });
});
