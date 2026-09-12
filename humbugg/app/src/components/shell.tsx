// The page chrome every screen sits in: header with the wordmark and account
// menu, a scrolling body, and the policy footer.
//
// Ports `src/components/Layout.tsx`. The footer's policy links now cross an
// origin — the legal pages live on the marketing site — so they open in the
// system browser rather than routing.
import { Card as DsCard, Spinner } from '@ansavva/design-system';
import { Link, usePathname } from 'expo-router';
import type { ReactNode } from 'react';
import { Linking, Pressable, ScrollView, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { LEGAL_EXTERNAL_LINKS } from '../config/site';
import { SERVICE_COUNTRY, SERVICE_CURRENCY } from '../config/policies';
import { useAuth } from '../context/auth-context';
import { useScrollRestoration } from '../hooks/use-scroll-restoration';
import { useTheme } from '../theme/styles';
import { AvatarMenu } from './avatar-menu';
import { Brand } from './brand';

/**
 * The page chrome. `aside` is a rail beside the scrolling page — outside the scroll, full height,
 * its own surface — for the one thing that has earned one: the anonymous chat, which wants to stay
 * put while the exchange scrolls past it the way a messenger sits beside the thing it is about.
 */
export function Shell({
  children,
  aside,
  sheet,
  sheetInset = 0,
}: {
  children: ReactNode;
  aside?: ReactNode;
  /** A `BottomSheet` over the page column; `sheetInset` is the room the page leaves for it at rest. */
  sheet?: ReactNode;
  sheetInset?: number;
}) {
  const { styles } = useTheme();
  const auth = useAuth();
  // One scroller for the page, so this is the one place the offset is kept and put back.
  const scroll = useScrollRestoration(usePathname());
  return (
    <SafeAreaView edges={['top']} style={styles.screen}>
      <View style={{ flex: 1, flexDirection: 'row', minHeight: 0 }}>
        {/* Header and page share a column, so the wordmark lines up with the page content
            whatever width the rail leaves them; the rail runs the full height beside both. */}
        <View style={{ flex: 1, minWidth: 0 }}>
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
          <ScrollView
            ref={scroll.ref}
            contentContainerStyle={{ flexGrow: 1, paddingBottom: sheetInset }}
            keyboardShouldPersistTaps="handled"
            scrollEventThrottle={100}
            onScroll={scroll.onScroll}
            onContentSizeChange={scroll.onContentSizeChange}
            onLayout={scroll.onLayout}
          >
            <View style={styles.main}>{children}</View>
            <SiteFooter />
          </ScrollView>
          {sheet}
        </View>
        {aside}
      </View>
    </SafeAreaView>
  );
}

export function SiteFooter() {
  const { styles } = useTheme();
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
  const { styles } = useTheme();
  return <DsCard.Root style={[styles.card, roomy && styles.cardRoomy, style]}>{children}</DsCard.Root>;
}

/**
 * `.loading-panel` — the full-height "please wait" state.
 *
 * A spinner, no copy. The panel used to narrate each wait ("Loading your
 * profile…", "Taking you to sign in…") and the words read as the app talking
 * to itself: a wait is a wait, and the destination explains itself on arrival.
 * The spinner carries an accessible "Loading" name for screen readers.
 * `children` is for the failure case only — a message and a retry button.
 */
export function LoadingPanel({ children }: { children?: ReactNode }) {
  const { styles } = useTheme();
  return (
    <View style={styles.loadingPanel}>
      {/* The native leaf shrink-wraps with `alignSelf: 'flex-start'`, which beats the panel's `alignItems`. */}
      {children ?? <Spinner size="lg" style={styles.loadingSpinner} />}
    </View>
  );
}
