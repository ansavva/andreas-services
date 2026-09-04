// The invitation landing page.
//
// The secret is in the URL fragment (`#invite=…`) — see `utils/invite.ts` — and is stashed the
// moment it is read, because signing in navigates away and the fragment does not survive the round
// trip.
//
// The page names the exchange before asking anybody to join it (#134). It did not, for a reason
// worth remembering: `api.getInvitation` existed, was never called, and was broken twice over —
// a relative `/api` path from a time the app was served same-origin, and the secret in a query
// string, which is the one place the fragment design exists to keep it out of.
import { Button } from '@ansavva/design-system';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { api, ApiError } from '../api/client';
import { BrandMark } from '../components/brand';
import { Card, Shell } from '../components/shell';
import { StatusMessage } from '../components/status-message';
import { useAuth } from '../context/auth-context';
import { styles } from '../theme/styles';
import type { InvitationPreview } from '../types';
import { readInviteSecret } from '../utils/invite';
import { sessionKeys, sessionStore } from '../utils/session-store';

/**
 * Why a join was refused, in words a person following a link can act on.
 *
 * The API's own messages are written for whoever the endpoint usually serves, which for most of
 * these is an organizer. Somebody who has just clicked a link in a group chat cannot reset a draw or
 * buy Plus for an exchange they are not in, and telling them to is worse than telling them nothing.
 */
function refusal(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return error instanceof Error ? error.message : 'Unable to join this exchange.';
  }
  switch (error.status) {
    case 403:
      // Invalid, rotated or expired are indistinguishable from here, and deliberately so: telling
      // somebody which one would tell a stranger whether a group id is real.
      return 'This invitation is no longer valid. The organizer may have created a fresh link — ask them for the current one.';
    case 402:
      return 'This exchange is full. Only the organizer can make room for more people.';
    case 409:
      return error.message;
    case 404:
      return 'This exchange no longer exists.';
    default:
      return error.message;
  }
}

export default function JoinScreen({ groupId }: { groupId: string }) {
  const auth = useAuth();
  const router = useRouter();
  const [invite, setInvite] = useState<string>(() => sessionStore.get(sessionKeys.join(groupId)) ?? '');
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
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

  // What this invitation is for, fetched signed-out. A failure here is not reported: the preview is
  // a courtesy, and the join below gives the authoritative answer with a better message.
  useEffect(() => {
    if (!invite) return;
    let cancelled = false;
    void api
      .getInvitation(groupId, invite)
      .then((value) => { if (!cancelled) setPreview(value); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [groupId, invite]);

  // Remember where to come back to, so signing in from here lands on the invitation rather than the
  // dashboard. The secret is already in sessionStorage, which survives the hosted round trip.
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
      setError(refusal(err));
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
          {preview ? preview.exchange_name : 'Join this Secret Santa exchange'}
        </Text>
        <Text style={[styles.bodyMuted, { marginTop: 16, maxWidth: 448, textAlign: 'center' }]}>
          {preview
            ? 'Add your wish list and Humbugg keeps the surprise safe until draw day.'
            : 'Sign in, add your wish list, and let Humbugg keep the surprise safe until draw day.'}
        </Text>

        {!invite ? (
          <StatusMessage message="This invitation link is incomplete. Ask the organizer to send it again — the part after the # matters." />
        ) : null}

        {auth.authenticated ? (
          <View style={{ marginTop: 28, width: '100%' }}>
            <Button style={styles.buttonBlock} size="lg" disabled={busy || !invite} onPress={() => void join()}>
              {busy ? 'Joining…' : 'Join the exchange'}
            </Button>
          </View>
        ) : (
          <View style={{ marginTop: 28, width: '100%' }}>
            {/*
              The account requirement, said BEFORE the button rather than discovered after it. Every
              exchange needs one — it is how a wishlist stays yours and an assignment stays private —
              and somebody deciding whether to click deserves to know they are about to make one.
            */}
            <Text style={[styles.small, { textAlign: 'center', marginBottom: 16 }]}>
              You need a free Humbugg account to take part. It is what keeps your wishlist yours and
              your assignment private.
            </Text>
            {/* One button, not two: sign-in and sign-up are the same hosted page now, and the
                visitor chooses between them there. */}
            <Button style={styles.buttonBlock} size="lg" onPress={() => router.push('/login')}>
              Sign in or create an account
            </Button>
          </View>
        )}
        <StatusMessage message={error} />
      </Card>
    </Shell>
  );
}
