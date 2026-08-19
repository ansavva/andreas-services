import type {
  DataExport,
  GroupDetail,
  GroupSummary,
  Membership,
  ManagedInvitation,
  PolicyConsent,
  PlusPurchaseStatus,
  Profile,
  RecipientAssignment,
  RevealAssignment,
} from '../types';

/**
 * The API's own origin, baked in at build time.
 *
 * The web app could say `fetch('/api' + path)` because the API was proxied
 * same-origin through the marketing CloudFront distribution. This app is never
 * same-origin with it — on a device there is no origin at all — so the base URL
 * has to be configuration. `EXPO_PUBLIC_*` is read statically by Metro, so the
 * lookup cannot be hoisted into a helper or read from a variable key.
 */
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? 'https://api.humbugg.com/api';

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
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
  // `consent` is sent only on first profile creation (captured at the signup checkbox); the backend
  // records it once, immutably, and ignores it on later saves.
  saveMe: (
    token: string,
    display_name: string,
    non_essential_emails_enabled?: boolean,
    consent?: PolicyConsent,
  ) => {
    const body: Record<string, unknown> = { display_name };
    if (non_essential_emails_enabled !== undefined) body.non_essential_emails_enabled = non_essential_emails_enabled;
    if (consent !== undefined) body.consent = consent;
    return request<Profile>('/me', token, json('PUT', body));
  },
  // The image is a data URL ("data:image/...;base64,...") sent as JSON so it rides the same API path as
  // every other call; the backend validates, safely re-encodes, and stores it, returning the new URL.
  uploadAvatar: (token: string, image: string) => request<Profile>('/me/avatar', token, json('PUT', { image })),
  removeAvatar: (token: string) => request<Profile>('/me/avatar', token, json('DELETE')),
  deleteAccount: (token: string) => request<void>('/me', token, json('DELETE')),
  exportMyData: (token: string) => request<DataExport>('/me/export', token),
  listGroups: (token: string) => request<GroupSummary[]>('/groups', token),
  createGroup: (token: string, data: Record<string, unknown>) => request<GroupDetail>('/groups', token, json('POST', data)),
  getGroup: (token: string, id: string) => request<GroupDetail>(`/groups/${id}`, token),
  getPlusPurchaseStatus: (token: string, id: string) =>
    request<PlusPurchaseStatus>(`/groups/${id}/billing/plus`, token),
  updateGroup: (token: string, id: string, data: Record<string, unknown>) => request<GroupDetail>(`/groups/${id}`, token, json('PATCH', data)),
  deleteGroup: (token: string, id: string) => request<void>(`/groups/${id}`, token, json('DELETE')),
  rotateInvite: (token: string, id: string) => request<{ invite_url: string }>(`/groups/${id}/invite`, token, json('POST')),
  listInvitations: (token: string, id: string) => request<ManagedInvitation[]>(`/groups/${id}/invitations`, token),
  createInvitations: (token: string, id: string, emails: string[]) => request<{ invitations: ManagedInvitation[] }>(`/groups/${id}/invitations`, token, json('POST', { emails })),
  resendInvitation: (token: string, id: string, invitationId: string) => request<ManagedInvitation>(`/groups/${id}/invitations/${invitationId}/resend`, token, json('POST')),
  revokeInvitation: (token: string, id: string, invitationId: string) => request<void>(`/groups/${id}/invitations/${invitationId}/revoke`, token, json('POST')),
  acceptInvitation: (token: string, id: string, invitationId: string, invitationToken: string, confirmAddressMismatch = false) =>
    request<{ group_id: string; accepted: boolean }>(`/groups/${id}/invitations/${invitationId}/accept`, token, json('POST', { token: invitationToken, confirm_address_mismatch: confirmAddressMismatch })),
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
