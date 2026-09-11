// Which library the app is looking at.
//
// **Every request is scoped to one.** The API resolves a library before any
// route runs: it takes `X-Studio-Library` when the header is there, falls back
// to a sole membership when it is not, and refuses to guess for a caller who
// has two. So a client that never sends the header works perfectly until the
// day somebody is added to a second library, and then stops working entirely.
// This is what sends it.
//
// **The chosen id is held here and mirrored into `localStorage`.** Not into the
// URL: a studio URL names a node by id, and a node belongs to exactly one
// library, so the library is already implied by every address the app has.
// Putting it in the URL as well would create two answers that can disagree —
// a `/f/<id>` link with the wrong `?lib=`, which is a 403 that reads like a
// broken link. What `localStorage` buys is that a reload comes back where you
// were, which is the only thing the URL would have bought.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { setLibrary } from "../apis/client";
import { getLibraries } from "../apis/studio";
import type { Library } from "../types";

/** Where the chosen id survives a reload. */
export const STORAGE_KEY = "studio.library";

interface LibraryContextValue {
  libraries: Library[];
  /** `null` only while the list is still loading, or when it came back empty. */
  current: string | null;
  loading: boolean;
  error: string | null;
  select(id: string): void;
}

const LibraryContext = createContext<LibraryContextValue | null>(null);

/**
 * The library the app opens on, out of the ones the caller can reach.
 *
 * The stored id wins if it is still one of theirs — a membership can be revoked
 * between visits, and a header naming a library you are not in is a 403 on
 * every request rather than an empty listing. Otherwise the first, which is not
 * arbitrary: `GET /api/libraries` sorts by name, so "the first" is the top of
 * the switcher and visibly the one being shown.
 *
 * Choosing at all is the client's job, and deliberately not the API's. The
 * server refuses to guess because a guess there would silently write a node into
 * the wrong library; here the guess is visible, reversible and attached to a
 * control that says which one it landed on.
 */
function chooseLibrary(libraries: Library[], stored: string | null): string | null {
  if (stored && libraries.some((library) => library.id === stored)) return stored;
  return libraries[0]?.id ?? null;
}

function read(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private-mode Safari throws on `localStorage`. Losing the preference is a
    // worse app, not a broken one.
    return null;
  }
}

function write(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* see `read` */
  }
}

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLibraries()
      .then((result) => {
        if (cancelled) return;
        const chosen = chooseLibrary(result, read());
        // **Before the state update, not after.** Everything below this provider
        // fetches on mount, and the header has to be on those requests rather
        // than on the ones after the next render.
        setLibrary(chosen);
        setLibraries(result);
        setCurrent(chosen);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const select = useCallback((id: string) => {
    setLibrary(id);
    write(id);
    setCurrent(id);
  }, []);

  const value = useMemo<LibraryContextValue>(
    () => ({ libraries, current, loading, error, select }),
    [libraries, current, loading, error, select],
  );

  return <LibraryContext.Provider value={value}>{children}</LibraryContext.Provider>;
}

export function useLibrary(): LibraryContextValue {
  const ctx = useContext(LibraryContext);
  if (!ctx) throw new Error("useLibrary must be used inside <LibraryProvider>");
  return ctx;
}
