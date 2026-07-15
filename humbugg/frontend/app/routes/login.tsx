import type { MetaFunction } from 'react-router';
import AuthPage from '../../src/pages/AuthPage';

export const meta: MetaFunction = () => [
  { title: 'Sign in · Humbugg' },
  { name: 'robots', content: 'noindex, nofollow' },
];

export default function LoginRoute() { return <AuthPage mode="login" />; }
