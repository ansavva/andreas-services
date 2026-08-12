// `/join/:groupId` sits OUTSIDE the `(protected)` group on purpose: an invited
// person arrives here signed out, and the screen itself offers sign-in and
// sign-up. Guarding it would bounce them to /login and lose the invite secret in
// the URL fragment.
import { useLocalSearchParams } from 'expo-router';

import JoinScreen from '../../screens/join';

export default function JoinRoute() {
  const { groupId } = useLocalSearchParams<{ groupId: string }>();
  return <JoinScreen groupId={groupId ?? ''} />;
}
