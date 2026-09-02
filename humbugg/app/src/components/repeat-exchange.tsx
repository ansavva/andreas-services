// Repeat an exchange (#136) — start next year's from last year's without retyping the group.
//
// What it does NOT do is the important half. It creates a new exchange rather than reopening the
// old one, so last year stays exactly as it was; and it invites nobody, because silently enrolling
// last year's roster would put people in a draw they never agreed to. The prior participants come
// back as a list of names — a reminder of who to send the link to, not a guest list.
//
// Nothing private travels, and not because this screen filters it: the new exchange has no
// memberships except the organizer's, so there is nowhere for a wishlist, an address, a
// conversation or a gift stage to land.
import { Button, Checkbox, Input } from '@ansavva/design-system';
import * as Clipboard from 'expo-clipboard';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { api } from '../api/client';
import { FieldLabel } from './field';
import { Card } from './shell';
import { StatusMessage } from './status-message';
import { useAuth } from '../context/auth-context';
import { blends, gap, styles } from '../theme/styles';
import type { GroupDetail, RepeatedExchange } from '../types';

export function RepeatExchangePanel({ group }: { group: GroupDetail }) {
  const auth = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(group.name);
  const [eventDate, setEventDate] = useState('');
  const [copyDetails, setCopyDetails] = useState(true);
  // Off by default. Last year's "these two are a couple" may not be true any more, and a constraint
  // nobody asked for is worse than one they have to add back.
  const [copyExclusions, setCopyExclusions] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RepeatedExchange | null>(null);
  const [copied, setCopied] = useState(false);

  async function repeat() {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await api.repeatExchange(await auth.accessToken(), group.group_id, {
          name: name.trim(),
          event_date: eventDate.trim(),
          copy_details: copyDetails,
          copy_exclusions: copyExclusions,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The new exchange could not be created.');
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <Card style={{ borderColor: blends.primaryBorder }}>
        <Text style={styles.eyebrow}>Ready</Text>
        <Text style={[styles.heading, { marginTop: 4 }]}>{result.group.name} is set up</Text>
        <Text style={[styles.smallMuted, { marginTop: 8 }]}>
          Nobody has been added. Send them this link and they join the way they did last time — this
          is the only time it is shown.
        </Text>

        <View style={{ marginTop: 20, flexDirection: 'row', gap: 8, alignItems: 'center' }}>
          <View style={{ flex: 1 }}>
            <Input aria-label="Invitation link for the new exchange" value={result.invite_url} disabled />
          </View>
          <Button
            intent="secondary"
            onPress={() => {
              void Clipboard.setStringAsync(result.invite_url);
              setCopied(true);
            }}
          >
            {copied ? 'Copied' : 'Copy'}
          </Button>
        </View>

        {result.prior_participants.length > 0 ? (
          <View style={{ marginTop: 20 }}>
            <Text style={[styles.small, styles.semibold]}>Who was in the last one</Text>
            <Text style={[styles.tiny, { marginTop: 4 }]}>
              {result.prior_participants.join(', ')}
            </Text>
          </View>
        ) : null}

        <View style={{ marginTop: 20, alignSelf: 'flex-start' }}>
          <Button onPress={() => router.push(`/groups/${result.group.group_id}` as '/')}>
            Open the new exchange
          </Button>
        </View>
      </Card>
    );
  }

  return (
    <Card>
      <Text style={styles.eyebrow}>Next time</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Run this exchange again</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Starts a new exchange from this one. This one is left exactly as it is, and nothing anybody
        wrote — wishlists, addresses, messages — comes with it.
      </Text>

      {open ? (
        <View style={{ marginTop: 24, gap: gap.md }}>
          <FieldLabel label="Name the new exchange">
            <Input maxLength={120} value={name} onValueChange={setName} />
          </FieldLabel>
          <FieldLabel label="Exchange date (optional)">
            <Input value={eventDate} onValueChange={setEventDate} placeholder="2027-12-19" />
          </FieldLabel>

          <Choice
            label="Copy the description, instructions and spending limit"
            checked={copyDetails}
            onChange={setCopyDetails}
          />
          <Choice
            label="Copy the pair exclusions"
            hint="Only for people who were in the last one and still have an account."
            checked={copyExclusions}
            onChange={setCopyExclusions}
          />

          <StatusMessage message={error} />
          <View style={{ flexDirection: 'row', gap: 8, alignSelf: 'flex-start' }}>
            <Button disabled={busy || name.trim().length === 0} onPress={() => void repeat()}>
              {busy ? 'Creating…' : 'Create it'}
            </Button>
            <Button intent="secondary" disabled={busy} onPress={() => setOpen(false)}>
              Cancel
            </Button>
          </View>
        </View>
      ) : (
        <View style={{ marginTop: 20, alignSelf: 'flex-start' }}>
          <Button intent="secondary" onPress={() => setOpen(true)}>Set up next year</Button>
        </View>
      )}
    </Card>
  );
}

function Choice({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange(next: boolean): void;
}) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
      <Checkbox.Root
        checked={checked}
        aria-label={label}
        onCheckedChange={(next) => onChange(next === true)}
      >
        <Checkbox.Indicator />
      </Checkbox.Root>
      <View style={{ flex: 1 }}>
        <Text style={styles.small}>{label}</Text>
        {hint ? <Text style={[styles.tiny, { marginTop: 2 }]}>{hint}</Text> : null}
      </View>
    </View>
  );
}
