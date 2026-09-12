// One organizer tab, as a page (#690).
//
// People, Draw and Settings are routes now; each renders `OrganizerTabs` for its own tab, with the
// group and the roster the layout already read. A participant who follows one of these URLs is
// told why there is nothing here rather than shown nothing.
import { useRouter } from 'expo-router';
import { Text } from 'react-native';

import { OrganizerTabs, type OrganizerTab } from '../../components/organizer-tabs';
import type { SettingsSection } from '../../components/settings-tab';
import { Card } from '../../components/shell';
import { useTheme } from '../../theme/styles';
import { useGroup } from './context';

export default function OrganizerScreen({
  tab,
  section,
  checkout,
}: {
  tab: OrganizerTab;
  /** The Settings section — the URL's last segment. */
  section?: SettingsSection;
  /** Stripe's `?checkout=` return value on the web. */
  checkout?: string | null;
}) {
  const { styles } = useTheme();
  const router = useRouter();
  const { groupId, group, readiness, readinessError, setGroup, reload } = useGroup();

  if (!group.is_organizer) {
    return (
      <Card>
        <Text style={styles.eyebrow}>Organizers only</Text>
        <Text style={[styles.heading, { marginTop: 4 }]}>This part is the organizer’s</Text>
        <Text style={[styles.smallMuted, { marginTop: 8 }]}>
          Only an organizer of this exchange can see who is ready, run the draw or change how it works.
        </Text>
      </Card>
    );
  }

  return (
    <OrganizerTabs
      tab={tab}
      group={group}
      readiness={readiness}
      readinessError={readinessError}
      checkout={checkout}
      section={section}
      onSectionChange={(next) => router.navigate(`/groups/${groupId}/settings/${next}`)}
      onGroupChanged={setGroup}
      onReload={reload}
    />
  );
}
