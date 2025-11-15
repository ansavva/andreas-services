import PropTypes from 'prop-types';

function formatDateLabel(date) {
  return new Intl.DateTimeFormat('en', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  }).format(new Date(date));
}

function TimelineEvent({ event }) {
  return (
    <li className="timeline-event" style={{ marginTop: `${event.spacing}px` }}>
      <div className="timeline-event__marker" aria-hidden="true" />
      <div className="timeline-event__content">
        {event.gapLabel ? <p className="timeline-event__gap">{event.gapLabel}</p> : null}
        <time className="timeline-event__date" dateTime={event.date}>
          {formatDateLabel(event.date)}
        </time>
        <h2 className="timeline-event__title">{event.title}</h2>
        <p className="timeline-event__description">{event.description}</p>
      </div>
    </li>
  );
}

TimelineEvent.propTypes = {
  event: PropTypes.shape({
    id: PropTypes.string.isRequired,
    date: PropTypes.string.isRequired,
    title: PropTypes.string.isRequired,
    description: PropTypes.string.isRequired,
    spacing: PropTypes.number.isRequired,
    gapLabel: PropTypes.string
  }).isRequired
};

export default TimelineEvent;
