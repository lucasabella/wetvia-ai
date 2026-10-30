import { describe, expect, it } from "vitest";

import { isNarrowViewport } from "./viewport";

describe("isNarrowViewport", () => {
  it("uses a bottom sheet below 768 px", () => {
    expect(isNarrowViewport(767)).toBe(true);
    expect(isNarrowViewport(375)).toBe(true);
  });

  it("keeps the sources column from 768 px", () => {
    expect(isNarrowViewport(768)).toBe(false);
    expect(isNarrowViewport(1280)).toBe(false);
  });
});
