import { useState } from "react";

import {
  Alert,
  Button,
  Dialog,
  Field,
  Input,
  Text,
} from "@ansavva/design-system";

import { confirmEmailChange, requestEmailChange } from "../../auth/account";
import { useAuth } from "../../context/AuthContext";

interface Props {
  open: boolean;
  onOpenChange(open: boolean): void;
}

/**
 * Changing the address the account signs in with. Two steps in one dialog:
 * the new address, then the code Cognito sent to it.
 *
 * Controlled from `AccountMenu` rather than carrying its own trigger, because
 * the trigger is a menu item, and a menu closes — and unmounts its items — on
 * select. A dialog mounted inside the item would go with it.
 *
 * Nothing changes until the code is right: the pool keeps the old address in
 * force until the new one is verified (`infra/modules/auth`), so closing this
 * halfway leaves the account exactly as it was. Cancelling after step 1 is
 * therefore free; the pending address simply lapses with its code.
 */
export function ChangeEmailDialog({ open, onOpenChange }: Props) {
  const { email: current, refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = email.trim();
  // The loosest check worth making here: Cognito is the authority on what an
  // address is, and refuses one it does not like with a message shown below.
  const looksLikeAddress = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed);
  const unchanged = trimmed.toLowerCase() === (current ?? "").toLowerCase();
  const awaitingCode = sentTo !== null;

  function reset() {
    setEmail("");
    setCode("");
    setSentTo(null);
    setError(null);
  }

  function close() {
    onOpenChange(false);
    reset();
  }

  async function sendCode() {
    if (!looksLikeAddress || unchanged) return;
    setBusy(true);
    setError(null);
    try {
      setSentTo(await requestEmailChange(trimmed));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    if (!code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await confirmEmailChange(code);
      // Re-reads the token store, which `confirmEmailChange` just renewed, so
      // the menu shows the new address without a reload.
      refresh();
      close();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next: boolean) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <Dialog.Backdrop />
      <Dialog.Popup className="flex w-full max-w-md flex-col gap-4 p-4">
        <Dialog.Title>Change email</Dialog.Title>

        {!awaitingCode ? (
          <>
            <Text variant="body" tone="muted">
              The address is what you sign in with — here and in{" "}
              <span className="font-mono">studio login</span>. A code goes to
              the new one first; nothing changes until it is entered.
            </Text>
            <Field.Root
              name="email"
              invalid={trimmed !== "" && (!looksLikeAddress || unchanged)}
            >
              <Field.Label>New address</Field.Label>
              <Input
                type="email"
                value={email}
                onValueChange={setEmail}
                placeholder={current ?? "you@example.com"}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") void sendCode();
                }}
              />
              {trimmed !== "" && unchanged && (
                <Field.Error>
                  That is already the address on this account.
                </Field.Error>
              )}
            </Field.Root>
          </>
        ) : (
          <>
            <Text variant="body" tone="muted">
              A code was sent to <span className="font-mono">{sentTo}</span>.
              Enter it to make the change.
            </Text>
            <Field.Root name="code">
              <Field.Label>Verification code</Field.Label>
              <Input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={code}
                onValueChange={setCode}
                placeholder="Six digits"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter") void verify();
                }}
              />
            </Field.Root>
          </>
        )}

        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not change the address</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Dialog.Close>Cancel</Dialog.Close>
          {!awaitingCode ? (
            <Button
              disabled={!looksLikeAddress || unchanged || busy}
              onClick={() => void sendCode()}
            >
              {busy ? "Sending…" : "Send code"}
            </Button>
          ) : (
            <Button
              disabled={!code.trim() || busy}
              onClick={() => void verify()}
            >
              {busy ? "Verifying…" : "Verify and change"}
            </Button>
          )}
        </div>
      </Dialog.Popup>
    </Dialog.Root>
  );
}
