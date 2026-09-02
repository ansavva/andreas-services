import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { Spinner } from "@ansavva/design-system";

import { useAuth } from "../context/AuthContext";

/**
 * Bounces an unauthenticated visitor to Cognito's hosted page, remembering
 * where they were headed so the callback can put them back.
 */
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { signedIn, signIn } = useAuth();
  const location = useLocation();

  useEffect(() => {
    if (!signedIn) signIn(location.pathname + location.search);
  }, [signedIn, signIn, location]);

  if (!signedIn) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }
  return <>{children}</>;
}
