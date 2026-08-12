// Reading the invite secret out of an invitation link.
//
// The backend mints `{APP_BASE_URL}/join/{groupId}#invite={secret}` and the
// secret rides in the URL **fragment** on purpose: a fragment is never sent to a
// server, never lands in an access log, and never leaks through a Referer
// header. That also means nothing in the routing layer can hand it to us —
// Expo Router parses the path and query, not the hash — so it is read from the
// raw URL here.
//
// Two sources, because a fragment reaches the two platforms differently:
//
//   web     the browser keeps it on `location.hash`, and a `single` (SPA) export
//           serves `index.html` for `/join/abc` without touching the fragment.
//   native  the link arrives as a deep link (`humbugg://join/abc#invite=…` or a
//           universal link), which `expo-linking` hands over whole.
import * as Linking from 'expo-linking';
import { Platform } from 'react-native';

/** Pulls `invite` out of a `#invite=…` fragment on a full or partial URL. */
export function inviteFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const hashIndex = url.indexOf('#');
  if (hashIndex === -1) return null;
  const params = new URLSearchParams(url.slice(hashIndex + 1));
  return params.get('invite');
}

/**
 * The invite secret for the URL that opened this screen, or null when the link
 * carried none. Async on native because the initial deep link is.
 */
export async function readInviteSecret(): Promise<string | null> {
  if (Platform.OS === 'web') {
    return inviteFromUrl(globalThis.location?.hash ? `#${globalThis.location.hash.replace(/^#/, '')}` : null);
  }
  return inviteFromUrl(await Linking.getInitialURL());
}
