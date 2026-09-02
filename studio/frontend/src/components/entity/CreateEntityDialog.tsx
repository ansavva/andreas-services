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

import { ApiError } from "../../apis/client";
import { createCharacter, createProject } from "../../apis/studio";
import { characterPath, projectPath } from "../../utils/location";

/**
 * A slug, as the API will read it.
 *
 * Folded here as well as server-side so the field shows what is about to be
 * claimed rather than what was typed — `Some Name` becoming `some-name` after
 * the request is a surprise, and the slug is the address a person types at the
 * CLI afterwards.
 *
 * It is a *courtesy*, not the check. `keys.clean_slug` refuses what it refuses
 * and a 409 is the real answer to "is this taken"; this only stops the obvious
 * cases reaching it.
 */
function slugify(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

interface Props {
  kind: "character" | "project";
}

/**
 * Making a character or a project, from the app.
 *
 * **Both routes existed and neither had a caller**, so every empty state in
 * this app told you to go and type a CLI command. That is a reasonable thing
 * for a pipeline to say about *generating* something, which costs money and has
 * a payload to approve — and an unreasonable thing to say about creating an
 * empty record with a name.
 *
 * One component for both because the shape is the same — a slug, a human name,
 * one extra field — and the two differ only in which fields and which route.
 * Two dialogs would be two places for the 409 handling to drift.
 *
 * **A taken slug is the expected failure, not an error state.** It is the one
 * thing the caller cannot know in advance, the API answers it with a 409, and
 * the message names the slug — so it is shown against the field and the draft
 * is kept. Anything else is surfaced as itself rather than guessed at.
 */
export function CreateEntityDialog({ kind }: Props) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [taken, setTaken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isCharacter = kind === "character";
  const clean = slugify(slug);

  function reset() {
    setSlug("");
    setName("");
    setDescription("");
    setTaken(null);
    setError(null);
  }

  async function submit() {
    if (!clean) return;
    setBusy(true);
    setTaken(null);
    setError(null);
    try {
      if (isCharacter) {
        const record = await createCharacter({
          name: name.trim() || clean,
        });
        navigate(characterPath(record.id));
      } else {
        const record = await createProject({
          ...(name.trim() ? { title: name.trim() } : {}),
          ...(description.trim() ? { description: description.trim() } : {}),
        });
        navigate(projectPath(record.id));
      }
      setOpen(false);
      reset();
    } catch (err) {
      // 409 is the one refusal worth answering in place: the slug is claimed,
      // which is a thing to change rather than a thing that went wrong.
      if (err instanceof ApiError && err.status === 409) setTaken(err.message);
      else setError((err as Error).message);
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
      <Dialog.Trigger className={buttonClass({ size: "sm" })}>New {kind}</Dialog.Trigger>
      <Dialog.Backdrop />
      <Dialog.Popup className="flex w-full max-w-md flex-col gap-4 p-4">
        <Dialog.Title>New {kind}</Dialog.Title>

        <Field.Root name="slug" invalid={taken !== null}>
          <Field.Label>Slug</Field.Label>
          <Input
            value={slug}
            onValueChange={setSlug}
            placeholder={isCharacter ? "a-character" : "a-project"}
            autoFocus
          />
          <Field.Description>
            {/* Shown as it will be stored, so the address a person types next is
                never a surprise. */}
            Library-unique, and the address you type at the CLI.
            {clean && clean !== slug ? ` Stored as “${clean}”.` : ""}
          </Field.Description>
          {taken && <Field.Error>{taken}</Field.Error>}
        </Field.Root>

        <Field.Root name="name">
          <Field.Label>{isCharacter ? "Display name" : "Title"}</Field.Label>
          <Input
            value={name}
            onValueChange={setName}
            placeholder={isCharacter ? "How they are written about" : "What this is called"}
          />
          <Field.Description>Optional — the slug is used when this is empty.</Field.Description>
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
          <Button disabled={!clean || busy} onClick={() => void submit()}>
            {busy ? "Creating…" : `Create ${kind}`}
          </Button>
        </div>
      </Dialog.Popup>
    </Dialog.Root>
  );
}
