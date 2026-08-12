// The 404, ported from `app/root.tsx`'s ErrorBoundary. The SPA export maps a
// CloudFront 403/404 to `/index.html`, so an unknown path reaches the router
// rather than the bucket — and lands here.
import { Link } from 'expo-router';
import { Text, View } from 'react-native';

import { styles } from '../theme/styles';

export default function NotFound() {
  return (
    <View style={[styles.screen, { alignItems: 'center', justifyContent: 'center', padding: 20 }]}>
      <Text style={styles.eyebrow}>Page not found</Text>
      <Text style={[styles.displayLg, { marginTop: 16, textAlign: 'center' }]}>
        That gift tag leads nowhere.
      </Text>
      <Text style={[styles.bodyMuted, { marginTop: 20, textAlign: 'center' }]}>
        Return home and we’ll get you back to the exchange.
      </Text>
      <Link href="/" style={[styles.link, { marginTop: 32 }]}>Return to Humbugg</Link>
    </View>
  );
}
