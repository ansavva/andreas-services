import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge, Tabs, Text } from "@ansavva/design-system";

import { deleteProject, getCharacters, getProject } from "../../apis/studio";
import { useInFlightRuns } from "../../hooks/useInFlightRuns";
import { useResource } from "../../hooks/useResource";
import type { HeroImage, ProjectRecord } from "../../types";
import { PROJECTS_PATH, projectPath } from "../../utils/location";
import { ApertureSpinner } from "../common/Aperture";
import { ConfirmDestroyDialog } from "../common/ConfirmDestroyDialog";
import { SettingsIcon, TrashIcon } from "../common/icons";
import { CharacterChipLink } from "../character/CharacterChip";
import { PageBar, useCopyLinkItem } from "../layout/PageBar";

/** The five tabs a project has, in the order the strip draws them. */
export type ProjectTab = "runs" | "scenes" | "movies" | "files" | "settings";

/**
 * A project open on one of its tabs — `/p/<id>?tab=scenes`.
 *
 * `runs` is the default and is written as nothing, the rule
 * `useSearchParamState` writes with, so a link to the feed is the bare path.
 */
export function projectTabPath(id: string, tab: string): string {
  return tab === "runs" ? projectPath(id) : `${projectPath(id)}?tab=${tab}`;
}

/**
 * The project's page bar: `Projects / <name>`, its counts, who it is about,
 * its `⋯`, and the five tabs — for whichever page wraps it in a `Tabs.Root`.
 *
 * **Drawn on a scene and a movie too, not only on the project.** A scene is
 * opened from the project's Scenes tab, and the page it opened on used to be
 * the scene's own — a different title, a different trail, and no strip: the
 * tabs a person had just been choosing between were gone, with nothing saying
 * the scene sat under one of them. The Files tab already had the answer: a
 * folder three deep keeps the project's bar and draws its own trail under the
 * tabs. A scene is a row under Scenes the way a folder is a row under Files,
 * so it is drawn the same way — this bar with Scenes selected, and the scene
 * as a trail beneath it (`SubTrail`). `ProjectPage` owns the panels; here the
 * bar is only the bar.
 *
 * **Delete lives behind `⋯`, and the noun still spells out the cascade.**
 * `ConfirmDestroyDialog` types the name because a project takes its runs,
 * scenes and movies with it.
 *
 * **Nothing here makes a run.** The create bar in the top bar is where a run
 * is authored, on every screen; the page's own primary slot holds who the
 * project is about instead, per the mockup.
 */
export function ProjectBar({ record, heroes }: { record: ProjectRecord; heroes: Record<string, HeroImage | null> }) {
  const copyLink = useCopyLinkItem();
  const navigate = useNavigate();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const running = useInFlightRuns()[record.id] ?? 0;
  const counts = record.counts;
  const held = counts.runs + counts.scenes + counts.movies;

  return (
    <>
      <PageBar
        crumbs={[{ label: "Projects", to: PROJECTS_PATH }]}
        title={record.name}
        meta={
          <>
            {/* A mono caption, as every listing page counts — a Badge is
                for a status, and the spinner beside it is one. */}
            <Text variant="caption" family="mono" tone="muted" className="tabular-nums">
              {counts.runs} {counts.runs === 1 ? "run" : "runs"}
            </Text>
            {running > 0 && (
              <Badge intent="neutral" className="gap-1.5 font-mono tabular-nums">
                <ApertureSpinner size="sm" label={`${running} running`} className="size-3.5" />
                {running} running
              </Badge>
            )}
          </>
        }
        primary={
          record.characters.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2" aria-label="Characters">
              {record.characters.map((each) => (
                <CharacterChipLink
                  key={each.id}
                  id={each.id}
                  name={each.name}
                  hero={heroes[each.id] ?? null}
                />
              ))}
            </div>
          ) : undefined
        }
        menu={[copyLink, {
            label: "Delete",
            icon: <TrashIcon className="size-4 shrink-0 fill-none stroke-current stroke-[1.5]" />,
            danger: true,
            onSelect: () => setDeleteOpen(true),
          }]}
        tabs={
          // Scrolls rather than wraps, like the character page's: a tab
          // strip that grows a second row draws a second underline, which
          // reads as two strips. Settings sits at the far end, after a gap,
          // because it is about the project rather than in it.
          <Tabs.List className="overflow-x-auto border-b border-line">
            <Tabs.Tab value="runs">Runs</Tabs.Tab>
            <Tabs.Tab value="scenes">Scenes</Tabs.Tab>
            <Tabs.Tab value="movies">Movies</Tabs.Tab>
            <Tabs.Tab value="files">Files</Tabs.Tab>
            <Tabs.Tab value="settings" className="ml-auto gap-1.5">
              <SettingsIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
              Settings
            </Tabs.Tab>
          </Tabs.List>
        }
      />

      <ConfirmDestroyDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        label="Delete"
        title={`Delete ${record.name}?`}
        summary={deleteSummary(held, counts)}
        confirmWord={record.name}
        onConfirm={async () => {
          await deleteProject(record.id, "delete", held > 0);
          navigate(PROJECTS_PATH);
        }}
      />
    </>
  );
}

/**
 * The project's bar as a scene or a movie draws it: on one tab, with the
 * other four leaving for the project.
 *
 * A `Tabs.Root` with no panels — the strip is navigation here, not a switch.
 * The record costs a request, the same one `ProjectPage` makes, so a person
 * coming from the project pays nothing and a person landing on a pasted link
 * pays one. Until it lands, nothing: the bar arriving a beat late is better
 * than a bar that says "Project" and then changes its mind.
 */
export function ProjectBarOn({ projectId, tab }: { projectId: string; tab: ProjectTab }) {
  const navigate = useNavigate();
  const load = useCallback(() => getProject(projectId), [projectId]);
  const project = useResource(["project", projectId], load);
  // The card image per character, for the chips — the listing the sidebar's
  // search already reads, so it costs no request of its own.
  const characters = useResource(["characters"], useCallback(() => getCharacters(), []));
  const heroes = useMemo<Record<string, HeroImage | null>>(
    () => Object.fromEntries((characters.data ?? []).map((each) => [each.id, each.hero])),
    [characters.data],
  );

  if (!project.data) return null;

  return (
    <Tabs.Root
      value={tab}
      defaultValue={tab}
      onValueChange={(picked) => navigate(projectTabPath(projectId, picked))}
    >
      <ProjectBar record={project.data} heroes={heroes} />
    </Tabs.Root>
  );
}

/**
 * What the delete dialog says is about to go.
 *
 * Spelled out rather than "this project", because the cascade is the part a
 * person cannot see from the header: the runs, scenes and movies go with it,
 * and the sentence is the last chance to notice that.
 */
function deleteSummary(held: number, counts: ProjectRecord["counts"]): string {
  if (held === 0) return "It holds no runs, scenes or movies. Its folder and files go with it.";
  return (
    `${counts.runs} run(s), ${counts.scenes} scene(s) and ${counts.movies} movie(s) ` +
    "go with it, along with the project's folder and everything in it."
  );
}
