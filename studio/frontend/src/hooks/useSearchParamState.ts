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
 * `replace`, because switching tab is not a journey. Pushing would make back
 * walk every tab somebody clicked through before it left the page, which is the
 * behaviour that makes in-page tabs feel broken in a browser.
 */
export function useSearchParamState(
  key: string,
  fallback: string,
): [string, (next: string) => void] {
  const [params, setParams] = useSearchParams();

  const set = useCallback(
    (next: string) => {
      const nextParams = new URLSearchParams(params);
      if (next === fallback) nextParams.delete(key);
      else nextParams.set(key, next);
      setParams(nextParams, { replace: true });
    },
    [fallback, key, params, setParams],
  );

  return [params.get(key) ?? fallback, set];
}
