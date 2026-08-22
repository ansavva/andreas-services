import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { Select } from "@ansavva/design-system";

import { useLibrary } from "../../context/LibraryContext";

/**
 * Which library you are looking at — shown only when there is a choice.
 *
 * **One library renders nothing.** That is the overwhelmingly common case and
 * has been the only case since studio existed: a picker with one entry is a
 * question with one answer, and the API resolves a sole membership without being
 * told. The header still goes out on every request (`apis/client`), so the two
 * kinds of caller differ in what they see and not in what they send.
 *
 * **It lives in the page chrome, and it has to.** Every card and row in a
 * listing is itself a `<button>`, and this renders one — a button inside a
 * button is invalid HTML that browsers resolve by dropping one of them, usually
 * the one you wanted. A control that belongs to the page rather than to a row is
 * also the honest place for it: switching library replaces the whole page.
 *
 * **Switching goes to the root and drops every cached listing.** The URL names a
 * node by id and that node is in the library you just left, so staying put is a
 * 403 on the next fetch. The listings already in hand are just as stale, and
 * they live in component state all over the tree — `App` remounts the route
 * table on the chosen id, which is what discards them. Navigating to `/` first
 * means the remount lands on the new library's root rather than on the id it is
 * about to fail on; both happen in one event, so there is one render.
 */
export function LibrarySwitcher() {
  const { libraries, current, select } = useLibrary();
  const navigate = useNavigate();

  const options = useMemo(
    () => libraries.map((library) => ({ value: library.id, label: library.name })),
    [libraries],
  );

  if (libraries.length <= 1) return null;

  return (
    <Select
      aria-label="Library"
      options={options}
      value={current}
      onValueChange={(id) => {
        if (id === current) return;
        navigate("/", { replace: true });
        select(id);
      }}
    />
  );
}
