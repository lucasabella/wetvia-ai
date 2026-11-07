import { describe, expect, it } from "vitest";

import type { components } from "@wetvia/api-client";
import {
  SourcesStore,
  citationLabelFor,
  formatDate,
  formatValidity,
  sourceBadge,
  type SourceMetadata,
} from "./sources.svelte";

describe("SourcesStore", () => {
  it("starts without sources and keeps selection attached to its turn", () => {
    const sources = new SourcesStore();
    expect(sources.items).toEqual([]);

    sources.showTurn("turn-1", [syntheticSource()]);
    sources.selectChunk(syntheticSource().chunk_id);

    expect(sources.activeTurnId).toBe("turn-1");
    expect(sources.selectedChunkId).toBe(syntheticSource().chunk_id);
    expect(sources.selectionRevision).toBe(2);

    sources.showTurn("turn-2", []);
    expect(sources.selectedChunkId).toBeNull();
    expect(sources.items).toEqual([]);

    sources.showTurn("turn-3", [syntheticSource()]);
    sources.clear();
    expect(sources.activeTurnId).toBeNull();
    expect(sources.selectedChunkId).toBeNull();
    expect(sources.items).toEqual([]);
  });

  it("maps API source status and formats open-ended validity", () => {
    const source = syntheticSource();
    expect(sourceBadge(source.metadata).label).toBe("Geldend");
    expect(formatValidity(source.metadata)).toBe(
      "Geldig van 01-01-2026 t/m heden",
    );
    expect(formatDate("2026-10-31")).toBe("31-10-2026");

    const future = { ...source.metadata, status: "toekomstig" as const };
    expect(sourceBadge(future).label).toBe("Toekomstig");
    const proposal = {
      ...source.metadata,
      status: "voorstel",
    } as unknown as SourceMetadata;
    expect(sourceBadge(proposal).label).toBe("Wetsvoorstel");
    const repealed = {
      ...source.metadata,
      artikel_status: "vervallen" as const,
    };
    expect(sourceBadge(repealed).label).toBe("Vervallen");
  });

  it("uses exact source IDs to find citation labels", () => {
    const source = syntheticSource();
    expect(citationLabelFor([source], source.chunk_id)).toBe("[1]");
    expect(citationLabelFor([source], "unknown")).toBeUndefined();
  });
});

function syntheticSource(): components["schemas"]["ChatSourceCard"] {
  return {
    label: "[1]",
    chunk_id: "1d44e29c-b982-4f28-b789-c5cd24fa2de8",
    tekst: "Synthetic source excerpt for interface testing.",
    score: 0.5,
    metadata: {
      bwb_id: "synthetic-interface-fixture",
      regeling_titel: "Synthetic test source",
      artikel: "Test item",
      kop_pad: "Interface fixture",
      bron_url: "https://example.test/synthetic-source",
      toestand_url: "https://example.test/synthetic-state",
      lid: null,
      onderdeel: null,
      opschrift: null,
      geldig_vanaf: "2026-01-01",
      geldig_tot: null,
      status: "geldend",
      artikel_status: "geldend",
    },
  };
}
