import type { MetaFunction } from 'react-router';

import ogImageUrl from '../assets/og.png?url';

export { default } from '../../src/pages/LandingPage';

export const meta: MetaFunction = () => {
  const socialImage = new URL(ogImageUrl, 'https://humbugg.andreas.services/').href;
  return [
    { title: 'Humbugg · Secret Santa made simple' },
    {
      name: 'description',
      content: 'Create a Secret Santa group, collect wish lists, set thoughtful exclusions, and give every participant one private assignment.',
    },
    { name: 'robots', content: 'index, follow' },
    { property: 'og:type', content: 'website' },
    { property: 'og:site_name', content: 'Humbugg' },
    { property: 'og:title', content: 'Humbugg · Secret Santa made simple' },
    {
      property: 'og:description',
      content: 'A calmer way to organize a thoughtful Secret Santa exchange.',
    },
    { property: 'og:url', content: 'https://humbugg.andreas.services/' },
    { property: 'og:image', content: socialImage },
    { property: 'og:image:width', content: '1731' },
    { property: 'og:image:height', content: '909' },
    { property: 'og:image:alt', content: 'Humbugg — More wonder. Less wrangling.' },
    { name: 'twitter:card', content: 'summary_large_image' },
    { name: 'twitter:image', content: socialImage },
    { tagName: 'link', rel: 'canonical', href: 'https://humbugg.andreas.services/' },
  ];
};
