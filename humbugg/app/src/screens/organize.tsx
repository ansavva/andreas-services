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
import { Button, Meter, Tabs } from '@ansavva/design-system';
import { Link, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { api, ApiError } from '../api/client';
import { SettingsTab } from '../components/settings-tab';
import { LateParticipantPanel } from '../components/late-participant';
import { PeoplePanel } from '../components/people';
import { PlusBillingPanel, PlusLockedNote } from '../components/plus';
import { Card, LoadingPanel, Shell } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { useAuth } from '../context/auth-context';
import { gap, useTheme } from '../theme/styles';
import type { GroupDetail, GroupReadiness, ParticipantReadiness } from '../types';

export default function OrganizeScreen({
  groupId,
  checkout,
}: {
  groupId: string;
  /** Stripe's `?checkout=` return value on the web. Native returns by closing the browser instead. */
  checkout?: string | null;
}) {
  const { styles } = useTheme();
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

  if (loading) return <Shell><LoadingPanel /></Shell>;

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
  const atFreeCeiling = group.plan === 'free' && counts.participating >= group.participant_limit;

  return (
    <Shell>
      <Link href={`/groups/${groupId}`} style={[styles.smallMuted, { marginBottom: 24 }]}>
        ← {group.name}
      </Link>
      <View style={{ gap: 28 }}>
        <View style={styles.groupHeading}>
          <View>
            <Text style={styles.eyebrow}>Organizer dashboard</Text>
            <Text style={[styles.displayLg, { marginTop: 16 }]}>{group.name}</Text>
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

        {/* When Free is full, the thing the organizer came to find out is why nobody can join —
            so the billing card leads, above both tabs, and drops back into Settings once there is
            room again. */}
        {group.is_owner && atFreeCeiling ? (
          <PlusBillingPanel group={group} checkout={checkout} onEntitled={() => void load(true)} />
        ) : null}

        {/*
          Two jobs, two tabs. PEOPLE is the exchange's roster — who has joined, who is invited, what
          each still owes, and the things an organizer does TO a person. SETTINGS is how the exchange
          runs — reminders, the organizer's words, templates, whether gifts are posted, billing.
          They used to be seven cards in one scroll, and the person-shaped ones and the
          settings-shaped ones were interleaved.
        */}
        <Tabs.Root defaultValue={checkout ? 'settings' : 'people'}>
          <Tabs.List>
            <Tabs.Tab value="people">People</Tabs.Tab>
            <Tabs.Tab value="settings">Settings</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="people">
            <View style={{ gap: 28, marginTop: 24 }}>
              <PeoplePanel
                group={group}
                readiness={readiness}
                onChanged={() => void load(true)}
                onNeedsPlus={() => setRolesNeedPlus(true)}
                onAddLate={setAddingLate}
              />

              {/* The late-participant flow, which is a decision rather than a control: it moves
                  matches people may already have acted on, so it gets a panel of its own with the
                  count in it. */}
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
                The roster's own "Make organizer" refusal. It is a whole card, so it cannot live
                inside a row's menu — and it only appears once somebody has actually tried, because
                a locked notice above an untouched roster is an advert rather than an answer.
              */}
              {rolesNeedPlus ? (
                <PlusLockedNote
                  reason="Sharing the organizing is part of Plus."
                  action="hand the running of this exchange to somebody alongside you"
                  isOwner={group.is_owner}
                />
              ) : null}

              <GiftProgressPanel readiness={readiness} />
            </View>
          </Tabs.Panel>

          <Tabs.Panel value="settings">
            <View style={{ marginTop: 24 }}>
              <SettingsTab
                group={group}
                readiness={readiness}
                checkout={checkout}
                busy={busy}
                onGroupChanged={setGroup}
                onReload={() => void load(true)}
                onRequiresAddress={(checked) => void setRequiresAddress(checked)}
                initial={checkout ? 'billing' : undefined}
              />
            </View>
          </Tabs.Panel>
        </Tabs.Root>

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
  const { styles } = useTheme();
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

function GiftProgressPanel({ readiness }: { readiness: GroupReadiness }) {
  const { styles } = useTheme();
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
});
