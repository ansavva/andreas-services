// The app's root. Everything global happens here, in this order:
//
//   1. The scheme the reader chose, which mounts the design system's
//      `ThemeProvider` — and therefore Humbugg's brand — inside itself.
//   2. The fonts, which on this side are real assets rather than a CSS import.
//   3. The auth and profile providers the SSR app kept in `app/root.tsx`.
//
// There is no polyfill import at the top any more. Amplify needed three of them
// before anything could import it; expo-auth-session needs none, because
// expo-crypto supplies the entropy Hermes has no WebCrypto for.
// Imported per WEIGHT, not from the family root. `@expo-google-fonts/archivo`
// re-exports all eighteen weights, and Metro follows the whole barrel into the
// asset graph — the export shipped 7.9 MB of unused `.ttf` before these were
// narrowed to the seven faces the app actually names.
import { LilyScriptOne_400Regular } from '@expo-google-fonts/lily-script-one/400Regular';
import { OpenSans_400Regular } from '@expo-google-fonts/open-sans/400Regular';
import { OpenSans_500Medium } from '@expo-google-fonts/open-sans/500Medium';
import { OpenSans_600SemiBold } from '@expo-google-fonts/open-sans/600SemiBold';
import { OpenSans_700Bold } from '@expo-google-fonts/open-sans/700Bold';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '../context/auth-context';
import { ProfileProvider } from '../context/profile-context';
import { SchemePreferenceProvider } from '../theme/scheme-preference';
import { useTheme } from '../theme/styles';

export default function RootLayout() {
  // OUTSIDE the tree, so the whole app is one scheme decision: the provider
  // renders nothing until the stored preference has been read, and everything
  // under it — including the font holder below, which paints a full screen of
  // `brand.bg` — is therefore drawn in the scheme the reader chose rather than
  // in whatever the OS was asking for a frame earlier.
  return (
    <SchemePreferenceProvider>
      <Shell />
    </SchemePreferenceProvider>
  );
}

function Shell() {
  const { brand } = useTheme();
  // Open Sans for everything that is type — headings included, since the serif
  // came out — and Lily Script One for the wordmark, which is a logo. The same
  // families the marketing site pulls from Google Fonts. React Native resolves
  // one registered family name per style, so each weight is its own
  // registration rather than a `font-weight`.
  const [fontsLoaded] = useFonts({
    OpenSans_400Regular,
    OpenSans_500Medium,
    OpenSans_600SemiBold,
    OpenSans_700Bold,
    LilyScriptOne_400Regular,
  });

  return (
    <SafeAreaProvider>
      {/*
        The bar's own glyphs, not the page: `dark` means dark icons, which is
        what a cream page wants and a deep green one cannot carry. `auto`
        asks the platform to follow the scheme, which is the same answer
        `useTheme()` gives every surface underneath.
      */}
      <StatusBar style="auto" />
      {/*
        Hold the first paint until the faces are registered. Without it the
        first frame renders in the platform's system font and reflows — which
        is very visible on the wordmark, whose whole identity is its face.
        The holder is the page background, so the wait reads as a load rather
        than a flash.
      */}
      {fontsLoaded ? (
        <AuthProvider>
          <ProfileProvider>
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: brand.bg },
              }}
            />
          </ProfileProvider>
        </AuthProvider>
      ) : (
        <View style={{ flex: 1, backgroundColor: brand.bg }} />
      )}
    </SafeAreaProvider>
  );
}
