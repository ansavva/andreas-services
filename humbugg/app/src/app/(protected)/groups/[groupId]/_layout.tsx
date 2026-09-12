import { Slot, useLocalSearchParams } from 'expo-router';

import GroupLayout from '../../../../screens/group/layout';

/** One exchange. The header and the tabs are here; each tab is a route below. */
export default function GroupRouteLayout() {
  const { groupId } = useLocalSearchParams<{ groupId: string }>();
  return (
    <GroupLayout groupId={groupId ?? ''}>
      <Slot />
    </GroupLayout>
  );
}
