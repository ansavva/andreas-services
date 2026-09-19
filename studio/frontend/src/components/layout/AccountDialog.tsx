import { useEffect, useRef, useState } from "react";

import {
  Alert,
  Button,
  Dialog,
  Field,
  Input,
  Text,
} from "@ansavva/design-system";

import { useAuth } from "../../context/AuthContext";
import { useAccount } from "../../hooks/useAccount";
import { AVATAR_ALLOWED_TYPES, readAsDataUrl, validateAvatarFile } from "../../utils/avatar";
import { cancelClass } from "../common/cancelClass";
import { UserAvatar } from "../common/UserAvatar";

interface Props {
  open: boolean;
  onOpenChange(open: boolean): void;
}

/**
 * The person's name and picture, in one dialog off the account menu.
 *
 * Controlled from `AccountMenu` for the reason `ChangeEmailDialog` is: the
 * trigger is a menu item, and a menu unmounts its items on select.
 *
 * **The picture saves on pick; the name saves on Save.** A picture is one
 * decision — choose it, see it — and waiting for a button after the preview
 * has already shown it is a step with nothing in it. A name is typed, and a
 * request per keystroke would be silly, so it has a button. Remove is
 * immediate too, and the preview drops to initials as the answer lands.
 *
 * The file input is hidden and driven by a button, because a bare
 * `<input type="file">` cannot be styled and its label says "No file chosen"
 * about a picture that is right there in the preview.
 */
export function AccountDialog({ open, onOpenChange }: Props) {
  const { email } = useAuth();
  const { account, rename, upload, remove } = useAccount();
  const [name, setName] = useState(account.name ?? "");
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  // Opening starts from what is saved, not from what was typed last time and
  // then cancelled.
  useEffect(() => {
    if (open) {
      setName(account.name ?? "");
      setError(null);
    }
  }, [open, account.name]);

  const trimmed = name.trim();
  const unchanged = trimmed === (account.name ?? "");
  const busy = rename.isPending || upload.isPending || remove.isPending;

  async function save() {
    if (unchanged || busy) return;
    setError(null);
    try {
      await rename.mutateAsync(trimmed);
      onOpenChange(false);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function pick(file: File | undefined) {
    if (!file) return;
    const problem = validateAvatarFile(file);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    try {
      await upload.mutateAsync(await readAsDataUrl(file));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function clear() {
    setError(null);
    try {
      await remove.mutateAsync();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Backdrop />
      <Dialog.Popup className="flex w-full max-w-md flex-col gap-4 p-4">
        <Dialog.Title>Your account</Dialog.Title>

        <div className="flex items-center gap-4">
          <UserAvatar src={account.avatar_url} name={account.name} email={email} size={80} />
          <div className="flex min-w-0 flex-col gap-2">
            <Text variant="body" tone="muted">
              A picture, or your initials without one. PNG, JPEG or WebP up to 3 MB;
              it is cropped square.
            </Text>
            <div className="flex flex-wrap gap-2">
              <Button
                intent="secondary"
                size="sm"
                disabled={busy}
                onClick={() => picker.current?.click()}
              >
                {upload.isPending ? "Uploading…" : account.avatar_url ? "Change picture" : "Choose picture"}
              </Button>
              {account.avatar_url && (
                <Button intent="ghost" size="sm" disabled={busy} onClick={() => void clear()}>
                  {remove.isPending ? "Removing…" : "Remove"}
                </Button>
              )}
            </div>
            <input
              ref={picker}
              type="file"
              accept={AVATAR_ALLOWED_TYPES.join(",")}
              className="sr-only"
              aria-label="Choose a picture"
              onChange={(e) => {
                const file = e.target.files?.[0];
                // Reset so choosing the same file again fires `change` again.
                e.target.value = "";
                void pick(file);
              }}
            />
          </div>
        </div>

        <Field.Root name="name">
          <Field.Label>Name</Field.Label>
          <Input
            value={name}
            onValueChange={setName}
            placeholder={email ?? "Your name"}
            maxLength={100}
            onKeyDown={(e) => {
              if (e.key === "Enter") void save();
            }}
          />
          <Field.Description>
            Shown beside your picture. Leave it blank to go by your address.
          </Field.Description>
        </Field.Root>

        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not save</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Dialog.Close className={cancelClass()}>{unchanged ? "Close" : "Cancel"}</Dialog.Close>
          <Button disabled={unchanged || busy} onClick={() => void save()}>
            {rename.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </Dialog.Popup>
    </Dialog.Root>
  );
}
