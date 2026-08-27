// Where the hosted sign-in page returns to on the WEB.
//
// Native never renders this: `promptAsync` intercepts `humbugg://auth/callback`
// and finishes the exchange inside `signInNative`. The route still exists on
// both platforms because the redirect URI is registered for both and a store
// build that ever loses the interception should land somewhere that says so
// rather than on the not-found screen.
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Platform, View } from 'react-native';

import { LoadingPanel, Shell } from '../../components/shell';
import { StatusMessage } from '../../components/status-message';
import { completeWebSignIn } from '../../auth/oauth';
import { useAuth } from '../../context/auth-context';
import { sessionKeys, sessionStore } from '../../utils/session-store';

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default function AuthCallbackRoute() {
  const auth = useAuth();
  const router = useRouter();
  const params = useLocalSearchParams<{
    code?: string;
    state?: string;
    error?: string;
    error_description?: string;
  }>();
  const [error, setError] = useState<string | null>(null);
  // React 18 mounts effects twice in development; a second exchange of the same
  // authorization code is rejected by Cognito, so it must not be attempted.
  const started = useRef(false);

  useEffect(() => {
    if (Platform.OS !== 'web' || started.current) return;
    started.current = true;

    const returnTo = sessionStore.get(sessionKeys.returnTo);
    sessionStore.remove(sessionKeys.returnTo);

    completeWebSignIn({
      code: first(params.code),
      state: first(params.state),
      error: first(params.error),
      errorDescription: first(params.error_description),
    })
      .then((tokens) => {
        auth.adopt(tokens);
        // `replace`, so the code never sits in history to be replayed.
        router.replace((returnTo ?? '/') as '/');
      })
      .catch((cause: unknown) => {
        setError(cause instanceof Error ? cause.message : 'Sign-in could not be completed.');
      });
    // Runs once, on mount, with whatever the landing URL carried.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <Shell>
        <View style={{ paddingVertical: 48, gap: 16 }}>
          <StatusMessage message={error} />
        </View>
      </Shell>
    );
  }

  return (
    <Shell>
      <LoadingPanel>Finishing sign-in…</LoadingPanel>
    </Shell>
  );
}
