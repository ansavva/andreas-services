import type { MetaFunction } from 'react-router';
import AuthPage from '../../src/pages/AuthPage';

export const meta: MetaFunction = () => [
  { title: 'Reset your password · Humbugg' },
  { name: 'robots', content: 'noindex, nofollow' },
];

export default function ForgotPasswordRoute() { return <AuthPage mode="forgot" />; }
