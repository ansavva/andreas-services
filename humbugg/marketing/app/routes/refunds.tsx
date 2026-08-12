import type { MetaFunction } from 'react-router';

import { canonicalUrl } from '../../src/config/site';

export { default } from '../../src/pages/RefundPage';

export const meta: MetaFunction = () => [
  { title: 'Refund Policy · Humbugg' },
  { name: 'description', content: 'When Humbugg refunds a payment, including full refunds before the draw.' },
  { name: 'robots', content: 'index, follow' },
  { tagName: 'link', rel: 'canonical', href: canonicalUrl('/refunds') },
];
