import { Redirect, useLocalSearchParams } from 'expo-router';

import { SETTINGS_SECTIONS, type SettingsSection } from '../../../../../components/settings-tab';
import OrganizerScreen from '../../../../../screens/group/organizer';

function isSection(value: string | undefined): value is SettingsSection {
  return SETTINGS_SECTIONS.some((item) => item.value === value);
}

/** One Settings section, by its name in the URL. A name that is not one goes to the first. */
export default function SettingsSectionRoute() {
  const { groupId, section, checkout } = useLocalSearchParams<{ groupId: string; section: string; checkout?: string }>();
  const requested = Array.isArray(section) ? section[0] : section;
  if (!isSection(requested)) return <Redirect href={`/groups/${groupId ?? ''}/settings/exchange`} />;
  return (
    <OrganizerScreen
      tab="settings"
      section={requested}
      checkout={Array.isArray(checkout) ? checkout[0] : checkout}
    />
  );
}
