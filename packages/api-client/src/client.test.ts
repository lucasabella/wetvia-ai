import { describe, expect, it } from "vitest";

import {
  createWetviaClient,
  streamChatEvents,
  type ChatEvent,
  type ChatRequest,
} from "./index.js";

describe("createWetviaClient", () => {
  it("uses the injected fetch implementation", async () => {
    let requestedUrl = "";
    const injectedFetch: typeof fetch = async (input) => {
      requestedUrl = input instanceof Request ? input.url : String(input);
      return new Response(
        JSON.stringify({
          status: "ok",
          db: "ok",
          llm_provider: "ollama",
          version: "test",
        }),
        { headers: { "content-type": "application/json" } },
      );
    };
    const client = createWetviaClient({
      baseUrl: "https://wetvia.example.test",
      fetch: injectedFetch,
    });

    const { data, error } = await client.GET("/api/health");

    expect(error).toBeUndefined();
    expect(data?.status).toBe("ok");
    expect(requestedUrl).toBe("https://wetvia.example.test/api/health");
  });

  it("exposes the generated SSE event union and verified answer envelope", () => {
    const events: ChatEvent[] = [
      { type: "sources", sources: [] },
      {
        type: "answer",
        answer: {
          status: "onzeker",
          samenvatting: "Synthetic uncertain response.",
          punten: [],
          voorbehouden: [],
          vervolgstappen: [],
          peildatum: "2026-10-31",
          verifier_notes: ["server-side diagnostic"],
        },
      },
      { type: "error", message: "Synthetic stream error." },
      { type: "done" },
    ];

    expect(events.map((event) => event.type)).toEqual([
      "sources",
      "answer",
      "error",
      "done",
    ]);
  });

  it("parses SSE frames incrementally and preserves typed answer data", async () => {
    const encoder = new TextEncoder();
    const sourceFrame = `event: sources\ndata: ${JSON.stringify({ type: "sources", sources: [] })}\n\n`;
    const answerFrame = `event: answer\ndata: ${JSON.stringify({
      type: "answer",
      answer: {
        status: "onzeker",
        samenvatting: "Onzeker — synthetic",
        punten: [],
        voorbehouden: [],
        vervolgstappen: [],
        peildatum: "2026-10-31",
        verifier_notes: ["checked by server"],
      },
    })}\n\n`;
    const sourceBytes = encoder.encode(sourceFrame);
    const answerBytes = encoder.encode(answerFrame);
    const sourceSplit = Math.floor(sourceBytes.length / 2);
    const unicodeStart = answerBytes.indexOf(0xe2);
    expect(unicodeStart).toBeGreaterThan(0);

    let releaseAnswer!: () => void;
    const answerAllowed = new Promise<void>((resolve) => {
      releaseAnswer = resolve;
    });
    const body = new ReadableStream<Uint8Array>({
      async start(controller) {
        controller.enqueue(sourceBytes.slice(0, sourceSplit));
        controller.enqueue(sourceBytes.slice(sourceSplit));
        await answerAllowed;
        controller.enqueue(answerBytes.slice(0, unicodeStart + 1));
        controller.enqueue(answerBytes.slice(unicodeStart + 1));
        controller.close();
      },
    });
    const client = createWetviaClient({
      baseUrl: "https://wetvia.example.test",
      fetch: async () =>
        new Response(body, {
          headers: { "content-type": "text/event-stream" },
        }),
    });
    const request: ChatRequest = {
      messages: [{ role: "user", content: "Synthetic question?" }],
      peildatum: "2026-10-31",
    };
    const events = streamChatEvents(client, request);

    try {
      const first = await events.next();
      expect(first.done).toBe(false);
      expect(first.value).toEqual({ type: "sources", sources: [] });

      releaseAnswer();
      const second = await events.next();
      expect(second.done).toBe(false);
      expect(second.value).toMatchObject({
        type: "answer",
        answer: {
          samenvatting: "Onzeker — synthetic",
          verifier_notes: ["checked by server"],
        },
      });
      expect(await events.next()).toMatchObject({ done: true });
    } finally {
      releaseAnswer();
      await events.return(undefined);
    }
  });
});
