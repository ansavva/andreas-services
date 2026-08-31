// Two browser APIs this jsdom does not provide, filled in for the whole suite.
//
// Neither is a polyfill the app ships or needs — both exist in every browser it
// runs in. They are here because a component test that touches them otherwise
// fails on the environment rather than on the component, and diagnosing that
// twice is once too often.
//
// * **`localStorage` is simply absent** under `environment: "jsdom"` here —
//   `window.localStorage` is `undefined`, not a throwing stub. `LibraryContext`
//   already tolerates that (private-mode Safari throws on the same calls), which
//   is exactly why the gap is worth closing in tests: without a store, "the
//   chosen library survives a reload" silently asserts nothing.
// * **`CSS.escape` is absent** and `@ansavva/design-system`'s `Select` calls it
//   unguarded when its listbox opens, so opening the library switcher throws
//   before the option list can be read.
// * **`IntersectionObserver` is absent**, and `useNearViewport` builds one to
//   decide whether a tile is close enough to be worth a request. It falls back
//   to "near" when the constructor is missing, so this stub is what makes a
//   test assert the real path rather than the fallback.
// * **`Element.scrollTo` is absent** — jsdom lays nothing out, so it implements
//   no scrolling. Nothing in the app calls it since the reel was replaced (the
//   filmstrip uses `scrollIntoView`, and guards for its absence), but the stub
//   costs one line and the next thing that scrolls will want it.

class MemoryStorage implements Storage {
  private items = new Map<string, string>();

  get length(): number {
    return this.items.size;
  }

  key(index: number): string | null {
    return [...this.items.keys()][index] ?? null;
  }

  getItem(key: string): string | null {
    return this.items.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.items.set(key, String(value));
  }

  removeItem(key: string): void {
    this.items.delete(key);
  }

  clear(): void {
    this.items.clear();
  }
}

if (!window.localStorage) {
  Object.defineProperty(window, "localStorage", { value: new MemoryStorage() });
}

if (typeof CSS === "undefined") {
  // Only the one function, and only enough of it for a selector built from a
  // node id or a library id. A real implementation is the CSSOM's job.
  Object.defineProperty(window, "CSS", {
    value: { escape: (value: string) => String(value).replace(/([^\w-])/g, "\\$1") },
  });
}

/**
 * A no-op `IntersectionObserver`.
 *
 * It observes nothing and reports nothing, which is the honest stub: jsdom lays
 * nothing out, so there is no intersection to compute and any callback it fired
 * would be fiction. A tile therefore never becomes "near" and never asks for
 * its bytes, which is what these tests want.
 */
if (typeof window.IntersectionObserver === "undefined") {
  class NoopObserver implements IntersectionObserver {
    readonly root = null;
    readonly rootMargin = "";
    readonly thresholds: readonly number[] = [];
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }
  Object.defineProperty(window, "IntersectionObserver", { value: NoopObserver, writable: true });
}

if (typeof Element.prototype.scrollTo !== "function") {
  // A no-op, because there is nothing to scroll.
  Element.prototype.scrollTo = () => {};
}
