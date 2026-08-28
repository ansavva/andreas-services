import { useLocalSearchParams } from 'expo-router';

import OrganizeScreen from '../../../screens/organize';

export default function OrganizeRoute() {
  const { groupId } = useLocalSearchParams<{ groupId: string }>();
  return <OrganizeScreen groupId={groupId ?? ''} />;
}
