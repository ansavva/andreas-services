// One exchange — the only page it has (#684).
//
// Everyone sees the EXCHANGE: what it is, how it works, their own wishlist and preferences, their
// match once drawn. An organizer sees three more tabs beside it — People, Draw, Settings — which
// `OrganizerTabs` renders and explains. This used to be two pages, "the group" and "the dashboard",
// and an organizer met the roster, the delete button and the exchange's details on both.
import { Button, Checkbox, Input, Tabs, Textarea } from '@ansavva/design-system';
import { Link, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, Text, View, useWindowDimensions } from 'react-native';

import { api, ApiError } from '../api/client';
import { ExchangeInstructions } from '../components/exchange-settings';
import { GiftReceivedPanel, GiftStagePanel } from '../components/gift-progress';
import { ORGANIZER_TABS, OrganizerTabs, type OrganizerTab } from '../components/organizer-tabs';
import { isPlusRequired, PlusRefusalCard } from '../components/plus';
import { ChatPanel } from '../components/questions';
import { FieldLabel } from '../components/field';
import { BottomSheet, PEEK } from '../components/sheet';
import { Card, LoadingPanel, Shell } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { RecipientWishList, WishListPanel } from '../components/wishlist';
import { useAuth } from '../context/auth-context';
import { gap, scopedStyles, useTheme } from '../theme/styles';
import type { GroupDetail, Membership, RecipientAssignment, WishClaimState } from '../types';
import { validateAddressForm } from '../utils/validation';

type PageTab = 'exchange' | OrganizerTab;

export default function GroupScreen({
  groupId,
  tab: requestedTab,
  checkout,
}: {
  groupId: string;
  /** `?tab=` — where a link into this page lands: `/organize/{id}` redirects here with `people`. */
  tab?: string | null;
  /** Stripe's `?checkout=` return value on the web; lands on Settings → Billing. */
  checkout?: string | null;
}) {
  const { styles } = useTheme();
  const auth = useAuth();
  const router = useRouter();
  // Wide enough for the chat to have a column of its own beside the page; narrower, it is a sheet
  // at the bottom of the screen that is dragged up to read and down to put away.
  const rail = useWindowDimensions().width >= 1024;
  const [group, setGroup] = useState<GroupDetail | null>(null);
  const [me, setMe] = useState<Membership | null>(null);
  const [assignment, setAssignment] = useState<RecipientAssignment | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [tab, setTab] = useState<PageTab>(() =>
    checkout ? 'settings' : isOrganizerTab(requestedTab) ? requestedTab : 'exchange',
  );
  // A 402 is not an error the member made; it is a price. Kept apart from `error` so it renders
  // as an offer with a way forward rather than a red bar with a dead end.
  const [plusRefusal, setPlusRefusal] = useState<string | null>(null);

  async function load(quiet = false) {
    if (!quiet) setLoading(true);
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
      if (!quiet) setLoading(false);
    }
  }

  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [groupId]);

  async function action(work: (token: string) => Promise<unknown>, message?: string) {
    setBusy(true);
    setError(null);
    setSuccess(null);
    setPlusRefusal(null);
    try {
      await work(await auth.accessToken());
      if (message) setSuccess(message);
      await load(true);
      return true;
    } catch (err) {
      if (isPlusRequired(err)) setPlusRefusal((err as Error).message);
      else setError(err instanceof Error ? err.message : 'The action could not be completed.');
      return false;
    } finally {
      setBusy(false);
    }
  }

  // Claims are their own action rather than `action()`: that one reloads the entire group, and
  // marking a gift bought is not a change to the roster, the draw or anyone's membership. It also
  // must not clear the success banner from whatever the organizer just did.
  async function claimAction(work: (token: string) => Promise<RecipientAssignment>) {
    setBusy(true);
    setError(null);
    try {
      setAssignment(await work(await auth.accessToken()));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Shell><LoadingPanel /></Shell>;
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

  // Anonymous chat (#131), both conversations: the one you opened about the gift you are buying,
  // and the one somebody opened about the gift you are getting. Only after the draw and only for
  // someone taking part — before that neither exists.
  const chatting = group.status === 'drawn' && me.is_participating;
  const recipient = assignment ? { name: assignment.display_name, avatar: assignment.avatar_url } : null;
  const chat = chatting ? (
    rail ? (
      <ChatPanel groupId={groupId} layout="rail" recipient={recipient} />
    ) : (
      <BottomSheet label="Anonymous chat">
        <ChatPanel groupId={groupId} layout="sheet" recipient={recipient} />
      </BottomSheet>
    )
  ) : null;

  const exchangeContent = (
    <>
        {assignment ? (
          <AssignmentCard
            assignment={assignment}
            busy={busy}
            // Both calls answer with the whole assignment, so the card re-renders from the server's
            // view rather than a locally patched one — a wish the recipient deleted while the giver
            // was deciding disappears instead of lingering with a claim attached to nothing.
            onClaim={(wishId, state, quantity) =>
              void claimAction((token) => api.setWishClaim(token, groupId, wishId, state, quantity))
            }
            onRelease={(wishId) =>
              void claimAction((token) => api.releaseWishClaim(token, groupId, wishId))
            }
          />
        ) : null}

        {group.status === 'drawn' && me.is_participating ? (
          <>
            {/* Gift progress (#132), both ends. The stage comes back on the assignment — it is the
                caller's own status for that assignment — so it needs no fetch of its own. */}
            {assignment?.gift ? (
              <GiftStagePanel
                gift={assignment.gift}
                busy={busy}
                onChange={(stage) =>
                  void claimAction((token) => api.setGiftStage(token, groupId, stage))
                }
              />
            ) : null}
            <GiftReceivedPanel groupId={groupId} />
          </>
        ) : null}

      <ExchangeInstructions instructions={group.instructions} />

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
    </>
  );

  return (
    <Shell aside={rail ? chat : undefined} sheet={rail ? undefined : chat} sheetInset={chatting && !rail ? PEEK : 0}>
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
              {group.spending_limit != null ? `$${group.spending_limit.toFixed(2)} USD` : 'No spending limit'}
            </MetaChip>
            {/* The plan and its ceiling are the organizer's billing relationship with Humbugg, and
                the organizer manages both on the dashboard. A participant sees who is taking part;
                "plus plan" and "7 / 50" in their chips said somebody paid, and asked what 50 was. */}
            <MetaChip>
              {group.is_organizer && group.plan !== 'work'
                ? `${participating} / ${group.participant_limit} participating · ${group.plan} plan`
                : `${participating} participating`}
            </MetaChip>
          </View>
        </View>
        <StatusMessage message={error} />
        <StatusMessage message={success} tone="success" />

        {plusRefusal ? (
          <PlusRefusalCard
            groupId={groupId}
            reason={plusRefusal}
            action="do what this exchange just asked for"
            // Billing is a section of this page now, not another page.
            onNavigate={() => { setPlusRefusal(null); setTab('settings'); }}
          />
        ) : null}

        {/* Participants get the exchange and nothing to switch between. The organizer gets tabs —
            and their own part in the exchange is still the first one. */}
        {group.is_organizer ? (
          <Tabs.Root defaultValue="exchange" value={tab} onValueChange={(next) => setTab(next as PageTab)}>
            <Tabs.List>
              <Tabs.Tab value="exchange">Exchange</Tabs.Tab>
              {ORGANIZER_TABS.map((item) => (
                <Tabs.Tab key={item.value} value={item.value}>{item.label}</Tabs.Tab>
              ))}
            </Tabs.List>
            <Tabs.Panel value="exchange">
              <View style={{ gap: 28, marginTop: 24 }}>{exchangeContent}</View>
            </Tabs.Panel>
            <OrganizerTabs
              group={group}
              checkout={checkout}
              onGroupChanged={setGroup}
              onReload={() => load(true)}
            />
          </Tabs.Root>
        ) : (
          exchangeContent
        )}
      </View>
    </Shell>
  );
}

function isOrganizerTab(value: string | null | undefined): value is OrganizerTab {
  return ORGANIZER_TABS.some((item) => item.value === value);
}

function MetaChip({ children }: { children: React.ReactNode }) {
  const { styles } = useTheme();
  return (
    <View style={styles.metaChip}>
      <Text style={styles.smallMuted}>{children}</Text>
    </View>
  );
}

function AssignmentCard({
  assignment,
  busy,
  onClaim,
  onRelease,
}: {
  assignment: RecipientAssignment;
  busy: boolean;
  onClaim(wishId: string, state: WishClaimState, quantity: number): void;
  onRelease(wishId: string): void;
}) {
  const { styles } = useTheme();
  const address = Object.values(assignment.address ?? {}).filter(Boolean).join(', ');
  return (
    <View style={styles.assignmentCard}>
      <Text style={styles.assignmentLabel}>Your secret recipient</Text>
      <Text style={[styles.displayLg, styles.assignmentHeading, { marginTop: 8 }]}>
        {assignment.display_name}
      </Text>
      <View style={{ marginTop: 28, gap: 20 }}>
        <View>
          <Text style={styles.assignmentLabel}>Their wishlist</Text>
          <View style={{ marginTop: 8 }}>
            <RecipientWishList
              wishes={assignment.wishes ?? []}
              busy={busy}
              onClaim={onClaim}
              onRelease={onRelease}
            />
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
  const theme = useTheme();
  const { brand, styles } = theme;
  const local = localStyles(theme);
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
            maxLength={2000}
            value={wishlist}
            onValueChange={setWishlist}
            placeholder="Medium in tops, size 9 shoes, into cycling and cooking…"
          />
        </FieldLabel>
        <FieldLabel label="Allergies and things to avoid">
          <Textarea
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
        <Button style={styles.buttonBlock} disabled={busy} onPress={submit}>Save my details</Button>
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

/** Built once per scheme — see `scopedStyles`. */
const localStyles = scopedStyles((t) => ({
  disclosure: { borderWidth: 1, borderColor: t.brand.line, borderRadius: 12, padding: 16 },
  // The web app's `.sr-only`: announced, never drawn.
  srOnly: { position: 'absolute', width: 1, height: 1, overflow: 'hidden', opacity: 0 },
}));
