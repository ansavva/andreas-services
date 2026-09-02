import { Link } from "react-router-dom";
import { Button, Text } from "@ansavva/design-system";

import { useAuth } from "../context/AuthContext";

export function Header() {
  const { signedIn, email, signOut } = useAuth();

  return (
    <header className="border-line bg-surface border-b">
      <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-4 py-3">
        <Link to="/" className="no-underline">
          <Text variant="title" family="heading">
            Classroom
          </Text>
        </Link>
        {signedIn && (
          <div className="flex items-center gap-3">
            {email && (
              <Text variant="caption" tone="muted">
                {email}
              </Text>
            )}
            <Button intent="ghost" size="sm" onClick={signOut}>
              Sign out
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}
