import { describe, expect, it } from "vitest";

import { DESKTOP_MEDIA_QUERY, sheetStaysOpen } from "./sheets";

describe("sheetStaysOpen", () => {
  it("closes an open sheet once the desktop breakpoint applies", () => {
    expect(DESKTOP_MEDIA_QUERY).toBe("(min-width: 768px)");
    expect(sheetStaysOpen(true, true)).toBe(false);
    expect(sheetStaysOpen(false, true)).toBe(false);
  });

  it("keeps the open state below the desktop breakpoint", () => {
    expect(sheetStaysOpen(true, false)).toBe(true);
    expect(sheetStaysOpen(false, false)).toBe(false);
  });
});
