import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * One query parameter, read and written like state.
 *
 * **This is what makes a tab a place.** Every tabbed screen in this app used
 * `Tabs.Root defaultValue`, which is uncontrolled — so a project's Runs tab had
 * no address, could not be sent to anyone, did not survive a refresh, and was
 * not what back went to. The same was true of the folder inside a Files tab.
 *
 * The default is written as *absence*. A URL carries `?tab=runs` and never
 * `?tab=overview`, so the address of a screen at rest is the screen's own path
 * — which is what a person copies when they mean "this page" rather than "this
 * page, on the tab it already opens on".
 *
 * `replace` by default, because switching tab is not a journey. Pushing would
 * make back walk every tab somebody clicked through before it left the page,
 * which is the behaviour that makes in-page tabs feel broken in a browser.
 *
 * **`push` is for the one parameter that IS a journey: the folder.** Three
 * subfolders deep in a character's Files, back is expected to climb out one
 * folder at a time — that is what it does in every file browser — and with
 * `replace` it left the character entirely, landing on the characters list.
 * Sort and tab stay `replace`; a folder is a place, a sort order is not.
 */
export function useSearchParamState(
  key: string,
  fallback: string,
  options: { push?: boolean } = {},
): [string, (next: string, options?: { replace?: boolean }) => void] {
  const [params, setParams] = useSearchParams();
  const { push = false } = options;

  const set = useCallback(
    // A call may still say `replace` on a pushing key: leaving a folder that
    // has just been deleted is not a journey either, and back must not
    // return to it.
    (next: string, { replace = !push }: { replace?: boolean } = {}) => {
      const nextParams = new URLSearchParams(params);
      if (next === fallback) nextParams.delete(key);
      else nextParams.set(key, next);
      setParams(nextParams, { replace });
    },
    [fallback, key, params, push, setParams],
  );

  return [params.get(key) ?? fallback, set];
}
