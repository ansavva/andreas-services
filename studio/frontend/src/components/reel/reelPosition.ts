/**
 * Where a project's reel was left, so opening it again picks up there.
 *
 * **Keyed by node id, not by index.** The reel runs oldest to newest, so
 * everything a project makes after this is remembered lands *after* it —
 * and an index would drift under every delete. An id is a place in the
 * order that survives both.
 *
 * **Reaching the end forgets the place.** A reel finished is a reel that
 * starts over next time; a person who stopped on the last item and came
 * back would otherwise open on the same last item with nowhere to go.
 * `ProjectReel` calls `forget` when the last pane is snapped and the walk
 * is exhausted, and `remember` for every other pane.
 *
 * `localStorage`, per project, per browser — a fact about the person
 * reading, not the library, which is the same line the sidebar's collapse
 * state and the chosen library sit on. Every call tolerates a store that
 * throws (private-mode Safari) by doing nothing.
 */

const PREFIX = "studio.reel.";

function key(projectId: string): string {
  return `${PREFIX}${projectId}`;
}

/** The node id the reel was left on, or `null` to start from the top. */
export function recallPosition(projectId: string): string | null {
  try {
    return window.localStorage.getItem(key(projectId));
  } catch {
    return null;
  }
}

export function rememberPosition(projectId: string, nodeId: string): void {
  try {
    window.localStorage.setItem(key(projectId), nodeId);
  } catch {
    /* nothing to remember into */
  }
}

export function forgetPosition(projectId: string): void {
  try {
    window.localStorage.removeItem(key(projectId));
  } catch {
    /* nothing to forget from */
  }
}
