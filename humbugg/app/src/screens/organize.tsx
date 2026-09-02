// The organizer readiness dashboard (#133) — "is this exchange ready, and who do I chase?".
//
// It is a READ of state the server computed. Nothing here decides whether someone is ready: the API
// returns a state per dimension and this screen renders its label, so the roll-up, the nudge list
// and the participant row cannot disagree with each other or with the backend.
//
// It is also deliberately its own route rather than another panel on the group screen. An organizer
// asking "who is holding this up" is doing a different job from a participant writing their list,
// and the six shipped Plus features — the invitation list, reminder settings, co-organizer
// management, the template picker — have no surface to live on until one exists.
import { Badge, Button, Meter, Switch } from '@ansavva/design-system';
import { Link, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { api, ApiError } from '../api/client';
import { CustomizationPanel } from '../components/customization';
import { InvitationsPanel } from '../components/invitations';
import { LateParticipantPanel } from '../components/late-participant';
import { isPlusRequired, PlusBillingPanel, PlusLockedNote } from '../components/plus';
import { RemindersPanel } from '../components/reminders';
import { TemplatesPanel } from '../components/templates';
import { Card, LoadingPanel, Shell } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { useAuth } from '../context/auth-context';
import { blends, gap, styles } from '../theme/styles';
import type {
  GroupDetail,
  GroupReadiness,
  ParticipantReadiness,
  PendingInvitation,
  ReadinessState,
} from '../types';
import { NUDGE_LABELS, PARTICIPANT_ROLE_LABELS, READINESS_LABELS } from '../types';

/** A state's tone. Only `missing` is a warning — the other three are all fine, in different ways. */
const TONE: Record<ReadinessState, 'success' | 'warning' | 'neutral'> = {
  ready: 'success',
  missing: 'warning',
  not_required: 'neutral',
  not_applicable: 'neutral',
};

export default function OrganizeScreen({
  groupId,
  checkout,
}: {
  groupId: string;
  /** Stripe's `?checkout=` return value on the web. Native returns by closing the browser instead. */
  checkout?: string | null;
}) {
  const auth = useAuth();
  const router = useRouter();
  const [group, setGroup] = useState<GroupDetail | null>(null);
  const [readiness, setReadiness] = useState<GroupReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [rolesNeedPlus, setRolesNeedPlus] = useState(false);
  const [lateNeedsPlus, setLateNeedsPlus] = useState(false);
  const [addingLate, setAddingLate] = useState<ParticipantReadiness | null>(null);

  /**
   * `quiet` re-reads without the full-screen loading state.
   *
   * It exists for the billing panel. A loud reload swaps the whole screen for `LoadingPanel`,
   * which UNMOUNTS that panel — and since Stripe's `?checkout=success` is still in the URL, the
   * remounted panel starts confirming again, reaches the same entitlement, and asks for another
   * reload. That is a loop, and it was one until this argument existed.
   */
  async function load(quiet = false) {
    if (!quiet) setLoading(true);
    setError(null);
    try {
      const token = await auth.accessToken();
      const [detail, overview] = await Promise.all([
        api.getGroup(token, groupId),
        api.getReadiness(token, groupId),
      ]);
      setGroup(detail);
      setReadiness(overview);
    } catch (err) {
      // A participant who follows this URL gets told what happened rather than an empty screen.
      if (err instanceof ApiError && err.status === 403) setForbidden(true);
      else setError(err instanceof Error ? err.message : 'Unable to load the dashboard.');
    } finally {
      if (!quiet) setLoading(false);
    }
  }

  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [groupId]);

  async function setRequiresAddress(next: boolean) {
    setBusy(true);
    setError(null);
    try {
      await api.updateGroup(await auth.accessToken(), groupId, { requires_address: next });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The setting could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Shell><LoadingPanel>Checking who is ready…</LoadingPanel></Shell>;

  if (forbidden || !group || !readiness) {
    return (
      <Shell>
        <View style={{ maxWidth: 576, alignSelf: 'center', width: '100%' }}>
          <StatusMessage
            message={
              forbidden
                ? 'Only an organizer of this exchange can see its readiness dashboard.'
                : error ?? 'This exchange could not be opened.'
            }
          />
          <Link href={`/groups/${groupId}`} style={[styles.link, { marginTop: 16 }]}>
            Back to the exchange
          </Link>
        </View>
      </Shell>
    );
  }

  const { counts } = readiness;
  const drawn = readiness.status === 'drawn';

  return (
    <Shell>
      <Link href={`/groups/${groupId}`} style={[styles.smallMuted, { marginBottom: 24 }]}>
        ← {group.name}
      </Link>
      <View style={{ gap: 28 }}>
        <View style={styles.groupHeading}>
          <View>
            <Text style={styles.eyebrow}>Organizer dashboard</Text>
            <Text style={[styles.displayLg, { marginTop: 16 }]}>Who is ready</Text>
            <Text style={[styles.bodyMuted, { marginTop: 12, maxWidth: 672 }]}>
              What everyone still has to do, and nothing they wrote. You can see that a list is
              empty; you cannot see what is on it, and you never see who drew whom.
            </Text>
          </View>
        </View>

        <StatusMessage message={error} />

        <StatRow>
          <Stat
            label="Taking part"
            value={`${counts.participating}`}
            detail={
              counts.not_participating > 0
                ? `${counts.not_participating} sitting out`
                : counts.pending_invitations > 0
                  ? `${counts.pending_invitations} invited, not joined`
                  : 'Everyone who joined'
            }
          />
          <Stat
            label="Wishlists"
            value={`${counts.wishlist_ready} of ${counts.participating}`}
            ready={counts.wishlist_ready}
            total={counts.participating}
          />
          <Stat
            label="Addresses"
            value={
              readiness.requires_address
                ? `${counts.address_ready} of ${counts.participating}`
                : 'Not needed'
            }
            detail={readiness.requires_address ? undefined : 'Gifts are not posted'}
            ready={readiness.requires_address ? counts.address_ready : undefined}
            total={counts.participating}
          />
          <Stat
            label="Matches opened"
            value={drawn ? `${counts.assignments_viewed} of ${counts.participating}` : 'Before the draw'}
            detail={drawn ? undefined : 'Draw first'}
            ready={drawn ? counts.assignments_viewed : undefined}
            total={counts.participating}
          />
        </StatRow>

        <NudgePanel
          participants={readiness.participants}
          invitations={readiness.pending_invitations}
          total={counts.needs_nudge}
        />

        <RosterPanel
          readiness={readiness}
          group={group}
          onRoleChanged={() => void load(true)}
          onNeedsPlus={() => setRolesNeedPlus(true)}
          onAddLate={setAddingLate}
        />

        {/* The late-participant flow, which is a decision rather than a control: it moves matches
            people may already have acted on, so it gets a panel of its own with the count in it. */}
        {addingLate ? (
          <LateParticipantPanel
            groupId={groupId}
            person={addingLate}
            onCancel={() => setAddingLate(null)}
            onAdded={() => { setAddingLate(null); void load(true); }}
            onNeedsPlus={() => { setAddingLate(null); setLateNeedsPlus(true); }}
          />
        ) : null}

        {lateNeedsPlus ? (
          <PlusLockedNote
            reason="Adding somebody after the draw is part of Plus."
            action="fit a late arrival in, changing as few matches as possible"
            isOwner={group.is_owner}
          />
        ) : null}

        {/*
          The roster's own "Make organizer" refusal. It is a whole card, so it cannot live inside a
          participant row — and it only appears once somebody has actually tried, because a locked
          notice above an untouched roster is an advert rather than an answer.
        */}
        {rolesNeedPlus ? (
          <PlusLockedNote
            reason="Sharing the organizing is part of Plus."
            action="hand the running of this exchange to somebody alongside you"
            isOwner={group.is_owner}
          />
        ) : null}

        <InvitationsPanel group={group} onChanged={() => void load(true)} />

        {/* Reminders sit under invitations because the first thing they chase is an unanswered
            invitation, and the settings read as nonsense before you have sent one. */}
        <RemindersPanel group={group} />

        <CustomizationPanel group={group} onSaved={setGroup} />

        <TemplatesPanel group={group} onApplied={(next) => { setGroup(next); void load(true); }} />

        <GiftProgressPanel readiness={readiness} />

        {/*
          The organizer's billing area (#141). Owner-only: `GET .../billing/plus` refuses a
          co-organizer, so a co-organizer would get a panel that could only show its own error.
        */}
        {group.is_owner ? (
          <PlusBillingPanel group={group} checkout={checkout} onEntitled={() => void load(true)} />
        ) : null}

        <Card>
          <Text style={styles.eyebrow}>Exchange setting</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>Are these gifts posted?</Text>
          <View style={local.settingRow}>
            <View style={{ flex: 1, minWidth: 220 }}>
              <Text style={styles.small}>
                Turn this on and the dashboard asks every participant for a mailing address. Leave it
                off for an exchange where the gifts change hands in person.
              </Text>
            </View>
            <Switch.Root
              checked={readiness.requires_address}
              disabled={busy}
              aria-label="Gifts are posted to a mailing address"
              onCheckedChange={(checked) => void setRequiresAddress(checked)}
            >
              <Switch.Thumb />
            </Switch.Root>
          </View>
        </Card>

        {readiness.status === 'open' ? (
          <View style={{ alignSelf: 'flex-start' }}>
            <Button intent="secondary" onPress={() => router.push(`/groups/${groupId}`)}>
              Back to organizer tools
            </Button>
          </View>
        ) : null}
      </View>
    </Shell>
  );
}

/**
 * The stat tiles. One column on a phone, two on a small tablet, four on a desktop.
 *
 * The cells are `flexBasis: 0` + `flexGrow: 1` and the break is forced by `minWidth`, NOT by a
 * percentage basis. A basis of `100 / columns`% ignores the row's `gap`, so four 25% tiles plus
 * three gaps overflow by the gaps and the fourth wraps to a row of its own — a full-width orphan
 * under three tiles, which is what this looked like the first time it was rendered.
 */
function StatRow({ children }: { children: React.ReactNode }) {
  const { width } = useWindowDimensions();
  const columns = width < 640 ? 1 : width < 1024 ? 2 : 4;
  const minWidth = columns === 1 ? '100%' : columns === 2 ? '45%' : 0;
  return (
    <View style={local.statRow}>
      {Array.isArray(children)
        ? children.map((child, index) => (
            <View key={index} style={{ flexBasis: 0, flexGrow: 1, minWidth }}>
              {child}
            </View>
          ))
        : children}
    </View>
  );
}

function Stat({
  label,
  value,
  detail,
  ready,
  total,
}: {
  label: string;
  value: string;
  detail?: string;
  /** Supplying both draws a meter under the number. Omit `ready` when the question does not apply. */
  ready?: number;
  total?: number;
}) {
  const showMeter = ready !== undefined && total !== undefined && total > 0;
  return (
    <Card style={local.stat}>
      <Text style={styles.eyebrow}>{label}</Text>
      <Text style={[styles.displayMd, { marginTop: 8 }]}>{value}</Text>
      {showMeter ? (
        <Meter.Root
          value={ready}
          max={total}
          aria-label={`${label}: ${ready} of ${total}`}
          style={{ marginTop: 12 }}
        >
          <Meter.Track>
            <Meter.Indicator />
          </Meter.Track>
        </Meter.Root>
      ) : null}
      {detail ? <Text style={[styles.tiny, { marginTop: 8 }]}>{detail}</Text> : null}
    </Card>
  );
}

function NudgePanel({
  participants,
  invitations,
  total,
}: {
  participants: ParticipantReadiness[];
  invitations: PendingInvitation[];
  total: number;
}) {
  const outstanding = participants.filter((person) => person.nudges.length > 0);
  return (
    <Card style={total > 0 ? { borderColor: blends.primaryBorder } : undefined}>
      <View style={local.panelHeading}>
        <View>
          <Text style={styles.eyebrow}>Needs a nudge</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>
            {total === 0 ? 'Nobody — everyone is ready' : `${total} to chase`}
          </Text>
        </View>
        <View style={styles.countBadge}>
          <Text style={styles.countBadgeText}>{total}</Text>
        </View>
      </View>

      {total === 0 ? (
        <View style={[styles.emptyPanel, { marginTop: 24 }]}>
          <Text style={styles.bodyMuted}>Every participant has done what the exchange asks.</Text>
        </View>
      ) : (
        <View style={{ marginTop: 24, gap: 12 }}>
          {outstanding.map((person) => (
            <View key={person.member_id} style={styles.memberRow}>
              <View style={styles.avatarChip}>
                <Text style={styles.avatarChipText}>{person.display_name[0]?.toUpperCase()}</Text>
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={[styles.small, styles.semibold]}>{person.display_name}</Text>
                <Text style={styles.tiny}>
                  {person.nudges.map((reason) => NUDGE_LABELS[reason]).join(' · ')}
                </Text>
              </View>
            </View>
          ))}
          {invitations.map((invitation) => (
            <View key={invitation.invitation_id} style={styles.memberRow}>
              <View style={styles.avatarChip}>
                <Text style={styles.avatarChipText}>@</Text>
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={[styles.small, styles.semibold]}>{invitation.email}</Text>
                <Text style={styles.tiny}>
                  {invitation.status === 'bounced'
                    ? 'Their invitation bounced — check the address'
                    : NUDGE_LABELS.invitation_not_accepted}
                </Text>
              </View>
            </View>
          ))}
        </View>
      )}
    </Card>
  );
}

function RosterPanel({
  readiness,
  group,
  onRoleChanged,
  onNeedsPlus,
  onAddLate,
}: {
  readiness: GroupReadiness;
  group: GroupDetail;
  onRoleChanged(): void;
  onNeedsPlus(): void;
  onAddLate(person: ParticipantReadiness): void;
}) {
  const auth = useAuth();
  const { width } = useWindowDimensions();
  // Under 640px the badges go under the name instead of beside it; three chips beside a name on a
  // phone squeeze the name to two characters.
  const stacked = width < 640;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  /**
   * Promote or demote a co-organizer (#574).
   *
   * Owner-only, and the backend says so: `UpdateOrganizerRoleAsync` calls `RequireOwner` before it
   * checks the plan. A co-organizer seeing these buttons could only ever be told no, so
   * `group.is_owner` decides whether they are drawn at all rather than whether they work.
   */
  async function setRole(person: ParticipantReadiness, isOrganizer: boolean) {
    setBusy(person.member_id);
    setError(null);
    try {
      await api.setOrganizerRole(
        await auth.accessToken(),
        group.group_id,
        person.member_id,
        isOrganizer,
      );
      onRoleChanged();
    } catch (err) {
      if (isPlusRequired(err)) onNeedsPlus();
      else setError(err instanceof Error ? err.message : 'That role could not be changed.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <View style={local.panelHeading}>
        <View>
          <Text style={styles.eyebrow}>Everyone</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>The full roster</Text>
        </View>
        <View style={styles.countBadge}>
          <Text style={styles.countBadgeText}>{readiness.counts.members}</Text>
        </View>
      </View>

      <View style={{ marginTop: error ? 20 : 0 }}>
        <StatusMessage message={error} />
      </View>

      {readiness.participants.length === 0 ? (
        <View style={[styles.emptyPanel, { marginTop: 24 }]}>
          <Text style={styles.bodyMuted}>Nobody has joined yet. Share the invitation link.</Text>
        </View>
      ) : (
        <View style={{ marginTop: 24, gap: 12 }}>
          {readiness.participants.map((person) => (
            <View
              key={person.member_id}
              accessibilityLabel={rowLabel(person, readiness.status === 'drawn')}
              style={[styles.memberRow, stacked && local.rowStacked]}
            >
              <View style={local.rowIdentity}>
                <View style={styles.avatarChip}>
                  <Text style={styles.avatarChipText}>{person.display_name[0]?.toUpperCase()}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={[styles.small, styles.semibold]}>{person.display_name}</Text>
                  <Text style={styles.tiny}>
                    {PARTICIPANT_ROLE_LABELS[person.role]}
                    {person.is_participating ? '' : ' · Sitting out'}
                  </Text>
                </View>
              </View>
              {person.is_participating ? (
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
                    <StateBadge
                      state={person.assignment}
                      label={READINESS_LABELS.assignment[person.assignment]}
                    />
                  )}
                </View>
              ) : null}
              {group.is_owner && person.role !== 'owner' ? (
                <Button
                  intent="secondary"
                  size="sm"
                  disabled={busy !== null}
                  onPress={() => void setRole(person, person.role !== 'co_organizer')}
                >
                  {person.role === 'co_organizer' ? 'Remove as organizer' : 'Make organizer'}
                </Button>
              ) : null}
              {/* A late participant is a member who is NOT participating — the backend's own
                  definition — so the sitting-out rows after a draw are exactly the candidates. */}
              {readiness.status === 'drawn' && !person.is_participating ? (
                <Button intent="secondary" size="sm" onPress={() => onAddLate(person)}>
                  Add to the draw
                </Button>
              ) : null}
            </View>
          ))}
        </View>
      )}
    </Card>
  );
}

function StateBadge({ state, label }: { state: ReadinessState; label: string }) {
  return <Badge intent={TONE[state]} size="sm">{label}</Badge>;
}

/**
 * One sentence per row for a screen reader, so a roster is listenable without stepping through
 * three separate chips per person and rebuilding the sentence by hand.
 */
function rowLabel(person: ParticipantReadiness, drawn: boolean): string {
  const parts = [person.display_name, PARTICIPANT_ROLE_LABELS[person.role]];
  if (!person.is_participating) return `${parts.join(', ')}, not participating`;
  parts.push(READINESS_LABELS.wishlist[person.wishlist]);
  if (person.address !== 'not_required') parts.push(READINESS_LABELS.address[person.address]);
  if (drawn) parts.push(READINESS_LABELS.assignment[person.assignment]);
  return parts.join(', ');
}

function GiftProgressPanel({ readiness }: { readiness: GroupReadiness }) {
  const progress = readiness.gift_progress;
  return (
    <Card>
      <Text style={styles.eyebrow}>Gift progress</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Purchased, sent and received</Text>
      {progress ? (
        <StatRow>
          <Stat label="Purchased" value={`${progress.purchased} of ${progress.total}`} ready={progress.purchased} total={progress.total} />
          <Stat label="Sent" value={`${progress.sent} of ${progress.total}`} ready={progress.sent} total={progress.total} />
          <Stat label="Received" value={`${progress.received} of ${progress.total}`} ready={progress.received} total={progress.total} />
        </StatRow>
      ) : (
        <View style={[styles.emptyPanel, { marginTop: 24 }]}>
          {/*
            Deliberately not three zeroes. Before a draw nobody has been asked to buy anything, so
            the API sends no progress at all; "0 of 5 purchased" would be a claim about the world,
            and this one would be false.
          */}
          <Text style={styles.bodyMuted}>Nothing to track yet.</Text>
          <Text style={[styles.tiny, { marginTop: 8, textAlign: 'center' }]}>
            Once the draw is done and givers start marking gifts bought, sent and received, the
            totals appear here — as counts only, so they never reveal who is giving to whom.
          </Text>
        </View>
      )}
    </Card>
  );
}

const local = StyleSheet.create({
  statRow: { flexDirection: 'row', flexWrap: 'wrap', gap: gap.md },
  stat: { padding: 20, height: '100%' },
  panelHeading: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: gap.md,
  },
  settingRow: {
    marginTop: 24,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: gap.md,
  },
  rowIdentity: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 13 },
  rowStacked: { alignItems: 'flex-start', flexDirection: 'column', gap: 10 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, justifyContent: 'flex-end' },
  chipsStacked: { justifyContent: 'flex-start', paddingLeft: 49 },
});
