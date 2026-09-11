import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  Alert,
  Button,
  Dialog,
  Field,
  Input,
  buttonClass,
} from "@ansavva/design-system";

import { createCharacter, createProject } from "../../apis/studio";
import { characterPath, projectPath } from "../../utils/location";
import { PlusIcon } from "../common/icons";

interface Props {
  kind: "character" | "project";
}

/**
 * Making a character or a project, from the app.
 *
 * **Both routes existed and neither had a caller**, so every empty state in
 * this app told you to go and type a CLI command. That is a reasonable thing
 * for a pipeline to say about *generating* something, which costs money and has
 * a payload to read — and an unreasonable thing to say about creating an
 * empty record with a name.
 *
 * One component for both because the shape is the same — a name and one extra
 * field — and the two differ only in which fields and which route.
 *
 * **The slug field this used to open on is gone.** Neither route ever took
 * one: `createCharacter` and `createProject` both take `name`, and the field
 * folded what was typed into an address that was never sent. It survived the
 * slug removal elsewhere in the entity model as a form asking a question the
 * API had stopped listening for.
 *
 * One button pattern now, everywhere something is made: a `Button size="sm"`
 * with a leading plus and "New ‹noun›", confirming "Create ‹noun›" — the same
 * shape `NewRunStrip`'s trigger wears.
 */
export function CreateEntityDialog({ kind }: Props) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isCharacter = kind === "character";
  const trimmed = name.trim();

  function reset() {
    setName("");
    setDescription("");
    setError(null);
  }

  async function submit() {
    // A character needs a name to be recognised by; a project does not — an
    // untitled project is a real thing to make and fill in later.
    if (isCharacter && !trimmed) return;
    setBusy(true);
    setError(null);
    try {
      if (isCharacter) {
        const record = await createCharacter({ name: trimmed });
        navigate(characterPath(record.id));
      } else {
        const record = await createProject({
          ...(trimmed ? { name: trimmed } : {}),
          ...(description.trim() ? { description: description.trim() } : {}),
        });
        navigate(projectPath(record.id));
      }
      setOpen(false);
      reset();
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
        setOpen(next);
        if (!next) reset();
      }}
    >
      {/* **The trigger IS the button, styled — not a `Button` inside one.**
          `Dialog.Trigger` renders its own `<button>`, so wrapping one in it
          nests a button in a button: invalid, and the browser quietly makes the
          press do nothing. `buttonClass` is what the package exports for
          exactly this. */}
      <Dialog.Trigger
        className={buttonClass({ size: "sm", className: "inline-flex items-center gap-1.5" })}
      >
        <PlusIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
        New {kind}
      </Dialog.Trigger>
      <Dialog.Backdrop />
      <Dialog.Popup className="flex w-full max-w-md flex-col gap-4 p-4">
        <Dialog.Title>New {kind}</Dialog.Title>

        <Field.Root name="name" invalid={isCharacter && trimmed === ""}>
          <Field.Label>{isCharacter ? "Name" : "Title"}</Field.Label>
          <Input
            value={name}
            onValueChange={setName}
            placeholder={isCharacter ? "How they are written about" : "What this is called"}
            autoFocus
          />
          {!isCharacter && (
            <Field.Description>Optional — left blank, the project is untitled.</Field.Description>
          )}
        </Field.Root>

        {!isCharacter && (
          <Field.Root name="description">
            <Field.Label>Description</Field.Label>
            <Input value={description} onValueChange={setDescription} placeholder="Optional" />
          </Field.Root>
        )}

        {error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not create this {kind}</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Dialog.Close>Cancel</Dialog.Close>
          <Button disabled={(isCharacter && !trimmed) || busy} onClick={() => void submit()}>
            {busy ? "Creating…" : `Create ${kind}`}
          </Button>
        </div>
      </Dialog.Popup>
    </Dialog.Root>
  );
}
