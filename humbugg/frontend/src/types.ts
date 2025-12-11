export interface Profile {
  id: string;
  firstName?: string;
  lastName?: string;
  email?: string;
  pictureUrl?: string;
}

export interface GroupMember {
  id: string;
  groupId: string;
  firstName?: string;
  lastName?: string;
  address1?: string;
  address2?: string;
  city?: string;
  state?: string;
  postalCode?: string;
  isAdmin: boolean;
  isParticipating: boolean;
  recipientId?: string | null;
  giftSuggestionsDescription?: string;
  giftAvoidancesDescription?: string;
}

export interface Group {
  id: string;
  name: string;
  description?: string;
  secretQuestion?: string;
  secretQuestionAnswer?: string;
  signUpDeadline?: string;
  eventDate?: string;
  spendingLimit?: number;
  groupMembers: GroupMember[];
}
