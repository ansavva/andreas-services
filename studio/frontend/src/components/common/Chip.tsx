/**
 * The square, bordered chip — pressed or not, one shape everywhere it appears.
 *
 * **It was drawn three times and drifted.** `AppHeader`'s mobile nav and
 * `ProjectDetails`' character toggles each retyped the same
 * `border-primary bg-primary text-primary-text` / `border-line text-muted
 * hover:bg-surface-alt` pair, closely enough that nobody noticed until they
 * were compared side by side. `FolderTab`'s folder-shortcut row was the third
 * copy and is gone with the row itself — see `FolderBrowser`.
 *
 * A class string, not a component — the same shape as the design system's own
 * `buttonClass`/`iconButtonClass` — because the two remaining callers need it
 * on different elements: `AppHeader`'s `NavLink` takes a function `className`,
 * and `ProjectDetails`' toggle is a plain `<button aria-pressed>`. Neither can
 * be handed a wrapping component without changing what element the router or
 * the a11y tree sees.
 */
export function chipClass(active: boolean, className = ""): string {
  return `shrink-0 snap-start rounded-none border px-3 py-1 font-body text-sm transition-colors
          focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${
            active
              ? "border-primary bg-primary text-primary-text"
              : "border-line text-muted hover:bg-surface-alt hover:text-ink"
          } ${className}`;
}
