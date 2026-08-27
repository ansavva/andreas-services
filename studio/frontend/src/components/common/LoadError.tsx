import { Alert, Button } from "@ansavva/design-system";

interface Props {
  /** What failed to load, in the sentence "Could not load <what>". */
  what: string;
  message: string;
  /** Absent where the caller has nothing to retry with. See below. */
  onRetry?: () => void;
}

/**
 * A failed read, with the way out of it.
 *
 * **Every load error in this app was a dead end.** The alert said what went
 * wrong and stopped there, so a listing that failed on a dropped connection
 * stayed failed until somebody reloaded the whole page — even though the hook
 * behind it had a `reload` the whole time.
 *
 * The retry is optional rather than assumed. A few callers render an error for
 * something they do not own the fetch of, and a button that cannot do anything
 * is worse than no button.
 */
export function LoadError({ what, message, onRetry }: Props) {
  return (
    <Alert.Root intent="danger">
      <Alert.Title>Could not load {what}</Alert.Title>
      <Alert.Description>{message}</Alert.Description>
      {onRetry && (
        <div className="mt-2">
          <Button intent="ghost" size="sm" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </Alert.Root>
  );
}
