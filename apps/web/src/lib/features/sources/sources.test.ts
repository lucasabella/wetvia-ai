import { describe, expect, it } from "vitest";

import { SourcesStore } from "./sources.svelte";

describe("SourcesStore", () => {
  it("starts without sources", () => {
    const sources = new SourcesStore();
    expect(sources.items).toEqual([]);
  });
});
