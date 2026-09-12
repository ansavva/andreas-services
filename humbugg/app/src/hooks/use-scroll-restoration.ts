// Where you were on the page, kept per URL (#690).
//
// The app scrolls inside one React Native `ScrollView`, not the document, so the browser's own
// scroll restoration never sees it: a reload, or a tab change and back, always landed at the top.
// This keeps the offset per pathname in the session store — `sessionStorage` on the web, so a
// reload survives; a module map on a device, which is the lifetime that matters there.
//
// Restoring has to wait for the page to be tall enough: the screen mounts as a spinner, and the
// content that makes the saved offset reachable arrives a request later. So the offset is held as
// `pending` and applied on every content-size change until it fits. A scroll the person makes
// before then abandons the restore — their thumb wins over a position from last time.
import { useCallback, useEffect, useRef } from 'react';
import type { LayoutChangeEvent, NativeScrollEvent, NativeSyntheticEvent, ScrollView } from 'react-native';

import { sessionKeys, sessionStore } from '../utils/session-store';

export function useScrollRestoration(key: string) {
  const ref = useRef<ScrollView>(null);
  const pending = useRef<number | null>(null);
  const content = useRef(0);
  const viewport = useRef(0);

  const tryRestore = useCallback(() => {
    const target = pending.current;
    if (target === null) return;
    if (target > 0 && content.current - viewport.current < target) return;
    ref.current?.scrollTo({ y: target, animated: false });
    pending.current = null;
  }, []);

  useEffect(() => {
    const saved = Number(sessionStore.get(sessionKeys.scroll(key)) ?? 0);
    pending.current = Number.isFinite(saved) && saved > 0 ? saved : 0;
    tryRestore();
  }, [key, tryRestore]);

  const onScroll = useCallback(
    (event: NativeSyntheticEvent<NativeScrollEvent>) => {
      const y = Math.max(0, Math.round(event.nativeEvent.contentOffset.y));
      // A scroll while a restore is still waiting is the person's, not ours: stop waiting.
      pending.current = null;
      sessionStore.set(sessionKeys.scroll(key), String(y));
    },
    [key],
  );

  const onContentSizeChange = useCallback(
    (_width: number, height: number) => {
      content.current = height;
      tryRestore();
    },
    [tryRestore],
  );

  const onLayout = useCallback(
    (event: LayoutChangeEvent) => {
      viewport.current = event.nativeEvent.layout.height;
      tryRestore();
    },
    [tryRestore],
  );

  return { ref, onScroll, onContentSizeChange, onLayout };
}
