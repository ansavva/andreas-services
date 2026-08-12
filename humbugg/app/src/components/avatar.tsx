// The user's avatar: the uploaded photo when one exists, otherwise a deterministic
// coloured circle with their initials.
//
// Composed from the design system's `Avatar` compound rather than hand-rolled —
// it already owns the image-load state machine that decides when the fallback
// shows. Two things are ours: the size (the package's `size` prop is a fixed
// scale and the web app used 32 / 64 / 80 px), and the fallback colours, which
// are per-person and therefore cannot be a semantic role. `Avatar.Fallback`
// paints `surfaceAlt` behind `muted` text; a `style` override and a nested
// `<Text>` restate both, which is the composition seam the package intends.
import { Avatar as DsAvatar } from '@ansavva/design-system';
import { StyleSheet, Text } from 'react-native';

import { fonts } from '../theme/theme';
import { avatarColor, initials } from '../utils/avatar';

interface AvatarProps {
  /** Uploaded photo URL. When present it is shown; otherwise a coloured initials circle renders. */
  src?: string | null;
  name?: string | null;
  email?: string | null;
  size?: number;
  /** Draws the hairline the web app applied with `border border-line`. */
  bordered?: boolean;
}

export function Avatar({ src, name, email, size = 36, bordered = false }: AvatarProps) {
  const { bg, fg } = avatarColor(name || email);
  const round = { width: size, height: size, borderRadius: size / 2 };

  return (
    <DsAvatar.Root
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[round, bordered && styles.bordered]}
    >
      {src ? <DsAvatar.Image source={{ uri: src }} alt="" style={round} /> : null}
      <DsAvatar.Fallback style={[round, { backgroundColor: bg }]}>
        <Text style={[styles.initials, { color: fg, fontSize: size * 0.4 }]}>
          {initials(name, email)}
        </Text>
      </DsAvatar.Fallback>
    </DsAvatar.Root>
  );
}

const styles = StyleSheet.create({
  bordered: { borderWidth: 1, borderColor: '#ddd6c5' },
  initials: { fontFamily: fonts.heading },
});
