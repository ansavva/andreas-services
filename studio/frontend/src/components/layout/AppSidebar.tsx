import { useCallback, useMemo, type MouseEvent, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Sidebar, useSidebar } from "@ansavva/design-system";

import { getProjects } from "../../apis/studio";
import { useShellSidebar } from "../../context/SidebarContext";
import { useResource } from "../../hooks/useResource";
import {
  CHARACTERS_PATH,
  HOME_PATH,
  PROJECTS_PATH,
  TEMPLATES_PATH,
  folderPath,
  projectPath,
} from "../../utils/location";
import { ApertureMark } from "../common/Aperture";
import { LibrarySwitcher } from "../common/LibrarySwitcher";
import {
  AccountIcon,
  FolderIcon,
  HomeIcon,
  ProjectsIcon,
  SidebarIcon,
  TemplateIcon,
} from "../common/icons";
import { AccountMenu } from "./AccountMenu";

/**
 * The sections, and which addresses light each one.
 *
 * `to` is where the item goes; `under` is every path prefix that counts as
 * being *in* that section — a project's page lights Projects, the way the
 * mockup draws it, and a scene or a movie belongs to a project too. `/f` is
 * the library root and matches every folder under it, which is what keeps
 * Files lit while you browse; an open file is a file, so `/o` is Files as well.
 * Home is exact, because every path starts with `/`.
 *
 * Exported for the phone's bottom tab bar, which draws the same five.
 */
export const DESTINATIONS: ReadonlyArray<{
  to: string;
  label: string;
  icon: ReactNode;
  under: readonly string[];
}> = [
  { to: HOME_PATH, label: "Home", icon: <HomeIcon />, under: [] },
  { to: CHARACTERS_PATH, label: "Characters", icon: <AccountIcon />, under: ["/c/"] },
  { to: PROJECTS_PATH, label: "Projects", icon: <ProjectsIcon />, under: ["/p/", "/s/", "/m/"] },
  { to: folderPath(null), label: "Files", icon: <FolderIcon />, under: ["/f/", "/o/", "/o"] },
  { to: TEMPLATES_PATH, label: "Templates", icon: <TemplateIcon />, under: [] },
];

export function isDestinationActive(
  pathname: string,
  { to, under }: { to: string; under: readonly string[] },
): boolean {
  if (pathname === to) return true;
  return under.some((prefix) => pathname === prefix || pathname.startsWith(prefix));
}

/** How many of the most recently touched projects the sidebar lists. */
const RECENT_PROJECTS = 5;

/**
 * The sidebar's contents, without the sidebar.
 *
 * Two hosts draw these: `AppSidebar`, the sticky column above `md`, and the
 * phone's menu drawer in `TopBar`. What differs is the Toggle — a drawer is
 * dismissed, not collapsed — and what happens after a link is followed, which
 * the drawer needs so it can close. Everything else is one component so the
 * two cannot drift into two menus.
 *
 * `collapsed` is read from the ENCLOSING `Sidebar.Root`, not from the shell
 * context: the drawer pins its Root open, and a rail collapsed on a desktop
 * must not come back as a column of icons when the window narrows to a phone.
 */
export function SidebarContents({
  toggle = true,
  onNavigate,
}: {
  /** Draw the collapse control. Off in the drawer. */
  toggle?: boolean;
  /** Told after a link is followed — the drawer closes on it. */
  onNavigate?: () => void;
}) {
  const { collapsed } = useSidebar();
  const { pathname } = useLocation();

  return (
    <>
      {/* Stacked when collapsed: the 64px rail cannot hold the mark and the
          toggle side by side, so the toggle drops under it — the same two
          things, one column. */}
      <Sidebar.Head className={collapsed ? "flex-col items-center gap-2 px-0" : ""}>
        <Sidebar.Logo>
          <ApertureMark size="lg" />
        </Sidebar.Logo>
        <Sidebar.Title>Studio</Sidebar.Title>
        {toggle && (
          <Sidebar.Toggle className={`rounded-none ${collapsed ? "ml-0" : ""}`}>
            <SidebarIcon className="size-4 fill-none stroke-current stroke-[1.5]" />
          </Sidebar.Toggle>
        )}
      </Sidebar.Head>

      <Sidebar.Nav label="Sections">
        <Sidebar.Section title="Library">
          {DESTINATIONS.map((each) => (
            <NavItem
              key={each.to}
              to={each.to}
              label={each.label}
              icon={each.icon}
              active={isDestinationActive(pathname, each)}
              onNavigate={onNavigate}
            />
          ))}
        </Sidebar.Section>

        {/* Nothing to draw a project as in a 64px rail — it has no icon — so
            the section goes with the labels rather than leaving five unnamed
            44px links. */}
        {!collapsed && (
          <>
            <Sidebar.Separator />
            <RecentProjects pathname={pathname} onNavigate={onNavigate} />
          </>
        )}
      </Sidebar.Nav>

      <Sidebar.Footer className={collapsed ? "items-center px-0" : ""}>
        {/* Renders nothing while the caller is in one library. A `Select` has
            no 64px form, so it goes with the labels too. */}
        {!collapsed && <LibrarySwitcher />}
        <AccountMenu collapsed={collapsed} />
      </Sidebar.Footer>
    </>
  );
}

/**
 * A `Sidebar.Item` the router takes.
 *
 * The package's item is a real `<a href>` — middle-click, copy address — and
 * the router intercepts only a plain click, the same bargain `PageBar`'s crumbs
 * strike. `preventDefault` is what stops the full reload the `href` would
 * otherwise cause.
 */
function NavItem({
  to,
  label,
  icon,
  active,
  onNavigate,
}: {
  to: string;
  label: string;
  icon?: ReactNode;
  active: boolean;
  onNavigate?: () => void;
}) {
  const navigate = useNavigate();
  const onClick = useCallback(
    (event: MouseEvent<HTMLAnchorElement>) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      navigate(to);
      onNavigate?.();
    },
    [navigate, onNavigate, to],
  );

  return (
    <Sidebar.Item
      href={to}
      label={label}
      icon={icon}
      active={active}
      onClick={onClick}
      className="rounded-none"
    />
  );
}

/**
 * The projects touched most recently, so the one being worked on is a click
 * away from every screen.
 *
 * Reads the same `["projects"]` query the search box and the Projects page
 * do, so it costs no request of its own; `updated` is what the listing sorts
 * on and what this sorts on, for the reason `WEB_APP.md` gives — a list
 * ordered by a date it does not show reads as a bug.
 *
 * TODO(slice 4): a project with a run in flight shows an `ApertureSpinner`
 * beside its name. Nothing cheap answers "which projects have a running run"
 * yet — `ProjectSummary.counts` has no `running`, and `GET /api/runs?status=`
 * is one request per project — so the spinner waits for the feed slice's
 * in-flight query.
 */
function RecentProjects({
  pathname,
  onNavigate,
}: {
  pathname: string;
  onNavigate?: () => void;
}) {
  const { data } = useResource(["projects"], useCallback(() => getProjects(), []));

  const recent = useMemo(
    () =>
      [...(data ?? [])]
        .sort((a, b) => (a.updated < b.updated ? 1 : a.updated > b.updated ? -1 : 0))
        .slice(0, RECENT_PROJECTS),
    [data],
  );

  if (recent.length === 0) return null;

  return (
    <Sidebar.Section title="Recent projects">
      {recent.map((project) => (
        <NavItem
          key={project.id}
          to={projectPath(project.id)}
          label={project.name}
          active={pathname === projectPath(project.id)}
          onNavigate={onNavigate}
        />
      ))}
    </Sidebar.Section>
  );
}

/**
 * The sidebar: 256px of navigation, or a 64px rail of icons, down the left of
 * every screen above `md`.
 *
 * **Sticky and viewport-tall**, so it stays put while a long grid scrolls past
 * it; `Sidebar.Nav` is the part that scrolls if the recent list ever outgrows
 * the height. The collapse state is `SidebarContext`'s rather than the
 * package's own, so the top bar's menu button and the opened-run screen can
 * reach it — see there.
 *
 * Below `md` it is not drawn at all. The same contents open in a drawer from
 * the top bar's menu button, which is what a 390px screen has room for.
 */
export function AppSidebar() {
  const { collapsed, setCollapsed } = useShellSidebar();

  return (
    <Sidebar.Root
      collapsed={collapsed}
      onCollapsedChange={setCollapsed}
      className="sticky top-0 z-30 hidden h-dvh shrink-0 md:flex"
    >
      <SidebarContents />
    </Sidebar.Root>
  );
}
