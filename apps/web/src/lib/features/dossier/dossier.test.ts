import { describe, expect, it } from "vitest";

import { DossierStore } from "./dossier.svelte";

describe("DossierStore", () => {
  it("starts without dossiers", () => {
    const dossier = new DossierStore();
    expect(dossier.items).toEqual([]);
  });
});
