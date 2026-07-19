import type { MetaFunction } from 'react-router';
import ProtectedRoute from '../../src/components/ProtectedRoute';
import SettingsPage from '../../src/pages/SettingsPage';

export const meta: MetaFunction = () => [
  { title: 'Settings · Humbugg' },
  { name: 'robots', content: 'noindex, nofollow' },
];

export default function SettingsRoute() {
  return <ProtectedRoute><SettingsPage /></ProtectedRoute>;
}
