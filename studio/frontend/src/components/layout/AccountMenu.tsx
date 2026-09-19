import { useState } from "react";

import { Dropdown, buttonClass, iconButtonClass } from "@ansavva/design-system";

import { useAuth } from "../../context/AuthContext";
import { useAccount } from "../../hooks/useAccount";
import { UserAvatar } from "../common/UserAvatar";
import { AccountDialog } from "./AccountDialog";
import { ChangeEmailDialog } from "./ChangeEmailDialog";

/**
 * The account, behind one button, at the foot of the sidebar.
 *
 * Two shapes for one control: the expanded column shows the picture and the
 * name — the address, for a person who has not given one — and the 64px rail
 * shows the picture alone. Both open the same menu, which is what the
 * `aria-label` is for. The menu opens UPWARD, because a footer control's
 * `top-full` is off the bottom of the screen.
 *
 * The picture is `UserAvatar`: the upload when there is one, initials off the
 * name and then the address when there is not. Nothing here waits for it —
 * `useAccount` answers the empty record until the request lands, and the
 * address is drawn in the meantime.
 *
 * The name and email are a **disabled menu item** rather than a heading: a
 * `role="menu"` may only hold menu items, so a plain `<div>` of text inside
 * one is a node a screen reader has no rule for. Disabled says "this is here
 * to be read, not pressed", which is exactly what it is.
 *
 * No `navigate` after sign-out: it leaves for the hosted `/logout`, which ends
 * the Cognito session and returns to `/` itself. Routing in this tab first
 * would only race that navigation.
 *
 * "Change email…" opens a dialog that is a SIBLING of the menu, not a child of
 * the item: selecting an item closes the menu and unmounts its content, so a
 * dialog rendered inside it would close with it. The item flips state; the
 * dialog reads it from out here.
 */
export function AccountMenu({ collapsed = false }: { collapsed?: boolean }) {
  const { email, logout } = useAuth();
  const { account } = useAccount();
  const [editing, setEditing] = useState(false);
  const [changingEmail, setChangingEmail] = useState(false);
  const shown = account.name ?? email;
  const name = shown ? `Account — ${shown}` : "Account";
  const picture = (
    <UserAvatar src={account.avatar_url} name={account.name} email={email} size={24} />
  );

  return (
    <>
      <Dropdown.Root>
        <Dropdown.Trigger
          aria-label={name}
          title={name}
          className={
            collapsed
              ? iconButtonClass({ size: "md", className: "" })
              : buttonClass({
                  intent: "secondary",
                  size: "md",
                  className: "w-full justify-between px-2",
                })
          }
        >
          {collapsed ? (
            picture
          ) : (
            <>
              {/* A name is a phrase and is set in the body face; an address
                  is a string to be read character by character, so it keeps
                  the mono the rule every node id, key and byte count in this
                  app is set under. */}
              <span
                className={
                  account.name
                    ? "min-w-0 truncate text-sm font-normal"
                    : "min-w-0 truncate font-mono text-xs font-normal"
                }
              >
                {shown ?? "Account"}
              </span>
              {picture}
            </>
          )}
        </Dropdown.Trigger>

        <Dropdown.Content className="bottom-full top-auto mb-1 mt-0">
          {(account.name || email) && (
            <Dropdown.Item disabled className="flex-col items-start gap-0">
              {account.name && <span className="text-sm">{account.name}</span>}
              {email && <span className="font-mono text-xs">{email}</span>}
            </Dropdown.Item>
          )}
          <Dropdown.Item onSelect={() => setEditing(true)}>Name and picture…</Dropdown.Item>
          <Dropdown.Item onSelect={() => setChangingEmail(true)}>
            Change email…
          </Dropdown.Item>
          <Dropdown.Item onSelect={() => void logout()}>Sign out</Dropdown.Item>
        </Dropdown.Content>
      </Dropdown.Root>
      <AccountDialog open={editing} onOpenChange={setEditing} />
      <ChangeEmailDialog open={changingEmail} onOpenChange={setChangingEmail} />
    </>
  );
}
