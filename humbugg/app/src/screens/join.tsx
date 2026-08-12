// The invitation landing page, ported from `src/pages/JoinPage.tsx`.
//
// The secret is in the URL fragment (`#invite=…`) — see `utils/invite.ts` — and
// is stashed the moment it is read, because signing in navigates away and the
// fragment does not survive the round trip.
import { Button } from '@ansavva/design-system';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { api } from '../api/client';
import { BrandMark } from '../components/brand';
import { Card, Shell } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { useAuth } from '../context/auth-context';
import { styles } from '../theme/styles';
import { readInviteSecret } from '../utils/invite';
import { sessionKeys, sessionStore } from '../utils/session-store';

export default function JoinScreen({ groupId }: { groupId: string }) {
  const auth = useAuth();
  const router = useRouter();
  const [invite, setInvite] = useState<string>(() => sessionStore.get(sessionKeys.join(groupId)) ?? '');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void readInviteSecret().then((secret) => {
      if (cancelled || !secret) return;
      sessionStore.set(sessionKeys.join(groupId), secret);
      setInvite(secret);
    });
    return () => { cancelled = true; };
  }, [groupId]);

  // Remember where to come back to, so signing in from here lands on the
  // invitation rather than the dashboard.
  useEffect(() => {
    if (!auth.authenticated) sessionStore.set(sessionKeys.returnTo, `/join/${groupId}`);
  }, [auth.authenticated, groupId]);

  async function join() {
    setBusy(true);
    setError(null);
    try {
      await api.joinGroup(await auth.accessToken(), groupId, invite);
      sessionStore.remove(sessionKeys.join(groupId));
      sessionStore.remove(sessionKeys.returnTo);
      router.replace(`/groups/${groupId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to join this group.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <Card roomy style={{ width: '100%', maxWidth: 576, alignSelf: 'center', marginTop: 48, alignItems: 'center' }}>
        <BrandMark large />
        <Text style={[styles.eyebrow, { marginTop: 28 }]}>You&apos;re invited</Text>
        <Text style={[styles.displayLg, { marginTop: 8, textAlign: 'center' }]}>
          Join this Secret Santa exchange
        </Text>
        <Text style={[styles.bodyMuted, { marginTop: 16, maxWidth: 448, textAlign: 'center' }]}>
          Sign in, add your wish list, and let Humbugg keep the surprise safe until draw day.
        </Text>
        {!invite ? <StatusMessage message="This invitation link is incomplete or has expired." /> : null}
        {auth.authenticated ? (
          <View style={{ marginTop: 28, width: '100%' }}>
            <Button size="lg" disabled={busy || !invite} onPress={() => void join()}>
              {busy ? 'Joining…' : 'Join the group'}
            </Button>
          </View>
        ) : (
          <View style={{ marginTop: 28, width: '100%', gap: 12 }}>
            <Button size="lg" onPress={() => router.push('/signup')}>
              Create account
            </Button>
            <Button size="lg" intent="secondary" onPress={() => router.push('/login')}>
              Sign in
            </Button>
          </View>
        )}
        <StatusMessage message={error} />
      </Card>
    </Shell>
  );
}
