// The scrolling body of a Drawer that holds a form.
//
// A react-native-web ScrollView clips horizontally (`overflow-x: hidden`), and
// a control that fills its width has nowhere to draw a focus ring: the design
// system's ring is a 2px outline 2px OUTSIDE the control, so the ring's left
// and right edges were cut off on every field in the wish and start-a-group
// drawers. Four pixels of horizontal padding inside the scrollport, pulled
// back with the same negative margin so nothing moves, gives the ring room.
import type React from 'react';
import { ScrollView, StyleSheet } from 'react-native';

/** 2px outline + 2px offset — `nativeFocusRing` in @ansavva/design-system. */
const RING = 4;

export function DrawerBody({ children }: { children: React.ReactNode }) {
  return (
    <ScrollView keyboardShouldPersistTaps="handled" style={styles.scroll} contentContainerStyle={styles.content}>
      {children}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { marginHorizontal: -RING },
  content: { paddingHorizontal: RING, paddingBottom: 8 },
});
