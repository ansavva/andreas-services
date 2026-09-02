import { useLocalSearchParams } from 'expo-router';

import OrganizeScreen from '../../../screens/organize';

export default function OrganizeRoute() {
  // `checkout` is what Stripe returns with on the web (`success` / `canceled`). Read here rather
  // than in the screen so the screen stays a function of its props, like every other one.
  const { groupId, checkout } = useLocalSearchParams<{ groupId: string; checkout?: string }>();
  return (
    <OrganizeScreen
      groupId={groupId ?? ''}
      checkout={Array.isArray(checkout) ? checkout[0] : checkout}
    />
  );
}
