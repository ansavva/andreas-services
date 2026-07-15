import type { MetaFunction } from 'react-router';
import ProtectedRoute from '../../src/components/ProtectedRoute';
import GroupPage from '../../src/pages/GroupPage';

export const meta: MetaFunction = () => [
  { title: 'Exchange details · Humbugg' },
  { name: 'robots', content: 'noindex, nofollow' },
];

export default function GroupRoute() {
  return <ProtectedRoute><GroupPage /></ProtectedRoute>;
}
