export type GroupStatus = 'open' | 'drawn';
export type PlanCode = 'free' | 'plus' | 'work';

export interface ApiErrorPayload {
  error: { code: string; message: string };
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
}

export interface Membership {
  member_id: string;
  display_name: string;
  is_organizer: boolean;
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
    role: 'organizer' | 'participant';
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
  created_at: string;
  updated_at: string;
}

export interface GroupDetail extends GroupSummary {
  description: string;
  signup_deadline?: string | null;
  exclusions: ExclusionPair[];
  members: Membership[];
  invite_url?: string;
}

export interface RecipientAssignment {
  member_id: string;
  display_name: string;
  wishlist: string;
  avoidances: string;
  address: Address;
}

export interface RevealAssignment {
  giver: Membership;
  recipient: RecipientAssignment;
}
