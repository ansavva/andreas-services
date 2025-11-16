import { useEffect, useMemo, useRef } from 'react';
import PropTypes from 'prop-types';
import TimelineEvent from './TimelineEvent.jsx';

const BASE_SPACING = 48;
const MAX_SPACING = 220;
const TIME_COMPRESSION = 90;
const SIGNIFICANT_DAY_GAP = 90;

const DAY_IN_MS = 1000 * 60 * 60 * 24;

function formatGapLabel(diffInDays) {
  if (diffInDays < SIGNIFICANT_DAY_GAP) {
    return undefined;
  }

  if (diffInDays >= 365) {
    const years = Math.max(1, Math.round(diffInDays / 365));
    return `${years} year${years === 1 ? '' : 's'} later`;
  }

  const months = Math.max(1, Math.round(diffInDays / 30));
  return `${months} month${months === 1 ? '' : 's'} later`;
}

function computeTemporalContext(previousDate, currentDate) {
  if (!previousDate) {
    return {
      spacing: MAX_SPACING / 2,
      gapLabel: undefined
    };
  }

  const diffInDays = Math.abs(currentDate - previousDate) / DAY_IN_MS;
  const stretched = Math.log1p(diffInDays) * TIME_COMPRESSION;
  const spacing = Math.min(MAX_SPACING, BASE_SPACING + stretched);

  return {
    spacing,
    gapLabel: formatGapLabel(diffInDays)
  };
}

function Timeline({ events, onReachStart, onReachEnd, isLoading, onEdit }) {
  const startSentinelRef = useRef(null);
  const endSentinelRef = useRef(null);

  const sentinelOptions = useMemo(
    () => ({
      root: null,
      rootMargin: '0px',
      threshold: 0.1
    }),
    []
  );

  useEffect(() => {
    if (!onReachStart || !startSentinelRef.current || typeof IntersectionObserver === 'undefined') {
      return undefined;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          onReachStart();
        }
      });
    }, sentinelOptions);

    observer.observe(startSentinelRef.current);

    return () => observer.disconnect();
  }, [onReachStart, sentinelOptions]);

  useEffect(() => {
    if (!onReachEnd || !endSentinelRef.current || typeof IntersectionObserver === 'undefined') {
      return undefined;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          onReachEnd();
        }
      });
    }, sentinelOptions);

    observer.observe(endSentinelRef.current);

    return () => observer.disconnect();
  }, [onReachEnd, sentinelOptions]);

  const decoratedEvents = useMemo(() => {
    return events.map((event, index) => {
      const previous = events[index - 1];
      const previousDate = previous ? new Date(previous.date) : undefined;
      const currentDate = new Date(event.date);
      const { spacing, gapLabel } = computeTemporalContext(previousDate, currentDate);
      return {
        ...event,
        spacing,
        gapLabel
      };
    });
  }, [events]);

  return (
    <section className="relative" aria-label="Historical timeline">
      <div ref={startSentinelRef} className="h-px" aria-hidden="true" />
      <ol className="relative border-l border-timeline-line/60 pl-8 sm:pl-12">
        {decoratedEvents.map((event) => (
          <TimelineEvent key={event.id} event={event} onEdit={onEdit} />
        ))}
      </ol>
      {isLoading ? (
        <div className="mt-10 flex items-center gap-3 text-sm text-slate-400" role="status" aria-live="polite">
          <span className="h-2 w-2 animate-ping rounded-full bg-sky-400" aria-hidden="true" />
          Loading events…
        </div>
      ) : null}
      <div ref={endSentinelRef} className="h-px" aria-hidden="true" />
    </section>
  );
}

Timeline.propTypes = {
  events: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      date: PropTypes.string.isRequired,
      title: PropTypes.string.isRequired,
      description: PropTypes.string.isRequired
    })
  ).isRequired,
  onReachStart: PropTypes.func,
  onReachEnd: PropTypes.func,
  isLoading: PropTypes.bool,
  onEdit: PropTypes.func
};

Timeline.defaultProps = {
  onReachStart: undefined,
  onReachEnd: undefined,
  isLoading: false,
  onEdit: undefined
};

export default Timeline;
