// Exchange customization (#574) — the organizer's greeting and instructions on what everyone else
// sees.
//
// Words only. Until September 2026 this panel also took two theme colours and a banner image
// (#677): a colour picker and an upload handed to somebody organizing a Secret Santa produced
// exchanges in a brown and an orange that were nobody's brand, and made the organizer's colour the
// one styled thing in every email. Humbugg's frame is Humbugg's; the organizer's words sit inside
// it.
//
// The one thing worth being careful about: this is the only place in Humbugg where an organizer
// writes text that OTHER people read, and the invitation preview renders it to somebody who is not
// signed in. That is why the server refuses HTML and links outright rather than escaping them, and
// why nothing here tries to render markup either — what is typed is what is shown, as text.
import { Button, Input, Textarea } from '@ansavva/design-system';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { api } from '../api/client';
import { useAuth } from '../context/auth-context';
import { gap, useTheme } from '../theme/styles';
import type { ExchangeCustomization, GroupDetail } from '../types';
import { FieldLabel } from './field';
import { isPlusRequired, PlusLockedNote } from './plus';
import { Card } from './shell';
import { StatusMessage } from './status-message';

/** The server's own fallbacks, so an untouched exchange shows what it will actually use. */
const DEFAULTS: ExchangeCustomization = { greeting: '', instructions: '' };

export function CustomizationPanel({
  group,
  onSaved,
  embedded = false,
}: {
  group: GroupDetail;
  onSaved(next: GroupDetail): void;
  /**
   * Rendered inside another card — the Exchange settings — as a titled group of fields rather
   * than a card of its own. The greeting and instructions describe the exchange; they are not a
   * separate thing an organizer goes looking for.
   */
  embedded?: boolean;
}) {
  const { styles } = useTheme();
  const auth = useAuth();
  const [draft, setDraft] = useState<ExchangeCustomization>({
    ...DEFAULTS,
    ...(group.customization ?? {}),
  });
  const [needsPlus, setNeedsPlus] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const set = <K extends keyof ExchangeCustomization>(key: K, value: ExchangeCustomization[K]) => {
    setDraft({ ...draft, [key]: value });
    setSaved(false);
    setError(null);
  };

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const next = await api.updateCustomization(await auth.accessToken(), group.group_id, {
        greeting: draft.greeting,
        instructions: draft.instructions,
      });
      setDraft({ ...DEFAULTS, ...(next.customization ?? {}) });
      setSaved(true);
      onSaved(next);
    } catch (err) {
      if (isPlusRequired(err)) setNeedsPlus(true);
      // "greeting cannot contain HTML or links" is the server's rule and its words, and it names
      // the field it means.
      else setError(err instanceof Error ? err.message : 'That could not be saved.');
    } finally {
      setBusy(false);
    }
  }

  // Customization is a PUT with no GET of its own, so unlike invitations and reminders there is no
  // read to be refused — without this the Free organizer gets a full form that only fails on save.
  // `group.plan` is the server's word carried on the group, not a re-derivation of it, and the 402
  // handler above stays as the authority.
  if (needsPlus || group.plan === 'free')
    return (
      <PlusLockedNote
        reason="Your own greeting and instructions are part of Plus."
        action="put your own words on what everybody else sees"
        isOwner={group.is_owner}
      />
    );

  const Frame = embedded ? View : Card;
  return (
    <Frame style={embedded ? { marginTop: 8 } : undefined}>
      {embedded ? (
        <Text style={[styles.small, styles.semibold]}>Greeting and instructions</Text>
      ) : (
        <>
          <Text style={styles.eyebrow}>Customization</Text>
          <Text style={[styles.heading, { marginTop: 4 }]}>Your words on the exchange</Text>
        </>
      )}
      <Text style={[styles.tiny, { marginTop: 4 }]}>
        What people read on the invitation before they join, and at the top of the exchange after.
      </Text>

      <View style={{ marginTop: 16, gap: gap.md }}>
        <FieldLabel label="Greeting" help="One line, at the top. 160 characters at most.">
          <Input
            maxLength={160}
            value={draft.greeting}
            onValueChange={(value) => set('greeting', value)}
            placeholder="Welcome to the Holly Jolly Crew"
          />
        </FieldLabel>

        <FieldLabel
          label="Instructions"
          help="Anything the exchange needs that Humbugg does not ask for — where to bring it, when, what counts."
        >
          <Textarea
            maxLength={1500}
            value={draft.instructions}
            onValueChange={(value) => set('instructions', value)}
            placeholder="Bring it wrapped to the Friday lunch."
          />
        </FieldLabel>

        <StatusMessage message={error} />
        <StatusMessage message={saved ? 'Saved.' : null} tone="success" />

        <View style={{ alignSelf: 'flex-start' }}>
          <Button disabled={busy} onPress={() => void save()}>
            {busy ? 'Saving…' : 'Save your words'}
          </Button>
        </View>
      </View>
    </Frame>
  );
}
