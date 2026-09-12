// The organizer's three tabs on the exchange page: People, Draw, Settings (#684, #690).
//
// There used to be two pages. `/groups/{id}` was "the participant's page" and grew organizer tools
// because the organizer is a participant too; `/organize/{id}` was "the dashboard" and grew
// settings because there was nowhere else. An organizer met the roster twice, the delete button
// twice, and the exchange's details split across both, and neither page's name said which had the
// thing they wanted. Now there is one exchange, with tabs. Everyone sees the two named for the
// people in their exchange — FOR <recipient> and FOR YOU. An organizer also sees these three, each
// named for a job:
//
//   PEOPLE   who is in, who is invited, what each still owes; the invite link and email invitations;
//            exclusions; roles, sitting out, removal; a late arrival after the draw.
//   DRAW     is it ready — the roll-up — and the draw itself: create, reset, the audited reveal;
//            gift progress after; next year's exchange once this one is drawn.
//   SETTINGS how the exchange runs: details, gifts posted, greeting, reminders, templates, billing,
//            and the danger zone.
//
// Each tab is a route (`/groups/{id}/people`, `/draw`, `/settings/{section}`), so this renders ONE
// tab — the one `tab` names — and the layout above it renders the tab bar. The layout also owns
// the group and the readiness read and hands both down; this owns every organizer action and asks
// the layout to re-read when one lands. Readiness is a READ of state the server computed — nothing
// here decides who is ready.
import { AlertDialog, Button, Input, Meter, Select, Textarea } from '@ansavva/design-system';
import * as Clipboard from 'expo-clipboard';
import { useMemo, useState } from 'react';
import { Pressable, Share, Text, View, useWindowDimensions } from 'react-native';

import { api, ApiError } from '../api/client';
import { useAuth } from '../context/auth-context';
import { gap, useTheme } from '../theme/styles';
import type {
  ExclusionPair,
  GroupDetail,
  GroupReadiness,
  ParticipantReadiness,
  RevealAssignment,
} from '../types';
import { sessionKeys, sessionStore } from '../utils/session-store';
import { LateParticipantPanel } from './late-participant';
import { PeoplePanel } from './people';
import { PanelLoadFailure, PlusBillingPanel, PlusLockedNote, isPlusRequired } from './plus';
import { RepeatExchangePanel } from './repeat-exchange';
import { SettingsTab, type SettingsSection } from './settings-tab';
import { Card, LoadingPanel } from './shell';
import { StatusMessage } from './status-message';

export type OrganizerTab = 'people' | 'draw' | 'settings';

/** The tabs, in the order an organizer works through them. The exchange layout renders them. */
export const ORGANIZER_TABS: { value: OrganizerTab; label: string }[] = [
  { value: 'people', label: 'People' },
  { value: 'draw', label: 'Draw' },
  { value: 'settings', label: 'Settings' },
];

export function OrganizerTabs({
  tab,
  group,
  readiness,
  readinessError,
  checkout,
  section,
  onSectionChange,
  onGroupChanged,
  onReload,
}: {
  /** Which of the three this page is. */
  tab: OrganizerTab;
  group: GroupDetail;
  /** The roster read, from the layout. `null` while it is still loading. */
  readiness: GroupReadiness | null;
  readinessError: string | null;
  /** Stripe's `?checkout=` return value on the web. Native returns by closing the browser instead. */
  checkout?: string | null;
  /** The Settings section open — its URL segment. Defaults to the first. */
  section?: SettingsSection;
  /** The person chose another Settings section: the URL should follow. */
  onSectionChange?(next: SettingsSection): void;
  /** A settings save that returned the new group — the page's header follows it. */
  onGroupChanged(next: GroupDetail): void;
  /** Something changed the roster, the draw or the plan: the page re-reads the group and the roster. */
  onReload(): Promise<unknown> | void;
}) {
  const { styles } = useTheme();
  const auth = useAuth();
  const groupId = group.group_id;

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState(() => sessionStore.get(sessionKeys.invite(groupId)) ?? '');
  const [reveal, setReveal] = useState<RevealAssignment[] | null>(null);
  const [addingLate, setAddingLate] = useState<ParticipantReadiness | null>(null);
  const [lateNeedsPlus, setLateNeedsPlus] = useState(false);
  const [rolesNeedPlus, setRolesNeedPlus] = useState(false);
  const [plusRefusal, setPlusRefusal] = useState<string | null>(null);

  /** Every organizer action: run it, say what happened, re-read both the group and the roster. */
  async function action(work: (token: string) => Promise<unknown>, message?: string) {
    setBusy(true);
    setError(null);
    setSuccess(null);
    setPlusRefusal(null);
    try {
      await work(await auth.accessToken());
      if (message) setSuccess(message);
      await onReload();
      return true;
    } catch (err) {
      if (isPlusRequired(err)) setPlusRefusal((err as Error).message);
      else setError(err instanceof Error ? err.message : 'The action could not be completed.');
      return false;
    } finally {
      setBusy(false);
    }
  }

  const refresh = () => { void onReload(); };

  const status = (
    <>
      <StatusMessage message={error} />
      <StatusMessage message={success} tone="success" />
      {plusRefusal ? (
        <PlusLockedNote reason={plusRefusal} action="do what this exchange just asked for" isOwner={group.is_owner} />
      ) : null}
    </>
  );

  const drawn = group.status === 'drawn';
  const atFreeCeiling =
    readiness !== null && group.plan === 'free' && readiness.counts.participating >= group.participant_limit;

  if (tab === 'people')
    return (
        <View style={{ gap: 28 }}>
          {status}
          {/* When Free is full, the thing the organizer came to People to find out is why nobody
              can join — so the billing card leads here, and lives in Settings otherwise. */}
          {group.is_owner && atFreeCeiling ? (
            <PlusBillingPanel group={group} checkout={checkout} onEntitled={refresh} />
          ) : null}
          {readiness ? (
            <PeoplePanel
              group={group}
              readiness={readiness}
              onChanged={refresh}
              onNeedsPlus={() => setRolesNeedPlus(true)}
              onAddLate={setAddingLate}
              onSetParticipation={(person, participating) =>
                action((token) => api.setParticipation(token, groupId, person.member_id, participating))
              }
              onRemove={(person) => action((token) => api.removeMember(token, groupId, person.member_id))}
            />
          ) : readinessError ? (
            <PanelLoadFailure title="People" message={readinessError} />
          ) : (
            <LoadingPanel />
          )}

          {addingLate ? (
            <LateParticipantPanel
              groupId={groupId}
              person={addingLate}
              onCancel={() => setAddingLate(null)}
              onAdded={() => { setAddingLate(null); refresh(); }}
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
          {/* Only once somebody has actually tried: a locked notice above an untouched roster is
              an advert rather than an answer. */}
          {rolesNeedPlus ? (
            <PlusLockedNote
              reason="Sharing the organizing is part of Plus."
              action="hand the running of this exchange to somebody alongside you"
              isOwner={group.is_owner}
            />
          ) : null}

          {!drawn ? (
            <>
              <InviteLinkCard
                inviteUrl={inviteUrl}
                busy={busy}
                onRotate={() =>
                  void action(async (token) => {
                    const result = await api.rotateInvite(token, groupId);
                    setInviteUrl(result.invite_url);
                    sessionStore.set(sessionKeys.invite(groupId), result.invite_url);
                  }, 'A fresh invitation link is ready.')
                }
              />
              <ExclusionsCard
                group={group}
                busy={busy}
                onSave={(pairs) =>
                  void action((token) => api.setExclusions(token, groupId, pairs), 'Exclusions updated.')
                }
              />
            </>
          ) : null}
        </View>
    );

  if (tab === 'draw')
    return (
        <View style={{ gap: 28 }}>
          {status}
          {readiness ? (
            <ReadinessStats readiness={readiness} />
          ) : readinessError ? (
            <PanelLoadFailure title="Readiness" message={readinessError} />
          ) : (
            <LoadingPanel />
          )}
          <DrawCard
            group={group}
            busy={busy}
            revealed={reveal}
            onDraw={() => void action((token) => api.draw(token, groupId), 'The draw is complete.')}
            onReset={() => void action((token) => api.reset(token, groupId), 'The exchange is open again.')}
            onReveal={async (reason) => {
              setBusy(true);
              setError(null);
              try {
                const result = await api.reveal(await auth.accessToken(), groupId, reason);
                setReveal(result.assignments);
              } catch (err) {
                setError(err instanceof Error ? err.message : 'Unable to reveal assignments.');
              } finally {
                setBusy(false);
              }
            }}
          />
          {readiness ? <GiftProgressPanel readiness={readiness} /> : null}
          {/* Next year's exchange, offered once this one is drawn — that is when an organizer
              thinks about it (#136). Owner-only: it creates an exchange. */}
          {group.is_owner && drawn ? <RepeatExchangePanel group={group} /> : null}
        </View>
    );

  return (
        <View style={{ gap: 16 }}>
          {status}
          {readiness ? (
            <SettingsTab
              group={group}
              readiness={readiness}
              checkout={checkout}
              busy={busy}
              onGroupChanged={onGroupChanged}
              onReload={refresh}
              onRequiresAddress={(checked) =>
                void action((token) => api.updateGroup(token, groupId, { requires_address: checked }))
              }
              section={section}
              onSectionChange={onSectionChange}
            />
          ) : readinessError ? (
            <PanelLoadFailure title="Settings" message={readinessError} />
          ) : (
            <LoadingPanel />
          )}
        </View>
  );
}

// ─── People: the link and the exclusions ────────────────────────────────────────────────────────

/** The Free way to invite: one link, shown once, rotated on demand. */
function InviteLinkCard({ inviteUrl, busy, onRotate }: { inviteUrl: string; busy: boolean; onRotate(): void }) {
  const { styles } = useTheme();
  const [copied, setCopied] = useState(false);
  return (
    <Card>
      <Text style={styles.eyebrow}>Invitation link</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Anyone with the link can join. Links are shown once; creating a fresh one invalidates the
        previous link.
      </Text>
      {inviteUrl ? (
        <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <View style={{ flex: 1, minWidth: 200 }}>
            <Input aria-label="Invitation link" value={inviteUrl} disabled />
          </View>
          <Button intent="secondary" onPress={() => { void Clipboard.setStringAsync(inviteUrl); setCopied(true); }}>
            {copied ? 'Copied' : 'Copy'}
          </Button>
          {/* Native sharing (#134), where the platform has it: a real sheet on iOS and Android, the
              Web Share API in a browser that supports it, and nothing where it does not. The
              message IS the link — anything prepended ends up quoted ahead of the URL. */}
          {Share.share ? (
            <Button
              intent="secondary"
              accessibilityLabel="Share the invitation link"
              onPress={() => { void Share.share({ message: inviteUrl }).catch(() => undefined); }}
            >
              Share
            </Button>
          ) : null}
        </View>
      ) : null}
      <View style={{ marginTop: 12, alignSelf: 'flex-start' }}>
        <Button intent="secondary" disabled={busy} onPress={onRotate}>
          {inviteUrl ? 'Create a fresh link' : 'Create a link'}
        </Button>
      </View>
    </Card>
  );
}

/** People in a pair cannot draw one another. */
function ExclusionsCard({
  group,
  busy,
  onSave,
}: {
  group: GroupDetail;
  busy: boolean;
  onSave(pairs: string[][]): void;
}) {
  const { styles } = useTheme();
  const [first, setFirst] = useState<string | null>(null);
  const [second, setSecond] = useState<string | null>(null);
  const [pairs, setPairs] = useState<ExclusionPair[]>(group.exclusions);
  const names = useMemo(
    () => Object.fromEntries(group.members.map((m) => [m.member_id, m.display_name])),
    [group.members],
  );
  const options = useMemo(
    () => group.members.filter((m) => m.is_participating).map((m) => ({ value: m.member_id, label: m.display_name })),
    [group.members],
  );
  function addPair() {
    if (first && second && first !== second && !pairs.some((pair) => pair.includes(first) && pair.includes(second)))
      setPairs([...pairs, [first, second]]);
  }
  return (
    <Card>
      <Text style={styles.eyebrow}>Exclusions</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>People in a pair cannot draw one another.</Text>
      <View style={{ marginTop: 12, gap: 8 }}>
        {/* The two people sit beside each other because a pair is one thing, not a list of two;
            stacked, each select read as its own question. They wrap under each other only when a
            phone leaves no room for two names on a line. */}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <View style={{ flex: 1, minWidth: 200 }}>
            <Select aria-label="First person in the pair" options={options} value={first} placeholder="Choose person" onValueChange={setFirst} />
          </View>
          <View style={{ flex: 1, minWidth: 200 }}>
            <Select aria-label="Second person in the pair" options={options} value={second} placeholder="Choose person" onValueChange={setSecond} />
          </View>
        </View>
        <View style={{ alignSelf: 'flex-start' }}>
          <Button intent="secondary" onPress={addPair}>Add</Button>
        </View>
      </View>
      <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {pairs.map((pair, index) => (
          <Pressable
            key={`${pair[0]}-${pair[1]}`}
            accessibilityRole="button"
            accessibilityLabel={`Remove exclusion ${names[pair[0]]} and ${names[pair[1]]}`}
            style={styles.pairChip}
            onPress={() => setPairs(pairs.filter((_, item) => item !== index))}
          >
            <Text style={styles.pairChipText}>{names[pair[0]]} + {names[pair[1]]} ×</Text>
          </Pressable>
        ))}
      </View>
      <View style={{ marginTop: 16, alignSelf: 'flex-start' }}>
        <Button intent="secondary" disabled={busy} onPress={() => onSave(pairs)}>Save exclusions</Button>
      </View>
    </Card>
  );
}

// ─── Draw ───────────────────────────────────────────────────────────────────────────────────────

function DrawCard({
  group,
  busy,
  revealed,
  onDraw,
  onReset,
  onReveal,
}: {
  group: GroupDetail;
  busy: boolean;
  revealed: RevealAssignment[] | null;
  onDraw(): void;
  onReset(): void;
  onReveal(reason: string): Promise<void>;
}) {
  const { blends, brand, styles } = useTheme();
  const [reason, setReason] = useState('');
  if (group.status === 'open')
    return (
      <Card style={{ borderColor: blends.primaryBorder }}>
        <Text style={styles.eyebrow}>The draw</Text>
        <Text style={[styles.heading, { marginTop: 4 }]}>Ready to draw?</Text>
        <Text style={[styles.smallMuted, { marginTop: 8 }]}>
          Drawing locks the roster and the exclusions. Every person sees only their own recipient.
        </Text>
        <View style={{ marginTop: 16 }}>
          <Button style={styles.buttonBlock} size="lg" disabled={busy} onPress={onDraw}>
            Create private assignments
          </Button>
        </View>
      </Card>
    );
  return (
    <Card>
      <Text style={styles.eyebrow}>The draw</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Drawn</Text>
      <View style={{ marginTop: 20, gap: 20 }}>
        <ResetDrawPanel group={group} busy={busy} onReset={onReset} />
        <View style={[styles.panel, { backgroundColor: 'transparent', borderWidth: 1, borderColor: blends.dangerBorder }]}>
          <Text style={[styles.small, styles.semibold]}>Emergency reveal</Text>
          <Text style={[styles.smallMuted, { marginTop: 8 }]}>
            Shows you, and only you, who is giving to whom — every pair, with each recipient’s
            wishlist. Nothing changes and nobody is told, but the surprise is gone for you, and the
            reveal is written to this exchange’s audit log with your name and your reason. For a
            draw that is stuck: somebody dropped out, a gift needs rerouting, a dispute needs settling.
          </Text>
          <View style={{ marginTop: 12 }}>
            <Textarea
              aria-label="Reason for revealing all assignments"
              value={reason}
              onValueChange={setReason}
              maxLength={500}
              placeholder="Why is this reveal necessary?"
            />
          </View>
          <View style={{ marginTop: 12, alignSelf: 'flex-start' }}>
            <Button intent="danger" disabled={reason.trim().length === 0 || busy} onPress={() => void onReveal(reason)}>
              Reveal all assignments
            </Button>
          </View>
        </View>
        {revealed ? (
          <View>
            <Text style={[styles.small, styles.semibold]}>Revealed assignments</Text>
            <View style={{ marginTop: 12, gap: 8 }}>
              {revealed.map((item) => (
                <View key={item.giver.member_id} style={[styles.panel, { padding: 16 }]}>
                  <Text style={styles.small}>
                    <Text style={styles.semibold}>{item.giver.display_name}</Text>
                    <Text style={{ color: brand.muted }}> → </Text>
                    {item.recipient.display_name}
                  </Text>
                </View>
              ))}
            </View>
          </View>
        ) : null}
      </View>
    </Card>
  );
}

/**
 * Resetting the draw, behind a confirmation.
 *
 * It undoes what everyone has done since the draw — the person they drew, the wishes they marked
 * bought, the gift stage, the questions asked — so it is a danger button, not a quiet secondary one
 * (which on the dark scheme rendered as bare text), and a dialog stands between the press and the
 * loss. Same shape as the danger zone's delete: a dialog rather than a two-press arm, because
 * nothing else on the tab could be mistaken for the confirmation.
 */
function ResetDrawPanel({ group, busy, onReset }: { group: GroupDetail; busy: boolean; onReset(): void }) {
  const { blends, styles } = useTheme();
  const [confirming, setConfirming] = useState(false);
  const participating = group.members.filter((member) => member.is_participating).length;
  return (
    <View style={styles.panel}>
      <Text style={[styles.small, styles.semibold]}>Need to change the exchange?</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Resetting clears every assignment and reopens the roster. Claims, gift progress and the
        anonymous chats go with it.
      </Text>
      <AlertDialog.Root open={confirming} onOpenChange={(next) => { if (!busy) setConfirming(next); }}>
        <View style={{ marginTop: 16, alignSelf: 'flex-start' }}>
          <Button intent="danger" disabled={busy} onPress={() => setConfirming(true)}>Reset the draw…</Button>
        </View>
        <AlertDialog.Popup style={{ borderWidth: 1, borderColor: blends.dangerBorder }}>
          <AlertDialog.Title>Reset the draw?</AlertDialog.Title>
          <AlertDialog.Description>
            {participating === 1 ? 'The one person taking part loses' : `All ${participating} people taking part lose`} the
            person they drew, along with anything they marked bought and any questions asked. You
            can draw again once the roster is settled.
          </AlertDialog.Description>
          <View style={{ marginTop: 24, flexDirection: 'row', justifyContent: 'flex-end', gap: gap.xs }}>
            <AlertDialog.Close>Keep the draw</AlertDialog.Close>
            <Button intent="danger" size="sm" disabled={busy} onPress={() => { setConfirming(false); onReset(); }}>
              Reset the draw
            </Button>
          </View>
        </AlertDialog.Popup>
      </AlertDialog.Root>
    </View>
  );
}

// ─── Readiness ──────────────────────────────────────────────────────────────────────────────────

/** The roll-up: is this exchange ready? One column on a phone, two on a small tablet, four wide. */
function ReadinessStats({ readiness }: { readiness: GroupReadiness }) {
  const { counts } = readiness;
  const drawn = readiness.status === 'drawn';
  return (
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
      <Stat label="Wishlists" value={`${counts.wishlist_ready} of ${counts.participating}`} ready={counts.wishlist_ready} total={counts.participating} />
      <Stat
        label="Addresses"
        value={readiness.requires_address ? `${counts.address_ready} of ${counts.participating}` : 'Not needed'}
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
  );
}

/**
 * The cells are `flexBasis: 0` + `flexGrow: 1` and the break is forced by `minWidth`, NOT by a
 * percentage basis: a basis of `100 / columns`% ignores the row's `gap`, so four 25% tiles plus
 * three gaps overflow and the fourth wraps alone.
 */
function StatRow({ children }: { children: React.ReactNode }) {
  const { width } = useWindowDimensions();
  const columns = width < 640 ? 1 : width < 1024 ? 2 : 4;
  const minWidth = columns === 1 ? '100%' : columns === 2 ? '45%' : 0;
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: gap.md }}>
      {Array.isArray(children)
        ? children.map((child, index) => (
            <View key={index} style={{ flexBasis: 0, flexGrow: 1, minWidth }}>{child}</View>
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
    <Card style={{ padding: 20, height: '100%' }}>
      <Text style={styles.eyebrow}>{label}</Text>
      <Text style={[styles.displayMd, { marginTop: 8 }]}>{value}</Text>
      {showMeter ? (
        <Meter.Root value={ready} max={total} aria-label={`${label}: ${ready} of ${total}`} style={{ marginTop: 12 }}>
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
          {/* Deliberately not three zeroes. Before a draw nobody has been asked to buy anything, so
              the API sends no progress at all; "0 of 5 purchased" would be a claim about the
              world, and this one would be false. */}
          <Text style={styles.bodyMuted}>Nothing to track yet.</Text>
          <Text style={[styles.tiny, { marginTop: 8, textAlign: 'center' }]}>
            Once the draw is done and givers start marking gifts bought, sent and received, the totals
            appear here — as counts only, so they never reveal who is giving to whom.
          </Text>
        </View>
      )}
    </Card>
  );
}
