import { ApertureSpinner } from "./Aperture";

interface Props {
  /** What is on its way, as the spinner's accessible name: "Loading scenes". */
  label: string;
}

/**
 * One section of a page waiting on its list.
 *
 * The page around it has drawn — a header, tabs, other sections — so this is
 * the small mark, centred in a short band rather than the tall one
 * `PageLoading` uses. A tab used to draw its spinner flush left with no
 * padding, and a picker's box centred it in a fixed height; both read as a
 * different app from the page they were on.
 */
export function SectionLoading({ label }: Props) {
  return (
    <div className="flex justify-center py-6">
      <ApertureSpinner size="md" label={label} />
    </div>
  );
}
