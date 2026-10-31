import { describe, expect, it } from "vitest";

import type { ChatEvent, components } from "@wetvia/api-client";
import { SourcesStore, type ChatSourceCard } from "../sources/sources.svelte";
import {
  ChatStore,
  buildChatRequest,
  currentDateISO,
  formatAnswerDate,
} from "./chat.svelte";

const chunkId = "1d44e29c-b982-4f28-b789-c5cd24fa2de8";

describe("ChatStore", () => {
  it("starts with no messages or persisted conversation", () => {
    const chat = new ChatStore(emptyStream, new SourcesStore());
    expect(chat.turns).toEqual([]);
    expect(chat.sending).toBe(false);
  });

  it("streams turn sources and the verified answer into the same shell state", async () => {
    const sources = new SourcesStore();
    const sourceCard = syntheticSource();
    const answer = syntheticAnswer([chunkId]);
    const chat = new ChatStore(async function* (): AsyncGenerator<ChatEvent> {
      yield { type: "sources", sources: [sourceCard] };
      yield { type: "answer", answer };
      yield { type: "done" };
    }, sources);
    chat.draft = "Synthetic interface question?";

    await chat.submit();

    expect(chat.turns).toHaveLength(1);
    expect(chat.turns[0]).toMatchObject({
      question: "Synthetic interface question?",
      status: "answered",
      sources: [sourceCard],
      answer,
    });
    expect(sources.items).toEqual([sourceCard]);
    expect(sources.activeTurnId).toBe(chat.turns[0].id);
  });

  it("selects a citation only from that turn's source cards", async () => {
    const sources = new SourcesStore();
    const sourceCard = syntheticSource();
    const chat = new ChatStore(async function* (): AsyncGenerator<ChatEvent> {
      yield { type: "sources", sources: [sourceCard] };
      yield { type: "answer", answer: syntheticAnswer([chunkId]) };
      yield { type: "done" };
    }, sources);
    await chat.submit("Synthetic interface question?");

    expect(chat.selectSource(chat.turns[0].id, chunkId)).toBe(true);
    expect(sources.selectedChunkId).toBe(chunkId);
    expect(chat.selectSource(chat.turns[0].id, "unknown")).toBe(false);
  });

  it("keeps a prior conversation within the API message limit", () => {
    const turns = Array.from({ length: 30 }, (_, index) => ({
      id: `turn-${index}`,
      question: `Synthetic question ${index}`,
      status: "answered" as const,
      sources: [],
      answer: syntheticAnswer([]),
      errorMessage: null,
    }));

    const request = buildChatRequest(
      turns,
      "Current synthetic question",
      "2026-10-31",
    );

    expect(request.messages).toHaveLength(39);
    expect(request.messages.at(-1)).toEqual({
      role: "user",
      content: "Current synthetic question",
    });
    expect(request.messages[0]?.content).toBe("Synthetic question 11");
    expect(request.peildatum).toBe("2026-10-31");
  });

  it("does not submit an empty or overlapping turn", async () => {
    let calls = 0;
    const chat = new ChatStore(async function* (): AsyncGenerator<ChatEvent> {
      calls += 1;
      yield { type: "sources", sources: [] };
      yield { type: "answer", answer: syntheticAnswer([]) };
      yield { type: "done" };
    }, new SourcesStore());
    await chat.submit("   ");
    const running = chat.submit("Synthetic interface question?");
    await chat.submit("A second question while busy");
    await running;

    expect(calls).toBe(1);
    expect(chat.turns).toHaveLength(1);
  });
});

describe("chat display helpers", () => {
  it("formats dates without depending on locale defaults", () => {
    expect(formatAnswerDate("2026-10-31")).toBe("31-10-2026");
    expect(currentDateISO(Date.UTC(2026, 9, 31, 12))).toBe("2026-10-31");
  });
});

function syntheticSource(): ChatSourceCard {
  return {
    label: "[1]",
    chunk_id: chunkId,
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

function syntheticAnswer(
  bronIds: string[],
): components["schemas"]["VerifiedAnswer"] {
  return {
    status: "beantwoord",
    samenvatting: "Synthetic answer for interface testing.",
    punten: bronIds.length
      ? [{ tekst: "Synthetic supported point.", bron_ids: bronIds }]
      : [],
    voorbehouden: [],
    vervolgstappen: [],
    peildatum: "2026-10-31",
    verifier_notes: [],
  };
}

async function* emptyStream(): AsyncGenerator<ChatEvent> {
  // Empty iterator for construction-only coverage.
}
