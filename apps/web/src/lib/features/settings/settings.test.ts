import { describe, expect, it } from "vitest";

import { SettingsStore } from "./settings.svelte";

describe("SettingsStore", () => {
  it("is available in the shell", () => {
    const settings = new SettingsStore();
    expect(settings.ready).toBe(true);
  });
});
