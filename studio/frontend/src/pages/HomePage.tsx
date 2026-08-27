import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, Button, Spinner, Text } from "@ansavva/design-system";

import { MediaTile } from "../components/browse/MediaTile";
import { CharactersSection, ProjectsSection } from "../components/entity/EntitySections";
import { ReelView } from "../components/viewer/ReelView";
import { useReel } from "../hooks/useReel";
import { folderPath, objectPath } from "../utils/location";

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
 * The reel stays, third, and unchanged: it is the answer to "what did the last
 * hour produce", which neither list answers and which is most of why anybody
 * opens studio between sessions.
 *
 * **The two lists are components now, not markup here.** `/characters` and
 * `/projects` are real screens the header links to, and they render exactly
 * these — so home is where all three meet rather than the only place any of them
 * exists. The page frame and the header went to `AppLayout`.
 */
export function HomePage() {
  const navigate = useNavigate();

  // Recent is the same recursive walk "Play reel" does at the root, fetched
  // eagerly because it *is* the section — there is nothing to click first.
  const reel = useReel(null, "newest", true);
  const [playing, setPlaying] = useState(false);

  const recent = reel.items.slice(0, 12);

  return (
    <>
      <CharactersSection />
      <ProjectsSection />

      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Text variant="title">Recent</Text>
          <div className="flex items-center gap-2">
            {/* The library's file tree. It is in the header now as well — this
                stays because it is the thing the tiles beside it come from, and
                a section that shows twelve of something wants a way to see the
                rest. */}
            <Button intent="ghost" size="sm" onClick={() => navigate(folderPath(null))}>
              Browse files
            </Button>
            <Button size="sm" disabled={reel.items.length === 0} onClick={() => setPlaying(true)}>
              Play reel
            </Button>
          </div>
        </div>

        {reel.loading && recent.length === 0 && <Spinner size="md" label="Loading recent media" />}
        {reel.error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not load recent media</Alert.Title>
            <Alert.Description>{reel.error}</Alert.Description>
          </Alert.Root>
        )}

        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
          {recent.map((file) => (
            // Selection is a *browser* affordance and there is nothing here to
            // act on a selection with, so the tiles open and do not pick.
            <MediaTile
              key={file.id}
              file={file}
              selected={false}
              selectionActive={false}
              onOpen={() => navigate(objectPath(file.id))}
              onToggleSelect={() => undefined}
            />
          ))}
        </div>
      </section>

      {/*
        The reel over home walks the whole library, exactly as it does from the
        root of the browser, with two things left off deliberately.

        It renames and deletes nothing: this page owns no listing to re-fetch
        afterwards, and both are one press away on the clip's own page.

        And it does **not** rewrite the address as it scrolls, which the browser's
        reel does. There the address is a folder and a clip in it, so replacing it
        is free; here it is `/`, and putting `/o/<id>` in its place would unmount
        this page under the open reel — the route would change to the browser
        while the overlay was still on screen.
      */}
      {playing && (
        <ReelView
          items={reel.items}
          loading={reel.loading}
          exhausted={reel.exhausted}
          truncated={reel.truncated}
          startIndex={0}
          onLoadMore={reel.loadMore}
          onClose={() => setPlaying(false)}
        />
      )}
    </>
  );
}
