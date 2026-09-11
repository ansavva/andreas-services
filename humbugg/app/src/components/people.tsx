// The organizer's one list of people: everyone who has joined and everyone who has been invited
// and not yet answered, with what each of them still has to do and what the organizer can do
// about it.
//
// It replaced three cards — "Needs a nudge", "Everyone", and "Invitations" — that were three views
// of the same people. The nudge list was the roster filtered to who had something outstanding; the
// invitations list was the roster's future members, with the actions that belong to an unanswered
// invitation. Somebody chasing an exchange read the same names three times and had to know which
// card held the button they wanted. Here it is one list, one row shape, and a filter instead of a
// second list (#682).
//
// Actions live in a menu on the row rather than as a row of secondary buttons. Three `secondary`
// `sm` buttons on a card are `bg-surface-alt` on a surface that is nearly that colour, and read as
// labels — "Send again  Nudge  Withdraw" looked like a status line. A menu is one control that
// announces itself as one, and holds the destructive action a step away from the others.
//
// Everything a row SHOWS is a read of state the server computed: readiness per dimension, and the
// invitation's delivery status. Nothing here decides who is ready.
import { Badge, Button, Dropdown, IconButton, Textarea, Toggle, ToggleGroup } from '@ansavva/design-system';
import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, Text, View, useWindowDimensions } from 'react-native';

import { api } from '../api/client';
import { useAuth } from '../context/auth-context';
import { gap, scopedStyles, useTheme } from '../theme/styles';
import type {
  GroupDetail,
  GroupReadiness,
  InvitationStatus,
  ManagedInvitation,
  ParticipantReadiness,
  ReadinessState,
} from '../types';
import { NUDGE_LABELS, PARTICIPANT_ROLE_LABELS, READINESS_LABELS } from '../types';
import { FieldLabel } from './field';
import { splitAddresses } from './invitations';
import { isPlusRequired, PlusLockedNote } from './plus';
import { Card } from './shell';
import { StatusMessage } from './status-message';

/** A state's tone. Only `missing` is a warning — the other three are all fine, in different ways. */
const TONE: Record<ReadinessState, 'success' | 'warning' | 'neutral'> = {
  ready: 'success',
  missing: 'warning',
  not_required: 'neutral',
  not_applicable: 'neutral',
};

/**
 * What each invitation status means to the person reading it, rather than what it is called in
 * the table. "sent" and "delivered" are deliberately different: a delivered invitation is the mail
 * provider's word that it arrived, which is the difference between chasing the address and chasing
 * the person.
 */
const INVITATION_STATUS: Record<InvitationStatus, { label: string; intent: 'success' | 'warning' | 'danger' | 'neutral' }> = {
  sent: { label: 'Sent', intent: 'neutral' },
  delivered: { label: 'Delivered', intent: 'neutral' },
  accepted: { label: 'Joined', intent: 'success' },
  bounced: { label: 'Bounced', intent: 'danger' },
  expired: { label: 'Expired', intent: 'warning' },
  revoked: { label: 'Revoked', intent: 'neutral' },
};

type Filter = 'all' | 'attention';

export function PeoplePanel({
  group,
  readiness,
  onChanged,
  onNeedsPlus,
  onAddLate,
}: {
  group: GroupDetail;
  readiness: GroupReadiness;
  /** The counts above change when somebody is invited, promoted, or an invitation is pulled. */
  onChanged(): void;
  /** A role change refused for want of Plus — the note is a whole card, so the screen owns it. */
  onNeedsPlus(): void;
  onAddLate(person: ParticipantReadiness): void;
}) {
  const { styles } = useTheme();
  const auth = useAuth();
  const { width } = useWindowDimensions();
  // Under 640px the badges go under the name instead of beside it; three chips beside a name on a
  // phone squeeze the name to two characters.
  const stacked = width < 640;
  const drawn = readiness.status === 'drawn';

  const [filter, setFilter] = useState<Filter>('all');
  const [inviting, setInviting] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Managed invitations are Plus. On Free the list is simply empty and the invite affordance is
  // the locked note — but only once somebody has pressed it, because a locked notice above an
  // untouched roster is an advert rather than an answer.
  const [invitations, setInvitations] = useState<ManagedInvitation[]>([]);
  const [invitationsLocked, setInvitationsLocked] = useState(false);
  const [invitationsError, setInvitationsError] = useState<string | null>(null);
  const loadInvitations = useCallback(async () => {
    try {
      setInvitations(await api.listInvitations(await auth.accessToken(), group.group_id));
      setInvitationsLocked(false);
      setInvitationsError(null);
    } catch (err) {
      if (isPlusRequired(err)) setInvitationsLocked(true);
      else setInvitationsError(err instanceof Error ? err.message : 'Unable to read the invitations.');
    }
  }, [auth, group.group_id]);
  useEffect(() => { void loadInvitations(); }, [loadInvitations]);

  // The rows: members first, then the invitations still in play. An accepted invitation IS a
  // member above; a revoked one is over. Bounced and expired stay, because both need a hand.
  const open = useMemo(
    () => invitations.filter((item) => item.status !== 'accepted' && item.status !== 'revoked'),
    [invitations],
  );
  const attention = readiness.participants.filter((person) => person.nudges.length > 0).length + open.length;
  const participants = filter === 'attention'
    ? readiness.participants.filter((person) => person.nudges.length > 0)
    : readiness.participants;
  const shownInvitations = open; // every open invitation needs attention by definition

  async function run(id: string, work: () => Promise<string | null>) {
    setBusy(id);
    setError(null);
    setNotice(null);
    try {
      const said = await work();
      setNotice(said);
      await loadInvitations();
      onChanged();
    } catch (err) {
      if (isPlusRequired(err)) onNeedsPlus();
      else setError(err instanceof Error ? err.message : 'That could not be done.');
    } finally {
      setBusy(null);
    }
  }

  /**
   * Promote or demote a co-organizer (#574). Owner-only, and the backend says so —
   * `UpdateOrganizerRoleAsync` calls `RequireOwner` before it checks the plan. A co-organizer
   * seeing this item could only ever be told no, so `group.is_owner` decides whether it is drawn.
   */
  const setRole = (person: ParticipantReadiness, isOrganizer: boolean) =>
    run(person.member_id, async () => {
      await api.setOrganizerRole(await auth.accessToken(), group.group_id, person.member_id, isOrganizer);
      return null;
    });

  /**
   * Resend, nudge, or withdraw. "Nudge" is `sendReminder`, a different thing from
   * `resendInvitation` even though both put mail in the same inbox: a resend sends the invitation
   * again, a nudge sends a reminder ABOUT it and is counted against the reminder schedule. It
   * refuses when reminders were never configured, and that refusal is shown as it comes.
   */
  const act = (invitation: ManagedInvitation, what: 'resend' | 'nudge' | 'revoke') =>
    run(invitation.invitation_id, async () => {
      const token = await auth.accessToken();
      if (what === 'resend') {
        await api.resendInvitation(token, group.group_id, invitation.invitation_id);
        return `Sent again to ${invitation.email}.`;
      }
      if (what === 'nudge') {
        await api.sendReminder(token, group.group_id, invitation.invitation_id, 'unaccepted_invitation');
        return `Reminded ${invitation.email}.`;
      }
      await api.revokeInvitation(token, group.group_id, invitation.invitation_id);
      return `Withdrew the invitation to ${invitation.email}.`;
    });

  const total = readiness.counts.members + open.length;
  const nothingToShow = participants.length === 0 && shownInvitations.length === 0;

  return (
    <Card>
      <View style={local.panelHeading}>
        <View style={{ flex: 1, minWidth: 200 }}>
          <Text style={styles.eyebrow}>People</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>
            {readiness.counts.members === 0 && open.length === 0
              ? 'Nobody yet'
              : `${readiness.counts.members} ${readiness.counts.members === 1 ? 'person' : 'people'}${open.length > 0 ? `, ${open.length} invited` : ''}`}
          </Text>
        </View>
        <Button intent="secondary" size="sm" onPress={() => setInviting((current) => !current)}>
          {inviting ? 'Done inviting' : 'Invite by email'}
        </Button>
      </View>

      {inviting ? (
        invitationsLocked ? (
          <View style={{ marginTop: 20 }}>
            <PlusLockedNote
              reason="Sending and tracking invitations is part of Plus."
              action="invite people by email and see who has not answered"
              isOwner={group.is_owner}
            />
          </View>
        ) : (
          <InviteByEmail group={group} onSent={(said) => { setNotice(said); void loadInvitations(); onChanged(); }} />
        )
      ) : null}

      <View style={{ marginTop: 20 }}>
        <StatusMessage message={error ?? invitationsError} />
        <StatusMessage message={notice} tone="success" />
      </View>

      {/* A filter, not a second list. "Needs attention" is the roster with the ready rows folded
          away: the same people, the same rows, the same menu. */}
      {total > 0 ? (
        <View style={{ marginTop: 16 }}>
          <ToggleGroup.Root
            value={[filter]}
            onValueChange={(value) => setFilter((value[0] as Filter | undefined) ?? 'all')}
            size="sm"
            style={{ flexDirection: 'row', gap: 6 }}
          >
            <Toggle value="all">Everyone ({total})</Toggle>
            <Toggle value="attention">Needs attention ({attention})</Toggle>
          </ToggleGroup.Root>
        </View>
      ) : null}

      {nothingToShow ? (
        <View style={[styles.emptyPanel, { marginTop: 24 }]}>
          <Text style={styles.bodyMuted}>
            {total === 0
              ? 'Nobody has joined yet. Share the invitation link, or invite people by email.'
              : 'Nobody needs a nudge — everyone has done what the exchange asks.'}
          </Text>
        </View>
      ) : (
        <View style={{ marginTop: 20, gap: 12 }}>
          {participants.map((person) => {
            const chips = person.is_participating ? (
              <View style={[local.chips, stacked && local.chipsStacked]}>
                <StateBadge
                  state={person.wishlist}
                  label={
                    person.wishlist === 'ready' && person.wish_count > 0
                      ? `${person.wish_count} ${person.wish_count === 1 ? 'wish' : 'wishes'}`
                      : READINESS_LABELS.wishlist[person.wishlist]
                  }
                />
                {person.address === 'not_required' ? null : (
                  <StateBadge state={person.address} label={READINESS_LABELS.address[person.address]} />
                )}
                {person.assignment === 'not_applicable' ? null : (
                  <StateBadge state={person.assignment} label={READINESS_LABELS.assignment[person.assignment]} />
                )}
              </View>
            ) : null;
            const menu = (
              <RowMenu
                label={`Actions for ${person.display_name}`}
                disabled={busy !== null}
                items={[
                  // A late participant is a member who is NOT participating — the backend's own
                  // definition — so the sitting-out rows after a draw are exactly the candidates.
                  ...(drawn && !person.is_participating
                    ? [{ label: 'Add to the draw', onSelect: () => onAddLate(person) }]
                    : []),
                  ...(group.is_owner && person.role !== 'owner'
                    ? [{
                        label: person.role === 'co_organizer' ? 'Remove as organizer' : 'Make organizer',
                        onSelect: () => void setRole(person, person.role !== 'co_organizer'),
                      }]
                    : []),
                ]}
              />
            );
            return (
              <PersonRow key={person.member_id} label={rowLabel(person, drawn)} stacked={stacked} chips={chips} menu={menu}>
                <View style={styles.avatarChip}>
                  <Text style={styles.avatarChipText}>{person.display_name[0]?.toUpperCase()}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={[styles.small, styles.semibold]}>{person.display_name}</Text>
                  <Text style={styles.tiny}>
                    {person.nudges.length > 0
                      ? person.nudges.map((reason) => NUDGE_LABELS[reason]).join(' · ')
                      : `${PARTICIPANT_ROLE_LABELS[person.role]}${person.is_participating ? '' : ' · Sitting out'}`}
                  </Text>
                </View>
              </PersonRow>
            );
          })}

          {shownInvitations.map((invitation) => (
            <PersonRow
              key={invitation.invitation_id}
              label={`${invitation.email}, invited, ${INVITATION_STATUS[invitation.status].label}`}
              stacked={stacked}
              chips={
                <View style={[local.chips, stacked && local.chipsStacked]}>
                  <Badge intent={INVITATION_STATUS[invitation.status].intent} size="sm">
                    {INVITATION_STATUS[invitation.status].label}
                  </Badge>
                </View>
              }
              menu={
                <RowMenu
                  label={`Actions for ${invitation.email}`}
                  disabled={busy !== null}
                  items={[
                    { label: 'Send again', onSelect: () => void act(invitation, 'resend') },
                    { label: 'Nudge', onSelect: () => void act(invitation, 'nudge') },
                    { label: 'Withdraw', onSelect: () => void act(invitation, 'revoke'), destructive: true },
                  ]}
                />
              }
            >
              <View style={styles.avatarChip}>
                <Text style={styles.avatarChipText}>@</Text>
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={[styles.small, styles.semibold]}>{invitation.email}</Text>
                <Text style={styles.tiny}>{invitationDetail(invitation)}</Text>
              </View>
            </PersonRow>
          ))}
        </View>
      )}
    </Card>
  );
}

/**
 * One row, two arrangements. Wide: avatar and name, then the badges, then the menu, in a line.
 * Stacked (under 640px): avatar, name and menu on the first line — the menu stays where a thumb
 * expects it, top right — and the badges on a second line under the name.
 */
function PersonRow({
  label,
  stacked,
  chips,
  menu,
  children,
}: {
  label: string;
  stacked: boolean;
  chips: React.ReactNode;
  menu: React.ReactNode;
  children: React.ReactNode;
}) {
  const { styles } = useTheme();
  if (!stacked)
    return (
      <View accessibilityLabel={label} style={styles.memberRow}>
        <View style={local.rowIdentity}>{children}</View>
        {chips}
        {menu}
      </View>
    );
  return (
    <View accessibilityLabel={label} style={[styles.memberRow, local.rowStacked]}>
      <View style={[local.rowIdentity, { alignSelf: 'stretch' }]}>
        {children}
        {menu}
      </View>
      {chips}
    </View>
  );
}

/** The address box, shown while inviting. Addresses go in, Humbugg sends and tracks each one. */
function InviteByEmail({ group, onSent }: { group: GroupDetail; onSent(said: string): void }) {
  const { styles } = useTheme();
  const auth = useAuth();
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const addresses = splitAddresses(draft);

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.createInvitations(await auth.accessToken(), group.group_id, addresses);
      setDraft('');
      onSent(
        result.invitations.length === 1
          ? `Invitation sent to ${result.invitations[0].email}.`
          : `${result.invitations.length} invitations sent.`,
      );
    } catch (err) {
      // Every refusal names the address or the reason — a duplicate, an address already invited,
      // one that is not an address. The server's own words are what make the fix obvious.
      setError(err instanceof Error ? err.message : 'The invitations could not be sent.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={{ marginTop: 20, gap: gap.md }}>
      <Text style={styles.smallMuted}>
        Humbugg sends each one and tells you what happened to it. They join by following their own
        link, so you never have to pass one on.
      </Text>
      <FieldLabel
        label="Email addresses"
        help="One per line, or separated by commas — however they come out of wherever you keep them."
      >
        <Textarea
          maxLength={4000}
          value={draft}
          onValueChange={(value) => { setDraft(value); setError(null); }}
          placeholder={'robin@example.com\nsam@example.com'}
        />
      </FieldLabel>
      <StatusMessage message={error} />
      <View style={{ alignSelf: 'flex-start' }}>
        <Button disabled={busy || addresses.length === 0} onPress={() => void send()}>
          {busy ? 'Sending…' : addresses.length <= 1 ? 'Send the invitation' : `Send ${addresses.length} invitations`}
        </Button>
      </View>
    </View>
  );
}

/**
 * The row's actions, behind one control. Rendered only when there is something to do — an
 * organizer looking at their own row, or a co-organizer looking at anyone's, gets no empty menu.
 *
 * The backdrop and the controlled `open` are the avatar menu's arrangement: native `Dropdown` has
 * no press-outside dismissal, so a sibling behind the menu gives it back.
 */
function RowMenu({
  label,
  items,
  disabled,
}: {
  label: string;
  items: { label: string; onSelect(): void; destructive?: boolean }[];
  disabled: boolean;
}) {
  const { styles } = useTheme();
  const local = localStyles(useTheme());
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <>
      {open ? (
        <Pressable
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          onPress={() => setOpen(false)}
          style={local.backdrop}
        />
      ) : null}
      <Dropdown.Root open={open} onOpenChange={setOpen}>
        <IconButton
          label={label}
          intent="secondary"
          size="sm"
          disabled={disabled}
          onPress={() => setOpen((current) => !current)}
        >
          <Text style={local.ellipsis}>⋯</Text>
        </IconButton>
        <Dropdown.Content accessibilityLabel={label} style={[styles.menu, local.anchorRight]}>
          {items.map((item) => (
            <Dropdown.Item
              key={item.label}
              onSelect={() => { setOpen(false); item.onSelect(); }}
            >
              {item.label}
            </Dropdown.Item>
          ))}
        </Dropdown.Content>
      </Dropdown.Root>
    </>
  );
}

function StateBadge({ state, label }: { state: ReadinessState; label: string }) {
  return <Badge intent={TONE[state]} size="sm">{label}</Badge>;
}

/**
 * One sentence per row for a screen reader, so a roster is listenable without stepping through
 * three separate chips per person and rebuilding the sentence by hand.
 */
export function rowLabel(person: ParticipantReadiness, drawn: boolean): string {
  const parts = [person.display_name, PARTICIPANT_ROLE_LABELS[person.role]];
  if (!person.is_participating) return `${parts.join(', ')}, not participating`;
  parts.push(READINESS_LABELS.wishlist[person.wishlist]);
  if (person.address !== 'not_required') parts.push(READINESS_LABELS.address[person.address]);
  if (drawn) parts.push(READINESS_LABELS.assignment[person.assignment]);
  return parts.join(', ');
}

/** The one line under an address: what happened to this invitation, and when. */
function invitationDetail(invitation: ManagedInvitation): string {
  if (invitation.status === 'bounced') return 'The address did not accept it — check it for a typo';
  if (invitation.status === 'expired') return `Invited · expired ${when(invitation.expires_at)}`;
  const sent = invitation.last_sent_at ? `Invited ${when(invitation.last_sent_at)}` : 'Invited';
  return `${sent} · expires ${when(invitation.expires_at)}`;
}

function when(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return 'at an unknown time';
  return at.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

const local = {
  panelHeading: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: gap.md,
  } as const,
  rowIdentity: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 13 } as const,
  rowStacked: { alignItems: 'flex-start', flexDirection: 'column', gap: 10 } as const,
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, justifyContent: 'flex-end' } as const,
  chipsStacked: { justifyContent: 'flex-start', paddingLeft: 49 } as const,
};

/** Built once per scheme — see `scopedStyles`. */
const localStyles = scopedStyles((t) => ({
  backdrop: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, zIndex: 10 },
  anchorRight: { right: 0, left: 'auto' },
  ellipsis: { color: t.brand.ink, fontSize: 18, lineHeight: 18, fontWeight: '700' },
}));
