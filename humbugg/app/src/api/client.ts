import type {
  DataExport,
  GroupDetail,
  GroupSummary,
  InvitationPreview,
  ExchangeTemplate,
  Membership,
  Wish,
  CreateWishInput,
  UpdateWishInput,
  ManagedInvitation,
  LateParticipantPreview,
  LateParticipantResult,
  PolicyConsent,
  PlusPurchaseStatus,
  Profile,
  RecipientAssignment,
  ReminderOverview,
  ReminderRule,
  ReminderSettings,
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
  listTemplates: (token: string) => request<ExchangeTemplate[]>('/templates', token),
  saveTemplate: (token: string, name: string, source_group_id: string) => request<ExchangeTemplate>('/templates', token, json('POST', { name, source_group_id })),
  duplicateTemplate: (token: string, id: string) => request<ExchangeTemplate>(`/templates/${id}/duplicate`, token, json('POST')),
  deleteTemplate: (token: string, id: string) => request<void>(`/templates/${id}`, token, json('DELETE')),
  applyTemplate: (token: string, id: string, target_group_id: string, event_date: string, prior_member_ids: string[]) => request<GroupDetail>(`/templates/${id}/apply`, token, json('POST', { target_group_id, event_date, prior_member_ids })),
  createGroup: (token: string, data: Record<string, unknown>) => request<GroupDetail>('/groups', token, json('POST', data)),
  getGroup: (token: string, id: string) => request<GroupDetail>(`/groups/${id}`, token),
  getPlusPurchaseStatus: (token: string, id: string) =>
    request<PlusPurchaseStatus>(`/groups/${id}/billing/plus`, token),
  updateGroup: (token: string, id: string, data: Record<string, unknown>) => request<GroupDetail>(`/groups/${id}`, token, json('PATCH', data)),
  updateCustomization: (token: string, id: string, data: Record<string, unknown>) => request<GroupDetail>(`/groups/${id}/customization`, token, json('PUT', data)),
  getInvitation: async (id: string, invite_token: string) => {
    const response = await fetch(`/api/groups/${id}/invitation?invite_token=${encodeURIComponent(invite_token)}`);
    if (!response.ok) throw new Error('This invitation is invalid or has expired.');
    return response.json() as Promise<InvitationPreview>;
  },
  getManagedInvitation: async (id: string, invitationId: string, token: string) => {
    const response = await fetch(`/api/groups/${id}/invitations/${invitationId}/preview?token=${encodeURIComponent(token)}`);
    if (!response.ok) throw new Error('This invitation is invalid or has expired.');
    return response.json() as Promise<InvitationPreview>;
  },
  deleteGroup: (token: string, id: string) => request<void>(`/groups/${id}`, token, json('DELETE')),
  rotateInvite: (token: string, id: string) => request<{ invite_url: string }>(`/groups/${id}/invite`, token, json('POST')),
  listWishes: (token: string, id: string) => request<Wish[]>(`/groups/${id}/members/me/wishes`, token),
  createWish: (token: string, id: string, wish: CreateWishInput) =>
    request<Wish>(`/groups/${id}/members/me/wishes`, token, json('POST', wish)),
  updateWish: (token: string, id: string, wishId: string, changes: UpdateWishInput) =>
    request<Wish>(`/groups/${id}/members/me/wishes/${wishId}`, token, json('PATCH', changes)),
  deleteWish: (token: string, id: string, wishId: string) =>
    request<void>(`/groups/${id}/members/me/wishes/${wishId}`, token, json('DELETE')),
  reorderWishes: (token: string, id: string, wish_ids: string[]) =>
    request<Wish[]>(`/groups/${id}/members/me/wishes/order`, token, json('PUT', { wish_ids })),
  listInvitations: (token: string, id: string) => request<ManagedInvitation[]>(`/groups/${id}/invitations`, token),
  createInvitations: (token: string, id: string, emails: string[]) => request<{ invitations: ManagedInvitation[] }>(`/groups/${id}/invitations`, token, json('POST', { emails })),
  resendInvitation: (token: string, id: string, invitationId: string) => request<ManagedInvitation>(`/groups/${id}/invitations/${invitationId}/resend`, token, json('POST')),
  revokeInvitation: (token: string, id: string, invitationId: string) => request<void>(`/groups/${id}/invitations/${invitationId}/revoke`, token, json('POST')),
  acceptInvitation: (token: string, id: string, invitationId: string, invitationToken: string, confirmAddressMismatch = false) =>
    request<{ group_id: string; accepted: boolean }>(`/groups/${id}/invitations/${invitationId}/accept`, token, json('POST', { token: invitationToken, confirm_address_mismatch: confirmAddressMismatch })),
  getReminders: (token: string, id: string) => request<ReminderOverview>(`/groups/${id}/reminders`, token),
  updateReminders: (token: string, id: string, settings: ReminderSettings) =>
    request<ReminderOverview>(`/groups/${id}/reminders`, token, json('PUT', settings)),
  sendReminder: (token: string, id: string, invitationId: string, rule: ReminderRule) =>
    request(`/groups/${id}/reminders/send`, token, json('POST', { invitation_id: invitationId, rule })),
  joinGroup: (token: string, id: string, invite_token: string) => request<GroupDetail>(`/groups/${id}/join`, token, json('POST', { invite_token })),
  getMembership: (token: string, id: string) => request<Membership>(`/groups/${id}/members/me`, token),
  updateMembership: (token: string, id: string, data: Record<string, unknown>) => request<Membership>(`/groups/${id}/members/me`, token, json('PATCH', data)),
  clearMyGroupData: (token: string, id: string) => request<Membership>(`/groups/${id}/members/me/private-data`, token, json('DELETE')),
  leaveGroup: (token: string, id: string) => request<void>(`/groups/${id}/members/me`, token, json('DELETE')),
  setParticipation: (token: string, id: string, memberId: string, is_participating: boolean) => request<Membership>(`/groups/${id}/members/${memberId}/participation`, token, json('PATCH', { is_participating })),
  setOrganizerRole: (token: string, id: string, memberId: string, is_organizer: boolean) => request<Membership>(`/groups/${id}/members/${memberId}/organizer-role`, token, json('PATCH', { is_organizer })),
  setExclusions: (token: string, id: string, exclusions: string[][]) => request<GroupDetail>(`/groups/${id}/exclusions`, token, json('PUT', { exclusions })),
  draw: (token: string, id: string) => request<RecipientAssignment>(`/groups/${id}/draw`, token, json('POST')),
  reset: (token: string, id: string) => request<GroupDetail>(`/groups/${id}/reset`, token, json('POST')),
  getAssignment: (token: string, id: string, drawVersion?: string | null) => request<RecipientAssignment>(`/groups/${id}/assignment${drawVersion ? `?draw_version=${encodeURIComponent(drawVersion)}` : ''}`, token),
  reveal: (token: string, id: string, reason: string) => request<{ assignments: RevealAssignment[] }>(`/groups/${id}/assignment/reveal`, token, json('POST', { reason })),
  previewLateParticipant: (token: string, id: string, memberId: string) =>
    request<LateParticipantPreview>(`/groups/${id}/late-participants/${memberId}/preview`, token, json('POST')),
  confirmLateParticipant: (token: string, id: string, proposalId: string) =>
    request<LateParticipantResult>(`/groups/${id}/late-participants/confirm`, token, json('POST', { proposal_id: proposalId, confirm: true })),
};
