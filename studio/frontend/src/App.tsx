import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Alert, Spinner } from "@ansavva/design-system";

import { isAuthConfigured } from "./amplify";
import { LoginForm } from "./components/auth/LoginForm";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { BrowsePage } from "./pages/BrowsePage";

function Gate() {
  const { authenticated, loading } = useAuth();

  if (!isAuthConfigured) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="max-w-md">
          <Alert.Root intent="warning">
            <Alert.Title>Auth is not configured</Alert.Title>
            <Alert.Description>
              Set VITE_COGNITO_USER_POOL_ID and VITE_COGNITO_CLIENT_ID (see .env.local.example).
            </Alert.Description>
          </Alert.Root>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <Spinner size="lg" label="Restoring your session" />
      </div>
    );
  }

  return authenticated ? <BrowsePage /> : <LoginForm />;
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Gate />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
