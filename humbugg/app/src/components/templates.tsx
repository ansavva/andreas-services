// Reusable exchange templates (#574) — save a setup once, start next year's from it.
//
// **Applying a template REWRITES the exchange it is applied to.** Name, description, both dates,
// greeting, instructions, colours, banner, reminder settings and (when the template says so)
// exclusions are all overwritten, and the selected prior participants are sent invitations. That is
// the backend's behaviour, not a choice made here — `ApplyAsync` calls `UpdateAsync`,
// `UpdateCustomizationAsync`, `SetExclusionsAsync`, `reminders.UpdateAsync` and `CreateAsync` in
// sequence. So the panel's job is to make sure nobody discovers that afterwards: it says what will
// be overwritten, it asks for the date rather than guessing one, and it invites NOBODY unless they
// are ticked.
//
// The prior participants carry email addresses, which is the organizer's own record of an exchange
// they ran. They are shown because re-inviting by name alone is impossible — the invitation goes to
// an address — and hiding the address while sending to it would be worse, not better.
import { Button, Checkbox, Input, Select } from '@ansavva/design-system';
import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { api } from '../api/client';
import { useAuth } from '../context/auth-context';
import { blends, gap, styles } from '../theme/styles';
import type { ExchangeTemplate, GroupDetail } from '../types';
import { FieldLabel } from './field';
import { isPlusRequired, PanelLoadFailure, PlusLockedNote } from './plus';
import { Card } from './shell';
import { StatusMessage } from './status-message';

export function TemplatesPanel({
  group,
  onApplied,
}: {
  group: GroupDetail;
  onApplied(next: GroupDetail): void;
}) {
  const auth = useAuth();
  const [templates, setTemplates] = useState<ExchangeTemplate[] | null>(null);
  const [needsPlus, setNeedsPlus] = useState(false);
  const [name, setName] = useState('');
  const [chosen, setChosen] = useState<string>('');
  const [eventDate, setEventDate] = useState('');
  const [invite, setInvite] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setTemplates(await api.listTemplates(await auth.accessToken()));
      setNeedsPlus(false);
    } catch (err) {
      if (isPlusRequired(err)) setNeedsPlus(true);
      else setError(err instanceof Error ? err.message : 'Unable to read your templates.');
    }
  }, [auth]);

  useEffect(() => { void load(); }, [load]);

  const template = templates?.find((item) => item.template_id === chosen) ?? null;

  async function save() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const created = await api.saveTemplate(await auth.accessToken(), name.trim(), group.group_id);
      setName('');
      setNote(`Saved as "${created.name}".`);
      await load();
    } catch (err) {
      if (isPlusRequired(err)) setNeedsPlus(true);
      else setError(err instanceof Error ? err.message : 'That could not be saved as a template.');
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!template) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const next = await api.applyTemplate(
        await auth.accessToken(),
        template.template_id,
        group.group_id,
        eventDate.trim(),
        invite,
      );
      onApplied(next);
      setNote(
        invite.length === 0
          ? 'Applied. Nobody was invited.'
          : `Applied, and ${invite.length} ${invite.length === 1 ? 'invitation was' : 'invitations were'} sent.`,
      );
    } catch (err) {
      if (isPlusRequired(err)) setNeedsPlus(true);
      else setError(err instanceof Error ? err.message : 'That template could not be applied.');
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError(null);
    try {
      await api.deleteTemplate(await auth.accessToken(), id);
      if (chosen === id) { setChosen(''); setInvite([]); }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That template could not be deleted.');
    } finally {
      setBusy(false);
    }
  }

  if (needsPlus)
    return (
      <PlusLockedNote
        reason="Saving a setup as a template is part of Plus."
        action="save this whole setup and start next year's from it"
        isOwner={group.is_owner}
      />
    );

  if (templates === null)
    return error ? <PanelLoadFailure title="Templates" message={error} /> : null;

  return (
    <Card>
      <Text style={styles.eyebrow}>Templates</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Save this setup, or start from one</Text>

      <View style={{ marginTop: 24, gap: gap.md }}>
        <FieldLabel
          label="Save this exchange as a template"
          help="Its name, description, deadline, colours, instructions, reminder settings — and who took part, so you can invite them again."
        >
          <Input
            maxLength={100}
            value={name}
            onValueChange={(value) => { setName(value); setError(null); setNote(null); }}
            placeholder="Office Secret Santa, the usual"
          />
        </FieldLabel>
        <View style={{ alignSelf: 'flex-start' }}>
          <Button intent="secondary" disabled={busy || name.trim().length === 0} onPress={() => void save()}>
            {busy ? 'Working…' : 'Save as a template'}
          </Button>
        </View>
      </View>

      {templates.length > 0 ? (
        <View style={{ marginTop: 28, gap: gap.md }}>
          <FieldLabel label="Start this exchange from a template">
            <Select
              options={[
                { value: '', label: 'Choose a template…' },
                ...templates.map((item) => ({ value: item.template_id, label: item.name })),
              ]}
              value={chosen}
              onValueChange={(value) => { setChosen(value); setInvite([]); setNote(null); setError(null); }}
            />
          </FieldLabel>

          {template ? (
            <View style={{ gap: gap.md }}>
              {/* Said before the button, not in the error afterwards. */}
              <View style={[styles.emptyPanel, { paddingVertical: 16, paddingHorizontal: 16, alignItems: 'flex-start' }]}>
                <Text style={[styles.small, styles.semibold]}>This replaces what is here now</Text>
                <Text style={[styles.tiny, { marginTop: 4 }]}>
                  “{group.name}” becomes “{template.exchange_name}”, and its description, dates,
                  greeting, instructions, colours and reminder settings are replaced by the
                  template’s
                  {template.exclusions_policy === 'none' ? ', and its exclusions are cleared' : ''}.
                  Nothing anybody wrote — wishlists, addresses, messages — is touched.
                </Text>
              </View>

              <FieldLabel label="The new event date" help="The join-by date follows the template’s.">
                <Input
                  value={eventDate}
                  onValueChange={(value) => { setEventDate(value); setError(null); }}
                  placeholder="2027-12-19"
                />
              </FieldLabel>

              {template.prior_participants.length > 0 ? (
                <View>
                  <Text style={styles.fieldLabelText}>Invite anybody from last time?</Text>
                  <Text style={[styles.tiny, { marginTop: 4 }]}>
                    Nobody is invited unless you tick them. Each one is sent an invitation as soon as
                    the template is applied.
                  </Text>
                  <View style={{ marginTop: 12, gap: 10 }}>
                    {template.prior_participants.map((person) => (
                      <View
                        key={person.member_id}
                        style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}
                      >
                        <Checkbox.Root
                          checked={invite.includes(person.member_id)}
                          aria-label={`Invite ${person.display_name}`}
                          onCheckedChange={(checked) =>
                            setInvite((current) =>
                              checked === true
                                ? [...current, person.member_id]
                                : current.filter((id) => id !== person.member_id),
                            )
                          }
                        >
                          <Checkbox.Indicator />
                        </Checkbox.Root>
                        <View style={{ flex: 1, minWidth: 0 }}>
                          <Text style={styles.small}>{person.display_name}</Text>
                          <Text style={styles.tiny}>{person.email}</Text>
                        </View>
                      </View>
                    ))}
                  </View>
                </View>
              ) : null}

              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <Button disabled={busy || eventDate.trim().length === 0} onPress={() => void apply()}>
                  {busy ? 'Applying…' : 'Apply this template'}
                </Button>
                <Button intent="secondary" disabled={busy} onPress={() => void remove(template.template_id)}>
                  Delete this template
                </Button>
              </View>
            </View>
          ) : null}
        </View>
      ) : null}

      <View style={{ marginTop: 20 }}>
        <StatusMessage message={error} />
        <StatusMessage message={note} tone="success" />
      </View>
    </Card>
  );
}
