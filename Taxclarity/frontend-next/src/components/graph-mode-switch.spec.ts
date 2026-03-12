import { describe, expect, it } from "vitest";

import { getGraphModeLabel } from "@/components/graph-mode-switch";

describe("getGraphModeLabel", () => {
  it("returns a label for combined mode", () => {
    expect(getGraphModeLabel("combined")).toBe("Combined");
  });
});
