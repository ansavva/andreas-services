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
  const [events, setEvents] = useState(sortedEvents);
  const [range, setRange] = useState({ start: initialStart, end: initialEnd });
  const [isLoading, setIsLoading] = useState(false);
  const pendingTimer = useRef();

  useEffect(() => () => clearTimeout(pendingTimer.current), []);

  const visibleEvents = useMemo(() => events.slice(range.start, range.end), [events, range]);

  const hasMorePast = range.start > 0;
  const hasMoreFuture = range.end < events.length;
  const totalEvents = events.length;

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
      end: Math.min(totalEvents, current.end + PAGE_SIZE)
    }));
  }, [hasMoreFuture, isLoading, scheduleUpdate, totalEvents]);

  const addEvent = useCallback((event) => {
    setEvents((currentEvents) => {
      const nextEvents = [...currentEvents, event].sort(
        (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
      );

      setRange((currentRange) => {
        const rangeSize = Math.max(1, currentRange.end - currentRange.start);
        const newIndex = nextEvents.findIndex((item) => item.id === event.id);

        if (newIndex < 0) {
          return currentRange;
        }

        if (newIndex < currentRange.start) {
          const newStart = newIndex;
          return {
            start: newStart,
            end: Math.min(newStart + rangeSize, nextEvents.length)
          };
        }

        if (newIndex >= currentRange.end) {
          const newEnd = Math.min(nextEvents.length, newIndex + 1);
          const newStart = Math.max(0, newEnd - rangeSize);
          return {
            start: newStart,
            end: newEnd
          };
        }

        return {
          start: currentRange.start,
          end: Math.min(currentRange.start + rangeSize, nextEvents.length)
        };
      });

      return nextEvents;
    });
  }, []);

  return {
    visibleEvents,
    loadMorePast,
    loadMoreFuture,
    hasMorePast,
    hasMoreFuture,
    isLoading,
    addEvent
  };
}
