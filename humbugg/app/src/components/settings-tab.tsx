// The Settings tab of the exchange page: one section at a time, chosen from a menu.
//
// The section is the URL's last segment — `/groups/{id}/settings/billing` — so a reload keeps it
// and Stripe's return lands on Billing by address rather than by a flag (#690).
//
// On a desktop the menu is a column on the left and the section fills the rest — the settings
// shape everyone knows. Under 768px a left column would leave the section forty characters wide,
// so the same menu wraps into rows above the section. One menu, two arrangements, the same
// `Toggle`s either way.
//
// Sections are the panels that used to be six full cards in one scroll: reminders, the
// organizer's words, templates, whether gifts are posted, billing, and the danger zone. Billing
// and the danger zone are the owner's alone — the backend refuses a co-organizer both, so showing
// them the sections would show them refusals.
import { AlertDialog, Button, Switch, Toggle, ToggleGroup } from '@ansavva/design-system';
import { useRouter } from 'expo-router';
import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { Text, View, useWindowDimensions } from 'react-native';

import { api } from '../api/client';
import { useAuth } from '../context/auth-context';
import { gap, useTheme } from '../theme/styles';
import type { GroupDetail, GroupReadiness } from '../types';
import { CustomizationPanel } from './customization';
import { ExchangeSettingsPanel } from './exchange-settings';
import { PlusBillingPanel } from './plus';
import { RemindersPanel } from './reminders';
import { Card } from './shell';
import { StatusMessage } from './status-message';
import { TemplatesPanel } from './templates';

export type SettingsSection = 'exchange' | 'reminders' | 'templates' | 'billing' | 'danger';

export const SETTINGS_SECTIONS: { value: SettingsSection; label: string; ownerOnly?: boolean }[] = [
  // General first, then what people read, then what runs on its own, then reuse; money and the
  // irreversible thing last, where every settings page keeps them.
  { value: 'exchange', label: 'Exchange' },
  { value: 'reminders', label: 'Reminders' },
  { value: 'templates', label: 'Templates' },
  { value: 'billing', label: 'Billing', ownerOnly: true },
  { value: 'danger', label: 'Danger zone', ownerOnly: true },
];

export function SettingsTab({
  group,
  readiness,
  checkout,
  busy,
  onGroupChanged,
  onReload,
  onRequiresAddress,
  /** Which section is open. The URL's, when there is one; the first otherwise. */
  section: requested,
  /** The person picked another section: the caller moves the URL, and `section` follows. */
  onSectionChange,
}: {
  group: GroupDetail;
  readiness: GroupReadiness;
  checkout?: string | null;
  busy: boolean;
  onGroupChanged(next: GroupDetail): void;
  onReload(): void;
  onRequiresAddress(checked: boolean): void;
  section?: SettingsSection;
  onSectionChange?(next: SettingsSection): void;
}) {
  const { styles } = useTheme();
  const { width } = useWindowDimensions();
  const sideBySide = width >= 768;
  const sections = SETTINGS_SECTIONS.filter((item) => !item.ownerOnly || group.is_owner);
  // Uncontrolled when nobody routes the section — the unit tests render it on its own.
  const [own, setOwn] = useState<SettingsSection>(requested ?? 'exchange');
  const section = requested ?? own;
  const setSection = (next: SettingsSection) => { setOwn(next); onSectionChange?.(next); };

  const menu = (
    <ToggleGroup.Root
      value={[section]}
      onValueChange={(value) => { if (value[0]) setSection(value[0] as SettingsSection); }}
      size="sm"
      style={sideBySide ? local.menuColumn : local.menuRow}
    >
      {sections.map((item) => (
        <Toggle key={item.value} value={item.value}>{item.label}</Toggle>
      ))}
    </ToggleGroup.Root>
  );

  const content = (
    <View style={{ flex: 1, minWidth: 0, gap: 28 }}>
      {section === 'reminders' ? <RemindersPanel group={group} /> : null}
      {section === 'templates' ? (
        <TemplatesPanel group={group} onApplied={(next) => { onGroupChanged(next); onReload(); }} />
      ) : null}
      {section === 'exchange' ? (
        <Card>
          <Text style={styles.eyebrow}>Exchange</Text>
          {/* What the exchange IS — name, dates, spending limit, how it works — then how it runs as
              one row per setting (label, one line of consequence, control on the right, so the
              next setting is another <SettingRow>), then the organizer's greeting. Before the draw
              only for the details: nothing in them changes the matching, but a roster that can
              still move is the mental model. */}
          {group.status === 'open' ? (
            <View style={{ marginTop: 20 }}>
              <ExchangeSettingsPanel group={group} onSaved={onGroupChanged} embedded />
            </View>
          ) : null}
          <View style={{ marginTop: 24 }}>
            <SettingRow
              label="Gifts are posted"
              help="Asks every participant for a mailing address. Leave it off when gifts change hands in person."
            >
              <Switch.Root
                checked={readiness.requires_address}
                disabled={busy}
                aria-label="Gifts are posted to a mailing address"
                onCheckedChange={(checked) => onRequiresAddress(checked)}
              >
                <Switch.Thumb />
              </Switch.Root>
            </SettingRow>
          </View>
          <View style={{ marginTop: 20 }}>
            <CustomizationPanel group={group} onSaved={onGroupChanged} embedded />
          </View>
        </Card>
      ) : null}
      {/*
        The organizer's billing area (#141). Owner-only: `GET .../billing/plus` refuses a
        co-organizer, so a co-organizer would get a panel that could only show its own error.
      */}
      {section === 'billing' && group.is_owner ? (
        <PlusBillingPanel group={group} checkout={checkout} onEntitled={onReload} />
      ) : null}
      {section === 'danger' && group.is_owner ? <DangerZone group={group} /> : null}
    </View>
  );

  if (sideBySide)
    return (
      <View style={{ flexDirection: 'row', gap: 28, alignItems: 'flex-start' }}>
        <View style={{ width: 208 }}>{menu}</View>
        {content}
      </View>
    );
  // Wrapped, not scrolled: five short labels fit on two lines of a phone, and a strip that
  // scrolls sideways hides the last item — the danger zone — off the edge.
  return (
    <View style={{ gap: 20 }}>
      {menu}
      {content}
    </View>
  );
}

/** A setting: what it is called, what it does in one line, and its control. */
function SettingRow({ label, help, children }: { label: string; help: string; children: React.ReactNode }) {
  const { styles } = useTheme();
  return (
    <View style={local.settingRow}>
      <View style={{ flex: 1, minWidth: 220 }}>
        <Text style={[styles.small, styles.semibold]}>{label}</Text>
        <Text style={[styles.tiny, { marginTop: 2 }]}>{help}</Text>
      </View>
      {children}
    </View>
  );
}

/**
 * Deleting the exchange, from the settings where somebody goes looking for it.
 *
 * The group page has had this button since the start, under the organizer tools; a setting that
 * ends everything belongs with the other settings as well, in the section whose name says what it
 * is. Same protection as there: the button arms, then a confirmation must follow within five
 * seconds or it disarms itself — a delete cannot sit primed behind a scrolled-away button. Here the
 * confirmation is a dialog, because on this tab there is nothing else that could be mistaken for it.
 */
function DangerZone({ group }: { group: GroupDetail }) {
  const { blends, styles } = useTheme();
  const auth = useAuth();
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const armedAt = useRef(0);

  useEffect(() => {
    if (!confirming) return;
    const timeout = setTimeout(() => { armedAt.current = 0; setConfirming(false); }, 8000);
    return () => clearTimeout(timeout);
  }, [confirming]);

  async function remove() {
    // Guards against a double-tap arming and committing in one gesture.
    if (Date.now() - armedAt.current < 500) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteGroup(await auth.accessToken(), group.group_id);
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The exchange could not be deleted.');
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }

  const people = group.members.length;
  return (
    <Card>
      <Text style={styles.eyebrow}>Danger zone</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Delete this exchange</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        Everything goes: the roster, every wishlist, the draw and its assignments, the invitations
        and reminders. {people === 1 ? 'You are the only member.' : `${people} people are in it.`} A
        Plus purchase is not refunded by deleting — see the Refund Policy.
      </Text>
      <StatusMessage message={error} />
      <AlertDialog.Root
        open={confirming}
        onOpenChange={(next) => {
          if (busy) return;
          if (next) armedAt.current = Date.now();
          setConfirming(next);
        }}
      >
        <View style={{ marginTop: 20, alignSelf: 'flex-start' }}>
          <Button
            intent="danger"
            disabled={busy}
            onPress={() => { armedAt.current = Date.now(); setConfirming(true); }}
          >
            {busy ? 'Deleting…' : 'Delete this exchange…'}
          </Button>
        </View>
        <AlertDialog.Popup style={{ borderWidth: 1, borderColor: blends.dangerBorder }}>
          <AlertDialog.Title>Delete {group.name} permanently?</AlertDialog.Title>
          <AlertDialog.Description>
            This cannot be undone. {people === 1 ? 'Nobody else is affected.' : `${people} people lose their place, their wishlists and their assignments.`}
          </AlertDialog.Description>
          <View style={{ marginTop: 24, flexDirection: 'row', justifyContent: 'flex-end', gap: gap.xs }}>
            <Button intent="secondary" size="sm" disabled={busy} onPress={() => setConfirming(false)}>Keep it</Button>
            <Button intent="danger" size="sm" disabled={busy} onPress={() => void remove()}>
              {busy ? 'Deleting…' : 'Permanently delete'}
            </Button>
          </View>
        </AlertDialog.Popup>
      </AlertDialog.Root>
    </Card>
  );
}

const local = {
  menuColumn: { flexDirection: 'column', alignItems: 'stretch', gap: 6 } as const,
  menuRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 } as const,
  settingRow: {
    paddingVertical: 12,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: gap.md,
  } as const,
};
