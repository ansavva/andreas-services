import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Combobox, type ComboboxOption } from "@ansavva/design-system";

import { getCharacters, getProjects } from "../../apis/studio";
import { useResource } from "../../hooks/useResource";
import { characterPath, projectPath } from "../../utils/location";

/**
 * Jump to a character or a project by name.
 *
 * **There was no search at all**, and home listed every character and every
 * project unpaged — so "open the one I was working on" meant reading down a
 * list that grows forever. This is the smallest thing that fixes that.
 *
 * ## It filters what is already loaded, and does not query
 *
 * `GET /api/characters?q=` exists, and this deliberately does not use it. Both
 * lists are small, already fetched for the pages that show them, and matching
 * locally means the result is instant and works with the value half-typed —
 * where a query per keystroke would be a request per keystroke against a route
 * that has to answer before anything can be drawn. If either list ever grows
 * past what is sensible to hold, `q=` is the escape hatch and this is where it
 * would go.
 *
 * Runs, scenes and movies are **not** here. A run has no name — it is a date —
 * and a scene or a movie is reached through the project that owns it. Searching
 * a nameless thing by name is a box that always comes back empty.
 */
export function HeaderSearch() {
  const navigate = useNavigate();
  const [value, setValue] = useState("");

  const characters = useResource(["characters"], useCallback(() => getCharacters(), []));
  const projects = useResource(["projects"], useCallback(() => getProjects(), []));

  /**
   * The value is the PATH, which is what makes selecting one a navigation.
   *
   * A `Combobox` reports the option's value, so putting the address there means
   * nothing has to look the choice back up — and two entities that share a name
   * still have different values, which an id-keyed list would need care to
   * preserve and a name-keyed one could not.
   */
  const options = useMemo<ComboboxOption[]>(
    () => [
      ...(characters.data ?? []).map((each) => ({
        value: characterPath(each.id),
        label: each.display_name || each.slug,
      })),
      ...(projects.data ?? []).map((each) => ({
        value: projectPath(each.id),
        label: each.title || each.slug,
      })),
    ],
    [characters.data, projects.data],
  );

  return (
    <div className="hidden w-48 md:block lg:w-64">
      <Combobox
        options={options}
        value={value}
        placeholder="Find a character or project…"
        aria-label="Find a character or project"
        onValueChange={(next: string) => {
          setValue("");
          if (next) navigate(next);
        }}
      />
    </div>
  );
}
