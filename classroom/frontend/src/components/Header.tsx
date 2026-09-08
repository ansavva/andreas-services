import { Link } from "react-router-dom";
import { Avatar, Dropdown, Text } from "@ansavva/design-system";

import { useAuth } from "../context/AuthContext";

/**
 * Initials for the circle.
 *
 * The pool stores an email and no name, so that is what there is to work with.
 * `anita.brown@school.test` gives "AB"; `teacher@classroom.test` gives "T".
 * Deliberately never more than two letters — three stops fitting the circle at
 * this size.
 */
function initialsFor(email: string): string {
  const [local = ""] = email.split("@");
  const parts = local.split(/[._-]+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((part) => part[0] ?? "");
  return (letters.join("") || local[0] || "?").toUpperCase();
}

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
          // The address and sign-out live behind the circle rather than beside
          // it. Sign out is the one irreversible control in the header and it
          // was sitting one stray click from "New page"; the address is
          // reassurance a teacher wants occasionally, not a permanent fixture.
          <Dropdown.Root>
            <Dropdown.Trigger
              aria-label={email ? `Account: ${email}` : "Account"}
              className="cursor-pointer rounded-pill"
            >
              <Avatar.Root size="sm">
                <Avatar.Fallback>{initialsFor(email ?? "?")}</Avatar.Fallback>
              </Avatar.Root>
            </Dropdown.Trigger>

            {/* `Dropdown.Content` is `absolute left-0` by default, which anchors
                it to the trigger's LEFT edge — and this trigger sits at the
                right edge of the header, so the menu ran off the side of the
                window and was clipped. `left-auto right-0` hangs it from the
                right edge instead, so it opens inward. */}
            {/* The package's own spacing is tuned for a dense menu of actions.
                This one is a person's address and a single control, so it reads
                as cramped at that density — more room around both, and a
                rounded corner matching the app's cards. */}
            <Dropdown.Content className="right-0 left-auto min-w-[15rem] rounded-lg py-2">
              {email && (
                <>
                  <Dropdown.Label className="text-ink px-4 py-2.5 text-sm font-medium normal-case">
                    {email}
                  </Dropdown.Label>
                  <Dropdown.Divider className="my-1" />
                </>
              )}
              <Dropdown.Item className="px-4 py-2.5" onClick={signOut}>
                Sign out
              </Dropdown.Item>
            </Dropdown.Content>
          </Dropdown.Root>
        )}
      </div>
    </header>
  );
}
