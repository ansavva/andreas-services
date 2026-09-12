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
import { StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

import { useTheme } from '../theme/styles';
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
  const letters = (
    <Text
      style={[
        styles.initials,
        { color: fg, fontSize: size * 0.4, lineHeight: size * 0.5, includeFontPadding: false },
      ]}
    >
      {initials(name, email)}
    </Text>
  );

  return (
    <DsAvatar.Root
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[round, bordered && styles.bordered]}
    >
      {src ? (
        // The package's pair: the photo, and its fallback if the photo fails to load.
        <>
          <DsAvatar.Image source={{ uri: src }} alt="" style={round} />
          <DsAvatar.Fallback style={{ borderRadius: size / 2, backgroundColor: bg }}>{letters}</DsAvatar.Fallback>
        </>
      ) : (
        // No photo means no load to wait on, so the initials are drawn directly: a centred box
        // of our own rather than the package's Fallback, whose label is a <Text> of its own
        // size that a nested, larger <Text> sits on the baseline of — a pixel high and right at
        // 24px, which is where a face beside a chat bubble lives.
        <View style={[StyleSheet.absoluteFill, styles.centred, { backgroundColor: bg }]}>{letters}</View>
      )}
    </DsAvatar.Root>
  );
}

/**
 * The mark for the one person in a chat who is deliberately unnamed: a Secret Santa.
 *
 * The same circle as everyone else's, so it reads as a person and not an error, with a Santa hat
 * where the face would be — the brand green, a cream brim, a gold pom — drawn as paths, so it is
 * one shape in either scheme rather than an emoji at the platform's mercy. The pom is the accent
 * role, the one warm colour in the palette, and it is what makes this read as a hat at 24px.
 */
export function SantaAvatar({ size = 36 }: { size?: number }) {
  const { brand } = useTheme();
  const round = { width: size, height: size, borderRadius: size / 2 };
  return (
    <DsAvatar.Root
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[round, styles.bordered, { borderColor: brand.line }]}
    >
      <DsAvatar.Fallback style={[styles.hatStage, { borderRadius: size / 2, backgroundColor: brand.surfaceAlt }]}>
        <Svg width={size - 2} height={size - 2} viewBox="0 0 40 40">
          <Path d="M11 27 C 12 15, 20 10, 27 8 C 25 14, 26 20, 30 27 Z" fill={brand.primary} />
          <Rect x={8} y={25.5} width={24} height={6} rx={3} fill={brand.card} stroke={brand.line} />
          <Circle cx={27.5} cy={8.5} r={3.4} fill={brand.accent} />
        </Svg>
      </DsAvatar.Fallback>
    </DsAvatar.Root>
  );
}

const styles = StyleSheet.create({
  bordered: { borderWidth: 1, borderColor: '#ddd6c5' },
  hatStage: { alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  initials: { fontFamily: fonts.heading, textAlign: 'center' },
  centred: { alignItems: 'center', justifyContent: 'center' },
});
