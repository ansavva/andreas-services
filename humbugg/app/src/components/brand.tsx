// `.brand-wordmark` and `.brand-mark` from the web app's stylesheet, as components.
//
// Both are Lily Script One, which is the whole reason fonts are a real step on
// this side: there is no `@fontsource` import to make a family available, so the
// face is loaded through `expo-font` in the root layout and named here.
import { Link } from 'expo-router';
import { Pressable, Text, View } from 'react-native';

import { styles } from '../theme/styles';

/** The wordmark, linking home. Matches the web app's `<Brand />`. */
export function Brand() {
  return (
    <Link href="/" asChild>
      <Pressable accessibilityRole="link" accessibilityLabel="Humbugg home">
        <Text style={styles.wordmark}>Humbugg</Text>
      </Pressable>
    </Link>
  );
}

/** `.brand-mark` — the rotated green square with the script H. */
export function BrandMark({ large = false }: { large?: boolean }) {
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[styles.brandMark, large && styles.brandMarkLarge]}
    >
      <Text style={[styles.brandMarkText, large && styles.brandMarkLargeText]}>H</Text>
    </View>
  );
}
