import { useRef } from "react";

import { Button } from "@ansavva/design-system";

interface Props {
  /** Runs with whatever was picked. Files, never a `FileList` — see below. */
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}

/**
 * Pick files to upload into the folder on screen.
 *
 * **`<input type="file" multiple>` and nothing cleverer**, because it is the one
 * picker that works on every surface this app is opened on: it is the Finder on
 * a desktop, the Files/Photos sheet on iOS, and the document picker on Android.
 *
 * **`capture` is deliberately absent.** Setting it — even `capture=""` — makes
 * iOS and Android open the camera *instead of* the picker, so the main case,
 * uploading a photo or a clip that already exists, becomes impossible. It reads
 * like a hint and behaves like a redirect.
 *
 * `accept` is absent too. The library holds video, stills, JSON, markdown and
 * YAML, and an `accept` list is the fastest way to make a legitimate file
 * unselectable on the one device where re-exporting it is hardest. What cannot
 * be *displayed* is refused with a message instead (`apis/upload.rejectionFor`),
 * which is a sentence rather than a file greyed out for no stated reason.
 *
 * The input is hidden and a design-system `Button` clicks it. That is the usual
 * way to have both the native picker and the app's own control: a bare
 * `<input type="file">` cannot be styled, and a `<label>` styled as a button
 * would be a second implementation of `Button`'s height, focus ring and hover.
 * Its 44px `md` size is the WCAG touch target, which is not optional on the
 * device this feature is for.
 *
 * `value` is cleared after every pick so that choosing *the same file twice in a
 * row* fires `change` the second time. Without it the second pick is silent,
 * which reads as the button having stopped working.
 */
export function UploadButton({ onFiles, disabled = false }: Props) {
  const input = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={input}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          const picked = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (picked.length > 0) onFiles(picked);
        }}
      />
      <Button
        intent="secondary"
        size="sm"
        disabled={disabled}
        onClick={() => input.current?.click()}
      >
        Upload
      </Button>
    </>
  );
}
