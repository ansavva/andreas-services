import { Disclosure, Transition } from '@headlessui/react';
import PropTypes from 'prop-types';
import { Fragment } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronDown, faPenToSquare } from '@fortawesome/free-solid-svg-icons';

function formatDateLabel(date) {
  return new Intl.DateTimeFormat('en', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  }).format(new Date(date));
}

function TimelineEvent({ event, onEdit }) {
  const handleEditClick = () => {
    if (onEdit) {
      onEdit(event);
    }
  };

  return (
    <li
      className="relative -ml-[1px] flex flex-col gap-2 pb-12 pl-8 sm:pl-12"
      style={{ marginTop: `${event.spacing}px` }}
    >
      <span className="absolute left-[-11px] top-2 flex h-5 w-5 items-center justify-center rounded-full border border-sky-500/40 bg-slate-950 shadow-glow">
        <span className="h-2 w-2 rounded-full bg-sky-400" aria-hidden="true" />
      </span>
      <div className="relative flex max-w-3xl flex-col gap-2 rounded-3xl border border-slate-800/60 bg-slate-900/60 p-5 shadow-lg ring-1 ring-slate-800/60 backdrop-blur">
        {event.gapLabel ? (
          <p className="text-xs font-medium uppercase tracking-[0.3em] text-slate-500">{event.gapLabel}</p>
        ) : null}
        <Disclosure>
          {({ open }) => (
            <>
              <div className="flex w-full items-start justify-between gap-4 text-left">
                <Disclosure.Button className="flex flex-1 items-start gap-4 text-left">
                  <div className="flex flex-col gap-1">
                    <time className="text-xs font-semibold uppercase tracking-[0.25em] text-sky-300" dateTime={event.date}>
                      {formatDateLabel(event.date)}
                    </time>
                    <h2 className="text-xl font-semibold text-slate-50">{event.title}</h2>
                  </div>
                  <FontAwesomeIcon
                    icon={faChevronDown}
                    className={`h-5 w-5 shrink-0 text-slate-400 transition-transform duration-200 ${open ? 'rotate-180 text-sky-300' : ''}`}
                  />
                </Disclosure.Button>
                <button
                  type="button"
                  onClick={handleEditClick}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-300 transition hover:border-sky-400 hover:text-sky-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
                >
                  <FontAwesomeIcon icon={faPenToSquare} />
                  Edit
                </button>
              </div>
              <Transition
                as={Fragment}
                enter="transition duration-150 ease-out"
                enterFrom="transform scale-95 opacity-0"
                enterTo="transform scale-100 opacity-100"
                leave="transition duration-100 ease-in"
                leaveFrom="transform scale-100 opacity-100"
                leaveTo="transform scale-95 opacity-0"
              >
                <Disclosure.Panel className="mt-3 text-base leading-relaxed text-slate-300">
                  {event.description}
                </Disclosure.Panel>
              </Transition>
            </>
          )}
        </Disclosure>
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
  }).isRequired,
  onEdit: PropTypes.func
};

TimelineEvent.defaultProps = {
  onEdit: undefined
};

export default TimelineEvent;
