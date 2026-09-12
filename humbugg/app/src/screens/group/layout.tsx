// One exchange: its header, its tabs, and the pages under them (#684, #690).
//
// Everyone sees two tabs named for the two people in their exchange: FOR <recipient> — the person
// they drew, that person's wishes, the gift's progress, the anonymous questions they asked — and
// FOR YOU — their own wishlist and details, whether their gift has arrived, the questions asked of
// them. Before the draw the first tab has no name yet, and says so. An organizer sees three more
// after a divider — People, Draw, Settings — which `OrganizerTabs` renders and explains.
//
// Each tab is a URL, not a state: `/groups/{id}/giving`, `/you`, `/people`, `/draw`,
// `/settings/{section}`. The page used to hold the active tab in `useState`, seeded once from
// `?tab=`, so a reload landed on the first tab and the browser's back button did nothing between
// them. Now the router owns it, this layout only reads it, and where you are is in the address bar.
import { Breadcrumbs, Tabs } from '@ansavva/design-system';
import { useRouter, useSegments } from 'expo-router';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Text, View, useWindowDimensions } from 'react-native';

import { api, ApiError } from '../../api/client';
import { isPlusRequired, PlusRefusalCard } from '../../components/plus';
import { ChatPanel } from '../../components/questions';
import { BottomSheet, PEEK } from '../../components/sheet';
import { LoadingPanel, Shell } from '../../components/shell';
import { StatusMessage } from '../../components/status-message';
import { useAuth } from '../../context/auth-context';
import { useTheme } from '../../theme/styles';
import type { GroupDetail, GroupReadiness, Membership, RecipientAssignment } from '../../types';
import { firstName, GroupContext, type GroupContextValue, type GroupTab } from './context';

const TABS: GroupTab[] = ['giving', 'you', 'people', 'draw', 'settings'];

function isGroupTab(value: string | undefined): value is GroupTab {
  return TABS.includes(value as GroupTab);
}

export default function GroupLayout({ groupId, children }: { groupId: string; children: ReactNode }) {
  const { styles, brand } = useTheme();
  const auth = useAuth();
  const router = useRouter();
  const segments = useSegments();
  // Wide enough for the chat to have a column of its own beside the page; narrower, it is a sheet
  // at the bottom of the screen that is dragged up to read and down to put away.
  const rail = useWindowDimensions().width >= 1024;
  const [group, setGroup] = useState<GroupDetail | null>(null);
  const [me, setMe] = useState<Membership | null>(null);
  const [assignment, setAssignment] = useState<RecipientAssignment | null>(null);
  const [readiness, setReadiness] = useState<GroupReadiness | null>(null);
  const [readinessError, setReadinessError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  // A 402 is not an error the member made; it is a price. Kept apart from `error` so it renders
  // as an offer with a way forward rather than a red bar with a dead end.
  const [plusRefusal, setPlusRefusal] = useState<string | null>(null);

  const loadReadiness = useCallback(async (token: string) => {
    try {
      setReadiness(await api.getReadiness(token, groupId));
      setReadinessError(null);
    } catch (err) {
      // A co-organizer demoted underneath us is a 403 here; say so rather than spin forever.
      setReadinessError(
        err instanceof ApiError && err.status === 403
          ? 'Only an organizer of this exchange can see who is ready.'
          : err instanceof Error ? err.message : 'Unable to load the roster.',
      );
    }
  }, [groupId]);

  const load = useCallback(async (quiet = false) => {
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
      const reads: Promise<unknown>[] = [];
      if (detail.status === 'drawn' && membership.is_participating) {
        reads.push(api.getAssignment(token, groupId).then(setAssignment, (err: unknown) => {
          if (err instanceof ApiError && err.status === 404) setAssignment(null);
          else throw err;
        }));
      } else setAssignment(null);
      if (detail.is_organizer) reads.push(loadReadiness(token));
      await Promise.all(reads);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load the group.');
    } finally {
      if (!quiet) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, loadReadiness]);

  useEffect(() => { void load(); }, [load]);

  const reload = useCallback(() => load(true), [load]);

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
  // must not clear the success banner from whatever the organizer just did. Both calls answer with
  // the whole assignment, so the page re-renders from the server's view rather than a locally
  // patched one — a wish the recipient deleted while the giver was deciding disappears instead of
  // lingering with a claim attached to nothing.
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

  // The segment after `[groupId]` is the tab; `settings/[section]` still starts with `settings`.
  const tab = useMemo(() => {
    const index = segments.findIndex((segment) => segment === '[groupId]');
    const next = index >= 0 ? segments[index + 1] : undefined;
    return isGroupTab(next) ? next : undefined;
  }, [segments]);

  const value = useMemo<GroupContextValue | null>(
    () => group && me
      ? { groupId, group, me, assignment, readiness, readinessError, busy, setGroup, reload, action, claimAction }
      : null,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [groupId, group, me, assignment, readiness, readinessError, busy, reload],
  );

  if (loading) return <Shell><LoadingPanel /></Shell>;
  if (!value) {
    return (
      <Shell>
        <View style={{ maxWidth: 576, alignSelf: 'center', width: '100%' }}>
          <StatusMessage message={error ?? 'Group not found.'} />
          <Breadcrumbs.Root style={{ marginTop: 16 }}>
            <Breadcrumbs.Item onPress={() => router.navigate('/')}>All groups</Breadcrumbs.Item>
          </Breadcrumbs.Root>
        </View>
      </Shell>
    );
  }

  const { group: detail, me: membership } = value;
  const participating = detail.members.filter((member) => member.is_participating).length;
  const meta = [
    detail.event_date ? new Date(`${detail.event_date}T12:00:00`).toLocaleDateString() : 'Date TBD',
    detail.spending_limit != null ? `$${detail.spending_limit.toFixed(2)} USD limit` : 'No spending limit',
    // The plan and its ceiling are the organizer's billing relationship with Humbugg. A participant
    // sees who is taking part; "plus plan" and "7 / 50" said somebody paid, and asked what 50 was.
    detail.is_organizer && detail.plan !== 'work'
      ? `${participating} / ${detail.participant_limit} participating · ${detail.plan} plan`
      : `${participating} participating`,
  ].join(' · ');

  const drawn = detail.status === 'drawn';
  // Somebody sitting out has nobody to give to, so there is no tab for it. Before the draw the
  // tab is there and nameless: the reveal has a place to land, and the page says when.
  const tabs: { value: GroupTab; label: string }[] = [
    ...(membership.is_participating
      ? [{ value: 'giving' as const, label: assignment ? `For ${firstName(assignment.display_name)}` : 'For ···' }]
      : []),
    { value: 'you', label: 'For you' },
  ];
  const organizerTabs: { value: GroupTab; label: string }[] = detail.is_organizer
    ? [
        { value: 'people', label: 'People' },
        { value: 'draw', label: 'Draw' },
        { value: 'settings', label: 'Settings' },
      ]
    : [];

  // Anonymous chat (#131), both conversations: the one you opened about the gift you are buying,
  // and the one somebody opened about the gift you are getting. It sits beside every tab rather
  // than on one of them, because it is a messenger about the exchange, not a section of it. Only
  // after the draw and only for someone taking part — before that neither conversation exists.
  const chatting = drawn && membership.is_participating;
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

  return (
    <GroupContext.Provider value={value}>
      <Shell aside={rail ? chat : undefined} sheet={rail ? undefined : chat} sheetInset={chatting && !rail ? PEEK : 0}>
        <Breadcrumbs.Root style={{ marginBottom: 20 }}>
          <Breadcrumbs.Item onPress={() => router.navigate('/')}>All groups</Breadcrumbs.Item>
          <Breadcrumbs.Item current>{detail.name}</Breadcrumbs.Item>
        </Breadcrumbs.Root>
        <View style={{ gap: 24 }}>
          <View style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <View style={[styles.statusPill, drawn && styles.statusDrawn]}>
                <Text style={[styles.statusPillText, drawn && styles.statusDrawnText]}>
                  {drawn ? 'Draw complete' : 'Open for joining'}
                </Text>
              </View>
              {detail.is_organizer ? <Text style={styles.smallMuted}>You’re organizing</Text> : null}
            </View>
            <Text style={styles.displayMd}>{detail.name}</Text>
            {detail.description ? (
              <Text style={[styles.bodyMuted, { maxWidth: 672 }]}>{detail.description}</Text>
            ) : null}
            <Text style={styles.smallMuted}>{meta}</Text>
          </View>

          <Tabs.Root
            defaultValue="you"
            value={tab}
            onValueChange={(next) => {
              // Settings opens on its first section, so the URL is the section's from the start.
              router.navigate(next === 'settings' ? `/groups/${groupId}/settings/exchange` : `/groups/${groupId}/${next as GroupTab}`);
            }}
          >
            {/* Wrapped, not scrolled: five short labels fit on two lines of a phone, and a strip
                that scrolls sideways hides the last tab off the edge. */}
            <Tabs.List style={{ flexWrap: 'wrap', borderBottomWidth: 1, borderBottomColor: brand.line }}>
              {tabs.map((item) => (
                <Tabs.Tab key={item.value} value={item.value}>{item.label}</Tabs.Tab>
              ))}
              {organizerTabs.length ? (
                <View accessible={false} style={{ width: 1, marginVertical: 10, marginHorizontal: 6, backgroundColor: brand.line }} />
              ) : null}
              {organizerTabs.map((item) => (
                <Tabs.Tab key={item.value} value={item.value}>{item.label}</Tabs.Tab>
              ))}
            </Tabs.List>
          </Tabs.Root>

          <StatusMessage message={error} />
          <StatusMessage message={success} tone="success" />
          {plusRefusal ? (
            <PlusRefusalCard
              groupId={groupId}
              reason={plusRefusal}
              action="do what this exchange just asked for"
              // Billing is a section of this page, not another page.
              onNavigate={(path) => { setPlusRefusal(null); router.navigate(path as never); }}
            />
          ) : null}

          <View style={{ gap: 28 }}>{children}</View>
        </View>
      </Shell>
    </GroupContext.Provider>
  );
}
