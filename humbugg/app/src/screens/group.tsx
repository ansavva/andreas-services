// One exchange, ported from `src/pages/GroupPage.tsx`: the heading, the
// assignment reveal, the participant list, your own wishlist, and — for the
// organizer — invites, exclusions, the draw and the destructive actions.
import { Button, Checkbox, Input, Select, Textarea } from '@ansavva/design-system';
import * as Clipboard from 'expo-clipboard';
import { Link, useRouter } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { api, ApiError } from '../api/client';
import { DangerButton } from '../components/danger-button';
import { FieldLabel } from '../components/field';
import { Card, LoadingPanel, Shell } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { RecipientWishList, WishListPanel } from '../components/wishlist';
import { useAuth } from '../context/auth-context';
import { blends, gap, styles } from '../theme/styles';
import { brand } from '../theme/theme';
import type {
  ExclusionPair,
  GroupDetail,
  Membership,
  RecipientAssignment,
  RevealAssignment,
} from '../types';
import { sessionKeys, sessionStore } from '../utils/session-store';
import { validateAddressForm } from '../utils/validation';

export default function GroupScreen({ groupId }: { groupId: string }) {
  const auth = useAuth();
  const router = useRouter();
  const [group, setGroup] = useState<GroupDetail | null>(null);
  const [me, setMe] = useState<Membership | null>(null);
  const [assignment, setAssignment] = useState<RecipientAssignment | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState(() => sessionStore.get(sessionKeys.invite(groupId)) ?? '');
  const [reveal, setReveal] = useState<RevealAssignment[] | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const token = await auth.accessToken();
      const [detail, membership] = await Promise.all([
        api.getGroup(token, groupId),
        api.getMembership(token, groupId),
      ]);
      setGroup(detail);
      setMe(membership);
      if (detail.status === 'drawn' && membership.is_participating) {
        try {
          setAssignment(await api.getAssignment(token, groupId));
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 404)) throw err;
        }
      } else setAssignment(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load the group.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [groupId]);

  async function action(work: (token: string) => Promise<unknown>, message?: string) {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await work(await auth.accessToken());
      if (message) setSuccess(message);
      await load();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The action could not be completed.');
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Shell><LoadingPanel>Opening your exchange…</LoadingPanel></Shell>;
  if (!group || !me) {
    return (
      <Shell>
        <View style={{ maxWidth: 576, alignSelf: 'center', width: '100%' }}>
          <StatusMessage message={error ?? 'Group not found.'} />
          <Link href="/" style={[styles.link, { marginTop: 16 }]}>Return to your groups</Link>
        </View>
      </Shell>
    );
  }

  const participating = group.members.filter((member) => member.is_participating).length;

  return (
    <Shell>
      <Link href="/" style={[styles.smallMuted, { marginBottom: 24 }]}>← All groups</Link>
      <View style={{ gap: 28 }}>
        <View style={styles.groupHeading}>
          <View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <View style={[styles.statusPill, group.status === 'drawn' && styles.statusDrawn]}>
                <Text style={[styles.statusPillText, group.status === 'drawn' && styles.statusDrawnText]}>
                  {group.status === 'drawn' ? 'Draw complete' : 'Open for joining'}
                </Text>
              </View>
              {group.is_organizer ? <Text style={styles.smallMuted}>You’re organizing</Text> : null}
            </View>
            <Text style={[styles.displayLg, { marginTop: 16 }]}>{group.name}</Text>
            <Text style={[styles.bodyMuted, { marginTop: 12, maxWidth: 672 }]}>
              {group.description || 'A little holiday magic is taking shape.'}
            </Text>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <MetaChip>
              {group.event_date ? new Date(`${group.event_date}T12:00:00`).toLocaleDateString() : 'Date TBD'}
            </MetaChip>
            <MetaChip>
              {group.spending_limit != null ? `$${group.spending_limit.toFixed(2)} USD` : 'No set limit'}
            </MetaChip>
            <MetaChip>{group.plan} plan</MetaChip>
            <MetaChip>
              {participating}
              {group.plan === 'work' ? '' : ` / ${group.participant_limit}`} participating
            </MetaChip>
          </View>
        </View>
        <StatusMessage message={error} />
        <StatusMessage message={success} tone="success" />

        {assignment ? <AssignmentCard assignment={assignment} /> : null}

        <Card>
          <Text style={styles.eyebrow}>Participants</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>The exchange circle</Text>
          <View style={{ marginTop: 24, gap: 12 }}>
            {group.members.map((member) => (
              <View key={member.member_id} style={styles.memberRow}>
                <View style={styles.avatarChip}>
                  <Text style={styles.avatarChipText}>{member.display_name[0]?.toUpperCase()}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.small, { fontFamily: styles.semibold.fontFamily }]}>
                    {member.display_name}
                  </Text>
                  <Text style={styles.tiny}>
                    {member.is_organizer
                      ? 'Organizer'
                      : member.is_participating
                        ? 'Participating'
                        : 'Not participating'}
                  </Text>
                </View>
                {group.is_organizer && group.status === 'open' && !member.is_organizer ? (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Checkbox.Root
                      checked={member.is_participating}
                      aria-label={`Include ${member.display_name}`}
                      onCheckedChange={(checked) =>
                        void action((token) =>
                          api.setParticipation(token, groupId, member.member_id, checked === true),
                        )
                      }
                    >
                      <Checkbox.Indicator />
                    </Checkbox.Root>
                    <Text style={styles.smallMuted}>Include</Text>
                  </View>
                ) : null}
              </View>
            ))}
          </View>
        </Card>

        <WishListPanel groupId={groupId} />

        <WishListForm
          key={`${me.wishlist ?? ''}|${me.avoidances ?? ''}|${me.address?.line1 ?? ''}`}
          membership={me}
          busy={busy}
          onSave={(data) =>
            void action((token) => api.updateMembership(token, groupId, data), 'Your gift details are saved.')
          }
          onClear={() =>
            void action(
              (token) => api.clearMyGroupData(token, groupId),
              'Your wishlist, preferences and mailing address were cleared.',
            )
          }
        />

        {group.is_organizer ? (
          <OrganizerPanel
            group={group}
            inviteUrl={inviteUrl}
            busy={busy}
            revealed={reveal}
            onInvite={() =>
              void action(async (token) => {
                const result = await api.rotateInvite(token, groupId);
                setInviteUrl(result.invite_url);
                sessionStore.set(sessionKeys.invite(groupId), result.invite_url);
              }, 'A fresh invitation link is ready.')
            }
            onExclusions={(pairs) =>
              void action((token) => api.setExclusions(token, groupId, pairs), 'Exclusions updated.')
            }
            onDraw={() => void action((token) => api.draw(token, groupId), 'The draw is complete.')}
            onReset={() => void action((token) => api.reset(token, groupId), 'The group is open again.')}
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
            onDelete={async () => {
              if (await action((token) => api.deleteGroup(token, groupId))) router.replace('/');
            }}
          />
        ) : null}
      </View>
    </Shell>
  );
}

function MetaChip({ children }: { children: React.ReactNode }) {
  return (
    <View style={styles.metaChip}>
      <Text style={styles.smallMuted}>{children}</Text>
    </View>
  );
}

function AssignmentCard({ assignment }: { assignment: RecipientAssignment }) {
  const address = Object.values(assignment.address ?? {}).filter(Boolean).join(', ');
  return (
    <View style={styles.assignmentCard}>
      <Text style={styles.assignmentLabel}>Your secret recipient</Text>
      <Text style={[styles.displayLg, { color: brand.primaryText, marginTop: 8 }]}>
        {assignment.display_name}
      </Text>
      <View style={{ marginTop: 28, gap: 20 }}>
        <View>
          <Text style={styles.assignmentLabel}>Their wishlist</Text>
          <View style={{ marginTop: 8 }}>
            <RecipientWishList wishes={assignment.wishes ?? []} />
          </View>
        </View>
        <View>
          <Text style={styles.assignmentLabel}>Likes, sizes and hobbies</Text>
          <Text style={styles.assignmentText}>{assignment.wishlist || 'Nothing added.'}</Text>
        </View>
        <View>
          <Text style={styles.assignmentLabel}>Please avoid</Text>
          <Text style={styles.assignmentText}>{assignment.avoidances || 'Nothing listed.'}</Text>
        </View>
        <View>
          <Text style={styles.assignmentLabel}>Delivery address</Text>
          <Text style={styles.assignmentText}>{address || 'No address provided.'}</Text>
        </View>
      </View>
    </View>
  );
}

function WishListForm({
  membership,
  busy,
  onSave,
  onClear,
}: {
  membership: Membership;
  busy: boolean;
  onSave(data: Record<string, unknown>): void;
  onClear(): void;
}) {
  const saved = membership.address ?? {};
  const [wishlist, setWishlist] = useState(membership.wishlist ?? '');
  const [avoidances, setAvoidances] = useState(membership.avoidances ?? '');
  const [line1, setLine1] = useState(saved.line1 ?? '');
  const [line2, setLine2] = useState(saved.line2 ?? '');
  const [city, setCity] = useState(saved.city ?? '');
  const [region, setRegion] = useState(saved.region ?? '');
  const [postalCode, setPostalCode] = useState(saved.postal_code ?? '');
  const [country, setCountry] = useState(saved.country ?? '');
  const [showAddress, setShowAddress] = useState(Boolean(saved.line1));
  const [validationError, setValidationError] = useState<string | null>(null);
  const [confirmingClear, setConfirmingClear] = useState(false);

  function submit() {
    const addressValues = { line1, line2, city, region, postalCode, country };
    const error = validateAddressForm(addressValues);
    if (error) { setValidationError(error); return; }
    setValidationError(null);
    onSave({
      wishlist: wishlist.trim(),
      avoidances: avoidances.trim(),
      address: {
        line1: line1.trim(),
        line2: line2.trim(),
        city: city.trim(),
        region: region.trim(),
        postal_code: postalCode.trim(),
        country: country.trim(),
      },
    });
  }

  return (
    <Card>
      <Text style={styles.eyebrow}>General preferences</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Sizes, likes and things to avoid</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        The things that apply to any gift, alongside your wishlist above. Only your assigned giver
        can see these, and only after the draw.
      </Text>
      <View style={{ marginTop: 24, gap: gap.md }}>
        <FieldLabel label="Likes, sizes and hobbies">
          <Textarea
            aria-label="Likes, sizes and hobbies"
            maxLength={2000}
            value={wishlist}
            onValueChange={setWishlist}
            placeholder="Medium in tops, size 9 shoes, into cycling and cooking…"
          />
        </FieldLabel>
        <FieldLabel label="Allergies and things to avoid">
          <Textarea
            aria-label="Allergies and things to avoid"
            maxLength={2000}
            value={avoidances}
            onValueChange={setAvoidances}
            placeholder="Nut allergy, no scented candles, already own the boxset…"
          />
        </FieldLabel>
        {/*
          The web app used `<details>`. There is no disclosure element on this
          side, so this is a plain toggle — the package's `Collapsible` animates
          a height it cannot measure for a block of inputs that grow.
        */}
        <View style={local.disclosure}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ expanded: showAddress }}
            onPress={() => setShowAddress((open) => !open)}
          >
            <Text style={[styles.small, styles.semibold]}>
              {showAddress ? '▾' : '▸'} Optional mailing address
            </Text>
          </Pressable>
          {showAddress ? (
            <View style={{ marginTop: 16, gap: 12 }}>
              <Text style={styles.tiny}>
                If you add an address, the address line, city, postal code, and country are required.
              </Text>
              <Input aria-label="Address line 1" maxLength={150} value={line1} onValueChange={setLine1} placeholder="Address line 1" />
              <Input aria-label="Address line 2" maxLength={150} value={line2} onValueChange={setLine2} placeholder="Address line 2" />
              <Input aria-label="City" maxLength={100} value={city} onValueChange={setCity} placeholder="City" />
              <Input aria-label="State or region" maxLength={100} value={region} onValueChange={setRegion} placeholder="State / region" />
              <Input aria-label="Postal code" maxLength={32} value={postalCode} onValueChange={setPostalCode} placeholder="Postal code" />
              <Input aria-label="Country" maxLength={100} value={country} onValueChange={setCountry} placeholder="Country" />
            </View>
          ) : null}
        </View>
        <StatusMessage message={validationError} />
        <Button disabled={busy} onPress={submit}>Save my details</Button>
      </View>
      <View style={{ marginTop: 16, borderTopWidth: 1, borderTopColor: brand.line, paddingTop: 16, gap: 12 }}>
        <Text style={styles.tiny}>
          Clear your wishlist, general preferences, and mailing address for this exchange —
          including every item on the list above. This does not remove you from the group.
        </Text>
        <View style={{ alignSelf: 'flex-start' }}>
          {/*
            `window.confirm` has no counterpart here, so the confirmation is the
            button itself: one press arms, the next commits.
          */}
          <Button
            intent="secondary"
            size="sm"
            disabled={busy}
            onPress={() => {
              if (!confirmingClear) { setConfirmingClear(true); return; }
              setConfirmingClear(false);
              onClear();
            }}
          >
            {confirmingClear ? 'Tap again to confirm' : 'Clear everything I saved'}
          </Button>
        </View>
      </View>
    </Card>
  );
}

interface OrganizerProps {
  group: GroupDetail;
  inviteUrl: string;
  busy: boolean;
  revealed: RevealAssignment[] | null;
  onInvite(): void;
  onExclusions(pairs: string[][]): void;
  onDraw(): void;
  onReset(): void;
  onReveal(reason: string): Promise<void>;
  onDelete(): Promise<void>;
}

function OrganizerPanel(props: OrganizerProps) {
  const { group } = props;
  const [first, setFirst] = useState<string | null>(null);
  const [second, setSecond] = useState<string | null>(null);
  const [pairs, setPairs] = useState<ExclusionPair[]>(group.exclusions);
  const [reason, setReason] = useState('');
  const [copied, setCopied] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleteAnnouncement, setDeleteAnnouncement] = useState('');
  const deleteArmedAt = useRef(0);

  const names = useMemo(
    () => Object.fromEntries(group.members.map((m) => [m.member_id, m.display_name])),
    [group.members],
  );
  const options = useMemo(
    () =>
      group.members
        .filter((m) => m.is_participating)
        .map((m) => ({ value: m.member_id, label: m.display_name })),
    [group.members],
  );

  function addPair() {
    if (first && second && first !== second && !pairs.some((pair) => pair.includes(first) && pair.includes(second)))
      setPairs([...pairs, [first, second]]);
  }

  // The armed state disarms itself after five seconds, so a delete cannot sit
  // primed behind a scrolled-away button.
  useEffect(() => {
    if (!confirmingDelete) return;
    const timeout = setTimeout(() => {
      deleteArmedAt.current = 0;
      setConfirmingDelete(false);
      setDeleteAnnouncement('Delete confirmation expired.');
    }, 5000);
    return () => clearTimeout(timeout);
  }, [confirmingDelete]);

  async function handleDeletePress() {
    if (!confirmingDelete) {
      deleteArmedAt.current = Date.now();
      setConfirmingDelete(true);
      setDeleteAnnouncement('Deletion armed. Press Confirm delete within five seconds to permanently delete this group.');
      return;
    }
    // Guards against a double-tap arming and committing in one gesture.
    if (Date.now() - deleteArmedAt.current < 500) return;
    setConfirmingDelete(false);
    setDeleteAnnouncement('Deleting group.');
    await props.onDelete();
    deleteArmedAt.current = 0;
  }

  return (
    <Card style={{ borderColor: blends.primaryBorder }}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 16 }}>
        <View>
          <Text style={styles.eyebrow}>Organizer tools</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>Prepare the draw</Text>
        </View>
        <View>
          <DangerButton
            size="sm"
            disabled={props.busy}
            accessibilityLabel={
              confirmingDelete ? 'Confirm permanent group deletion within five seconds' : 'Delete group'
            }
            accessibilityLiveRegion="polite"
            onPress={() => void handleDeletePress()}
            style={{ width: 160 }}
          >
            {props.busy ? 'Deleting…' : confirmingDelete ? 'Confirm delete' : 'Delete group'}
          </DangerButton>
          <Text accessibilityLiveRegion="polite" style={local.srOnly}>{deleteAnnouncement}</Text>
        </View>
      </View>

      {group.status === 'open' ? (
        <View style={{ marginTop: 28, gap: 28 }}>
          <View>
            <Text style={[styles.small, styles.semibold]}>Invitation link</Text>
            <Text style={[styles.smallMuted, { marginTop: 4 }]}>
              Links are shown once. Rotating invalidates the previous link.
            </Text>
            {props.inviteUrl ? (
              <View style={{ marginTop: 12, flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                <View style={{ flex: 1 }}>
                  <Input aria-label="Invitation link" value={props.inviteUrl} disabled />
                </View>
                <Button
                  intent="secondary"
                  onPress={() => {
                    void Clipboard.setStringAsync(props.inviteUrl);
                    setCopied(true);
                  }}
                >
                  {copied ? 'Copied' : 'Copy'}
                </Button>
              </View>
            ) : (
              <View style={{ marginTop: 12, alignSelf: 'flex-start' }}>
                <Button intent="secondary" onPress={props.onInvite}>Create a fresh link</Button>
              </View>
            )}
          </View>

          <View>
            <Text style={[styles.small, styles.semibold]}>Pair exclusions</Text>
            <Text style={[styles.smallMuted, { marginTop: 4 }]}>
              People in a pair cannot draw one another.
            </Text>
            <View style={{ marginTop: 12, gap: 8 }}>
              <Select
                aria-label="First person in the pair"
                options={options}
                value={first}
                placeholder="Choose person"
                onValueChange={setFirst}
              />
              <Select
                aria-label="Second person in the pair"
                options={options}
                value={second}
                placeholder="Choose person"
                onValueChange={setSecond}
              />
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
                  <Text style={styles.pairChipText}>
                    {names[pair[0]]} + {names[pair[1]]} ×
                  </Text>
                </Pressable>
              ))}
            </View>
            <View style={{ marginTop: 16, alignSelf: 'flex-start' }}>
              <Button intent="secondary" onPress={() => props.onExclusions(pairs)}>Save exclusions</Button>
            </View>
          </View>

          <View style={styles.panel}>
            <Text style={[styles.small, styles.semibold]}>Ready to draw?</Text>
            <Text style={[styles.smallMuted, { marginTop: 4 }]}>
              Drawing locks the roster and exclusions. Every person sees only their own recipient.
            </Text>
            <View style={{ marginTop: 16 }}>
              <Button size="lg" disabled={props.busy} onPress={props.onDraw}>
                Create private assignments
              </Button>
            </View>
          </View>
        </View>
      ) : (
        <View style={{ marginTop: 28, gap: 28 }}>
          <View style={styles.panel}>
            <Text style={[styles.small, styles.semibold]}>Need to change the group?</Text>
            <Text style={[styles.smallMuted, { marginTop: 8 }]}>
              Resetting clears every assignment and reopens the roster.
            </Text>
            <View style={{ marginTop: 16, alignSelf: 'flex-start' }}>
              <Button intent="secondary" onPress={props.onReset}>Reset the draw</Button>
            </View>
          </View>
          <View style={[styles.panel, { backgroundColor: 'transparent', borderWidth: 1, borderColor: blends.dangerBorder }]}>
            <Text style={[styles.small, styles.semibold]}>Emergency reveal</Text>
            <Text style={[styles.smallMuted, { marginTop: 8 }]}>
              This action is permanently audited. Give a reason before viewing all assignments.
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
              <DangerButton
                disabled={reason.trim().length === 0 || props.busy}
                onPress={() => void props.onReveal(reason)}
              >
                Reveal all assignments
              </DangerButton>
            </View>
          </View>
          {props.revealed ? (
            <View>
              <Text style={[styles.small, styles.semibold]}>Revealed assignments</Text>
              <View style={{ marginTop: 12, gap: 8 }}>
                {props.revealed.map((item) => (
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
      )}
    </Card>
  );
}

const local = StyleSheet.create({
  disclosure: { borderWidth: 1, borderColor: brand.line, borderRadius: 12, padding: 16 },
  // The web app's `.sr-only`: announced, never drawn.
  srOnly: { position: 'absolute', width: 1, height: 1, overflow: 'hidden', opacity: 0 },
});
