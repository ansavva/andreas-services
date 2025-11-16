import { useCallback, useMemo, useState } from 'react';
import EventModal from './components/EventModal.jsx';
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
    removeEvent
  } = useLazyTimeline();

  const [modalState, setModalState] = useState({ mode: null, event: null });
  const [modalError, setModalError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

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
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleOpenCreate}
              className="inline-flex items-center justify-center rounded-full border border-sky-500/40 bg-sky-500/10 px-5 py-2 text-sm font-semibold text-sky-200 shadow-glow transition hover:border-sky-400 hover:bg-sky-500/20 hover:text-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
            >
              Create event
            </button>
          </div>
        </header>
        <main className="flex-1">
          {error ? (
            <div className="rounded-3xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-100">
              {error}
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
