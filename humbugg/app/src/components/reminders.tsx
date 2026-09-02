// Scheduled reminders (#574) — Humbugg chases the people who have not answered, so the organizer
// does not have to.
//
// This is the capability with the most ways to be quietly wrong, because it sends mail to other
// people on a schedule nobody is watching. So the panel's job is less "collect six settings" than
// "say, in one sentence, what is about to happen and to whom" — `summary()` below is the part that
// matters most.
//
// The hours are UTC and the panel says so rather than pretending otherwise. The backend stores UTC
// hours with no timezone alongside them, so rendering them as local time would be a guess that
// reads as a fact — and the guess is wrong for everybody who moves or has participants elsewhere.
import { Badge, Button, Checkbox, Input, Select } from '@ansavva/design-system';
import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { api } from '../api/client';
import { useAuth } from '../context/auth-context';
import { gap, styles } from '../theme/styles';
import type { GroupDetail, ReminderOverview, ReminderSettings, ReminderState } from '../types';
import { FieldLabel } from './field';
import { isPlusRequired, PanelLoadFailure, PlusLockedNote } from './plus';
import { Card } from './shell';
import { StatusMessage } from './status-message';

const STATES: Array<{ value: ReminderState; label: string }> = [
  { value: 'active', label: 'On — send them automatically' },
  { value: 'paused', label: 'Paused — keep the settings, send nothing' },
  { value: 'stopped', label: 'Off' },
];

/** What the settings mean, as a sentence, before anybody commits to them. */
export function summary(settings: ReminderSettings): string {
  if (settings.state === 'stopped') return 'Nothing is sent.';
  const who = [
    settings.remind_unaccepted_invitations ? 'people who have not accepted their invitation' : null,
    settings.remind_incomplete_readiness ? 'people whose list or address is not finished' : null,
  ].filter(Boolean);
  if (who.length === 0) return 'Nothing is sent — no reminder is switched on.';
  const every =
    settings.interval_days === 1 ? 'every day' : `every ${settings.interval_days} days`;
  const window = `${hour(settings.quiet_start_utc_hour)}–${hour(settings.quiet_end_utc_hour)} UTC`;
  const when = settings.state === 'paused' ? 'Paused. When switched on it reminds' : 'Reminds';
  return `${when} ${who.join(' and ')}, ${every}, between ${window}.`;
}

const hour = (value: number) => `${String(value).padStart(2, '0')}:00`;

export function RemindersPanel({ group }: { group: GroupDetail }) {
  const auth = useAuth();
  const [overview, setOverview] = useState<ReminderOverview | null>(null);
  const [draft, setDraft] = useState<ReminderSettings | null>(null);
  const [needsPlus, setNeedsPlus] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await api.getReminders(await auth.accessToken(), group.group_id);
      setOverview(next);
      setDraft(next.settings);
      setNeedsPlus(false);
    } catch (err) {
      if (isPlusRequired(err)) setNeedsPlus(true);
      else setError(err instanceof Error ? err.message : 'Unable to read the reminder settings.');
    }
  }, [auth, group.group_id]);

  useEffect(() => { void load(); }, [load]);

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      const next = await api.updateReminders(await auth.accessToken(), group.group_id, draft);
      setOverview(next);
      setDraft(next.settings);
      setSaved(summary(next.settings));
    } catch (err) {
      if (isPlusRequired(err)) setNeedsPlus(true);
      // Ranges, and "switch one on before you start", are the server's rules and its wording. A
      // second copy of "between 1 and 14 days" here is a second thing to keep in step.
      else setError(err instanceof Error ? err.message : 'Those settings could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  if (needsPlus)
    return (
      <PlusLockedNote
        reason="Automatic reminders are part of Plus."
        action="have Humbugg chase the people who have not answered, instead of you"
        isOwner={group.is_owner}
      />
    );

  // A failed first read is its own state, not the same as one still in flight — see
  // `PanelLoadFailure`.
  if (!draft || !overview)
    return error ? <PanelLoadFailure title="Reminders" message={error} /> : null;

  const set = <K extends keyof ReminderSettings>(key: K, value: ReminderSettings[K]) => {
    setDraft({ ...draft, [key]: value });
    setSaved(null);
    setError(null);
  };

  return (
    <Card>
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12 }}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.eyebrow}>Reminders</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>Chasing, without you doing it</Text>
        </View>
        <Badge intent={overview.settings.state === 'active' ? 'success' : 'neutral'} size="sm">
          {overview.settings.state === 'active'
            ? 'On'
            : overview.settings.state === 'paused'
              ? 'Paused'
              : 'Off'}
        </Badge>
      </View>

      {/* The saved state, not the draft — so this line never describes something nobody agreed to. */}
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>{summary(overview.settings)}</Text>
      {overview.next_scheduled_at && overview.settings.state === 'active' ? (
        <Text style={[styles.tiny, { marginTop: 4 }]}>Next one {when(overview.next_scheduled_at)}.</Text>
      ) : null}

      <View style={{ marginTop: 24, gap: gap.md }}>
        <FieldLabel label="Automatic reminders">
          <Select
            options={STATES}
            value={draft.state}
            onValueChange={(value) => set('state', value as ReminderState)}
          />
        </FieldLabel>

        <Rule
          label="People who have not accepted their invitation"
          checked={draft.remind_unaccepted_invitations}
          onChange={(next) => set('remind_unaccepted_invitations', next)}
        />
        <Rule
          label="People whose wishlist or address is not finished"
          checked={draft.remind_incomplete_readiness}
          onChange={(next) => set('remind_incomplete_readiness', next)}
        />

        <FieldLabel label="How often, in days" help="Between 1 and 14.">
          <Input
            type="number"
            value={String(draft.interval_days)}
            onValueChange={(value) => set('interval_days', Number(value) || 0)}
          />
        </FieldLabel>

        <View style={{ flexDirection: 'row', gap: gap.md, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 140 }}>
            <FieldLabel label="Not before, UTC hour">
              <Input
                type="number"
                value={String(draft.quiet_start_utc_hour)}
                onValueChange={(value) => set('quiet_start_utc_hour', Number(value) || 0)}
              />
            </FieldLabel>
          </View>
          <View style={{ flex: 1, minWidth: 140 }}>
            <FieldLabel label="Not after, UTC hour">
              <Input
                type="number"
                value={String(draft.quiet_end_utc_hour)}
                onValueChange={(value) => set('quiet_end_utc_hour', Number(value) || 0)}
              />
            </FieldLabel>
          </View>
        </View>
        {/* UTC, said once, plainly. A participant in Auckland is not read a local hour here. */}
        <Text style={styles.tiny}>
          These hours are UTC, the same for everybody, so nobody is emailed in the middle of their
          night because of where you are.
        </Text>

        {/* What the DRAFT would do, so the sentence changes as the settings do. */}
        <Text style={[styles.small, styles.semibold]}>{summary(draft)}</Text>

        <StatusMessage message={error} />
        <StatusMessage message={saved ? `Saved. ${saved}` : null} tone="success" />

        <View style={{ alignSelf: 'flex-start' }}>
          <Button disabled={busy} onPress={() => void save()}>
            {busy ? 'Saving…' : 'Save reminder settings'}
          </Button>
        </View>
      </View>

      {overview.recent_history.length > 0 ? (
        <View style={{ marginTop: 28 }}>
          <Text style={[styles.small, styles.semibold]}>Recently sent</Text>
          <View style={{ marginTop: 12, gap: 8 }}>
            {overview.recent_history.slice(0, 5).map((item) => (
              <View key={item.reminder_id} style={styles.memberRow}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={styles.small}>
                    {item.rule === 'unaccepted_invitation'
                      ? 'Invitation not accepted'
                      : 'List or address not finished'}
                  </Text>
                  <Text style={styles.tiny}>{when(item.created_at)}</Text>
                </View>
                <Badge intent={item.status === 'sent' ? 'neutral' : 'warning'} size="sm">
                  {item.status === 'sent' ? 'Sent' : 'Held back'}
                </Badge>
              </View>
            ))}
          </View>
        </View>
      ) : null}
    </Card>
  );
}

function Rule({
  label,
  checked,
  onChange,
}: {
  label: string;
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
      <Text style={[styles.small, { flex: 1 }]}>{label}</Text>
    </View>
  );
}

function when(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return 'at an unknown time';
  return at.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
