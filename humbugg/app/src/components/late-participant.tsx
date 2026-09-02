// Adding somebody after the draw (#574).
//
// The draw is the one thing in Humbugg that cannot be quietly redone: people have already opened
// their assignment, some have already bought. So this is a two-step flow on purpose — a preview
// that says how many matches would move, then a confirmation of that exact proposal — and the
// number is the whole point. "This changes 2 people's matches" and "this changes everyone's" are
// different decisions, and an organizer should make the second one knowingly.
//
// A late participant is a member with `is_participating: false`; that is the backend's own
// definition (`RequirePendingMemberAsync` refuses anyone already in the draw), so the roster's
// "Sitting out" rows are exactly the candidates and no separate list is needed.
import { Button } from '@ansavva/design-system';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { api } from '../api/client';
import { useAuth } from '../context/auth-context';
import { blends, styles } from '../theme/styles';
import type { LateParticipantPreview, ParticipantReadiness } from '../types';
import { isPlusRequired } from './plus';
import { Card } from './shell';
import { StatusMessage } from './status-message';

export function LateParticipantPanel({
  groupId,
  person,
  onCancel,
  onAdded,
  onNeedsPlus,
}: {
  groupId: string;
  person: ParticipantReadiness;
  onCancel(): void;
  onAdded(): void;
  onNeedsPlus(): void;
}) {
  const auth = useAuth();
  const [preview, setPreview] = useState<LateParticipantPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function look() {
    setBusy(true);
    setError(null);
    try {
      setPreview(await api.previewLateParticipant(await auth.accessToken(), groupId, person.member_id));
    } catch (err) {
      if (isPlusRequired(err)) onNeedsPlus();
      else setError(message(err, 'That could not be worked out.'));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      await api.confirmLateParticipant(await auth.accessToken(), groupId, preview.proposal_id);
      onAdded();
    } catch (err) {
      // A stale proposal is the expected failure, not an exceptional one: the preview expires, and
      // any draw change invalidates it. The server says "create a new preview" and means it, so the
      // preview is dropped here and the flow restarts rather than retrying a dead proposal_id.
      setPreview(null);
      setError(message(err, 'That could not be confirmed.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card style={{ borderColor: blends.primaryBorder }}>
      <Text style={styles.eyebrow}>After the draw</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Add {person.display_name} to the draw</Text>

      {preview ? (
        <Text style={[styles.smallMuted, { marginTop: 8 }]}>
          {preview.affected_participant_count === 0
            ? 'Nobody else’s match changes.'
            : preview.affected_participant_count === 1
              ? 'One other person’s match changes. They are told, and whatever they had already chosen is for somebody else now.'
              : `${preview.affected_participant_count} other people’s matches change. They are told, and whatever they had already chosen is for somebody else now.`}
        </Text>
      ) : (
        <Text style={[styles.smallMuted, { marginTop: 8 }]}>
          Humbugg will work out the smallest change that fits them in, and tell you how many people
          it affects before anything moves.
        </Text>
      )}

      <StatusMessage message={error} />

      <View style={{ marginTop: 20, flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
        {preview ? (
          <Button disabled={busy} onPress={() => void confirm()}>
            {busy ? 'Adding…' : 'Yes, change the matches'}
          </Button>
        ) : (
          <Button disabled={busy} onPress={() => void look()}>
            {busy ? 'Working it out…' : 'See what it would change'}
          </Button>
        )}
        <Button intent="secondary" disabled={busy} onPress={onCancel}>
          Cancel
        </Button>
      </View>
    </Card>
  );
}

const message = (err: unknown, fallback: string) =>
  err instanceof Error && err.message ? err.message : fallback;
