import { Alert, Button } from "@ansavva/design-system";

interface Props {
  /** What failed to load, in the sentence "Could not load <what>". */
  what: string;
  message: string;
  /** Re-runs the read. Every caller owns a `reload`; pass it. */
  onRetry: () => void;
  /**
   * A way off a page that cannot draw — "Back to home", "Back". Only for a
   * failure that took the whole screen with it; a section that failed inside
   * a page that drew has the page's own navigation.
   */
  escape?: { label: string; onClick: () => void };
}

/**
 * A failed read, with the way out of it.
 *
 * **Every load error in this app was a dead end.** The alert said what went
 * wrong and stopped there, so a listing that failed on a dropped connection
 * stayed failed until somebody reloaded the whole page — even though the hook
 * behind it had a `reload` the whole time.
 *
 * The retry is required now. It was optional for callers that did not own the
 * fetch, and half the pages then left it off out of habit — every read in the
 * app comes through `useResource` or a feed hook, and both hand back a
 * `reload`. The escape is the second half: a run, scene or movie page that
 * failed offered no button at all while a character page offered "Back to
 * home", and a person on a dead link could only reach for the address bar.
 */
export function LoadError({ what, message, onRetry, escape }: Props) {
  return (
    <Alert.Root intent="danger">
      <Alert.Title>Could not load {what}</Alert.Title>
      <Alert.Description>{message}</Alert.Description>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button intent="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
        {escape && (
          <Button intent="secondary" size="sm" onClick={escape.onClick}>
            {escape.label}
          </Button>
        )}
      </div>
    </Alert.Root>
  );
}
