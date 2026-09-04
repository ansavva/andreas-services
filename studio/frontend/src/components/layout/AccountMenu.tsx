import { Dropdown, buttonClass, iconButtonClass } from "@ansavva/design-system";

import { useAuth } from "../../context/AuthContext";
import { ProfileIcon } from "../common/icons";

/**
 * The account, behind one button, at the foot of the sidebar.
 *
 * Two shapes for one control: the expanded column shows the address, the 64px
 * rail shows the glyph — and both open the same menu, which is what the
 * `aria-label` is for. The menu opens UPWARD, because a footer control's
 * `top-full` is off the bottom of the screen.
 *
 * The email is a **disabled menu item** rather than a heading: a `role="menu"`
 * may only hold menu items, so a plain `<div>` of text inside one is a node a
 * screen reader has no rule for. Disabled says "this is here to be read, not
 * pressed", which is exactly what it is.
 *
 * No `navigate` after sign-out: it leaves for the hosted `/logout`, which ends
 * the Cognito session and returns to `/` itself. Routing in this tab first
 * would only race that navigation.
 */
export function AccountMenu({ collapsed = false }: { collapsed?: boolean }) {
  const { email, logout } = useAuth();
  const name = email ? `Account — ${email}` : "Account";

  return (
    <Dropdown.Root>
      <Dropdown.Trigger
        aria-label={name}
        title={name}
        className={
          collapsed
            ? iconButtonClass({ size: "md", className: "rounded-none" })
            : buttonClass({
                intent: "secondary",
                size: "md",
                className: "w-full justify-between rounded-none px-2",
              })
        }
      >
        {/* Mono, because an address is a string to be read character by
            character rather than a phrase — the rule every node id, key and
            byte count in this app is set under. */}
        {!collapsed && (
          <span className="min-w-0 truncate font-mono text-xs font-normal">
            {email ?? "Account"}
          </span>
        )}
        <ProfileIcon />
      </Dropdown.Trigger>

      <Dropdown.Content className="bottom-full top-auto mb-1 mt-0 rounded-none">
        {email && (
          <Dropdown.Item disabled className="font-mono text-xs">
            {email}
          </Dropdown.Item>
        )}
        <Dropdown.Item onSelect={() => void logout()}>Sign out</Dropdown.Item>
      </Dropdown.Content>
    </Dropdown.Root>
  );
}
