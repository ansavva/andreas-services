// A destructive button.
//
// The package has no `danger` intent, and that is a decision rather than a gap:
// `button.props.ts` records that the semantic token set has no `danger-text`
// pair to put on a danger fill. Humbugg has three genuinely destructive actions
// (delete group, delete account, emergency reveal) and the web app styled them
// all with one intent, so rather than hand-roll a Pressable — which would be the
// first component of a second design system — this is the package's own Button
// with the fill swapped. `primary` keeps the cream `primaryText` label, which is
// exactly what belongs on the danger red.
import { Button } from '@ansavva/design-system';
import type { ComponentProps } from 'react';
import type { StyleProp, ViewStyle } from 'react-native';

import { brand } from '../theme/theme';

type ButtonProps = ComponentProps<typeof Button>;

export function DangerButton({
  style,
  ...props
}: Omit<ButtonProps, 'intent' | 'style'> & { style?: StyleProp<ViewStyle> }) {
  // `Button` inherits `PressableProps['style']`, which may be a function of the
  // press state; the fill has to sit under whatever the caller passes, so the
  // two are composed rather than concatenated.
  return (
    <Button
      intent="primary"
      style={(state) => [{ backgroundColor: brand.danger }, style] as StyleProp<ViewStyle>}
      {...props}
    />
  );
}
