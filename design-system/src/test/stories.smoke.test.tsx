/// <reference types="vite/client" />
import { composeStories } from '@storybook/react';
import { cleanup, render } from '@testing-library/react';
import * as React from 'react';
import { afterEach, describe, expect, it } from 'vitest';

/**
 * Renders every exported story to catch runtime render failures — e.g. a
 * component part used outside a required context provider. `build-storybook`
 * only bundles stories, it doesn't execute their render, so it can't catch
 * this class of bug; this test does.
 */
const storyModules = import.meta.glob('../components/**/*.stories.tsx', { eager: true });

afterEach(cleanup);

describe('stories render without throwing', () => {
  for (const [path, mod] of Object.entries(storyModules)) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const composed = composeStories(mod as any);
    for (const [name, Story] of Object.entries(composed) as [string, React.ComponentType][]) {
      it(`${path.replace('../components/', '')} › ${name}`, () => {
        expect(() => render(<Story />)).not.toThrow();
      });
    }
  }
});
