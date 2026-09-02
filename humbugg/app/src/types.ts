export type GroupStatus = 'open' | 'drawn';
export type PlanCode = 'free' | 'plus' | 'work';
export type PaymentStatus = 'pending' | 'paid' | 'failed' | 'expired' | 'refunded';

export interface ApiErrorPayload {
  error: { code: string; message: string };
}

/**
 * Recorded proof that a user actively agreed to the Terms of Service and Privacy Policy at profile setup
 * (GDPR Art. 7 — demonstrable consent). `version` mirrors POLICY_VERSION in config/policies so the
 * record stays in sync with the published policies; `accepted_at` is a UTC ISO-8601 timestamp.
 */
export interface PolicyConsent {
  version: string;
  accepted_at: string;
}

export interface Profile {
  user_id: string;
  display_name: string;
  created_at: string;
  updated_at: string;
  /** Absolute URL of the uploaded profile photo, or null/undefined when the initials fallback applies. */
  avatar_url?: string | null;
  /**
   * Whether Humbugg may send this account non-essential product email (reminders, group-activity
   * notifications, product news). Essential mail (security/account and join-critical) always sends.
   */
  non_essential_emails_enabled: boolean;
  /** Terms/Privacy consent recorded at signup; absent only for rows written before it was captured. */
  consent?: PolicyConsent | null;
}

export interface Membership {
  member_id: string;
  display_name: string;
  is_organizer: boolean;
  is_owner?: boolean;
  is_ready?: boolean;
  is_participating: boolean;
  wishlist?: string;
  avoidances?: string;
  address?: Address;
}

export interface Address {
  line1?: string;
  line2?: string;
  city?: string;
  region?: string;
  postal_code?: string;
  country?: string;
}

export type ExclusionPair = [string, string];
export interface ExchangeCustomization { greeting: string; instructions: string; primary_color: string; accent_color: string; image_data_url?: string | null; }
export interface InvitationPreview { group_id: string; exchange_name: string; customization: ExchangeCustomization; }
export interface TemplateParticipant { member_id: string; display_name: string; email: string; }
export interface ExchangeTemplate { template_id: string; name: string; exchange_name: string; description: string; signup_deadline_days_before_event: number; wishlist_prompt: string; exclusions_policy: 'none' | 'preserve_existing'; reminder_preferences: ReminderSettings; customization: ExchangeCustomization; prior_participants: TemplateParticipant[]; source_group_id?: string | null; }

// Self-service GDPR data export (right of access / portability). Mirrors the backend `DataExport`
// DTO. Contains only the caller's own data — never another member's PII or any draw assignment.
export interface DataExport {
  metadata: {
    generated_at: string;
    format_version: string;
    subject_user_id: string;
    notes: string[];
  };
  profile: {
    user_id: string;
    display_name?: string | null;
    email?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
    avatar?: string | null;
    non_essential_emails_enabled?: boolean | null;
    consent?: { policy_version: string; agreed_at: string } | null;
  };
  memberships: Array<{
    group_id: string;
    group_name: string;
    group_status: GroupStatus;
    member_id: string;
    role: 'owner' | 'co_organizer' | 'participant';
    is_participating: boolean;
    wishlist?: string | null;
    avoidances?: string | null;
    address?: Address | null;
    joined_at: string;
    updated_at: string;
  }>;
}

export interface GroupSummary {
  group_id: string;
  name: string;
  status: GroupStatus;
  event_date?: string | null;
  spending_limit?: number | null;
  currency: 'USD';
  plan: PlanCode;
  participant_limit: number;
  is_organizer: boolean;
  is_owner: boolean;
  created_at: string;
  updated_at: string;
  /** Whether this exchange posts its gifts, and so whether a mailing address is asked for. */
  requires_address?: boolean;
}

export interface GroupDetail extends GroupSummary {
  description: string;
  signup_deadline?: string | null;
  exclusions: ExclusionPair[];
  members: Membership[];
  invite_url?: string;
  customization?: ExchangeCustomization | null;
}

export interface PlusPurchaseStatus {
  group_id: string;
  status?: PaymentStatus | null;
  checkout_session_id?: string | null;
  checkout_url?: string | null;
  receipt_url?: string | null;
  /**
   * Set the moment the webhook applies a paid purchase — the group's plan and this field are
   * written in one transaction. It, not `status`, is what the backend's `HasCapability` reads, so
   * it is what "Plus is active" means here too: a `paid` row with no entitlement is a purchase
   * still being applied, and the screen says so rather than promising a capability that would 402.
   */
  entitlement_id?: string | null;
  updated_at?: string | null;
}

export type BillingCadence = 'free' | 'one_time' | 'annual';

/** A plan as the server defines it. The price is configuration, never a constant in this app. */
export interface PlanDefinition {
  code: PlanCode;
  name: string;
  participant_limit: number;
  marketed_as_unlimited: boolean;
  price_cents: number;
  currency: string;
  billing_cadence: BillingCadence;
  product_id?: string | null;
  price_id?: string | null;
}

/** A freshly opened Stripe Checkout Session. `status` is always `pending` at this point. */
export interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
  status: PaymentStatus;
}

// Lowercase because that is what the wire carries. The API serialises every enum through
// `JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower)`, so `WishKind.Product` arrives as
// "product" — these were PascalCase, which type-checked and then failed silently at runtime: every
// `kindLabel[wish.kind]` lookup missed and rendered an empty badge, and `priority !== 'Normal'` was
// always true, so every wish also carried a second empty one. Writes were unaffected (the backend
// parses case-insensitively), which is why it survived: only the read was wrong.
export type WishKind = 'product' | 'custom' | 'experience' | 'charity';
export type WishPriority = 'low' | 'normal' | 'high';

/**
 * How far along the giver is on one wish (#130).
 *
 * Two states, not three. "planned" is a soft hold that stops a giver buying the same thing twice
 * across sessions; "purchased" is done. Sent and received are the exchange's milestones, not the
 * wish's, and belong to the organizer roll-up (#132).
 */
export type WishClaimState = 'planned' | 'purchased';

/** The GIVER's own claim on a wish. Never the wishlist owner's — they are never sent one. */
export interface WishClaim {
  state: WishClaimState;
  quantity: number;
  updated_at: string;
}

/** A wish on your own list. */
export interface Wish {
  wish_id: string;
  kind: WishKind;
  title: string;
  url?: string | null;
  image_url?: string | null;
  price_cents?: number | null;
  currency?: string | null;
  quantity: number;
  priority: WishPriority;
  details?: string | null;
  position: number;
  created_at: string;
  updated_at: string;
}

/**
 * A wish on the list of the person you were assigned. Separate from `Wish` on purpose, and not an
 * alias: purchase claims (#130) will be visible here and never on the owner's own view, so the two
 * shapes are going to diverge.
 */
export interface RecipientWish {
  wish_id: string;
  kind: WishKind;
  title: string;
  url?: string | null;
  image_url?: string | null;
  price_cents?: number | null;
  currency?: string | null;
  quantity: number;
  priority: WishPriority;
  details?: string | null;
  position: number;
  /**
   * The reader's OWN claim, or absent. Deliberately not on `Wish`: a claim on your own list would
   * tell you what your giver has already bought, which is the one thing this feature must not do.
   */
  claim?: WishClaim | null;
}

export interface RecipientAssignment {
  member_id: string;
  display_name: string;
  /** Free-text general preferences; structured wishes did not replace it. */
  wishlist: string;
  avoidances: string;
  address: Address;
  wishes: RecipientWish[];
}

export interface CreateWishInput {
  kind?: WishKind;
  title: string;
  url?: string;
  image_url?: string;
  price_cents?: number;
  currency?: string;
  quantity?: number;
  priority?: WishPriority;
  details?: string;
}

/** Omitted fields are left unchanged; an empty string clears an optional field. */
export type UpdateWishInput = Partial<CreateWishInput>;

export interface RevealAssignment {
  giver: Membership;
  recipient: RecipientAssignment;
}

export interface LateParticipantPreview {
  proposal_id: string;
  member_id: string;
  affected_participant_count: number;
  expires_at: string;
}

export interface LateParticipantResult {
  member_id: string;
  affected_participant_count: number;
  assignment_version: string;
}

export type InvitationStatus = 'sent' | 'delivered' | 'bounced' | 'accepted' | 'expired' | 'revoked';
export interface ManagedInvitation {
  invitation_id: string;
  email: string;
  status: InvitationStatus;
  expires_at: string;
  accepted_at?: string | null;
  last_sent_at?: string | null;
}

export type ReminderState = 'active' | 'paused' | 'stopped';
export type ReminderRule = 'unaccepted_invitation' | 'incomplete_readiness';
export interface ReminderSettings {
  state: ReminderState;
  remind_unaccepted_invitations: boolean;
  remind_incomplete_readiness: boolean;
  interval_days: number;
  quiet_start_utc_hour: number;
  quiet_end_utc_hour: number;
}
export interface ReminderHistoryItem {
  reminder_id: string;
  rule: ReminderRule;
  invitation_id: string;
  status: 'sent' | 'suppressed';
  created_at: string;
}
export interface ReminderOverview {
  settings: ReminderSettings;
  next_scheduled_at?: string | null;
  recent_history: ReminderHistoryItem[];
}

// ─── Organizer readiness (#133) ─────────────────────────────────────────────────────────────────
//
// Mirrors the backend's `GroupReadiness`. Every state below is DECIDED BY THE SERVER; nothing here
// re-derives one from a wish count or an address. That is the whole point of the seam — "ready" has
// to mean one thing, and a second implementation on this side is how it quietly stops meaning it.

export type ReadinessState = 'ready' | 'missing' | 'not_required' | 'not_applicable';
export type ParticipantRole = 'owner' | 'co_organizer' | 'participant';
export type NudgeReason =
  | 'no_wishlist'
  | 'no_address'
  | 'assignment_not_viewed'
  | 'invitation_not_accepted';

export interface ParticipantReadiness {
  member_id: string;
  display_name: string;
  role: ParticipantRole;
  is_participating: boolean;
  wishlist: ReadinessState;
  wish_count: number;
  has_general_preferences: boolean;
  address: ReadinessState;
  assignment: ReadinessState;
  nudges: NudgeReason[];
}

export interface PendingInvitation {
  invitation_id: string;
  email: string;
  status: InvitationStatus;
  expires_at: string;
  last_sent_at?: string | null;
}

/** Aggregate counts only — absent until gift tracking ships (#132). */
export interface GiftProgress {
  purchased: number;
  sent: number;
  received: number;
  total: number;
}

export interface ReadinessCounts {
  members: number;
  participating: number;
  not_participating: number;
  pending_invitations: number;
  wishlist_ready: number;
  address_ready: number;
  assignments_viewed: number;
  needs_nudge: number;
}

export interface GroupReadiness {
  group_id: string;
  status: GroupStatus;
  plan: PlanCode;
  requires_address: boolean;
  counts: ReadinessCounts;
  participants: ParticipantReadiness[];
  pending_invitations: PendingInvitation[];
  gift_progress?: GiftProgress | null;
}

/**
 * What each state is called, per dimension. Keyed by the union rather than by string, so a state
 * added to the backend enum fails this file to compile until somebody decides what to call it —
 * which is cheaper than shipping a row that renders a blank chip.
 */
export const READINESS_LABELS: Record<'wishlist' | 'address' | 'assignment', Record<ReadinessState, string>> = {
  wishlist: {
    ready: 'Wishlist ready',
    missing: 'No wishlist',
    not_required: 'Wishlist not needed',
    not_applicable: 'Not participating',
  },
  address: {
    ready: 'Address on file',
    missing: 'No address',
    not_required: 'Address not needed',
    not_applicable: 'Not participating',
  },
  assignment: {
    ready: 'Opened their match',
    missing: 'Has not looked yet',
    not_required: 'Not needed',
    not_applicable: 'Before the draw',
  },
};

/** What the organizer is being asked to chase, in the words they would use to chase it. */
export const NUDGE_LABELS: Record<NudgeReason, string> = {
  no_wishlist: 'Has not written a wishlist',
  no_address: 'Has not given a mailing address',
  assignment_not_viewed: 'Has not opened their match',
  invitation_not_accepted: 'Has not accepted their invitation',
};

export const PARTICIPANT_ROLE_LABELS: Record<ParticipantRole, string> = {
  owner: 'Owner',
  co_organizer: 'Co-organizer',
  participant: 'Participant',
};
