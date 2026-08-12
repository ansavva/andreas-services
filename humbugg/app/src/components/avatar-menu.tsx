// The top-right account menu.
//
// Built on the design system's `Dropdown`, with two deliberate departures.
//
// 1. THE TRIGGER IS OURS. `Dropdown.Trigger` wraps its children in a `<Text>`,
//    which a photo and a chevron cannot live inside on React Native. `Dropdown.Root`
//    supports a controlled `open` / `onOpenChange` pair, so the state lives here
//    and our own `Pressable` toggles it — the menu, its items, its roles and its
//    ids all still come from the package.
//
// 2. THERE IS AN EXPLICIT CLOSE. A native `Dropdown` has no press-outside
//    dismissal, because React Native has no document to listen to — a documented
//    platform difference, not a bug. The web app's menu closed on an outside
//    click and on Escape, so without a replacement this menu would have no way
//    out at all on a device. A full-bleed backdrop behind the menu restores
//    press-outside, and a labelled Close row gives keyboard and screen-reader
//    users a target that does not depend on it.
import { Dropdown } from '@ansavva/design-system';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useAuth } from '../context/auth-context';
import { useProfile } from '../context/profile-context';
import { styles } from '../theme/styles';
import { brand, fonts } from '../theme/theme';
import { Avatar } from './avatar';

export function AvatarMenu() {
  const auth = useAuth();
  const { profile } = useProfile();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const displayName = profile?.display_name ?? auth.email ?? 'Your account';

  function select(run: () => void) {
    setOpen(false);
    run();
  }

  return (
    <>
      {/*
        The backdrop that gives back press-outside dismissal. Rendered as a
        sibling *behind* the menu (the menu's own `zIndex: 20` puts it on top)
        and only while open, so it never intercepts a press otherwise.
      */}
      {open ? (
        <Pressable
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          onPress={() => setOpen(false)}
          style={local.backdrop}
        />
      ) : null}
      <Dropdown.Root open={open} onOpenChange={setOpen}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: open }}
          accessibilityLabel={`Account menu for ${displayName}`}
          onPress={() => setOpen((current) => !current)}
          style={local.trigger}
        >
          <Avatar src={profile?.avatar_url} name={profile?.display_name} email={auth.email} size={32} />
          <Text numberOfLines={1} style={local.triggerLabel}>
            {displayName}
          </Text>
          <Text aria-hidden style={local.chevron}>
            ⌄
          </Text>
        </Pressable>
        <Dropdown.Content
          accessibilityLabel="Account"
          // The package anchors the menu to the trigger's left edge; Humbugg's
          // sits at the right, as it does on the web.
          style={[styles.menu, local.anchorRight]}
        >
          <Dropdown.Item onSelect={() => select(() => router.push('/settings'))}>Settings</Dropdown.Item>
          <Dropdown.Item onSelect={() => select(() => router.push('/'))}>My groups</Dropdown.Item>
          <Dropdown.Item
            onSelect={() =>
              select(() => {
                void auth.logout();
              })
            }
          >
            Sign out
          </Dropdown.Item>
          <Dropdown.Divider />
          <Dropdown.Item onSelect={() => setOpen(false)}>Close menu</Dropdown.Item>
        </Dropdown.Content>
      </Dropdown.Root>
    </>
  );
}

const local = StyleSheet.create({
  backdrop: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, zIndex: 10 },
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderColor: brand.line,
    borderRadius: 999,
    backgroundColor: brand.card,
    padding: 4,
    paddingRight: 10,
  },
  triggerLabel: { maxWidth: 160, color: brand.ink, fontFamily: fonts.bodyMedium, fontSize: 14 },
  chevron: { color: brand.muted, fontSize: 14, lineHeight: 14 },
  // `left: undefined` unsets the package's `left: 0` when the two style objects
  // are flattened, leaving `right: 0` to anchor the menu.
  anchorRight: { left: undefined, right: 0 },
});
