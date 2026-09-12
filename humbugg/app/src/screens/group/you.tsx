// FOR YOU: everything the other way round (#690).
//
// Your wishlist and your details — what the person who drew you gets to read — and, once drawn,
// whether their gift has arrived. It never names them: "your giver" is a role, and the page has
// nothing to fill it with. What they asked you is in the chat beside every tab.
import { Text, View, useWindowDimensions } from 'react-native';

import { api } from '../../api/client';
import { ExchangeInstructions } from '../../components/exchange-settings';
import { GiftReceivedPanel } from '../../components/gift-progress';
import { Card } from '../../components/shell';
import { WishListPanel } from '../../components/wishlist';
import { WishListForm } from '../../components/wishlist-form';
import { useTheme } from '../../theme/styles';
import { useGroup } from './context';

export default function YouScreen() {
  const { styles, brand } = useTheme();
  const { groupId, group, me, busy, action } = useGroup();
  // Two columns once there is room for a form beside a list; one under each other on a phone.
  const wide = useWindowDimensions().width >= 1024;
  const drawn = group.status === 'drawn' && me.is_participating;

  return (
    <>
      <Card style={{ backgroundColor: brand.surfaceAlt, borderColor: brand.surfaceAlt }}>
        <Text style={styles.eyebrow}>For you</Text>
        <Text style={[styles.heading, { marginTop: 4 }]}>
          {drawn ? 'Someone drew you. Help them out.' : 'Help your Secret Santa out.'}
        </Text>
        <Text style={[styles.smallMuted, { marginTop: 8 }]}>
          Only the person who drew you sees what is on this page, and only after the draw. You never
          learn who they are.
        </Text>
      </Card>

      {/* The recipient's word that it turned up (#132) — only once there is a gift coming. */}
      {drawn ? <GiftReceivedPanel groupId={groupId} /> : null}

      <ExchangeInstructions instructions={group.instructions} />

      <View style={wide ? { flexDirection: 'row', gap: 28, alignItems: 'flex-start' } : { gap: 28 }}>
        <View style={wide ? { flex: 1, minWidth: 0 } : undefined}>
          <WishListPanel groupId={groupId} />
        </View>
        <View style={wide ? { flex: 1, minWidth: 0 } : undefined}>
          <WishListForm
            key={`${me.wishlist ?? ''}|${me.avoidances ?? ''}|${me.address?.line1 ?? ''}`}
            membership={me}
            busy={busy}
            onSave={(data) =>
              void action((token) => api.updateMembership(token, groupId, data), 'Your gift details are saved.')
            }
            onClear={() =>
              void action(
                (token) => api.clearMyGroupData(token, groupId),
                'Your wishlist, preferences and mailing address were cleared.',
              )
            }
          />
        </View>
      </View>
    </>
  );
}
