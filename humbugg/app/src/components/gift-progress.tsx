// Gift progress (#132) — how far along the gift is, from both ends.
//
// Two panels rather than one, because these are two facts about two different gifts. The stage row
// is the giver's record of what THEY have done for the person they drew; the receipt is the
// recipient's word about the gift somebody else is giving THEM. Merging them into one control would
// mean one of the two people editing the other's record.
//
// Neither panel names anybody. The stage row is about "your gift" and the receipt about "your gift
// from your giver" — the recipient does not learn who that is here any more than they do in the
// question thread.
import { Button, Switch } from '@ansavva/design-system';
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api, ApiError } from '../api/client';
import { useAuth } from '../context/auth-context';
import { gap, styles } from '../theme/styles';
import type { GiftReceipt, GiftStage, GiftStatus } from '../types';
import { Card } from './shell';
import { StatusMessage } from './status-message';

/** The three stages in the order a gift actually goes through them. */
const STAGES: { value: GiftStage; label: string }[] = [
  { value: 'choosing', label: 'Still choosing' },
  { value: 'purchased', label: 'Bought it' },
  { value: 'sent', label: 'Sent it' },
];

/**
 * The giver's own three stages.
 *
 * The organizer only ever sees counts of these, never who is where — which is why marking honestly
 * costs the giver nothing.
 */
export function GiftStagePanel({
  gift,
  busy,
  onChange,
}: {
  gift: GiftStatus;
  busy: boolean;
  onChange(stage: GiftStage): void;
}) {
  return (
    <Card>
      <Text style={styles.eyebrow}>Your gift</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Where has it got to?</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Your organizer sees how many gifts are bought and sent, never whose or what. Nobody learns
        who you drew from this.
      </Text>

      <View style={[local.stageRow, { marginTop: 24 }]}>
        {STAGES.map((stage) => (
          <Button
            key={stage.value}
            intent={gift.stage === stage.value ? 'primary' : 'secondary'}
            size="sm"
            disabled={busy || !gift.can_change_stage}
            onPress={() => onChange(stage.value)}
          >
            {stage.label}
          </Button>
        ))}
      </View>

      {gift.received ? (
        // The one ordering rule that is actually true, said in words: they have it, so the stage is
        // settled. Everything else — including going back to "still choosing" after a return — stays
        // a legitimate correction.
        <Text style={[styles.tiny, { marginTop: 12 }]}>
          They have said this arrived, so the stage is now fixed.
        </Text>
      ) : gift.stage_at ? (
        <Text style={[styles.tiny, { marginTop: 12 }]}>Last updated {when(gift.stage_at)}.</Text>
      ) : null}
    </Card>
  );
}

/**
 * The recipient's word that the gift turned up.
 *
 * Deliberately not gated on the giver having marked it sent: a gift handed over at a party never
 * was, and refusing the confirmation would make the organizer's roll-up wrong in order to protect a
 * sequence nobody promised.
 */
export function GiftReceivedPanel({ groupId }: { groupId: string }) {
  const auth = useAuth();
  const [receipt, setReceipt] = useState<GiftReceipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  const load = useCallback(async () => {
    try {
      setReceipt(await api.getGiftReceipt(await auth.accessToken(), groupId));
    } catch (err) {
      // Sitting out, or a draw reset while the page was open: there is no gift coming, and saying
      // so with a red bar would report a failure where nothing failed.
      if (err instanceof ApiError && (err.status === 403 || err.status === 404 || err.status === 409))
        setUnavailable(true);
      else setError(err instanceof Error ? err.message : 'That could not be loaded.');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId]);

  useEffect(() => { void load(); }, [load]);

  async function confirm(received: boolean) {
    setBusy(true);
    setError(null);
    try {
      setReceipt(await api.setGiftReceived(await auth.accessToken(), groupId, received));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  if (unavailable) return null;

  return (
    <Card>
      <View style={local.heading}>
        <View style={{ flex: 1, minWidth: 200 }}>
          <Text style={styles.eyebrow}>Your gift from your giver</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>Has it arrived?</Text>
        </View>
        {receipt ? (
          <Switch.Root
            checked={receipt.received}
            disabled={busy}
            aria-label="My gift has arrived"
            onCheckedChange={(received) => void confirm(received)}
          >
            <Switch.Thumb />
          </Switch.Root>
        ) : null}
      </View>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Saying so tells your organizer one more gift landed. It does not tell you, or them, who sent
        it.
      </Text>
      <StatusMessage message={error} />
      {receipt?.received_at ? (
        <Text style={[styles.tiny, { marginTop: 12 }]}>Marked as arrived {when(receipt.received_at)}.</Text>
      ) : null}
    </Card>
  );
}

function when(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : at.toLocaleDateString();
}

const local = StyleSheet.create({
  stageRow: { flexDirection: 'row', flexWrap: 'wrap', gap: gap.xs },
  heading: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: gap.sm,
  },
});
