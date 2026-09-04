import { useNavigate } from "react-router-dom";

import { Button, Text } from "@ansavva/design-system";

import { SectionLoading } from "../components/common/SectionLoading";
import { MediaTile } from "../components/browse/MediaTile";
import {
  CharactersSection,
  ProjectsSection,
} from "../components/entity/EntitySections";
import { PageBar } from "../components/layout/PageBar";
import { useMedia } from "../hooks/useMedia";
import { MEDIA_GRID } from "../utils/grid";
import { folderPath, objectPath } from "../utils/location";
import { LoadError } from "../components/common/LoadError";

/**
 * What studio opens on: who there is, what is being made, and what came out most
 * recently.
 *
 * **This is the reversal the entity model bought.** Studio's users are not files
 * — they are characters and projects — and until now the app could not say so,
 * because both were a folder name with a document inside it and the app was
 * forbidden to read the document. They are rows with ids now, so the first screen
 * can be the two lists instead of a listing of the library root.
 *
 * Recent stays, third: it is the answer to "what did the last hour produce",
 * which neither list answers and which is most of why anybody opens studio
 * between sessions. It is a *grid*, not a mode, and there is no "play" button
 * beside it: opening any tile already scrolls the same recursive walk, and a
 * button that only chose the first tile for you would be a second name for
 * the thing under it.
 *
 * **The two lists are components now, not markup here.** `/characters` and
 * `/projects` are real screens the header links to, and they render exactly
 * these — so home is where all three meet rather than the only place any of them
 * exists. The page frame and the header went to `AppLayout`.
 */
export function HomePage() {
  const navigate = useNavigate();

  /**
   * The recursive walk of the whole library, newest first, fetched eagerly
   * because it *is* the section — there is nothing to click first.
   *
   * It asks for the twelve it draws rather than the API's default of two
   * hundred, which shrinks the response and the presigning.
   *
   * **It does not shrink the enumeration, and that is the honest limit here.**
   * `/api/reel` reads the branch, filters, sorts and slices, because `total` and
   * the cursor are defined against the whole of it — a windowed read makes both
   * meaningless, which is what a test caught when this tried it. Making home
   * cheap needs a purpose-built "recent" rather than a page of the reel
   * pretending to be one.
   */
  const RECENT = 12;
  const feed = useMedia(null, "newest", true, RECENT);

  const recent = feed.items.slice(0, RECENT);

  return (
    <>
      <PageBar title="Home" />

      <CharactersSection />
      <ProjectsSection />

      <section className="flex flex-col gap-3">
        {/* Same ruled heading as the two `EntitySections` above it — this
            section is open-coded because its action pair is its own, not
            because it is a different kind of thing. */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
          <Text variant="title">Recent</Text>
          {/* The library's file tree. It is in the header now as well — this
              stays because it is the thing the tiles beside it come from, and
              a section that shows twelve of something wants a way to see the
              rest. */}
          <Button
            intent="secondary"
            size="sm"
            onClick={() => navigate(folderPath(null))}
          >
            Browse files
          </Button>
        </div>

        {feed.loading && recent.length === 0 && <SectionLoading label="Loading recent media" />}
        {feed.error && (
          <LoadError what="recent media" message={feed.error} onRetry={feed.reload} />
        )}

        <div className={MEDIA_GRID}>
          {recent.map((file) => (
            // Selection is a *browser* affordance and there is nothing here to
            // act on a selection with, so the tiles open and do not pick.
            //
            // They open into the same walk they were drawn from, so the twelve
            // shown here are the start of a feed rather than twelve dead ends —
            // this section is a preview of that walk, and `in=recursive` is what
            // carries the rest of it into the viewer. It is also the only way
            // in: a "play" button would open this on the first tile, and so
            // does clicking the first tile.
            <MediaTile
              key={file.id}
              file={file}
              selected={false}
              selectionActive={false}
              onOpen={() =>
                navigate(objectPath(file.id, { in: "recursive", id: null }))
              }
              to={objectPath(file.id, { in: "recursive", id: null })}
              onToggleSelect={() => undefined}
            />
          ))}
        </div>
      </section>
    </>
  );
}
