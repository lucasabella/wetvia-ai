import { describe, expect, it } from "vitest";

import { createWetviaClient, type ChatEvent } from "./index.js";

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
});
