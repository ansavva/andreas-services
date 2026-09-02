// The organizer's edit form (#135) — the one criterion the API has always satisfied and the app
// never offered. `PATCH /groups/{id}` has accepted name, description, dates and spending limit since
// the beginning; until now the app called it from exactly one place, the readiness dashboard's
// address switch. Everything else was set at creation and then unchangeable.
//
// It saves against the `updated_at` it loaded with. Two organizers editing at once is not a rare
// case in a Plus exchange with co-organizers, and last-write-wins is the wrong default when the
// loser is never told: somebody rewrites the description, somebody else saves a date from a page
// loaded ten minutes ago, and the description quietly reverts.
import { Button, Input, Textarea } from '@ansavva/design-system';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { api, ApiError } from '../api/client';
import { FieldLabel } from './field';
import { Card } from './shell';
import { StatusMessage } from './status-message';
import { useAuth } from '../context/auth-context';
import { gap, styles } from '../theme/styles';
import type { GroupDetail } from '../types';

export function ExchangeSettingsPanel({
  group,
  onSaved,
}: {
  group: GroupDetail;
  onSaved(group: GroupDetail): void;
}) {
  const auth = useAuth();
  const [name, setName] = useState(group.name);
  const [description, setDescription] = useState(group.description ?? '');
  const [instructions, setInstructions] = useState(group.instructions ?? '');
  const [eventDate, setEventDate] = useState(group.event_date ?? '');
  const [signupDeadline, setSignupDeadline] = useState(group.signup_deadline ?? '');
  const [spendingLimit, setSpendingLimit] = useState(
    group.spending_limit != null ? String(group.spending_limit) : '',
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // Set when the server refuses a stale save. It is not an ordinary error: the fix is to reload,
  // and the message says so rather than inviting a retry that would fail the same way.
  const [conflict, setConflict] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    setConflict(false);
    try {
      const limit = spendingLimit.trim();
      const updated = await api.updateGroup(await auth.accessToken(), group.group_id, {
        name: name.trim(),
        description: description.trim(),
        instructions: instructions.trim(),
        event_date: eventDate.trim(),
        signup_deadline: signupDeadline.trim(),
        ...(limit === '' ? {} : { spending_limit: Number(limit) }),
        // The row as this form loaded it. The server refuses the save if anybody has written since.
        expected_updated_at: group.updated_at,
      });
      onSaved(updated);
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setConflict(true);
      else setError(err instanceof Error ? err.message : 'The exchange could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <Text style={styles.eyebrow}>Organizer</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Exchange details</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Everyone who has joined sees these. Change them whenever you like — none of it affects the
        draw.
      </Text>

      {/*
        No `aria-label` on any control below. `FieldLabel` wraps the design system's `Field.Root`,
        which supplies the accessible name from the label text via `aria-labelledby` — an
        `aria-label` on the control inside is silently ignored, so "(optional)" belongs in the label
        rather than sitting in a second, ineffective one.
      */}
      <View style={{ marginTop: 24, gap: gap.md }}>
        <FieldLabel label="Exchange name">
          <Input maxLength={120} value={name} onValueChange={setName} />
        </FieldLabel>
        <FieldLabel label="Description (optional)">
          <Textarea
            maxLength={1000}
            value={description}
            onValueChange={setDescription}
            placeholder="The office exchange, back for another year."
          />
        </FieldLabel>
        <FieldLabel label="How it works (optional)">
          <Textarea
            maxLength={2000}
            value={instructions}
            onValueChange={setInstructions}
            placeholder="Bring it wrapped to the Friday lunch. No name on the label."
          />
        </FieldLabel>
        <FieldLabel label="Exchange date (optional)">
          <Input
            value={eventDate}
            onValueChange={setEventDate}
            placeholder="2026-12-19"
          />
        </FieldLabel>
        <FieldLabel label="Joining closes (optional)">
          <Input
            value={signupDeadline}
            onValueChange={setSignupDeadline}
            placeholder="2026-12-05"
          />
        </FieldLabel>
        <FieldLabel label="Spending limit in dollars (optional)">
          <Input
            inputMode="decimal"
            value={spendingLimit}
            onValueChange={setSpendingLimit}
            placeholder="25"
          />
        </FieldLabel>

        <StatusMessage message={error} />
        {conflict ? (
          <StatusMessage message="Somebody else changed this exchange while you were editing. Reload the page to see their version, then make your change again." />
        ) : null}
        {saved ? <StatusMessage message="Saved." tone="success" /> : null}

        <View style={{ alignSelf: 'flex-start' }}>
          <Button disabled={busy || name.trim().length === 0} onPress={() => void save()}>
            {busy ? 'Saving…' : 'Save changes'}
          </Button>
        </View>
      </View>
    </Card>
  );
}

/**
 * What the organizer wrote about how the exchange works, shown to everybody who has joined.
 *
 * Renders nothing when it is empty rather than an empty panel — a heading over nothing is worse
 * than no heading, and most exchanges will never need this.
 */
export function ExchangeInstructions({ instructions }: { instructions?: string }) {
  if (!instructions?.trim()) return null;
  return (
    <Card>
      <Text style={styles.eyebrow}>From your organizer</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>How this one works</Text>
      <Text style={[styles.body, { marginTop: 16 }]}>{instructions}</Text>
    </Card>
  );
}
