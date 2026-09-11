import { useLocalSearchParams } from 'expo-router';

import GroupScreen from '../../../screens/group';

export default function GroupRoute() {
  // `tab` is where a link lands (`/organize/{id}` redirects here with `people`); `checkout` is what
  // Stripe returns with on the web. Read here so the screen stays a function of its props.
  const { groupId, tab, checkout } = useLocalSearchParams<{ groupId: string; tab?: string; checkout?: string }>();
  return (
    <GroupScreen
      groupId={groupId ?? ''}
      tab={Array.isArray(tab) ? tab[0] : tab}
      checkout={Array.isArray(checkout) ? checkout[0] : checkout}
    />
  );
}
