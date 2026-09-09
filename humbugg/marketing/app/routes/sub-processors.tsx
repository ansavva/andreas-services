import type { MetaFunction } from 'react-router';

import { canonicalUrl } from '../../src/config/site';

export { default } from '../../src/pages/SubProcessorsPage';

export const meta: MetaFunction = () => [
  { title: 'Sub-processors · Humbugg' },
  { name: 'description', content: 'The service providers Humbugg uses to process personal data, and how international transfers are protected.' },
  { name: 'robots', content: 'index, follow' },
  { tagName: 'link', rel: 'canonical', href: canonicalUrl('/sub-processors') },
];
