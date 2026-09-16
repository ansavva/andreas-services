import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { TestProviders } from "../../test-providers";
import type { FileEntry } from "../../types";

vi.mock("../../utils/download", () => ({ downloadNode: vi.fn().mockResolvedValue(undefined) }));

import { downloadNode } from "../../utils/download";
import { FilePage } from "./FilePage";

afterEach(cleanup);

const FILE: FileEntry = {
  id: "node-1",
  key: "runpod-test/input/wan22_14b_i2v_orbit_high_noise.safetensors",
  name: "wan22_14b_i2v_orbit_high_noise.safetensors",
  size: 153453568,
  last_modified: null,
  kind: "other",
  content_type: "application/octet-stream",
  url: "https://signed.example/x",
};

it("says what the file is, how big, and offers it for download", () => {
  render(
    <MemoryRouter>
      <FilePage file={FILE} onClose={() => {}} />
    </MemoryRouter>,
    { wrapper: TestProviders },
  );
  expect(screen.getByText("LoRA / model weights")).toBeTruthy();
  expect(screen.getByText("146 MB")).toBeTruthy();
  expect(screen.getByText("application/octet-stream")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Download" }));
  expect(downloadNode).toHaveBeenCalledWith("node-1");
});
