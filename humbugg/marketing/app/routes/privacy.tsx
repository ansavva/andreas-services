import type { MetaFunction } from 'react-router';

import { canonicalUrl } from '../../src/config/site';

export { default } from '../../src/pages/PrivacyPage';

export const meta: MetaFunction = () => [
  { title: 'Privacy Policy · Humbugg' },
  { name: 'description', content: 'What information Humbugg collects, why, and the choices you have.' },
  { name: 'robots', content: 'index, follow' },
  { tagName: 'link', rel: 'canonical', href: canonicalUrl('/privacy') },
];
