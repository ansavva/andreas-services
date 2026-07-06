import * as React from 'react';

import './preview.css';

import type { Preview } from '@storybook/react';

const preview: Preview = {
  parameters: {
    controls: { expanded: true },
  },
  globalTypes: {
    theme: {
      description: 'Theme',
      toolbar: {
        title: 'Theme',
        icon: 'mirror',
        items: [
          { value: 'light', title: 'Light' },
          { value: 'dark', title: 'Dark' },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: {
    theme: 'light',
  },
  decorators: [
    (Story, context) => {
      const theme = context.globals.theme ?? 'light';

      return React.createElement(
        'div',
        { 'data-theme': theme, className: 'bg-bg text-ink min-h-screen p-8 transition-colors' },
        React.createElement(Story),
      );
    },
  ],
};

export default preview;
