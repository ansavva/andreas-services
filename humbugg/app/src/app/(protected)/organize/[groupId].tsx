import { Redirect, useLocalSearchParams } from 'expo-router';

/**
 * The organizer dashboard is a set of tabs on the exchange page now (#684), and each tab is a
 * route (#690). This stays so every link that was ever minted to it still lands — Stripe's return
 * URL from a Checkout the backend set up before this shipped, the seeder's hint, a bookmark — on
 * the page it meant.
 */
export default function OrganizeRoute() {
  const { groupId, checkout } = useLocalSearchParams<{ groupId: string; checkout?: string }>();
  const value = Array.isArray(checkout) ? checkout[0] : checkout;
  const base = `/groups/${groupId ?? ''}`;
  return (
    <Redirect
      href={value ? `${base}/settings/billing?checkout=${encodeURIComponent(value)}` : `${base}/people`}
    />
  );
}
