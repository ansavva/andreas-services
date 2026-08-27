import { NavLink } from "react-router-dom";

import { Dropdown, Text } from "@ansavva/design-system";

import { useAuth } from "../../context/AuthContext";
import { CHARACTERS_PATH, HOME_PATH, PROJECTS_PATH, folderPath } from "../../utils/location";
import { ChipRow } from "../common/ChipRow";
import { LibrarySwitcher } from "../common/LibrarySwitcher";
import { HeaderSearch } from "./HeaderSearch";
import { AccountIcon } from "../common/icons";

/**
 * The persistent strip: where you can go, and who you are.
 *
 * **It carries navigation now, which is the change.** The old header held a
 * title, an email and a sign-out button — so the only way to reach the two
 * lists this app is about was to go home and scroll, and the file browser was a
 * ghost button buried in the *Recent* section's heading. Three destinations sit
 * here instead, in the one place every screen has.
 *
 * **A header rather than a sidebar, and that is a decision rather than an
 * omission.** There are three destinations; a rail for three items spends a
 * grid column — the media grids run to six and eight across — on chrome. The
 * depth this app has is `entity → tab → item`, which a breadcrumb carries and a
 * tree does not. And a sidebar on a phone becomes a fourth overlay in an app
 * that already has too many, on a surface half this rework exists to fix.
 *
 * On narrow screens the links move to their own scrolling line rather than a
 * bottom bar. The bottom edge is where the browser's own toolbar sits — the bug
 * `app.css` and `ViewerChrome` both carry scars from — so nothing this app
 * needs pressed goes there.
 *
 * Sign-out moved into the account menu. It was a full-width ghost button
 * competing with the library switcher for a bar that now has to hold
 * navigation, and it is pressed roughly never.
 */
export function AppHeader() {
  const { email, logout } = useAuth();

  return (
    // `bg-bg` and not a translucent blur: the page background is the token, and
    // media scrolling under a frosted bar reads as a rendering fault on a grid
    // of dark frames.
    <header className="sticky top-0 z-30 border-b border-line bg-bg">
      <div className="mx-auto flex w-full max-w-7xl items-center gap-2 px-4 py-2 sm:gap-3 sm:px-6">
        <NavLink
          to={HOME_PATH}
          className="shrink-0 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2
                     focus-visible:outline-primary"
        >
          <Text variant="title">Studio</Text>
        </NavLink>

        <nav aria-label="Sections" className="hidden items-center gap-1 sm:flex">
          {DESTINATIONS.map((each) => (
            <HeaderLink key={each.to} {...each} />
          ))}
        </nav>

        <div className="flex-1" />

        {/* Hidden below `md`: a search box and three nav chips cannot share a
            390px row, and the chips are the thing you cannot do without. */}
        <HeaderSearch />

        {/* Renders nothing while the caller is in one library. See `LibrarySwitcher`. */}
        <LibrarySwitcher />
        {/* No `navigate` afterwards: sign-out leaves for the hosted `/logout`,
            which ends the Cognito session and returns to `/` itself. Routing in
            this tab first would only race that navigation.

            Carried over from `components/common/AppHeader.tsx`, which this
            replaced — the two changes crossed, and the header moving here does
            not make the Managed Login behaviour optional. */}
        <AccountMenu email={email} onSignOut={() => void logout()} />
      </div>

      <nav aria-label="Sections" className="px-4 pb-2 sm:hidden">
        <ChipRow>
          {DESTINATIONS.map((each) => (
            <HeaderLink key={each.to} {...each} chip />
          ))}
        </ChipRow>
      </nav>
    </header>
  );
}

/**
 * `/f` is the library root and matches every folder under it, which is what
 * makes the Files link stay lit while you browse. The entity pages are
 * deliberately not listed: `/c/<id>` is a *place*, not a section, and the
 * breadcrumb is what says where it sits.
 */
const DESTINATIONS = [
  { to: CHARACTERS_PATH, label: "Characters" },
  { to: PROJECTS_PATH, label: "Projects" },
  { to: folderPath(null), label: "Files" },
];

function HeaderLink({ to, label, chip = false }: { to: string; label: string; chip?: boolean }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `font-body text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2
         focus-visible:outline-primary ${chip ? "shrink-0 snap-start rounded-full border px-3 py-1" : "rounded-md px-3 py-1.5"}
         ${
           isActive
             ? chip
               ? "border-primary bg-primary text-primary-text"
               : "bg-surface-alt text-ink"
             : `text-muted hover:bg-surface-alt hover:text-ink ${chip ? "border-line" : ""}`
         }`
      }
    >
      {label}
    </NavLink>
  );
}

/**
 * The account, behind one button.
 *
 * The email is a **disabled menu item** rather than a heading: a `role="menu"`
 * may only hold menu items, so a plain `<div>` of text inside one is a node a
 * screen reader has no rule for. Disabled says "this is here to be read, not
 * pressed", which is exactly what it is.
 */
function AccountMenu({ email, onSignOut }: { email: string | null; onSignOut: () => void }) {
  return (
    <Dropdown.Root>
      <Dropdown.Trigger
        aria-label={email ? `Account — ${email}` : "Account"}
        title={email ?? "Account"}
        className="shrink-0 rounded-md p-2 text-muted transition-colors hover:bg-surface-alt
                   hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2
                   focus-visible:outline-primary"
      >
        <AccountIcon />
      </Dropdown.Trigger>

      {/* Right-aligned: the trigger is the last thing on the row, so a menu
          growing rightwards would hang off the page. Same reason as `ItemActions`. */}
      <Dropdown.Content className="left-auto right-0">
        {email && <Dropdown.Item disabled>{email}</Dropdown.Item>}
        <Dropdown.Item onSelect={onSignOut}>Sign out</Dropdown.Item>
      </Dropdown.Content>
    </Dropdown.Root>
  );
}
