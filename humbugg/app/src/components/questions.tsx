// Anonymous questions (#131) — one panel, rendered from both ends of the same conversation.
//
// A giver can ask their recipient about a gift without saying who is asking. The app is the last of
// the five surfaces the issue names, and it is the easiest to get wrong: a name is exactly the thing
// a chat UI reaches for. It never has one to reach for here, because the API sends a SIDE and not a
// person, and this file renders that side through a label the viewer's own role decides.
//
// One component for both ends, deliberately. Two panels would be two places to write a name into,
// and the first divergence between them would be an identity.
import { Button, Switch, Textarea } from '@ansavva/design-system';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api, ApiError } from '../api/client';
import { useAuth } from '../context/auth-context';
import { blends, gap, styles } from '../theme/styles';
import { brand } from '../theme/theme';
import type { QuestionAuthor, QuestionThread } from '../types';
import { Card } from './shell';
import { StatusMessage } from './status-message';

/** Which end of the conversation this panel is. It decides the labels and nothing else. */
export type QuestionSide = 'giver' | 'recipient';

const COPY: Record<QuestionSide, {
  eyebrow: string;
  heading: string;
  blurb: string;
  empty: string;
  placeholder: string;
  send: string;
  /** What the OTHER side's messages are called. Never a name — there is none to use. */
  them: string;
}> = {
  giver: {
    eyebrow: 'Anonymous questions',
    heading: 'Ask about their gift',
    blurb:
      'They are told someone in the exchange asked, and never who. Ask about a size, a colour, ' +
      'or whether they already own it.',
    empty: 'You have not asked anything yet.',
    placeholder: 'What size do you take?',
    send: 'Send anonymously',
    them: 'Them',
  },
  recipient: {
    eyebrow: 'Anonymous questions',
    heading: 'Questions about your gift',
    blurb:
      'Someone giving you a gift can ask about it here. Humbugg does not tell you who, and your ' +
      'answers do not tell them anything either.',
    empty: 'Nobody has asked you anything.',
    placeholder: 'Medium, and I already have the blue one.',
    send: 'Reply',
    them: 'Your giver',
  },
};

export function QuestionsPanel({ groupId, side }: { groupId: string; side: QuestionSide }) {
  const auth = useAuth();
  const copy = COPY[side];
  const [thread, setThread] = useState<QuestionThread | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A member who is sitting out, or an exchange whose draw was reset while the page was open, has
  // no thread to show. The panel removes itself rather than reporting an error for a conversation
  // that correctly does not exist.
  const [unavailable, setUnavailable] = useState(false);

  const load = useCallback(async () => {
    try {
      const token = await auth.accessToken();
      setThread(side === 'giver'
        ? await api.getGiverQuestions(token, groupId)
        : await api.getRecipientQuestions(token, groupId));
    } catch (err) {
      if (err instanceof ApiError && (err.status === 403 || err.status === 404 || err.status === 409))
        setUnavailable(true);
      else setError(err instanceof Error ? err.message : 'Questions could not be loaded.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, side]);

  useEffect(() => { void load(); }, [load]);

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

  if (unavailable) return null;

  return (
    <Card>
      <View style={local.heading}>
        <View style={{ flex: 1, minWidth: 200 }}>
          <Text style={styles.eyebrow}>{copy.eyebrow}</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>{copy.heading}</Text>
        </View>
        {side === 'recipient' && thread ? (
          <View style={local.blockRow}>
            <Text style={styles.smallMuted}>Allow questions</Text>
            <Switch.Root
              checked={!thread.blocked}
              disabled={busy}
              aria-label="Allow anonymous questions about my gift"
              onCheckedChange={(allowed) =>
                void run((token) => api.setQuestionsBlocked(token, groupId, !allowed))
              }
            >
              <Switch.Thumb />
            </Switch.Root>
          </View>
        ) : null}
      </View>

      <Text style={[styles.smallMuted, { marginTop: 8 }]}>{copy.blurb}</Text>

      <View style={{ marginTop: 24, gap: gap.sm }}>
        <StatusMessage message={error} />

        {!thread ? (
          <Text style={styles.smallMuted}>Loading…</Text>
        ) : thread.messages.length === 0 ? (
          <View style={styles.emptyPanel}>
            <Text style={styles.bodyMuted}>{copy.empty}</Text>
          </View>
        ) : (
          thread.messages.map((message) => (
            <View
              key={message.message_id}
              accessibilityLabel={`${label(message.author, side, copy.them)}: ${message.body}`}
              style={[local.bubble, message.author === side ? local.mine : local.theirs]}
            >
              <Text style={styles.eyebrow}>{label(message.author, side, copy.them)}</Text>
              <Text style={[styles.small, { marginTop: 6 }]}>{message.body}</Text>
            </View>
          ))
        )}

        {thread?.can_send ? (
          <View style={{ gap: gap.sm }}>
            <Textarea
              aria-label={copy.heading}
              value={draft}
              onValueChange={setDraft}
              maxLength={1000}
              placeholder={copy.placeholder}
            />
            <View style={{ alignSelf: 'flex-start' }}>
              <Button
                disabled={busy || draft.trim().length === 0}
                onPress={() =>
                  void run((token) =>
                    side === 'giver'
                      ? api.askQuestion(token, groupId, draft.trim())
                      : api.replyToQuestion(token, groupId, draft.trim()),
                  ).then((sent) => { if (sent) setDraft(''); })
                }
              >
                {copy.send}
              </Button>
            </View>
          </View>
        ) : thread ? (
          <Text style={styles.tiny}>{thread.blocked_reason}</Text>
        ) : null}
      </View>
    </Card>
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

const local = StyleSheet.create({
  heading: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: gap.sm,
  },
  blockRow: { flexDirection: 'row', alignItems: 'center', gap: gap.xs },
  bubble: { borderRadius: 12, padding: gap.md, borderWidth: 1 },
  // Mine sits on the brand wash, theirs on the plain surface — a contrast that carries no identity,
  // only "this one is yours".
  mine: { backgroundColor: blends.primaryWash, borderColor: blends.primaryBorder },
  theirs: { backgroundColor: brand.surfaceAlt, borderColor: brand.line },
});
