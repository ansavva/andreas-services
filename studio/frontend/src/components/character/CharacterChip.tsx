import type { MouseEvent, ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Chip, chipClass } from "@ansavva/design-system";

import type { HeroImage } from "../../types";
import { characterPath } from "../../utils/location";
import { AccountIcon } from "../common/icons";
import { MediaThumb } from "../media/MediaThumb";

/**
 * A character, as a chip: a small square avatar and the name.
 *
 * **The avatar is the character's `hero`**, the card image the listing already
 * signs for every character, read off `getCharacters()` when the caller has
 * it. That is the image on hand; nothing here asks for one per chip. It is
 * not necessarily the first `default`-tagged identity image — `hero` is the
 * picture a person chose for the card, which is usually one of those and is
 * not required to be. A character with no hero yet draws a dashed square
 * carrying the account glyph, which is what the mockup shows for one whose
 * identity is not settled.
 */
export function CharacterAvatar({ hero, name }: { hero: HeroImage | null; name: string }) {
  if (hero) {
    return (
      <MediaThumb
        nodeId={hero.node}
        url={hero.url}
        name={name}
        isVideo={false}
        aspect="square"
        className="size-[22px] shrink-0 rounded-none border border-line"
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className="flex size-[22px] shrink-0 items-center justify-center rounded-none border border-dashed border-line text-muted"
    >
      <AccountIcon className="size-3 fill-none stroke-current stroke-[1.5]" />
    </span>
  );
}

/**
 * The chip, as a LINK to the character — for the project header, where a
 * chip opens the character it names.
 *
 * A real `<a href>` styled with `chipClass`, the same bargain `PageBar`'s
 * crumbs strike: middle-click and copy-address go to the browser, a plain
 * click to the router.
 */
export function CharacterChipLink({
  id,
  name,
  hero,
  trailing,
}: {
  id: string;
  name: string;
  hero: HeroImage | null;
  /** Something after the name — the involvement editor draws nothing here. */
  trailing?: ReactNode;
}) {
  const navigate = useNavigate();
  const to = characterPath(id);
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate(to);
  };

  return (
    <a
      href={to}
      onClick={onClick}
      className={chipClass({ size: "sm", className: "rounded-none pl-1.5 text-ink" })}
    >
      <CharacterAvatar hero={hero} name={name} />
      <span className="truncate">{name}</span>
      {trailing}
    </a>
  );
}

/**
 * The chip, as a TOGGLE — for the involvement editor, where pressing one adds
 * or removes the character from the project.
 */
export function CharacterChipToggle({
  name,
  hero,
  pressed,
  disabled,
  onClick,
}: {
  name: string;
  hero: HeroImage | null;
  pressed: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <Chip
      pressed={pressed}
      size="sm"
      disabled={disabled}
      onClick={onClick}
      className="rounded-none pl-1.5 disabled:opacity-60"
    >
      <CharacterAvatar hero={hero} name={name} />
      <span className="truncate">{name}</span>
    </Chip>
  );
}
