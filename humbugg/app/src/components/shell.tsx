// The page chrome every screen sits in: header with the wordmark and account
// menu, a scrolling body, and the policy footer.
//
// Ports `src/components/Layout.tsx`. The footer's policy links now cross an
// origin — the legal pages live on the marketing site — so they open in the
// system browser rather than routing.
import { Card as DsCard } from '@ansavva/design-system';
import { Link } from 'expo-router';
import type { ReactNode } from 'react';
import { Linking, Pressable, ScrollView, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { LEGAL_EXTERNAL_LINKS } from '../config/site';
import { SERVICE_COUNTRY, SERVICE_CURRENCY } from '../config/policies';
import { useAuth } from '../context/auth-context';
import { styles } from '../theme/styles';
import { AvatarMenu } from './avatar-menu';
import { Brand } from './brand';

export function Shell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  return (
    <SafeAreaView edges={['top']} style={styles.screen}>
      <View style={styles.header}>
        <View style={styles.headerInner}>
          <Brand />
          <View accessibilityLabel="Primary navigation" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {auth.authenticated ? (
              <AvatarMenu />
            ) : (
              <>
                <Link href="/login" asChild>
                  <Pressable accessibilityRole="link" style={styles.navLink}>
                    <Text style={styles.navLinkText}>Sign in</Text>
                  </Pressable>
                </Link>
              </>
            )}
          </View>
        </View>
      </View>
      <ScrollView contentContainerStyle={{ flexGrow: 1 }} keyboardShouldPersistTaps="handled">
        <View style={styles.main}>{children}</View>
        <SiteFooter />
      </ScrollView>
    </SafeAreaView>
  );
}

export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <View style={styles.footer}>
      <View style={styles.footerInner}>
        <View
          accessibilityLabel="Policies"
          style={{ flexDirection: 'row', flexWrap: 'wrap', columnGap: 24, rowGap: 12 }}
        >
          {LEGAL_EXTERNAL_LINKS.map((link) => (
            <Pressable
              key={link.href}
              accessibilityRole="link"
              onPress={() => void Linking.openURL(link.href)}
            >
              <Text style={styles.smallMuted}>{link.label}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.smallMuted}>
          © {year} Humbugg · Available in the {SERVICE_COUNTRY} · Prices in {SERVICE_CURRENCY}
        </Text>
      </View>
    </View>
  );
}

/**
 * Humbugg's card surface — the design system's `Card.Root` with Humbugg's own
 * radius, padding and shadow on top. `Card.Root` supplies the `card`/`line`
 * colours from the theme; the geometry is Humbugg's (`rounded-2xl … p-6
 * shadow-sm`, which is not the package's default).
 */
export function Card({
  children,
  style,
  roomy = false,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  roomy?: boolean;
}) {
  return <DsCard.Root style={[styles.card, roomy && styles.cardRoomy, style]}>{children}</DsCard.Root>;
}

/** `.loading-panel` — the full-height "please wait" state. */
export function LoadingPanel({ children }: { children: ReactNode }) {
  return (
    <View style={styles.loadingPanel}>
      <Text style={styles.bodyMuted}>{children}</Text>
    </View>
  );
}
