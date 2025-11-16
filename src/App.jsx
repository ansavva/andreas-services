import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faPlus, faSearch, faTimes, faCircleNotch, faCalendarDay } from '@fortawesome/free-solid-svg-icons';
import EventModal from './components/EventModal.jsx';
import DatePickerField from './components/DatePickerField.jsx';
import Timeline from './components/Timeline.jsx';
import { useLazyTimeline } from './hooks/useLazyTimeline.js';

function App() {
  const {
    events,
    loadMorePast,
    loadMoreFuture,
    hasMorePast,
    hasMoreFuture,
    isLoading,
    error,
    addEvent,
    editEvent,
    removeEvent,
    jumpToDate,
    jumpToEvent,
    searchResults,
    searchEvents,
    isSearching,
    searchError
  } = useLazyTimeline();

  const [modalState, setModalState] = useState({ mode: null, event: null });
  const [modalError, setModalError] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [jumpError, setJumpError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const searchDebounceRef = useRef(null);

  const handleOpenCreate = useCallback(() => {
    setModalError('');
    setModalState({ mode: 'create', event: null });
  }, []);

  const handleOpenEdit = useCallback((event) => {
    setModalError('');
    setModalState({ mode: 'edit', event });
  }, []);

  const closeModal = useCallback(() => {
    setModalState({ mode: null, event: null });
    setModalError('');
    setIsSaving(false);
  }, []);

  const handleSubmit = useCallback(
    async (payload) => {
      if (!modalState.mode) {
        return;
      }
      setIsSaving(true);
      setModalError('');
      try {
        if (modalState.mode === 'create') {
          await addEvent(payload);
        } else if (modalState.mode === 'edit' && modalState.event) {
          await editEvent(modalState.event.id, payload);
        }
        closeModal();
      } catch (submitError) {
        setModalError(submitError.message || 'Unable to save event.');
        setIsSaving(false);
      }
    },
    [addEvent, closeModal, editEvent, modalState]
  );

  const handleDelete = useCallback(async () => {
    if (!modalState.event) {
      return;
    }
    const shouldDelete = window.confirm('Are you sure you want to delete this event? This action cannot be undone.');
    if (!shouldDelete) {
      return;
    }

    setIsSaving(true);
    setModalError('');
    try {
      await removeEvent(modalState.event.id);
      closeModal();
    } catch (deleteError) {
      setModalError(deleteError.message || 'Unable to delete event.');
      setIsSaving(false);
    }
  }, [closeModal, modalState.event, removeEvent]);

  const handleJumpToDate = useCallback(
    async (date) => {
      if (!date) {
        return;
      }
      setJumpError('');
      try {
        await jumpToDate(date);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (jumpErr) {
        setJumpError(jumpErr.message || 'Unable to jump to date.');
      }
    },
    [jumpToDate]
  );

  const handleSearchSelect = useCallback(
    async (eventId) => {
      if (!eventId) {
        return;
      }
      setJumpError('');
      try {
        await jumpToEvent(eventId);
        setSearchTerm('');
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (jumpErr) {
        setJumpError(jumpErr.message || 'Unable to jump to event.');
      }
    },
    [jumpToEvent]
  );

  useEffect(() => {
    if (searchDebounceRef.current) {
      clearTimeout(searchDebounceRef.current);
    }

    searchDebounceRef.current = setTimeout(() => {
      searchEvents(searchTerm).catch(() => {});
    }, 250);

    return () => {
      if (searchDebounceRef.current) {
        clearTimeout(searchDebounceRef.current);
      }
    };
  }, [searchEvents, searchTerm]);

  const modalInitialValues = useMemo(() => {
    if (modalState.mode === 'edit' && modalState.event) {
      return {
        title: modalState.event.title,
        date: modalState.event.date,
        description: modalState.event.description
      };
    }
    return { title: '', date: '', description: '' };
  }, [modalState]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-12 sm:px-6 lg:px-8">
        <header className="mb-12 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex flex-col gap-3">
            <p className="text-sm font-semibold uppercase tracking-[0.35em] text-slate-500">Project Xronos</p>
            <h1 className="text-4xl font-semibold tracking-tight text-slate-50 sm:text-5xl">
              A timeline for expansive histories
            </h1>
            <p className="max-w-3xl text-base text-slate-400 sm:text-lg">
              Explore moments in time without losing the sense of distance between them. Scroll to travel further and we&apos;ll
              reveal additional chapters as you go.
            </p>
          </div>
          <div className="flex flex-col gap-4 sm:w-80">
            <div className="relative">
              <label className="sr-only" htmlFor="timeline-search">
                Search events
              </label>
              <div className="relative">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-500">
                  <FontAwesomeIcon icon={faSearch} />
                </div>
                <input
                  id="timeline-search"
                  type="search"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Search timeline"
                  className="w-full rounded-2xl border border-slate-700 bg-slate-950/60 py-3 pl-10 pr-10 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-400/60"
                />
                {searchTerm ? (
                  <button
                    type="button"
                    onClick={() => setSearchTerm('')}
                    className="absolute inset-y-0 right-3 flex items-center text-slate-500 transition hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
                    aria-label="Clear search"
                  >
                    <FontAwesomeIcon icon={faTimes} />
                  </button>
                ) : null}
              </div>
              {searchError ? <p className="mt-2 text-sm text-rose-400">{searchError}</p> : null}
              {isSearching ? (
                <p className="mt-2 flex items-center gap-2 text-xs text-slate-400">
                  <FontAwesomeIcon icon={faCircleNotch} spin /> Searching…
                </p>
              ) : null}
              {searchTerm.trim() && searchResults.length === 0 && !isSearching && !searchError ? (
                <p className="mt-2 text-xs text-slate-500">No matches found.</p>
              ) : null}
              {searchResults.length ? (
                <ul className="absolute z-10 mt-2 max-h-80 w-full overflow-y-auto rounded-2xl border border-slate-800/70 bg-slate-900/90 p-2 shadow-xl ring-1 ring-slate-800/70 backdrop-blur">
                  {searchResults.map((result) => (
                    <li key={result.id}>
                      <button
                        type="button"
                        onClick={() => handleSearchSelect(result.id)}
                        className="flex w-full flex-col gap-1 rounded-xl px-3 py-2 text-left text-sm text-slate-100 transition hover:bg-slate-800/70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
                      >
                        <span className="flex items-center justify-between gap-2 text-xs uppercase tracking-[0.2em] text-sky-300">
                          <span className="inline-flex items-center gap-2">
                            <FontAwesomeIcon icon={faCalendarDay} />
                            {result.date}
                          </span>
                        </span>
                        <span className="font-semibold text-slate-50">{result.title}</span>
                        <span className="line-clamp-2 text-xs text-slate-400">{result.description}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <DatePickerField
              label="Jump to date"
              onChange={handleJumpToDate}
              buttonClassName="text-sm"
              align="right"
            />
            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={handleOpenCreate}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-sky-500/40 bg-sky-500/10 px-5 py-2 text-sm font-semibold text-sky-200 shadow-glow transition hover:border-sky-400 hover:bg-sky-500/20 hover:text-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
              >
                <FontAwesomeIcon icon={faPlus} />
                Create event
              </button>
            </div>
          </div>
        </header>
        <main className="flex-1">
          {error || jumpError ? (
            <div className="rounded-3xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-100">
              {error || jumpError}
            </div>
          ) : null}
          <Timeline
            events={events}
            onReachStart={hasMorePast ? loadMorePast : undefined}
            onReachEnd={hasMoreFuture ? loadMoreFuture : undefined}
            isLoading={isLoading}
            onEdit={handleOpenEdit}
          />
        </main>
      </div>
      <EventModal
        isOpen={Boolean(modalState.mode)}
        mode={modalState.mode ?? 'create'}
        initialValues={modalInitialValues}
        isProcessing={isSaving}
        error={modalError}
        onClose={closeModal}
        onSubmit={handleSubmit}
        onDelete={modalState.mode === 'edit' ? handleDelete : undefined}
      />
    </div>
  );
}

export default App;
