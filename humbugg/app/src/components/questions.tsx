// Anonymous chat (#131) — one panel holding both of a participant's conversations.
//
// A giver can ask their recipient about a gift without saying who is asking. The app is the last of
// the five surfaces the issue names, and it is the easiest to get wrong: a name is exactly the thing
// a chat UI reaches for. It never has one to reach for here, because the API sends a SIDE and not a
// person, and this file renders that side through a label the viewer's own role decides.
//
// It reads as a chat on purpose — bubbles on two sides, newest at the bottom, a composer that sends
// on Enter, the thread refreshed while the panel is open, and on a wide screen a column of its own
// beside the exchange, the way a messenger sits beside the thing it is about. Nothing about the
// chat shape touches the guarantee: a bubble's side is the author's role, the only label ever drawn
// is the other side's role, and "You" lives in the accessibility label alone.
//
// One thread view for both conversations, deliberately. Two would be two places to write a name
// into, and the first divergence between them would be an identity.
import { Button, IconButton, Popover, Separator, Switch, Textarea, Toggle, ToggleGroup } from '@ansavva/design-system';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, ScrollView, Text, View } from 'react-native';

import { api, ApiError } from '../api/client';
import { useAuth } from '../context/auth-context';
import { useProfile } from '../context/profile-context';
import { radii } from '../theme/radii';
import { gap, scopedStyles, useTheme } from '../theme/styles';
import type { QuestionAuthor, QuestionMessage, QuestionThread } from '../types';
import { chatRailPreference } from '../utils/chat-rail-preference';
import { Avatar, SantaAvatar } from './avatar';
import { Card } from './shell';
import { StatusMessage } from './status-message';

/** Which end of a conversation the viewer is. It decides the labels and nothing else. */
export type QuestionSide = 'giver' | 'recipient';

/**
 * How often an open panel asks for the thread again.
 *
 * There is no push channel, so "the other side replied" reaches a panel by asking. Fifteen seconds
 * is slow enough that a page left open all day costs nothing worth measuring and fast enough that
 * a reply lands while you are still looking.
 */
const POLL_MS = 15_000;

/** The composer grows with the draft, from one line to about five, then scrolls. */
const COMPOSER_MIN = 44;
const COMPOSER_MAX = 120;

const COPY: Record<QuestionSide, {
  /** The switcher's word for this conversation when there is no one to name — see `tabLabel`. */
  tab: string;
  heading: string;
  blurb: string;
  empty: string;
  placeholder: string;
  send: string;
  /** What the OTHER side's messages are called. Never a name — there is none to use. */
  them: string;
}> = {
  giver: {
    tab: 'About their gift',
    heading: 'Ask about their gift',
    blurb: 'They are told someone in the exchange is asking, and never who.',
    empty: 'Ask about a size, a colour, or whether they already own it.',
    placeholder: 'What size do you take?',
    send: 'Send anonymously',
    them: 'Them',
  },
  recipient: {
    // The role, because a name is exactly what this conversation must never carry. "Santa" rather
    // than "giver" here because the tab is a person's name on the other side, and this reads as
    // one too.
    tab: 'Your Secret Santa',
    heading: 'Questions about your gift',
    blurb:
      'Someone giving you a gift can ask about it here. Humbugg does not tell you who, and your ' +
      'answers do not tell them anything either.',
    empty: 'Nobody has asked you anything yet.',
    placeholder: 'Medium, and I already have the blue one.',
    send: 'Reply',
    them: 'Your Secret Santa',
  },
};

// ── The panel ────────────────────────────────────────────────────────────────────────────────────

/**
 * Both conversations, one surface.
 *
 * Three layouts. `rail` is the wide screen: the panel fills the column `Shell` gives it beside the
 * page — a thin header, the thread taking every pixel between, the composer pinned at the bottom —
 * the shape every side-panel messenger has; it folds away to a launcher in the page's corner, and
 * the choice is remembered. `sheet` is the phone: the same fill-the-box shape inside a
 * `BottomSheet`, which owns the handle and the height. `card` is a card in the page's flow, the
 * thread bounded on its own.
 *
 * `recipient` names (and pictures) the giver's conversation after the person it is with. It can
 * only ever be the giver's OWN recipient — the name on their assignment card, which they already
 * have — and it reaches that one conversation only. The other conversation is with someone this
 * component must never name, and there is no prop through which it could.
 */
export type ChatLayout = 'card' | 'rail' | 'sheet';

export interface ChatRecipient {
  name: string;
  avatar?: string | null | undefined;
}

export function ChatPanel({
  groupId,
  layout = 'card',
  recipient: recipientPerson,
}: {
  groupId: string;
  layout?: ChatLayout;
  recipient?: ChatRecipient | null | undefined;
}) {
  const rail = layout === 'rail';
  const fill = layout !== 'card';
  const theme = useTheme();
  const { styles } = theme;
  const local = localStyles(theme);
  const giver = useThread(groupId, 'giver');
  const recipient = useThread(groupId, 'recipient');
  const [chosen, setChosen] = useState<QuestionSide>('giver');
  // What a conversation is, shown while its tab is hovered or focused. The bubble is the
  // package's Popover rather than its Tooltip: on this leaf Tooltip opens on long-press alone and
  // anchors ABOVE its trigger, and the tabs sit at the top of the rail, where above is off the
  // screen. Popover anchors below. One Root around the whole row, not one per tab, so the bubble
  // hangs from the row's left edge — 320 wide, the one place in a 420 rail it fits.
  const [hovered, setHovered] = useState<QuestionSide | null>(null);
  // Null until the stored preference is read, so the rail does not open and then snap shut.
  const [open, setOpen] = useState<boolean | null>(null);
  useEffect(() => {
    if (!rail) return;
    void chatRailPreference.loadOpen().then(setOpen);
  }, [rail]);
  function toggle(next: boolean) {
    setOpen(next);
    void chatRailPreference.saveOpen(next);
  }

  const available = (['giver', 'recipient'] as const).filter(
    (side) => !(side === 'giver' ? giver : recipient).unavailable,
  );
  // A member who is sitting out, or an exchange whose draw was reset while the page was open, has
  // no conversations. The panel removes itself rather than reporting an error for something that
  // correctly does not exist.
  if (available.length === 0) return null;
  const side = available.includes(chosen) ? chosen : available[0]!;
  const state = side === 'giver' ? giver : recipient;
  const copy = COPY[side];
  const unread = (giver.thread?.unread ?? 0) + (recipient.thread?.unread ?? 0);

  if (rail && open === null) return null;
  if (rail && !open) {
    return (
      <View style={styles.asideLauncher}>
        <Button
          intent="primary"
          aria-label={unread > 0 ? `Open chat, ${unread} unread` : 'Open chat'}
          onPress={() => toggle(true)}
        >
          {unread > 0 ? `Chat · ${unread}` : 'Chat'}
        </Button>
      </View>
    );
  }

  const Surface = fill ? View : Card;
  return (
    <Surface style={rail ? [styles.aside, local.rail] : layout === 'sheet' ? local.sheet : undefined}>
      <View style={local.heading}>
        <View style={{ flex: 1, minWidth: 160 }}>
          {fill ? (
            <Text style={styles.headingSm}>
              Anonymous chat
              {/* In the sheet the title is all that shows at rest, so it carries the count. */}
              {layout === 'sheet' && unread > 0 ? <Text style={styles.semibold}>{` · ${unread}`}</Text> : null}
            </Text>
          ) : (
            <>
              <Text style={styles.eyebrow}>Anonymous chat</Text>
              <Text style={[styles.heading, { marginTop: 4 }]}>{copy.heading}</Text>
            </>
          )}
        </View>
        {/* The recipient's door, in the header's corner: it is the one control that is about the
            conversation rather than a line in it. */}
        {side === 'recipient' && state.thread ? (
          <View style={local.blockRow}>
            <Text style={styles.smallMuted}>Allow questions</Text>
            <Switch.Root
              checked={!state.thread.blocked}
              disabled={state.busy}
              aria-label="Allow anonymous questions about my gift"
              onCheckedChange={(allowed) => void state.setBlocked(!allowed)}
            >
              <Switch.Thumb />
            </Switch.Root>
          </View>
        ) : null}
        {rail ? (
          <IconButton label="Close chat" size="sm" onPress={() => toggle(false)}>
            ✕
          </IconButton>
        ) : null}
      </View>

      {/* Two conversations, the way a messenger lists threads — named for who is on the other end
          where there is a name to use (your recipient, whom you know) and for the role where there
          is not (your giver, whom you must not). */}
      {available.length > 1 ? (
        <Popover.Root open={hovered !== null} onOpenChange={(next) => { if (!next) setHovered(null); }}>
          <ToggleGroup.Root
            value={[side]}
            onValueChange={(value) => { if (value[0]) setChosen(value[0] as QuestionSide); }}
            size="sm"
            style={local.switcher}
          >
            {available.map((item) => {
              const count = (item === 'giver' ? giver : recipient).thread?.unread ?? 0;
              const name = tabLabel(item, recipientPerson?.name);
              return (
                <Toggle
                  key={item}
                  value={item}
                  // The note is the tab's description too, so a screen reader hears it without a
                  // pointer to hover.
                  aria-label={count > 0 ? `${name}, ${count} unread. ${COPY[item].blurb}` : `${name}. ${COPY[item].blurb}`}
                  onHoverIn={() => setHovered(item)}
                  onHoverOut={() => setHovered((current) => (current === item ? null : current))}
                  onFocus={() => setHovered(item)}
                  onBlur={() => setHovered((current) => (current === item ? null : current))}
                  // A click focuses too, and a note that stays open over the thread you just
                  // switched to is in the way. Pressing closes it; the next hover reopens it.
                  onPressIn={() => setHovered(null)}
                >
                  {name}
                  {/* Nested text, not a pill: the toggle's label is a <Text>, and a View inside
                      one does not render on native. */}
                  {count > 0 ? <Text style={styles.semibold}>{` · ${count}`}</Text> : null}
                </Toggle>
              );
            })}
          </ToggleGroup.Root>
          <Popover.Content label="About this conversation">
            <Text style={styles.small}>{hovered ? COPY[hovered].blurb : ''}</Text>
          </Popover.Content>
        </Popover.Root>
      ) : null}

      {/* Who is on the other end — the thing the whole feature is about, said with a face. The
          giver's recipient by photo and name, because the giver already knows both parties; the
          recipient's giver as a Santa hat and a role, because they never will. */}
      <View style={local.who}>
        {side === 'giver' && recipientPerson ? (
          <Avatar src={recipientPerson.avatar} name={recipientPerson.name} size={32} bordered />
        ) : (
          <SantaAvatar size={32} />
        )}
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={[styles.small, styles.semibold]} numberOfLines={1}>{them(side, recipientPerson?.name)}</Text>
          <Text style={styles.tiny} numberOfLines={1}>
            {side === 'giver' ? 'You are their Secret Santa here' : 'Knows who you are — you never will'}
          </Text>
        </View>
      </View>
      {fill ? <Separator style={local.rule} /> : null}

      <ThreadView
        side={side}
        state={state}
        fill={fill}
        them={them(side, recipientPerson?.name)}
        recipient={side === 'giver' ? recipientPerson : null}
      />
    </Surface>
  );
}

/** The conversation's name in the switcher: the person where there is one, the role otherwise. */
function tabLabel(side: QuestionSide, recipientName: string | null | undefined): string {
  return side === 'giver' && recipientName ? recipientName : COPY[side].tab;
}

/**
 * What the other side is called on the giver's conversation — their recipient, by name — and on the
 * recipient's, the role. The second branch has no name to reach for, by construction.
 */
function them(side: QuestionSide, recipientName: string | null | undefined): string {
  return side === 'giver' && recipientName ? recipientName : COPY[side].them;
}

// ── One conversation ─────────────────────────────────────────────────────────────────────────────

interface ThreadState {
  thread: QuestionThread | null;
  error: string | null;
  busy: boolean;
  unavailable: boolean;
  send(body: string): Promise<boolean>;
  setBlocked(blocked: boolean): Promise<boolean>;
  /** The conversation is on screen. Quiet: a failure here is retried by the next poll. */
  markSeen(): Promise<void>;
}

/** Loads one conversation, keeps it fresh, and is the only place the API is called. */
function useThread(groupId: string, side: QuestionSide): ThreadState {
  const auth = useAuth();
  const [thread, setThread] = useState<QuestionThread | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  // Read by the poll, so a refresh never lands on top of a send in flight and reorders it.
  const sending = useRef(false);

  const load = useCallback(async ({ quiet }: { quiet: boolean }) => {
    if (quiet && sending.current) return;
    try {
      const token = await auth.accessToken();
      setThread(side === 'giver'
        ? await api.getGiverQuestions(token, groupId)
        : await api.getRecipientQuestions(token, groupId));
    } catch (err) {
      if (err instanceof ApiError && (err.status === 403 || err.status === 404 || err.status === 409))
        setUnavailable(true);
      // A refresh that fails is tried again in fifteen seconds; only the first load reports.
      else if (!quiet) setError(err instanceof Error ? err.message : 'Questions could not be loaded.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, side]);

  useEffect(() => { void load({ quiet: false }); }, [load]);

  useEffect(() => {
    if (unavailable) return undefined;
    const timer = setInterval(() => void load({ quiet: true }), POLL_MS);
    return () => clearInterval(timer);
  }, [load, unavailable]);

  async function run(work: (token: string) => Promise<QuestionThread>) {
    setBusy(true);
    setError(null);
    try {
      setThread(await work(await auth.accessToken()));
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That could not be sent.');
      return false;
    } finally {
      setBusy(false);
    }
  }

  return {
    thread,
    error,
    busy,
    unavailable,
    async send(body) {
      sending.current = true;
      try {
        return await run((token) =>
          side === 'giver' ? api.askQuestion(token, groupId, body) : api.replyToQuestion(token, groupId, body),
        );
      } finally {
        sending.current = false;
      }
    },
    setBlocked: (blocked) => run((token) => api.setQuestionsBlocked(token, groupId, blocked)),
    async markSeen() {
      try {
        setThread(await api.markQuestionsSeen(await auth.accessToken(), groupId, side));
      } catch {
        /* the badge stays one poll longer */
      }
    },
  };
}

function ThreadView({
  side,
  state,
  fill,
  them,
  recipient,
}: {
  side: QuestionSide;
  state: ThreadState;
  fill: boolean;
  /** What the other side's bubbles are captioned. */
  them: string;
  /** On the giver's side, who they are writing to — pictured beside that side's runs. */
  recipient?: ChatRecipient | null | undefined;
}) {
  const theme = useTheme();
  const { styles } = theme;
  const local = localStyles(theme);
  const copy = COPY[side];
  const { thread } = state;
  const { profile } = useProfile();

  // This view exists only while its conversation is the one on screen — the panel renders the
  // chosen thread and no other, and none at all when folded away — so being mounted with unread
  // messages IS having seen them.
  const unread = thread?.unread ?? 0;
  useEffect(() => {
    if (unread > 0) void state.markSeen();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unread, side]);
  const [draft, setDraft] = useState('');
  const [composerHeight, setComposerHeight] = useState(COMPOSER_MIN);
  const list = useRef<ScrollView>(null);

  // Newest at the bottom, and the bottom is where the panel rests whenever something arrives.
  const count = thread?.messages.length ?? 0;
  useEffect(() => {
    if (count > 0) list.current?.scrollToEnd({ animated: true });
  }, [count, side]);

  const body = draft.trim();
  const canSend = !state.busy && body.length > 0;

  function send() {
    if (!canSend) return;
    void state.send(body).then((sent) => {
      if (sent) {
        setDraft('');
        setComposerHeight(COMPOSER_MIN);
      }
    });
  }

  return (
    <View style={[local.thread, fill && local.threadFill]}>
      <StatusMessage message={state.error} />

      {!thread ? (
        <Text style={styles.smallMuted}>Loading…</Text>
      ) : thread.messages.length === 0 ? (
        // In the rail the empty thread is simply empty space with a line in the middle of it —
        // a dashed placeholder box filling a whole column reads as a broken page.
        <View style={fill ? local.emptyFill : styles.emptyPanel}>
          <Text style={[styles.bodyMuted, fill && { textAlign: 'center' }]}>{copy.empty}</Text>
        </View>
      ) : (
        <ScrollView
          ref={list}
          style={fill ? local.listFill : local.list}
          contentContainerStyle={local.listContent}
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => list.current?.scrollToEnd({ animated: false })}
        >
          {rows(thread.messages, side).map((row) =>
            row.kind === 'day' ? (
              <Text key={row.key} style={[styles.tiny, local.day]}>{row.label}</Text>
            ) : (
              <View
                key={row.message.message_id}
                accessibilityLabel={`${label(row.message.author, side, them)}: ${row.message.body}`}
                style={[local.runRow, row.mine ? local.runRowMine : local.runRowTheirs, row.first && local.runRowFirst]}
              >
                {/* A face beside the last bubble of a run, on the outside, the way a messenger
                    does — and the faces say what the feature is. Their side: the recipient's photo
                    on the giver's conversation, the hat on the recipient's. My side: the hat on the
                    giver's conversation, the standing reminder that here you write as Santa; your
                    own face on the recipient's, because there you are simply yourself. */}
                <View style={local.face}>
                  {row.last && !row.mine ? (
                    recipient ? (
                      <Avatar src={recipient.avatar} name={recipient.name} size={24} bordered />
                    ) : (
                      <SantaAvatar size={24} />
                    )
                  ) : null}
                  {row.last && row.mine ? (
                    side === 'giver' ? (
                      <SantaAvatar size={24} />
                    ) : (
                      <Avatar src={profile?.avatar_url} name={profile?.display_name} size={24} bordered />
                    )
                  ) : null}
                </View>
                <View style={[local.run, row.mine ? local.runMine : local.runTheirs]}>
                  {row.first && !row.mine ? (
                    <Text style={[styles.tiny, local.caption]}>{them}</Text>
                  ) : null}
                  <View
                    style={[
                      local.bubble,
                      row.mine ? local.mine : local.theirs,
                      row.last && (row.mine ? local.tailMine : local.tailTheirs),
                    ]}
                  >
                    <Text style={[styles.small, row.mine ? local.mineText : local.theirsText]}>
                      {row.message.body}
                    </Text>
                  </View>
                  {row.last && row.time ? (
                    <Text style={[styles.tiny, local.time]}>{row.time}</Text>
                  ) : null}
                </View>
              </View>
            ),
          )}
        </ScrollView>
      )}

      {thread?.can_send ? (
        <View style={local.composer}>
          <Textarea
            aria-label={copy.heading}
            value={draft}
            onValueChange={setDraft}
            maxLength={1000}
            rows={1}
            placeholder={copy.placeholder}
            style={[local.input, { height: composerHeight }]}
            onContentSizeChange={(event) =>
              setComposerHeight(
                Math.min(COMPOSER_MAX, Math.max(COMPOSER_MIN, event.nativeEvent.contentSize.height)),
              )
            }
            // Enter sends and Shift+Enter breaks the line, on a keyboard. A phone's return key
            // keeps breaking the line — every messaging app on the platform does the same, and
            // the send button is right there.
            onKeyPress={(event) => {
              if (Platform.OS !== 'web') return;
              const key = event.nativeEvent as { key: string; shiftKey?: boolean };
              if (key.key === 'Enter' && !key.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
          />
          <IconButton label={copy.send} intent="primary" disabled={!canSend} onPress={send}>
            ↑
          </IconButton>
        </View>
      ) : thread ? (
        <Text style={styles.tiny}>{thread.blocked_reason}</Text>
      ) : null}
    </View>
  );
}

/**
 * What to call a message's author, from this viewer's seat.
 *
 * The only two answers are "You" and the other side's role. There is deliberately no branch that
 * could produce a name: `author` is a role and this function has nothing else to work from.
 */
function label(author: QuestionAuthor, side: QuestionSide, them: string): string {
  return author === side ? 'You' : them;
}

type Row =
  | { kind: 'day'; key: string; label: string }
  | {
      kind: 'message';
      message: QuestionMessage;
      mine: boolean;
      /** First and last of a run of messages from one side — where the label and the time go. */
      first: boolean;
      last: boolean;
      time: string | null;
    };

/**
 * The thread as a chat lays it out: a day marker where the date turns, and messages grouped into
 * runs by side so the role label and the time appear once per run rather than on every bubble.
 */
function rows(messages: QuestionMessage[], side: QuestionSide): Row[] {
  const out: Row[] = [];
  let lastDay: string | null = null;
  messages.forEach((message, index) => {
    const at = when(message.created_at);
    const day = at ? dayLabel(at) : null;
    if (day && day !== lastDay) {
      out.push({ kind: 'day', key: `day-${message.message_id}`, label: day });
      lastDay = day;
    }
    const previous = messages[index - 1];
    const next = messages[index + 1];
    const last = next?.author !== message.author;
    out.push({
      kind: 'message',
      message,
      mine: message.author === side,
      first: previous?.author !== message.author,
      last,
      time: last && at ? timeLabel(at) : null,
    });
  });
  return out;
}

function when(iso: string): Date | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dayLabel(date: Date, now = new Date()): string {
  const midnight = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const daysAgo = Math.round((midnight(now) - midnight(date)) / 86_400_000);
  if (daysAgo === 0) return 'Today';
  if (daysAgo === 1) return 'Yesterday';
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    ...(date.getFullYear() === now.getFullYear() ? {} : { year: 'numeric' }),
  });
}

function timeLabel(date: Date): string {
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/** Built once per scheme — see `scopedStyles`. */
const localStyles = scopedStyles((t) => ({
  // The rail's padding; its width, height and rule are `styles.aside`. No `flex` here — in the
  // Shell's row that would widen it, not fill it.
  rail: { paddingHorizontal: gap.xl, paddingTop: gap.xl, paddingBottom: gap.lg },
  // The sheet: `BottomSheet` owns the box and the handle; this fills what is left of it.
  sheet: { flex: 1, minHeight: 0, paddingHorizontal: gap.lg, paddingBottom: gap.md, paddingTop: 2 },
  who: { flexDirection: 'row', alignItems: 'center', gap: gap.sm, marginTop: gap.xl },
  rule: { marginTop: gap.lg },
  heading: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: gap.sm,
  },
  blockRow: { flexDirection: 'row', alignItems: 'center', gap: gap.xs },
  switcher: { flexDirection: 'row', gap: 6, marginTop: gap.lg },
  thread: { marginTop: gap.lg, gap: gap.md },
  threadFill: { flex: 1, minHeight: 0 },
  // Bounded, so a long conversation scrolls inside the card instead of pushing the rest of the
  // page — and the composer stays in reach under it.
  list: { maxHeight: 420 },
  listFill: { flex: 1, minHeight: 0 },
  emptyFill: { flex: 1, justifyContent: 'center', paddingHorizontal: gap.lg },
  listContent: { gap: 4, paddingVertical: gap.xs },
  day: { alignSelf: 'center', marginVertical: gap.md },
  // A run is a row: the face column on the outside, the bubbles beside it. The face column is
  // always there so bubbles in one run line up whether or not this one carries the face.
  runRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, alignSelf: 'stretch' },
  runRowMine: { flexDirection: 'row-reverse' },
  runRowTheirs: {},
  runRowFirst: { marginTop: gap.xs },
  face: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center', marginBottom: 18 },
  // Of the row, which spans the list — so a bubble may use most of the width and no more.
  run: { maxWidth: '82%', flexShrink: 1 },
  runMine: { alignItems: 'flex-end' },
  runTheirs: { alignItems: 'flex-start' },
  caption: { marginBottom: 2, marginLeft: 4 },
  time: { marginTop: 2, marginHorizontal: 4 },
  bubble: { borderRadius: radii.lg, paddingVertical: 8, paddingHorizontal: 12 },
  // The tail: the last bubble in a run squares off the corner nearest the sender, the way every
  // chat client points a run at the person who wrote it.
  tailMine: { borderBottomRightRadius: radii.xs },
  tailTheirs: { borderBottomLeftRadius: radii.xs },
  // Mine sits on the brand fill, theirs on the plain surface — a contrast that carries no identity,
  // only "this one is yours".
  mine: { backgroundColor: t.brand.primary },
  mineText: { color: t.brand.primaryText },
  theirs: { backgroundColor: t.brand.surfaceAlt },
  theirsText: { color: t.brand.ink },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: gap.xs },
  input: { flex: 1, width: 'auto', minHeight: COMPOSER_MIN, maxHeight: COMPOSER_MAX },
}));
