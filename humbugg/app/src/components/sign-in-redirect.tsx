// Signed out on an app-only domain means one thing: go and sign in.
//
// This replaced a launcher screen that showed pitch copy and a "Continue to
// sign in" button. The button was a second click to reach a page the app had
// already decided to send you to, and the pitch belongs on www.humbugg.com —
// app.humbugg.com is entirely behind auth, so nobody arrives here to be
// persuaded.
//
// The one thing that still needs rendering is the failure: if the hosted page
// cannot be reached there is nowhere to redirect to, so the retry lives here
// rather than leaving a blank screen.
import { Button } from '@ansavva/design-system';
import { useCallback, useEffect, useState } from 'react';

import { useAuth } from '../context/auth-context';
import { LoadingPanel } from './shell';
import { StatusMessage } from './status-message';

export function SignInRedirect({ returnTo }: { returnTo?: string }) {
  const auth = useAuth();
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    setError(null);
    try {
      // On web this navigates the document away and nothing after it runs.
      // `startWebSignIn` stashes `returnTo` itself, so it survives that load.
      await auth.login(returnTo);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not reach the sign-in page.');
    }
  }, [auth, returnTo]);

  useEffect(() => {
    void start();
  }, [start]);

  if (error) {
    return (
      <LoadingPanel>
        <StatusMessage message={error} />
        <Button onPress={() => void start()}>Try again</Button>
      </LoadingPanel>
    );
  }

  return <LoadingPanel>Taking you to sign in…</LoadingPanel>;
}
