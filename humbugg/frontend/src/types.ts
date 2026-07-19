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
