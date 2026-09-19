import { Avatar } from "@ansavva/design-system";

import { initials } from "../../utils/avatar";

interface Props {
  /** The uploaded picture. When present it is drawn; otherwise initials. */
  src?: string | null;
  name?: string | null;
  email?: string | null;
  /** A pixel edge. The package's `size` is three fixed steps; the dialog wants 80. */
  size?: number;
  className?: string;
}

/**
 * The person's picture, or their initials where there is none.
 *
 * The design system's `Avatar` compound, which owns the one piece of state
 * here — whether the image has loaded — and paints `Fallback` until it has.
 * Two things are ours: the edge, as a pixel `style` because the package's
 * three steps stop at 40; and the letters, which come off the name and then
 * the address. No per-person colour: humbugg tints each person, and in a
 * dark sidebar of one muted tint the package's `surface-alt` on `muted` is
 * the right fallback. Weight, not hue.
 *
 * **Keyed on `src`.** The package's root holds one piece of state, "has the
 * image loaded", and nothing resets it when the image goes: remove the
 * picture and the root still says `loaded`, so `Fallback` renders nothing and
 * the circle is blank — seen live, the moment after Remove. A new key is a new
 * root, back at `idle`, and the letters draw.
 *
 * Decorative: the name it stands beside is the accessible text, so the image
 * has an empty `alt` and the letters are hidden from a reader that would
 * otherwise announce "A L" before "Ada Lovelace".
 */
export function UserAvatar({ src, name, email, size = 32, className }: Props) {
  const edge = { width: size, height: size };
  const letters = (
    <span aria-hidden style={{ fontSize: Math.round(size * 0.38) }} className="font-medium">
      {initials(name, email)}
    </span>
  );
  return (
    <Avatar.Root key={src ?? ""} style={edge} className={className}>
      {src ? (
        <>
          <Avatar.Image src={src} alt="" />
          <Avatar.Fallback>{letters}</Avatar.Fallback>
        </>
      ) : (
        <Avatar.Fallback>{letters}</Avatar.Fallback>
      )}
    </Avatar.Root>
  );
}
