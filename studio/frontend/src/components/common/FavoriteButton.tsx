import { IconButton } from "@ansavva/design-system";

import { useFavorites } from "../../hooks/useFavorites";
import { HeartFilledIcon, HeartIcon } from "./icons";

interface Props {
  /** The node the heart is about. */
  id: string;
  /** What it is called, so the label says which file is being favorited. */
  name?: string;
  /**
   * `overlay` is the intent every control drawn over media uses in this app —
   * a scrim behind the glyph, because the frame under it is a picture whose
   * colour this app did not choose.
   */
  intent?: "overlay" | "default";
  size?: "sm" | "md";
  className?: string;
}

/**
 * The heart: press it to favorite a file, press it again to stop.
 *
 * **It reads the set rather than a prop**, and that is what makes it droppable
 * anywhere. A grid tile, a page header and a filmstrip all know a node id and
 * none of them knows whether it is favorited; `useFavorites` answers from one
 * cached read that every instance shares, so a hundred hearts on a screen are
 * one request between them and all hundred update together when one is pressed.
 *
 * **`aria-pressed`, not a second label.** The control is "Favorite <name>" in
 * both states — what it is *for* does not change — and whether it is on is the
 * pressed state, which is the distinction a screen reader already has a word
 * for. A label that flipped between "Favorite" and "Unfavorite" would make the
 * two states read as two different controls appearing in one place.
 */
export function FavoriteButton({
  id,
  name,
  intent = "default",
  size = "md",
  className,
}: Props) {
  const favorites = useFavorites();
  const on = favorites.isFavorite(id);

  return (
    <IconButton
      label={name ? `Favorite ${name}` : "Favorite"}
      pressed={on}
      size={size}
      intent={intent === "overlay" ? "overlay" : undefined}
      className={className}
      onClick={(event) => {
        // Hearts sit inside tiles that are themselves links. Without this a
        // press both favorites the file and opens it, which is the one
        // interaction that makes the control feel broken rather than slow.
        event.preventDefault();
        event.stopPropagation();
        favorites.setFavorite(id, !on);
      }}
    >
      {on ? (
        <HeartFilledIcon
          className={`${size === "sm" ? "size-4" : "size-5"} fill-current stroke-none text-danger`}
        />
      ) : (
        <HeartIcon
          className={`${size === "sm" ? "size-4" : "size-5"} fill-none stroke-current stroke-[1.5]`}
        />
      )}
    </IconButton>
  );
}
