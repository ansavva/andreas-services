import type { MetaFunction } from 'react-router';
import AuthPage from '../../src/pages/AuthPage';
import { canonicalUrl } from '../../src/config/site';

export const meta: MetaFunction = () => [
  { title: 'Create an account · Humbugg' },
  { name: 'description', content: 'Create a free Humbugg account and start your Secret Santa exchange.' },
  { name: 'robots', content: 'index, follow' },
  { tagName: 'link', rel: 'canonical', href: canonicalUrl('/signup') },
];

export default function SignupRoute() { return <AuthPage mode="signup" />; }
