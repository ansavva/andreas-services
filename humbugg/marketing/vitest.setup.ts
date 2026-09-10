// Registers the jest-dom matchers (toBeVisible, toHaveAttribute, …) with Vitest's
// expect. This file existing is what turned the installed-but-unused Testing Library
// stack into a working one — the deps sat in package.json for months with no test
// environment to run in.
import '@testing-library/jest-dom/vitest';

// jsdom implements neither `matchMedia` nor a live-updating query object, and
// `<Shell>` (rendered by nearly every page test, not just Layout's own)
// reads `prefers-color-scheme` via `ThemeToggle`'s mount effect — so every
// suite in this project needs SOME implementation to avoid `window.matchMedia
// is not a function` on first render, not only the tests that care about it.
// Defaults to "light" (`matches: false`); `Layout.test.tsx` overrides this
// per test with `vi.stubGlobal` for the cases that care which way it goes.
if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

// This Vitest environment's `window` IS `globalThis` (Node's own, not a
// jsdom-created one), and Node ships its own `localStorage` global gated
// behind a CLI flag this project doesn't pass — so `window.localStorage` is
// `undefined` here, not merely empty. `theme.ts`'s reads/writes are
// try/catch-wrapped and tolerate that already (the same path Safari private
// mode takes), but a test that asserts what got written needs a real store
// to assert against. A minimal in-memory `Storage` is enough for that; it is
// not a jsdom bug to work around so much as this Node/Vitest combination
// never wiring one up.
if (typeof window !== 'undefined' && typeof window.localStorage === 'undefined') {
  class MemoryStorage {
    #store = new Map<string, string>();
    get length() {
      return this.#store.size;
    }
    clear = () => this.#store.clear();
    getItem = (key: string) => (this.#store.has(key) ? this.#store.get(key)! : null);
    key = (index: number) => Array.from(this.#store.keys())[index] ?? null;
    removeItem = (key: string) => void this.#store.delete(key);
    setItem = (key: string, value: string) => void this.#store.set(key, String(value));
  }
  Object.defineProperty(window, 'localStorage', {
    value: new MemoryStorage() as unknown as Storage,
    configurable: true,
  });
}
