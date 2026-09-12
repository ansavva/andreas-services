// A bottom sheet that stays: a panel pinned to the bottom of the screen that peeks, and is dragged
// up to show more of itself or down to show less.
//
// Not the design system's `Drawer`. That is a modal — a scrim, open or closed, dismissed by
// tapping outside — and this is the opposite shape: always present, never covering the page with
// a scrim, and sized by the reader's thumb rather than by a boolean. The package has no persistent
// sheet, so this composes one from `Animated` and `PanResponder`; if a second surface needs it,
// that is the moment to raise it upstream rather than copy this.
//
// Three snap points: `peek` (the handle and one header row), `half`, and `full`. A drag settles on
// the one it was heading for — a flick decides by direction, a slow drag by nearness — and a tap on
// the handle steps between peek and half. The page underneath is expected to leave `PEEK` of
// bottom padding so nothing hides behind the resting sheet.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Animated, PanResponder, StyleSheet, View, useWindowDimensions } from 'react-native';

import { radii } from '../theme/radii';
import { scopedStyles, useTheme } from '../theme/styles';

/** The resting height: the handle strip plus one title row of whatever is inside. */
export const PEEK = 64;
const HANDLE = 24;
/** Above `full` the page header would be covered, and the sheet is not a page. */
const TOP_INSET = 80;

type Snap = 'peek' | 'half' | 'full';

export function BottomSheet({ children, label }: { children: ReactNode; label: string }) {
  const theme = useTheme();
  const local = localStyles(theme);
  const { height: window } = useWindowDimensions();
  const snaps = useMemo<Record<Snap, number>>(
    () => ({ peek: PEEK, half: Math.round(window * 0.5), full: window - TOP_INSET }),
    [window],
  );
  const [snap, setSnap] = useState<Snap>('peek');
  // Read by the pan responder, which is built once and would otherwise close over the first value.
  const snapRef = useRef<Snap>('peek');
  const height = useRef(new Animated.Value(PEEK)).current;
  // What the drag started from, so a move is start minus travel rather than a running sum.
  const startHeight = useRef(PEEK);
  const current = useRef(PEEK);
  useEffect(() => {
    const id = height.addListener(({ value }) => { current.current = value; });
    return () => height.removeListener(id);
  }, [height]);

  function settle(target: Snap) {
    snapRef.current = target;
    setSnap(target);
    Animated.spring(height, { toValue: snaps[target], useNativeDriver: false, bounciness: 2 }).start();
  }

  // A window resize (rotation, a keyboard on the web) moves the snap the sheet is resting on.
  useEffect(() => { height.setValue(snaps[snap]); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [snaps]);

  const pan = useMemo(
    () =>
      PanResponder.create({
        // Claimed at the start, not on the first move: a Pressable underneath would otherwise take
        // the responder first and, under react-native-web, never hand it over. A tap is a drag
        // that went nowhere, decided on release.
        onStartShouldSetPanResponder: () => true,
        onPanResponderGrant: () => { startHeight.current = current.current; },
        onPanResponderMove: (_event, gesture) => {
          height.setValue(Math.min(snaps.full, Math.max(snaps.peek, startHeight.current - gesture.dy)));
        },
        onPanResponderRelease: (_event, gesture) => {
          const order: Snap[] = ['peek', 'half', 'full'];
          const at = current.current;
          if (Math.abs(gesture.dx) < 6 && Math.abs(gesture.dy) < 6) {
            settle(snapRef.current === 'peek' ? 'half' : 'peek');
            return;
          }
          // A flick goes the way it was flicked; a slow drag rests on the nearest point.
          if (gesture.vy < -0.3) settle(order.find((s) => snaps[s] > at + 8) ?? 'full');
          else if (gesture.vy > 0.3) settle([...order].reverse().find((s) => snaps[s] < at - 8) ?? 'peek');
          else settle(order.reduce((best, s) => (Math.abs(snaps[s] - at) < Math.abs(snaps[best] - at) ? s : best), 'peek'));
        },
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [snaps],
  );

  return (
    <Animated.View style={[local.sheet, { height }]} accessibilityLabel={label}>
      <View
        {...pan.panHandlers}
        accessibilityRole="button"
        accessibilityLabel={snap === 'peek' ? 'Expand chat' : 'Collapse chat'}
        style={local.handleStrip}
      >
        <View style={local.handle} />
      </View>
      <View style={{ flex: 1, minHeight: 0 }}>{children}</View>
    </Animated.View>
  );
}

const localStyles = scopedStyles((t) => ({
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderColor: t.brand.line,
    backgroundColor: t.brand.card,
    shadowColor: t.brand.shadow,
    shadowOpacity: 0.12,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: -4 },
    elevation: 8,
    overflow: 'hidden',
  },
  handleStrip: { height: HANDLE, alignItems: 'center', justifyContent: 'center' },
  handle: { width: 40, height: 4, borderRadius: radii.pill, backgroundColor: t.brand.line },
}));
