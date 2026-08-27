import SignInLauncherScreen from '../../screens/sign-in-launcher';
import { sessionKeys, sessionStore } from '../../utils/session-store';

export default function LoginRoute() {
  // Where `(protected)/_layout.tsx` stashed the destination it bounced someone
  // off. Read at render rather than after the round trip, because on web the
  // round trip is a full page load and this component will not survive it.
  return <SignInLauncherScreen returnTo={sessionStore.get(sessionKeys.returnTo) ?? undefined} />;
}
