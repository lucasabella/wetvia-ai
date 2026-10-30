import { describe, expect, it } from "vitest";

import { appName } from "./index";

describe("web skeleton", () => {
  it("names the app", () => {
    expect(appName).toBe("wetvia");
  });
});
