import { Redirect, useLocalSearchParams } from 'expo-router';

import { useGroup } from '../../../../screens/group/context';

const ORGANIZER = ['people', 'draw', 'settings'];

/**
 * `/groups/{id}` on its own is where every link minted before the tabs were routes lands — the
 * dashboard row, a reminder email, Stripe's return with `?tab=settings&checkout=…`. It goes to the
 * page the link meant, or to the one that matters most: the person you drew once there is one,
 * your own wishlist until then.
 */
export default function GroupIndexRoute() {
  const { groupId, tab, checkout } = useLocalSearchParams<{ groupId: string; tab?: string; checkout?: string }>();
  const { group, me, assignment } = useGroup();
  const requested = Array.isArray(tab) ? tab[0] : tab;
  const returned = Array.isArray(checkout) ? checkout[0] : checkout;
  const base = `/groups/${groupId ?? ''}`;

  if (returned) return <Redirect href={`${base}/settings/billing?checkout=${encodeURIComponent(returned)}`} />;
  if (requested && ORGANIZER.includes(requested) && group.is_organizer)
    return <Redirect href={requested === 'settings' ? `${base}/settings/exchange` : `${base}/${requested}`} />;
  return <Redirect href={group.status === 'drawn' && me.is_participating && assignment ? `${base}/giving` : `${base}/you`} />;
}
