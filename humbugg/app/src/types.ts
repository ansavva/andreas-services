export type GroupStatus = 'open' | 'drawn';
export type PlanCode = 'free' | 'plus' | 'work';
export type PaymentStatus = 'pending' | 'paid' | 'failed' | 'expired' | 'refunded';

export interface ApiErrorPayload {
  error: { code: string; message: string };
}

/**
 * Recorded proof that a user actively agreed to the Terms of Service and Privacy Policy at signup
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
export interface ExchangeTemplate { template_id: string; name: string; exchange_name: string; description: string; event_date_offset_days: number; signup_deadline_offset_days: number; wishlist_prompt: string; exclusions_policy: string; reminders_enabled: boolean; customization: ExchangeCustomization; source_group_id?: string | null; }

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
  entitlement_id?: string | null;
  updated_at?: string | null;
}

export type WishKind = 'Product' | 'Custom' | 'Experience' | 'Charity';
export type WishPriority = 'Low' | 'Normal' | 'High';

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
