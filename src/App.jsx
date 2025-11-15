import Timeline from './components/Timeline.jsx';
import { useLazyTimeline } from './hooks/useLazyTimeline.js';
import './styles/app.css';

function App() {
  const { visibleEvents, loadMorePast, loadMoreFuture, hasMorePast, hasMoreFuture, isLoading } =
    useLazyTimeline();

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Xronos</h1>
        <p className="app-tagline">A crafted timeline that adapts to the rhythm of history.</p>
      </header>
      <main className="app-content">
        <Timeline
          events={visibleEvents}
          onReachStart={hasMorePast ? loadMorePast : undefined}
          onReachEnd={hasMoreFuture ? loadMoreFuture : undefined}
          isLoading={isLoading}
        />
      </main>
    </div>
  );
}

export default App;
