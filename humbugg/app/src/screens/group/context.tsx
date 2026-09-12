// What every page of one exchange shares (#690).
//
// The exchange is a layout route with pages under it — `giving`, `you`, `people`, `draw`,
// `settings/*` — and the layout reads the group once for all of them. This is how a page gets at
// it: the group, the caller's own membership, their assignment once drawn, and the organizer's
// readiness read; plus the two ways of changing things that need the page to re-read afterwards.
//
// Every value here is already loaded. The layout renders a spinner or a failure until it has the
// group and the membership, so a page never has to ask "is it there yet".
import { createContext, useContext } from 'react';

import type { GroupDetail, GroupReadiness, Membership, RecipientAssignment } from '../../types';

export interface GroupContextValue {
  groupId: string;
  group: GroupDetail;
  /** The caller's own membership row. */
  me: Membership;
  /** Who the caller drew — present only after the draw, and only for someone taking part. */
  assignment: RecipientAssignment | null;
  /** The organizer's roster read. `null` until it lands, and forever for a participant. */
  readiness: GroupReadiness | null;
  readinessError: string | null;
  busy: boolean;
  /** A save that returned the new group — the header follows it without a round trip. */
  setGroup(next: GroupDetail): void;
  /** Re-read everything quietly: the group, the membership, the assignment and the roster. */
  reload(): Promise<void>;
  /**
   * Run something that changes the group or the membership, say what happened, and re-read. The
   * layout shows the message, or the error, or the Plus offer a 402 is, under the header.
   */
  action(work: (token: string) => Promise<unknown>, message?: string): Promise<boolean>;
  /**
   * A change to the caller's own claims or gift stage: both calls answer with the whole assignment,
   * so this swaps it in rather than re-reading the group. See the layout for why.
   */
  claimAction(work: (token: string) => Promise<RecipientAssignment>): Promise<void>;
}

export const GroupContext = createContext<GroupContextValue | null>(null);

export function useGroup(): GroupContextValue {
  const value = useContext(GroupContext);
  if (!value) throw new Error('useGroup must be used inside the exchange layout');
  return value;
}

/** The pages of an exchange, in tab order. `settings` has sections of its own. */
export type GroupTab = 'giving' | 'you' | 'people' | 'draw' | 'settings';

/** First name only: the tab says who, the page says the rest. */
export function firstName(displayName: string): string {
  return displayName.trim().split(/\s+/)[0] ?? displayName;
}
