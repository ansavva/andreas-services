// Exchange customization (#574) — the organizer's greeting, instructions, colours and banner on
// what everyone else sees.
//
// The one thing worth being careful about: this is the only place in Humbugg where an organizer
// writes text that OTHER people read, and the invitation preview renders it to somebody who is not
// signed in. That is why the server refuses HTML and links outright rather than escaping them, and
// why nothing here tries to render markup either — what is typed is what is shown, as text.
import { Button, Input, Textarea } from '@ansavva/design-system';
import { useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { api } from '../api/client';
import { useAuth } from '../context/auth-context';
import { blends, gap, styles } from '../theme/styles';
import { brand } from '../theme/theme';
import type { ExchangeCustomization, GroupDetail } from '../types';
import { pickBanner } from '../utils/image-picker';
import { FieldLabel } from './field';
import { isPlusRequired, PlusLockedNote } from './plus';
import { Card } from './shell';
import { StatusMessage } from './status-message';

/** The server's own fallbacks, so an untouched exchange shows what it will actually use. */
const DEFAULTS: ExchangeCustomization = {
  greeting: '',
  instructions: '',
  primary_color: '#7C2D12',
  accent_color: '#F59E0B',
  image_data_url: null,
};

export function CustomizationPanel({
  group,
  onSaved,
}: {
  group: GroupDetail;
  onSaved(next: GroupDetail): void;
}) {
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

  async function choose() {
    const picked = await pickBanner();
    if (picked.kind === 'cancelled') return;
    if (picked.kind === 'error') { setError(picked.message); return; }
    set('image_data_url', picked.dataUrl);
  }

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const next = await api.updateCustomization(await auth.accessToken(), group.group_id, {
        greeting: draft.greeting,
        instructions: draft.instructions,
        primary_color: draft.primary_color,
        accent_color: draft.accent_color,
        // The field is `image` on the wire and `image_data_url` in the response. Sending the
        // response's name silently saves nothing, which looks exactly like a picker that failed.
        image: draft.image_data_url ?? '',
      });
      setDraft({ ...DEFAULTS, ...(next.customization ?? {}) });
      setSaved(true);
      onSaved(next);
    } catch (err) {
      if (isPlusRequired(err)) setNeedsPlus(true);
      // "greeting cannot contain HTML or links" and "Theme colors must use #RRGGBB" are the
      // server's rules and its words, and both name the field they mean.
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
        reason="Your own greeting, instructions and colours are part of Plus."
        action="put your own words and colours on what everybody else sees"
        isOwner={group.is_owner}
      />
    );

  return (
    <Card>
      <Text style={styles.eyebrow}>Customization</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>How this exchange looks</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        What people see on the invitation before they join, and at the top of the exchange after.
      </Text>

      <View style={{ marginTop: 24, gap: gap.md }}>
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

        <View style={{ flexDirection: 'row', gap: gap.md, flexWrap: 'wrap' }}>
          <Colour label="Main colour" value={draft.primary_color} onChange={(v) => set('primary_color', v)} />
          <Colour label="Highlight colour" value={draft.accent_color} onChange={(v) => set('accent_color', v)} />
        </View>

        <View>
          <Text style={styles.fieldLabelText}>Banner image</Text>
          {draft.image_data_url ? (
            <Image
              source={{ uri: draft.image_data_url }}
              style={local.banner}
              // The banner is decoration around words that are already on the screen, so describing
              // it would be describing the greeting twice.
              accessibilityElementsHidden
              importantForAccessibility="no-hide-descendants"
            />
          ) : (
            <View style={[styles.emptyPanel, { marginTop: 8, paddingVertical: 24 }]}>
              <Text style={styles.bodyMuted}>No banner. The exchange shows its name instead.</Text>
            </View>
          )}
          <View style={{ marginTop: 12, flexDirection: 'row', gap: 8 }}>
            <Button intent="secondary" size="sm" disabled={busy} onPress={() => void choose()}>
              {draft.image_data_url ? 'Choose a different image' : 'Choose an image'}
            </Button>
            {draft.image_data_url ? (
              <Button
                intent="secondary"
                size="sm"
                disabled={busy}
                onPress={() => set('image_data_url', null)}
              >
                Remove it
              </Button>
            ) : null}
          </View>
        </View>

        <StatusMessage message={error} />
        <StatusMessage message={saved ? 'Saved.' : null} tone="success" />

        <View style={{ alignSelf: 'flex-start' }}>
          <Button disabled={busy} onPress={() => void save()}>
            {busy ? 'Saving…' : 'Save how it looks'}
          </Button>
        </View>
      </View>
    </Card>
  );
}

/**
 * A colour, as its hex and a swatch of itself.
 *
 * There is no colour picker: the design system ships none, and a hand-rolled wheel that has to work
 * with a keyboard, a screen reader and a thumb is a component, not a field. The swatch is what makes
 * the hex legible, and an invalid one is the server's answer rather than a silently ignored value.
 */
function Colour({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange(next: string): void;
}) {
  return (
    <View style={{ flex: 1, minWidth: 160 }}>
      <FieldLabel label={label} help="#RRGGBB">
        <Input maxLength={7} value={value} onValueChange={(next) => onChange(next.toUpperCase())} />
      </FieldLabel>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 }}>
        <View
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          style={[local.swatch, { backgroundColor: /^#[0-9A-F]{6}$/.test(value) ? value : brand.line }]}
        />
        <Text style={styles.tiny}>{/^#[0-9A-F]{6}$/.test(value) ? value : 'Not a colour yet'}</Text>
      </View>
    </View>
  );
}

const local = StyleSheet.create({
  banner: {
    marginTop: 8,
    width: '100%',
    aspectRatio: 2,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: blends.primaryBorder,
  },
  swatch: { width: 24, height: 24, borderRadius: 6, borderWidth: 1, borderColor: brand.line },
});
