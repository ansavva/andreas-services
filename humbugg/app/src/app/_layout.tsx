// The app's root. Everything global happens here, in this order:
//
//   1. Amplify's React Native wiring, which MUST run before anything imports
//      `aws-amplify` — hence the bare side-effect import on the first line.
//   2. Humbugg's brand, through the design system's one native theming seam.
//   3. The fonts, which on this side are real assets rather than a CSS import.
//   4. The auth and profile providers the SSR app kept in `app/root.tsx`.
import '../amplify';

import { ThemeProvider } from '@ansavva/design-system';
// Imported per WEIGHT, not from the family root. `@expo-google-fonts/archivo`
// re-exports all eighteen weights, and Metro follows the whole barrel into the
// asset graph — the export shipped 7.9 MB of unused `.ttf` before these were
// narrowed to the seven faces the app actually names.
import { Archivo_400Regular } from '@expo-google-fonts/archivo/400Regular';
import { Archivo_500Medium } from '@expo-google-fonts/archivo/500Medium';
import { Archivo_600SemiBold } from '@expo-google-fonts/archivo/600SemiBold';
import { Archivo_700Bold } from '@expo-google-fonts/archivo/700Bold';
import { LilyScriptOne_400Regular } from '@expo-google-fonts/lily-script-one/400Regular';
import { Spectral_500Medium } from '@expo-google-fonts/spectral/500Medium';
import { Spectral_600SemiBold } from '@expo-google-fonts/spectral/600SemiBold';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '../context/auth-context';
import { ProfileProvider } from '../context/profile-context';
import { humbuggTheme } from '../theme/theme';
import { brand } from '../theme/theme';

export default function RootLayout() {
  // Spectral for headings, Archivo for body, Lily Script One for the wordmark —
  // the same three families the web app pulls from Google Fonts and
  // `@fontsource`. React Native resolves one registered family name per style,
  // so each weight is its own registration rather than a `font-weight`.
  const [fontsLoaded] = useFonts({
    Spectral_500Medium,
    Spectral_600SemiBold,
    Archivo_400Regular,
    Archivo_500Medium,
    Archivo_600SemiBold,
    Archivo_700Bold,
    LilyScriptOne_400Regular,
  });

  return (
    <ThemeProvider theme={humbuggTheme}>
      <SafeAreaProvider>
        <StatusBar style="dark" />
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
    </ThemeProvider>
  );
}
