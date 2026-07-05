import tailwindcss from '@tailwindcss/vite';

import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-essentials'],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  async viteFinal(viteConfig) {
    const { mergeConfig } = await import('vite');

    return mergeConfig(viteConfig, {
      plugins: [tailwindcss()],
    });
  },
};

export default config;
