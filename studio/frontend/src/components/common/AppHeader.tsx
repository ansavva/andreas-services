import { useNavigate } from "react-router-dom";

import { Button, Text } from "@ansavva/design-system";

import { useAuth } from "../../context/AuthContext";
import { HOME_PATH } from "../../utils/location";
import { LibrarySwitcher } from "./LibrarySwitcher";

/**
 * The one strip every screen carries: where you are in studio, and who you are.
 *
 * It exists because there are seven screens now rather than one. The browse page
 * used to own this markup outright, which was fine while it *was* the app; a
 * character page and a run page repeating it would be three copies of a sign-out
 * button that have to agree about what sign-out does.
 *
 * The title is a link home rather than a heading, and that is the only thing
 * here that changed in behaviour: home is the entity index now, so there is
 * somewhere above a character page to go.
 */
export function AppHeader({ subtitle }: { subtitle?: string }) {
  const navigate = useNavigate();
  const { email, logout } = useAuth();

  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <button
        type="button"
        onClick={() => navigate(HOME_PATH)}
        className="min-w-0 rounded-md text-left focus-visible:outline-2 focus-visible:outline-offset-2
                   focus-visible:outline-primary"
      >
        <Text variant="display">Studio</Text>
        <Text variant="caption" tone="muted" className="truncate">
          {subtitle ?? "media library"}
        </Text>
      </button>

      <div className="flex items-center gap-2">
        {/* A sibling of the sign-out button, never inside a listing row: every
            card and row in this app is itself a `<button>`, and the switcher
            renders one. See `LibrarySwitcher`. */}
        <LibrarySwitcher />
        {email && (
          <Text variant="caption" tone="muted" className="hidden sm:block">
            {email}
          </Text>
        )}
        {/* No `navigate` afterwards: sign-out leaves for the hosted `/logout`,
            which ends the Cognito session and returns to `/` itself. Routing
            in this tab first would only race that navigation. */}
        <Button
          intent="ghost"
          size="sm"
          onClick={() => {
            void logout();
          }}
        >
          Sign out
        </Button>
      </div>
    </header>
  );
}
