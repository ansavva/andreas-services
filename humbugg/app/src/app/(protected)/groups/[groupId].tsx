import { useLocalSearchParams } from 'expo-router';

import GroupScreen from '../../../screens/group';

export default function GroupRoute() {
  const { groupId } = useLocalSearchParams<{ groupId: string }>();
  return <GroupScreen groupId={groupId ?? ''} />;
}
