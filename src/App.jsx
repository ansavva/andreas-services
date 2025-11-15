import { useCallback, useState } from 'react';
import CreateEventModal from './components/CreateEventModal.jsx';
import Timeline from './components/Timeline.jsx';
import { useLazyTimeline } from './hooks/useLazyTimeline.js';

function App() {
  const { visibleEvents, loadMorePast, loadMoreFuture, hasMorePast, hasMoreFuture, isLoading, addEvent } =
    useLazyTimeline();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleCreateEvent = useCallback(
    (event) => {
      addEvent(event);
      setIsModalOpen(false);
    },
    [addEvent]
  );

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
              Explore moments in time without losing the sense of distance between them. Scroll to travel
              further and we&apos;ll reveal additional chapters as you go.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIsModalOpen(true)}
              className="inline-flex items-center justify-center rounded-full border border-sky-500/40 bg-sky-500/10 px-5 py-2 text-sm font-semibold text-sky-200 shadow-glow transition hover:border-sky-400 hover:bg-sky-500/20 hover:text-sky-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
            >
              Create event
            </button>
          </div>
        </header>
        <main className="flex-1">
          <Timeline
            events={visibleEvents}
            onReachStart={hasMorePast ? loadMorePast : undefined}
            onReachEnd={hasMoreFuture ? loadMoreFuture : undefined}
            isLoading={isLoading}
          />
        </main>
      </div>
      <CreateEventModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreate={handleCreateEvent}
      />
    </div>
  );
}

export default App;
