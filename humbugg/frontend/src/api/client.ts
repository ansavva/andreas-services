import type {
  DataExport,
  GroupDetail,
  GroupSummary,
  Membership,
  Profile,
  RecipientAssignment,
  RevealAssignment,
} from '../types';

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.error?.code ?? 'request_failed', body?.error?.message ?? 'Request failed.');
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const json = (method: string, data?: unknown): RequestInit => ({
  method,
  body: data === undefined ? undefined : JSON.stringify(data),
});

export const api = {
  getMe: (token: string) => request<Profile>('/me', token),
  saveMe: (token: string, display_name: string) => request<Profile>('/me', token, json('PUT', { display_name })),
  deleteAccount: (token: string) => request<void>('/me', token, json('DELETE')),
  exportMyData: (token: string) => request<DataExport>('/me/export', token),
  listGroups: (token: string) => request<GroupSummary[]>('/groups', token),
  createGroup: (token: string, data: Record<string, unknown>) => request<GroupDetail>('/groups', token, json('POST', data)),
  getGroup: (token: string, id: string) => request<GroupDetail>(`/groups/${id}`, token),
  updateGroup: (token: string, id: string, data: Record<string, unknown>) => request<GroupDetail>(`/groups/${id}`, token, json('PATCH', data)),
  deleteGroup: (token: string, id: string) => request<void>(`/groups/${id}`, token, json('DELETE')),
  rotateInvite: (token: string, id: string) => request<{ invite_url: string }>(`/groups/${id}/invite`, token, json('POST')),
  joinGroup: (token: string, id: string, invite_token: string) => request<GroupDetail>(`/groups/${id}/join`, token, json('POST', { invite_token })),
  getMembership: (token: string, id: string) => request<Membership>(`/groups/${id}/members/me`, token),
  updateMembership: (token: string, id: string, data: Record<string, unknown>) => request<Membership>(`/groups/${id}/members/me`, token, json('PATCH', data)),
  clearMyGroupData: (token: string, id: string) => request<Membership>(`/groups/${id}/members/me/private-data`, token, json('DELETE')),
  leaveGroup: (token: string, id: string) => request<void>(`/groups/${id}/members/me`, token, json('DELETE')),
  setParticipation: (token: string, id: string, memberId: string, is_participating: boolean) => request<Membership>(`/groups/${id}/members/${memberId}/participation`, token, json('PATCH', { is_participating })),
  setExclusions: (token: string, id: string, exclusions: string[][]) => request<GroupDetail>(`/groups/${id}/exclusions`, token, json('PUT', { exclusions })),
  draw: (token: string, id: string) => request<RecipientAssignment>(`/groups/${id}/draw`, token, json('POST')),
  reset: (token: string, id: string) => request<GroupDetail>(`/groups/${id}/reset`, token, json('POST')),
  getAssignment: (token: string, id: string) => request<RecipientAssignment>(`/groups/${id}/assignment`, token),
  reveal: (token: string, id: string, reason: string) => request<{ assignments: RevealAssignment[] }>(`/groups/${id}/assignment/reveal`, token, json('POST', { reason })),
};
