import type { MetaFunction } from 'react-router';

import { canonicalUrl } from '../../src/config/site';

export { default } from '../../src/pages/TermsPage';

export const meta: MetaFunction = () => [
  { title: 'Terms of Service · Humbugg' },
  { name: 'description', content: 'The terms that cover organizing and joining a Humbugg gift exchange.' },
  { name: 'robots', content: 'index, follow' },
  { tagName: 'link', rel: 'canonical', href: canonicalUrl('/terms') },
];
