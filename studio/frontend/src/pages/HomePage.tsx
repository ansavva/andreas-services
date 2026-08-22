import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert, Button, Spinner, Text } from "@ansavva/design-system";

import { getCharacters, getProjects } from "../apis/studio";
import { MediaTile } from "../components/browse/MediaTile";
import { AppHeader } from "../components/common/AppHeader";
import { EntityCard } from "../components/entity/EntityCard";
import { ReelView } from "../components/viewer/ReelView";
import { useReel } from "../hooks/useReel";
import { useResource } from "../hooks/useResource";
import { characterPath, folderPath, objectPath, projectPath } from "../utils/location";

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
 */
export function HomePage() {
  const navigate = useNavigate();

  const characters = useResource(useCallback(() => getCharacters(), []));
  const projects = useResource(useCallback(() => getProjects(), []));

  // Recent is the same recursive walk "Play reel" does at the root, fetched
  // eagerly because it *is* the section — there is nothing to click first.
  const reel = useReel(null, "newest", true);
  const [playing, setPlaying] = useState(false);

  const recent = reel.items.slice(0, 12);

  return (
    <div className="mx-auto flex min-h-full w-full max-w-7xl flex-col gap-8 p-4 sm:p-6">
      <AppHeader />

      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Text variant="title">
            Characters{" "}
            {characters.data && (
              <span className="font-body text-sm text-muted">({characters.data.length})</span>
            )}
          </Text>
        </div>

        {characters.loading && <Spinner size="md" label="Loading characters" />}
        {characters.error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not load characters</Alert.Title>
            <Alert.Description>{characters.error}</Alert.Description>
          </Alert.Root>
        )}
        {characters.data?.length === 0 && (
          <Text variant="body" tone="muted">
            No characters yet. `studio character create &lt;slug&gt;` makes one.
          </Text>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {(characters.data ?? []).map((character) => (
            <EntityCard
              key={character.id}
              title={character.display_name}
              slug={character.slug}
              hero={character.hero}
              counts={`${character.counts.references} references · ${character.counts.files} files`}
              onOpen={() => navigate(characterPath(character.id))}
            />
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <Text variant="title">
          Projects{" "}
          {projects.data && (
            <span className="font-body text-sm text-muted">({projects.data.length})</span>
          )}
        </Text>

        {projects.loading && <Spinner size="md" label="Loading projects" />}
        {projects.error && (
          <Alert.Root intent="danger">
            <Alert.Title>Could not load projects</Alert.Title>
            <Alert.Description>{projects.error}</Alert.Description>
          </Alert.Root>
        )}
        {projects.data?.length === 0 && (
          <Text variant="body" tone="muted">
            No projects yet. `studio projects new &lt;slug&gt;` makes one.
          </Text>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {(projects.data ?? []).map((project) => (
            <EntityCard
              key={project.id}
              title={project.title || project.slug}
              slug={project.slug}
              hero={project.hero}
              counts={`${project.counts.runs} runs · ${project.counts.scenes} scenes · ${project.counts.movies} movies`}
              onOpen={() => navigate(projectPath(project.id))}
            />
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Text variant="title">Recent</Text>
          <div className="flex items-center gap-2">
            {/* The library's file tree, which is no longer what `/` shows. It is
                still one click away and still where a link to a folder lands. */}
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
    </div>
  );
}
