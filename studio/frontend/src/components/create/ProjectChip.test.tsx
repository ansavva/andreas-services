import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { TestProviders } from "../../test-providers";
import type { ProjectSummary } from "../../types";
import { ProjectChip } from "./CreateChips";

afterEach(cleanup);

const projects = [
  { id: "proj-a", name: "A test project", hero: null, updated: "", counts: { runs: 12, scenes: 3, movies: 1 } },
  { id: "proj-b", name: "runpod-test", hero: null, updated: "", counts: { runs: 2, scenes: 0, movies: 0 } },
] as ProjectSummary[];

it("says Project until one is picked, then says the name", () => {
  const onProject = vi.fn();
  const { rerender } = render(
    <TestProviders>
      <ProjectChip projects={projects} value={null} onProject={onProject} />
    </TestProviders>,
  );
  expect(screen.getByRole("button", { name: "Project: none" }).textContent).toContain("Project");
  rerender(
    <TestProviders>
      <ProjectChip projects={projects} value="proj-b" onProject={onProject} />
    </TestProviders>,
  );
  expect(screen.getByRole("button", { name: "Project: runpod-test" }).textContent).toContain("runpod-test");
});

it("opens a searchable list, and a press picks the project and closes it", () => {
  const onProject = vi.fn();
  render(
    <TestProviders>
      <ProjectChip projects={projects} value={null} onProject={onProject} />
    </TestProviders>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Project: none" }));
  const list = screen.getByRole("listbox", { name: "Projects" });
  expect(list.querySelectorAll("[role=option]")).toHaveLength(2);

  fireEvent.change(screen.getByRole("textbox", { name: "Search projects" }), {
    target: { value: "runpod" },
  });
  expect(list.querySelectorAll("[role=option]")).toHaveLength(1);

  fireEvent.click(screen.getByRole("option", { name: /runpod-test/ }));
  expect(onProject).toHaveBeenCalledWith("proj-b");
  expect(screen.queryByRole("listbox", { name: "Projects" })).toBeNull();
});
