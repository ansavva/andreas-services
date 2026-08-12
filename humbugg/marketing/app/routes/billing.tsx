import type { MetaFunction } from 'react-router';

import { canonicalUrl } from '../../src/config/site';

export { default } from '../../src/pages/BillingPage';

export const meta: MetaFunction = () => [
  { title: 'Billing Terms · Humbugg' },
  { name: 'description', content: 'How Humbugg plans are priced and charged, including the Work plan renewal.' },
  { name: 'robots', content: 'index, follow' },
  { tagName: 'link', rel: 'canonical', href: canonicalUrl('/billing') },
];
