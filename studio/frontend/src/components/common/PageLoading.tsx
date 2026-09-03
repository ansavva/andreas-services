import { ApertureSpinner } from "./Aperture";

interface Props {
  /** What is on its way, as the spinner's accessible name: "Loading run". */
  label: string;
}

/**
 * A whole screen waiting on its record.
 *
 * Five pages drew this box by hand, each with its own idea of the padding,
 * and one page drew a bare unlabelled spinner. The label is required because
 * a spinner without one announces "Loading" for every page, and a screen
 * reader stepping between tabs cannot tell which of them is still coming.
 *
 * For a tab or a section inside a page that has already drawn, use
 * `SectionLoading`.
 */
export function PageLoading({ label }: Props) {
  return (
    <div className="flex justify-center py-16">
      <ApertureSpinner size="lg" label={label} />
    </div>
  );
}
