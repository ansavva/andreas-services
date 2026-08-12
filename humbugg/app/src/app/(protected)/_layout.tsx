// The redirect guard that replaces `src/components/ProtectedRoute.tsx`.
//
// The web app wrapped each protected element in a `<ProtectedRoute>` component.
// Expo Router's idiom is a route GROUP whose layout decides whether anything
// below it may render at all: `(protected)` adds no path segment, so `/`,
// `/settings` and `/groups/:id` keep the URLs the route map promises while
// sharing one gate.
//
// The three states are the same three the wrapper had:
//   session unknown    → hold, so a signed-in user is never bounced to /login
//                        during the token restore.
//   signed out         → remember where they were headed, then redirect.
//   profile not loaded → hold, so a first-run account is not judged missing.
import { Redirect, Stack, usePathname } from 'expo-router';

import { LoadingPanel } from '../../components/shell';
import { useAuth } from '../../context/auth-context';
import { useProfile } from '../../context/profile-context';
import { sessionKeys, sessionStore } from '../../utils/session-store';

export default function ProtectedLayout() {
  const auth = useAuth();
  const { loaded: profileLoaded } = useProfile();
  const pathname = usePathname();

  if (auth.loading) return <LoadingPanel>Checking your session…</LoadingPanel>;

  if (!auth.authenticated) {
    sessionStore.set(sessionKeys.returnTo, pathname);
    return <Redirect href="/login" />;
  }

  if (!profileLoaded) return <LoadingPanel>Loading your profile…</LoadingPanel>;

  // The web app also redirected a profile-less user away from every protected
  // route except the dashboard. That branch is gone because the dashboard IS
  // the index of this group: a user with no profile lands on it and gets the
  // setup form, and the other two screens tolerate `profile === null` on their
  // own rather than needing the layout to police it.
  return <Stack screenOptions={{ headerShown: false }} />;
}
