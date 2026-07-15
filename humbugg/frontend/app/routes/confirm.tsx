import type { MetaFunction } from 'react-router';
import AuthPage from '../../src/pages/AuthPage';

export const meta: MetaFunction = () => [
  { title: 'Confirm your email · Humbugg' },
  { name: 'robots', content: 'noindex, nofollow' },
];

export default function ConfirmRoute() { return <AuthPage mode="confirm" />; }
