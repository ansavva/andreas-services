import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPanel from './components/LoginPanel';
import Dashboard from './components/Dashboard';

function AppContent() {
  const auth = useAuth();

  if (!auth.token) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-16">
        <LoginPanel />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 px-4 py-10">
      <div className="mx-auto max-w-6xl space-y-6">
        <Dashboard />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
