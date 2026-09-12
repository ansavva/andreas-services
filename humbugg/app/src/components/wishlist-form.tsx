// The member's own general preferences and mailing address — the free-text half of "for you".
//
// Alongside the structured wishlist (`WishListPanel`): the things that apply to any gift, and the
// address if gifts are posted. Only the assigned giver sees any of it, and only after the draw.
import { Button, Input, Textarea } from '@ansavva/design-system';
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { gap, scopedStyles, useTheme } from '../theme/styles';
import type { Membership } from '../types';
import { validateAddressForm } from '../utils/validation';
import { FieldLabel } from './field';
import { Card } from './shell';
import { StatusMessage } from './status-message';

export function WishListForm({
  membership,
  busy,
  onSave,
  onClear,
}: {
  membership: Membership;
  busy: boolean;
  onSave(data: Record<string, unknown>): void;
  onClear(): void;
}) {
  const theme = useTheme();
  const { brand, styles } = theme;
  const local = localStyles(theme);
  const saved = membership.address ?? {};
  const [wishlist, setWishlist] = useState(membership.wishlist ?? '');
  const [avoidances, setAvoidances] = useState(membership.avoidances ?? '');
  const [line1, setLine1] = useState(saved.line1 ?? '');
  const [line2, setLine2] = useState(saved.line2 ?? '');
  const [city, setCity] = useState(saved.city ?? '');
  const [region, setRegion] = useState(saved.region ?? '');
  const [postalCode, setPostalCode] = useState(saved.postal_code ?? '');
  const [country, setCountry] = useState(saved.country ?? '');
  const [showAddress, setShowAddress] = useState(Boolean(saved.line1));
  const [validationError, setValidationError] = useState<string | null>(null);
  const [confirmingClear, setConfirmingClear] = useState(false);

  function submit() {
    const addressValues = { line1, line2, city, region, postalCode, country };
    const error = validateAddressForm(addressValues);
    if (error) { setValidationError(error); return; }
    setValidationError(null);
    onSave({
      wishlist: wishlist.trim(),
      avoidances: avoidances.trim(),
      address: {
        line1: line1.trim(),
        line2: line2.trim(),
        city: city.trim(),
        region: region.trim(),
        postal_code: postalCode.trim(),
        country: country.trim(),
      },
    });
  }

  return (
    <Card>
      <Text style={styles.eyebrow}>Your details</Text>
      <Text style={[styles.heading, { marginTop: 4 }]}>Sizes, likes and things to avoid</Text>
      <Text style={[styles.smallMuted, { marginTop: 8 }]}>
        The things that apply to any gift, alongside your wishlist. Only your assigned giver can see
        these, and only after the draw.
      </Text>
      <View style={{ marginTop: 24, gap: gap.md }}>
        <FieldLabel label="Likes, sizes and hobbies">
          <Textarea
            maxLength={2000}
            value={wishlist}
            onValueChange={setWishlist}
            placeholder="Medium in tops, size 9 shoes, into cycling and cooking…"
          />
        </FieldLabel>
        <FieldLabel label="Allergies and things to avoid">
          <Textarea
            maxLength={2000}
            value={avoidances}
            onValueChange={setAvoidances}
            placeholder="Nut allergy, no scented candles, already own the boxset…"
          />
        </FieldLabel>
        {/*
          The web app used `<details>`. There is no disclosure element on this
          side, so this is a plain toggle — the package's `Collapsible` animates
          a height it cannot measure for a block of inputs that grow.
        */}
        <View style={local.disclosure}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ expanded: showAddress }}
            onPress={() => setShowAddress((open) => !open)}
          >
            <Text style={[styles.small, styles.semibold]}>
              {showAddress ? '▾' : '▸'} Optional mailing address
            </Text>
          </Pressable>
          {showAddress ? (
            <View style={{ marginTop: 16, gap: 12 }}>
              <Text style={styles.tiny}>
                If you add an address, the address line, city, postal code, and country are required.
              </Text>
              <Input aria-label="Address line 1" maxLength={150} value={line1} onValueChange={setLine1} placeholder="Address line 1" />
              <Input aria-label="Address line 2" maxLength={150} value={line2} onValueChange={setLine2} placeholder="Address line 2" />
              <Input aria-label="City" maxLength={100} value={city} onValueChange={setCity} placeholder="City" />
              <Input aria-label="State or region" maxLength={100} value={region} onValueChange={setRegion} placeholder="State / region" />
              <Input aria-label="Postal code" maxLength={32} value={postalCode} onValueChange={setPostalCode} placeholder="Postal code" />
              <Input aria-label="Country" maxLength={100} value={country} onValueChange={setCountry} placeholder="Country" />
            </View>
          ) : null}
        </View>
        <StatusMessage message={validationError} />
        <Button style={styles.buttonBlock} disabled={busy} onPress={submit}>Save my details</Button>
      </View>
      <View style={{ marginTop: 16, borderTopWidth: 1, borderTopColor: brand.line, paddingTop: 16, gap: 12 }}>
        <Text style={styles.tiny}>
          Clear your wishlist, general preferences, and mailing address for this exchange —
          including every item on your list. This does not remove you from the group.
        </Text>
        <View style={{ alignSelf: 'flex-start' }}>
          {/*
            `window.confirm` has no counterpart here, so the confirmation is the
            button itself: one press arms, the next commits.
          */}
          <Button
            intent="secondary"
            size="sm"
            disabled={busy}
            onPress={() => {
              if (!confirmingClear) { setConfirmingClear(true); return; }
              setConfirmingClear(false);
              onClear();
            }}
          >
            {confirmingClear ? 'Tap again to confirm' : 'Clear everything I saved'}
          </Button>
        </View>
      </View>
    </Card>
  );
}

/** Built once per scheme — see `scopedStyles`. */
const localStyles = scopedStyles((t) => ({
  disclosure: { borderWidth: 1, borderColor: t.brand.line, borderRadius: 12, padding: 16 },
}));
