import { Redirect, useLocalSearchParams } from 'expo-router';

/** `/settings` on its own opens the first section. */
export default function SettingsIndexRoute() {
  const { groupId } = useLocalSearchParams<{ groupId: string }>();
  return <Redirect href={`/groups/${groupId ?? ''}/settings/exchange`} />;
}
