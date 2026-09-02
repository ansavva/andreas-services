import type {
  DataExport,
  GroupDetail,
  GroupReadiness,
  GroupSummary,
  InvitationPreview,
  ExchangeTemplate,
  CheckoutResponse,
  PlanDefinition,
  Membership,
  Wish,
  WishClaimState,
  WishPreview,
  CreateWishInput,
  UpdateWishInput,
  ManagedInvitation,
  LateParticipantPreview,
  LateParticipantResult,
  GiftReceipt,
  GiftStage,
  PolicyConsent,
  RepeatedExchange,
  QuestionThread,
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

/**
 * A signed-out GET carrying an invite secret.
 *
 * Separate from `request` because that one demands an access token, and the whole point of an
 * invitation preview is that it is read by somebody who does not have one yet. The secret goes in a
 * header rather than the URL: `X-Humbugg-Invite` is not written to an access log, and a query string
 * is.
 */
async function anonymous<T>(path: string, inviteToken: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'X-Humbugg-Invite': inviteToken },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      body?.error?.code ?? 'request_failed',
      body?.error?.message ?? 'This invitation is invalid or has expired.',
    );
  }
  return response.json() as Promise<T>;
}

const json = (method: string, data?: unknown): RequestInit => ({
  method,
  body: data === undefined ? undefined : JSON.stringify(data),
});

export const api = {
  getMe: (token: string) => request<Profile>('/me', token),
  // `consent` is sent only on first profile creation (captured by the checkbox on the profile-setup
  // form); the backend records it once, immutably, and ignores it on later saves.
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
  updateTemplate: (token: string, id: string, data: Record<string, unknown>) => request<ExchangeTemplate>(`/templates/${id}`, token, json('PUT', data)),
  duplicateTemplate: (token: string, id: string) => request<ExchangeTemplate>(`/templates/${id}/duplicate`, token, json('POST')),
  deleteTemplate: (token: string, id: string) => request<void>(`/templates/${id}`, token, json('DELETE')),
  applyTemplate: (token: string, id: string, target_group_id: string, event_date: string, prior_member_ids: string[]) => request<GroupDetail>(`/templates/${id}/apply`, token, json('POST', { target_group_id, event_date, prior_member_ids })),
  createGroup: (token: string, data: Record<string, unknown>) => request<GroupDetail>('/groups', token, json('POST', data)),
  getGroup: (token: string, id: string) => request<GroupDetail>(`/groups/${id}`, token),
  // Organizer-only. Every state in the response is computed server-side; see types.ts.
  getReadiness: (token: string, id: string) => request<GroupReadiness>(`/groups/${id}/readiness`, token),
  // Every plan's price, limit and cadence, as the server defines them. The app never states a
  // price of its own: the amount is Stripe/SSM configuration and a hardcoded "$12" would go stale
  // silently, on the one screen where being wrong about the price matters most.
  listPlans: (token: string) => request<PlanDefinition[]>('/plans', token),
  getPlusPurchaseStatus: (token: string, id: string) =>
    request<PlusPurchaseStatus>(`/groups/${id}/billing/plus`, token),
  // Owner-only, and idempotent per pending purchase: a second call while one is unpaid returns the
  // same Checkout Session rather than opening a second payable one.
  createPlusCheckout: (token: string, id: string) =>
    request<CheckoutResponse>(`/groups/${id}/billing/plus/checkout`, token, json('POST')),
  // `expected_updated_at` is optimistic concurrency (#135): send back the `updated_at` you read and
  // a save that would flatten somebody else's edit is refused instead. Omit it for a one-field flip
  // computed from a value you already hold — there is nothing to conflict with.
  updateGroup: (token: string, id: string, data: Record<string, unknown>) => request<GroupDetail>(`/groups/${id}`, token, json('PATCH', data)),
  // Repeat an exchange (#136). A POST on the SOURCE — that is what the caller has and what
  // authorizes the copy; the new exchange and its one-time link come back in the response.
  repeatExchange: (token: string, id: string, data: Record<string, unknown>) =>
    request<RepeatedExchange>(`/groups/${id}/repeat`, token, json('POST', data)),
  removeMember: (token: string, id: string, memberId: string) =>
    request<void>(`/groups/${id}/members/${memberId}`, token, json('DELETE')),
  updateCustomization: (token: string, id: string, data: Record<string, unknown>) => request<GroupDetail>(`/groups/${id}/customization`, token, json('PUT', data)),
  // Both previews are signed OUT — somebody deciding whether to join does not have an account yet —
  // and both carry the invite secret in a header (#134).
  //
  // They used to `fetch('/api/…')` with the secret in the query string, and both halves of that were
  // wrong. The relative path assumed the app was served same-origin behind the marketing
  // distribution, which stopped being true when it moved to app.humbugg.com — so the request hit the
  // SPA fallback, got index.html back and threw on `response.json()`. And a query string is logged
  // by API Gateway and CloudFront, which is the exact leak the URL fragment exists to avoid.
  getInvitation: (id: string, inviteToken: string) =>
    anonymous<InvitationPreview>(`/groups/${id}/invitation`, inviteToken),
  getManagedInvitation: (id: string, invitationId: string, token: string) =>
    anonymous<InvitationPreview>(`/groups/${id}/invitations/${invitationId}/preview`, token),
  deleteGroup: (token: string, id: string) => request<void>(`/groups/${id}`, token, json('DELETE')),
  rotateInvite: (token: string, id: string) => request<{ invite_url: string }>(`/groups/${id}/invite`, token, json('POST')),
  listWishes: (token: string, id: string) => request<Wish[]>(`/groups/${id}/members/me/wishes`, token),
  // Reading a pasted product link (#129). A POST, because it makes Humbugg's servers fetch a page
  // somebody else chose — and because a URL in a body is not written to an access log the way a
  // query string is.
  previewWishUrl: (token: string, id: string, url: string) =>
    request<WishPreview>(`/groups/${id}/members/me/wishes/preview`, token, json('POST', { url })),
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
  // Purchase claims (#130). Both return the whole assignment, so one round trip leaves the giver's
  // view consistent — including a wish the owner deleted while the giver was deciding.
  setWishClaim: (token: string, id: string, wishId: string, state: WishClaimState, quantity?: number) =>
    request<RecipientAssignment>(
      `/groups/${id}/assignment/wishes/${wishId}/claim`,
      token,
      json('PUT', quantity === undefined ? { state } : { state, quantity }),
    ),
  releaseWishClaim: (token: string, id: string, wishId: string) =>
    request<RecipientAssignment>(`/groups/${id}/assignment/wishes/${wishId}/claim`, token, json('DELETE')),
  // Gift progress (#132). The giver's three stages, and the recipient's confirmation — two facts
  // about one gift, owned by two people, so two routes. The recipient's PUT lands on their giver's
  // row, whose id the server resolves by inverting the draw and never returns.
  setGiftStage: (token: string, id: string, stage: GiftStage) =>
    request<RecipientAssignment>(`/groups/${id}/assignment/gift`, token, json('PUT', { stage })),
  getGiftReceipt: (token: string, id: string) =>
    request<GiftReceipt>(`/groups/${id}/members/me/gift`, token),
  setGiftReceived: (token: string, id: string, received: boolean) =>
    request<GiftReceipt>(`/groups/${id}/members/me/gift`, token, json('PUT', { received })),
  // Anonymous questions (#131). Two routes, one shape: the giver's hangs off `assignment` because
  // the assignment is the authorization, the recipient's off `members/me` because the only member a
  // caller can address is themselves. Neither URL carries a member id — a URL is one of the surfaces
  // the identity could leak through, and the way to keep it out is to have no id to put there.
  getGiverQuestions: (token: string, id: string) =>
    request<QuestionThread>(`/groups/${id}/assignment/questions`, token),
  askQuestion: (token: string, id: string, body: string) =>
    request<QuestionThread>(`/groups/${id}/assignment/questions`, token, json('POST', { body })),
  getRecipientQuestions: (token: string, id: string) =>
    request<QuestionThread>(`/groups/${id}/members/me/questions`, token),
  replyToQuestion: (token: string, id: string, body: string) =>
    request<QuestionThread>(`/groups/${id}/members/me/questions`, token, json('POST', { body })),
  setQuestionsBlocked: (token: string, id: string, blocked: boolean) =>
    request<QuestionThread>(`/groups/${id}/members/me/questions/blocked`, token, json('PUT', { blocked })),
  reveal: (token: string, id: string, reason: string) => request<{ assignments: RevealAssignment[] }>(`/groups/${id}/assignment/reveal`, token, json('POST', { reason })),
  previewLateParticipant: (token: string, id: string, memberId: string) =>
    request<LateParticipantPreview>(`/groups/${id}/late-participants/${memberId}/preview`, token, json('POST')),
  confirmLateParticipant: (token: string, id: string, proposalId: string) =>
    request<LateParticipantResult>(`/groups/${id}/late-participants/confirm`, token, json('POST', { proposal_id: proposalId, confirm: true })),
};
