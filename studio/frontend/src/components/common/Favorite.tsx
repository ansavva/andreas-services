import { useFavorites } from "../../hooks/useFavorites";
import type { MenuAction } from "./ActionMenu";
import { HeartFilledIcon, HeartIcon } from "./icons";

/**
 * The heart, as the two things it is on a screen: a line in a menu that
 * favorites a file, and the mark a favorited file carries.
 *
 * **This was `FavoriteButton`, an icon button pressed in place.** It sat on
 * every browsed tile until the tile's controls became one `⋮` (#625), and
 * on the open file's row until that row became one button and a `⋯`
 * (2026-09-21). Nothing draws a heart *button* now; the press is a menu line
 * everywhere, and the state it leaves is a mark. `useFavorites` still does
 * the work — one cached id set for the app, an optimistic press, a rollback
 * on failure — and neither of these knows more than a node id.
 */

/**
 * "Add to favorites" or "Remove from favorites", by which it is now.
 *
 * **One line, built in one place, because it is on four menus.** A browsed
 * tile's `⋮`, a run output's `⋮`, the opened run's `⋯` and the open file's
 * `⋯` all offer it — and the run's surfaces had lost it: when the heart left
 * the tile for the menu the run's outputs kept no heart at all, so a picture
 * could be favorited from the folder it landed in and not from the run that
 * made it. The caller passes what it knows — the node, whether it is in the
 * set, and the press — so a plain function like `outputMenu` can build it
 * without a hook.
 */
export function favoriteAction(id: string, on: boolean, toggle: (id: string) => void): MenuAction {
  return {
    key: "favorite",
    label: on ? "Remove from favorites" : "Add to favorites",
    icon: on ? (
      <HeartFilledIcon className="size-4 shrink-0 fill-current stroke-none" />
    ) : (
      <HeartIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5]" />
    ),
    onSelect: () => toggle(id),
  };
}

/**
 * A filled heart on a tile that is in the set — the state the menu line
 * leaves behind, readable at a glance and not a control.
 *
 * `aria-hidden` and `pointer-events-none`: it takes no presses, and the
 * tile's own label says what the tile is. Nothing at all when the file is
 * not favorited, so a grid reads as pictures with a few marks on it rather
 * than as a grid of empty hearts. The caller places it, because what else
 * sits on the tile's corners differs — a browsed tile has a checkbox top
 * left, a run's output has nothing there.
 */
export function FavoriteMark({ id, className = "" }: { id: string; className?: string }) {
  const on = useFavorites().isFavorite(id);
  if (!on) return null;
  return (
    <span
      aria-hidden="true"
      data-testid="favorite-mark"
      className={`pointer-events-none absolute flex size-5 items-center justify-center
                  rounded-pill bg-overlay-scrim/70 ${className}`}
    >
      <HeartFilledIcon className="size-3 fill-current stroke-none text-danger" />
    </span>
  );
}
