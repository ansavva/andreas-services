import type { MetaFunction } from 'react-router';
import ProtectedRoute from '../../src/components/ProtectedRoute';
import DashboardPage from '../../src/pages/DashboardPage';

export const meta: MetaFunction = () => [
  { title: 'My groups · Humbugg' },
  { name: 'robots', content: 'noindex, nofollow' },
];

export default function DashboardRoute() {
  return <ProtectedRoute><DashboardPage /></ProtectedRoute>;
}
