import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { timelineEvents } from '../data/events.js';

const PAGE_SIZE = 8;
const LOAD_DELAY = 350;

const sortedEvents = [...timelineEvents].sort(
  (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
);

const middleIndex = Math.floor(sortedEvents.length / 2);
const initialStart = Math.max(0, middleIndex - Math.floor(PAGE_SIZE / 2));
const initialEnd = Math.min(sortedEvents.length, initialStart + PAGE_SIZE);

export function useLazyTimeline() {
  const [range, setRange] = useState({ start: initialStart, end: initialEnd });
  const [isLoading, setIsLoading] = useState(false);
  const pendingTimer = useRef();

  useEffect(() => () => clearTimeout(pendingTimer.current), []);

  const visibleEvents = useMemo(() => sortedEvents.slice(range.start, range.end), [range]);

  const hasMorePast = range.start > 0;
  const hasMoreFuture = range.end < sortedEvents.length;

  const scheduleUpdate = useCallback((updater) => {
    clearTimeout(pendingTimer.current);
    setIsLoading(true);
    pendingTimer.current = setTimeout(() => {
      setRange((current) => updater(current));
      setIsLoading(false);
    }, LOAD_DELAY);
  }, []);

  const loadMorePast = useCallback(() => {
    if (!hasMorePast || isLoading) return;
    scheduleUpdate((current) => ({
      start: Math.max(0, current.start - PAGE_SIZE),
      end: current.end
    }));
  }, [hasMorePast, isLoading, scheduleUpdate]);

  const loadMoreFuture = useCallback(() => {
    if (!hasMoreFuture || isLoading) return;
    scheduleUpdate((current) => ({
      start: current.start,
      end: Math.min(sortedEvents.length, current.end + PAGE_SIZE)
    }));
  }, [hasMoreFuture, isLoading, scheduleUpdate]);

  return {
    visibleEvents,
    loadMorePast,
    loadMoreFuture,
    hasMorePast,
    hasMoreFuture,
    isLoading
  };
}
