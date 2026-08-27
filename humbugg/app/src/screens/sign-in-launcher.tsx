// The whole of sign-in that still lives in this app: a button.
//
// Every credential screen this file replaced — sign in, sign up, confirm code,
// forgot password, confirm reset — is a Managed Login page now, so there is no
// form here to build and no error state to render but the one where launching
// the hosted page itself fails.
//
// The pitch copy is kept because it is the last thing a signed-out visitor sees
// before leaving for Cognito's page, and it is the only place this app gets to
// say what it is.
import { Button } from '@ansavva/design-system';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Card, Shell } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { useAuth } from '../context/auth-context';
import { styles } from '../theme/styles';

export default function SignInLauncherScreen({ returnTo }: { returnTo?: string }) {
  const auth = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setMessage(null);
    try {
      // On web this navigates the document away and nothing below runs. On
      // native it resolves once the hosted page has handed back a code.
      await auth.login(returnTo);
      router.replace((returnTo ?? '/') as '/');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <View style={{ gap: 40, paddingVertical: 32 }}>
        <View style={local.pitch}>
          <Text style={styles.eyebrow}>A calmer way to coordinate</Text>
          <Text style={[styles.displayXl, { marginTop: 16 }]}>The magic stays secret.{'\n'}The planning stays simple.</Text>
          <Text style={[styles.bodyMuted, { marginTop: 20, maxWidth: 448 }]}>
            One account keeps your groups, wish lists, and private assignments together.
          </Text>
        </View>
        <Card roomy style={local.card}>
          <Text style={styles.displayMd}>Sign in to Humbugg</Text>
          <Text style={[styles.bodyMuted, { marginTop: 8 }]}>
            You&apos;ll finish on Humbugg&apos;s secure sign-in page, where you can also create an
            account or reset your password.
          </Text>
          <View style={{ marginTop: 28, gap: 16 }}>
            <StatusMessage message={message} />
            <Button size="lg" disabled={busy} onPress={() => void start()}>
              {busy ? 'Opening…' : 'Continue to sign in'}
            </Button>
          </View>
        </Card>
      </View>
    </Shell>
  );
}

const local = StyleSheet.create({
  // Decoration beside the card, with no room for it on a phone; the container's
  // max width drops it on narrow layouts rather than a media query.
  pitch: { maxWidth: 520, alignSelf: 'center', width: '100%' },
  card: { width: '100%', maxWidth: 576, alignSelf: 'center' },
});
