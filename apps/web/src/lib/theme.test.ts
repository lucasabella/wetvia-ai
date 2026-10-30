import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

describe("house style", () => {
  it("keeps the documented color tokens and self-hosted fonts", () => {
    const css = readFileSync(
      resolve(root, "src/routes/layout.css"),
      "utf8",
    ).toLowerCase();
    for (const token of [
      "#fafaf7",
      "#1b1f24",
      "#1f4e79",
      "#e8eff6",
      "#2e7d4f",
      "#2563eb",
      "#6b7280",
      "#7c3aed",
      "#b45309",
      "#fef3c7",
      "#111418",
      "#e6e8eb",
      "#7fb0e0",
    ]) {
      expect(css).toContain(token);
    }
    expect(css).toContain("@fontsource-variable/inter");
    expect(css).toContain("@fontsource-variable/source-serif-4");
    expect(css).not.toContain("fonts.googleapis.com");
  });

  it("ships the section-mark logo in static", () => {
    const svg = readFileSync(resolve(root, "static/logo.svg"), "utf8");
    expect(svg).toContain("<svg");
    expect(svg).toContain("Wetvia");
    expect(svg.toLowerCase()).not.toContain("fonts.googleapis");
  });
});
