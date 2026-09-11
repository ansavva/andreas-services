import { Redirect, useLocalSearchParams } from 'expo-router';

/**
 * The organizer dashboard is a set of tabs on the exchange page now (#684). This route stays so
 * every link that was ever minted to it still lands — Stripe's return URL from a Checkout the
 * backend set up before this shipped, the seeder's hint, a bookmark — on the tab it meant.
 */
export default function OrganizeRoute() {
  const { groupId, checkout } = useLocalSearchParams<{ groupId: string; checkout?: string }>();
  const value = Array.isArray(checkout) ? checkout[0] : checkout;
  const query = value ? `tab=settings&checkout=${encodeURIComponent(value)}` : 'tab=people';
  return <Redirect href={`/groups/${groupId ?? ''}?${query}`} />;
}
