// The scroll offset comes back per URL, and only once the page is tall enough to hold it.
import { act, renderHook } from '@testing-library/react-native';
import type { ScrollView } from 'react-native';

import { sessionKeys, sessionStore } from '../utils/session-store';
import { useScrollRestoration } from './use-scroll-restoration';

function attach(result: { current: ReturnType<typeof useScrollRestoration> }) {
  const scrollTo = jest.fn();
  (result.current.ref as { current: unknown }).current = { scrollTo } as unknown as ScrollView;
  return scrollTo;
}

const scrolled = (y: number) => ({ nativeEvent: { contentOffset: { y } } }) as never;
const laidOut = (height: number) => ({ nativeEvent: { layout: { height } } }) as never;

beforeEach(() => {
  sessionStore.remove(sessionKeys.scroll('/a'));
  sessionStore.remove(sessionKeys.scroll('/b'));
});

it('waits for the content to reach the saved offset, then puts it back once', () => {
  sessionStore.set(sessionKeys.scroll('/a'), '900');
  const { result } = renderHook(() => useScrollRestoration('/a'));
  const scrollTo = attach(result);

  // A spinner-tall page cannot hold 900px yet.
  act(() => { result.current.onLayout(laidOut(700)); result.current.onContentSizeChange(0, 800); });
  expect(scrollTo).not.toHaveBeenCalled();

  act(() => result.current.onContentSizeChange(0, 2400));
  expect(scrollTo).toHaveBeenCalledWith({ y: 900, animated: false });

  act(() => result.current.onContentSizeChange(0, 2600));
  expect(scrollTo).toHaveBeenCalledTimes(1);
});

it('records where the person scrolled to, per key', () => {
  const { result, rerender } = renderHook(({ key }: { key: string }) => useScrollRestoration(key), { initialProps: { key: '/a' } });
  attach(result);

  act(() => result.current.onScroll(scrolled(412.6)));
  expect(sessionStore.get(sessionKeys.scroll('/a'))).toBe('413');

  rerender({ key: '/b' });
  act(() => result.current.onScroll(scrolled(50)));
  expect(sessionStore.get(sessionKeys.scroll('/b'))).toBe('50');
  expect(sessionStore.get(sessionKeys.scroll('/a'))).toBe('413');
});

it('goes to the top of a page it has no record of, and lets a scroll cancel a pending restore', () => {
  sessionStore.set(sessionKeys.scroll('/a'), '900');
  const { result, rerender } = renderHook(({ key }: { key: string }) => useScrollRestoration(key), { initialProps: { key: '/c' } });
  const scrollTo = attach(result);
  rerender({ key: '/b' });
  expect(scrollTo).toHaveBeenCalledWith({ y: 0, animated: false });

  rerender({ key: '/a' });
  act(() => { result.current.onLayout(laidOut(700)); result.current.onContentSizeChange(0, 800); });
  // The person moves before the page is tall enough: their position wins.
  act(() => result.current.onScroll(scrolled(120)));
  act(() => result.current.onContentSizeChange(0, 2400));
  expect(scrollTo).toHaveBeenCalledTimes(1);
  expect(sessionStore.get(sessionKeys.scroll('/a'))).toBe('120');
});
