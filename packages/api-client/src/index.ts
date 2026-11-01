import createClient from "openapi-fetch";

import type { components, paths } from "./schema.js";

export type { components, operations, paths } from "./schema.js";

export type ChatEvent = components["schemas"]["ChatEvent"];
export type ChatRequest = components["schemas"]["ChatRequest"];
export type DakkapelRuleRequest = components["schemas"]["DakkapelRuleRequest"];
export type DakkapelRuleResponse =
  components["schemas"]["DakkapelRuleResponse"];

export type WetviaClientOptions = {
  baseUrl: string;
  fetch?: typeof globalThis.fetch;
};

export function createWetviaClient({
  baseUrl,
  fetch = globalThis.fetch,
}: WetviaClientOptions) {
  return createClient<paths>({ baseUrl, fetch });
}

export type WetviaClient = ReturnType<typeof createWetviaClient>;

export async function* streamChatEvents(
  client: WetviaClient,
  request: ChatRequest,
  options: { signal?: AbortSignal } = {},
): AsyncGenerator<ChatEvent> {
  const result = await client.POST("/api/chat", {
    body: request,
    parseAs: "stream",
    signal: options.signal,
  });
  if (!("data" in result) || !result.data) {
    throw new Error(`Chat request failed with HTTP ${result.response.status}.`);
  }
  yield* parseChatEventStream(result.data);
}

export async function* parseChatEventStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<ChatEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let reachedEnd = false;
  let sawDone = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        reachedEnd = true;
        buffer += decoder.decode();
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      while (true) {
        const frame = takeSseFrame(buffer);
        if (frame === undefined) {
          break;
        }
        buffer = frame.rest;
        const event = parseSseFrame(frame.content);
        if (event !== undefined) {
          if (sawDone) {
            throw new Error("SSE event received after done.");
          }
          sawDone = event.type === "done";
          yield event;
        }
      }
    }
    if (buffer.trim()) {
      const event = parseSseFrame(buffer);
      if (event !== undefined) {
        if (sawDone) {
          throw new Error("SSE event received after done.");
        }
        sawDone = event.type === "done";
        yield event;
      }
    }
    if (!sawDone) {
      throw new Error("SSE stream ended before the done event.");
    }
  } finally {
    if (!reachedEnd) {
      await reader.cancel().catch(() => undefined);
    }
    reader.releaseLock();
  }
}

function takeSseFrame(
  buffer: string,
): { content: string; rest: string } | undefined {
  const separator = /\r?\n\r?\n/.exec(buffer);
  if (separator === null || separator.index === undefined) {
    return undefined;
  }
  return {
    content: buffer.slice(0, separator.index),
    rest: buffer.slice(separator.index + separator[0].length),
  };
}

function parseSseFrame(frame: string): ChatEvent | undefined {
  let eventName = "";
  const dataLines: string[] = [];
  for (const line of frame.split(/\r\n|\r|\n/)) {
    if (!line || line.startsWith(":")) {
      continue;
    }
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    const rawValue = separator === -1 ? "" : line.slice(separator + 1);
    const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;
    if (field === "event") {
      eventName = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }
  if (dataLines.length === 0) {
    return undefined;
  }

  const payload: unknown = JSON.parse(dataLines.join("\n"));
  if (!isRecord(payload) || payload.type !== eventName) {
    throw new Error("SSE event name and JSON envelope do not match.");
  }
  switch (eventName) {
    case "sources":
      if (
        !hasOnlyKeys(payload, ["type", "sources"]) ||
        !Array.isArray(payload.sources) ||
        !payload.sources.every(isChatSourceCard)
      ) {
        throw new Error("Invalid sources SSE envelope.");
      }
      return payload as ChatEvent;
    case "answer":
      if (
        !hasOnlyKeys(payload, ["type", "answer"]) ||
        !isVerifiedAnswer(payload.answer)
      ) {
        throw new Error("Invalid answer SSE envelope.");
      }
      return payload as ChatEvent;
    case "error":
      if (
        !hasOnlyKeys(payload, ["type", "message"]) ||
        typeof payload.message !== "string" ||
        payload.message.length === 0
      ) {
        throw new Error("Invalid error SSE envelope.");
      }
      return payload as ChatEvent;
    case "done":
      if (!hasOnlyKeys(payload, ["type"])) {
        throw new Error("Invalid done SSE envelope.");
      }
      return payload as ChatEvent;
    default:
      throw new Error(`Unsupported SSE event: ${eventName || "(missing)"}.`);
  }
}

function isChatSourceCard(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ["label", "chunk_id", "tekst", "metadata", "score"])
  ) {
    return false;
  }
  return (
    typeof value.label === "string" &&
    /^\[[1-8]\]$/.test(value.label) &&
    isUuid(value.chunk_id) &&
    typeof value.tekst === "string" &&
    isSourceMetadata(value.metadata) &&
    typeof value.score === "number" &&
    Number.isFinite(value.score)
  );
}

function isSourceMetadata(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }
  const requiredStrings = [
    "bwb_id",
    "regeling_titel",
    "artikel",
    "kop_pad",
    "bron_url",
    "toestand_url",
  ];
  return (
    requiredStrings.every((key) => typeof value[key] === "string") &&
    ["lid", "onderdeel", "opschrift"].every(
      (key) => value[key] === null || typeof value[key] === "string",
    ) &&
    isDateString(value.geldig_vanaf) &&
    (value.geldig_tot === null || isDateString(value.geldig_tot)) &&
    ["geldend", "toekomstig", "vervallen"].includes(String(value.status)) &&
    ["geldend", "vervallen"].includes(String(value.artikel_status))
  );
}

function isVerifiedAnswer(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, [
      "status",
      "samenvatting",
      "punten",
      "voorbehouden",
      "vervolgstappen",
      "peildatum",
      "verifier_notes",
    ])
  ) {
    return false;
  }
  if (
    !["beantwoord", "onzeker", "buiten_scope"].includes(String(value.status)) ||
    typeof value.samenvatting !== "string" ||
    value.samenvatting.trim().length === 0 ||
    value.samenvatting.trim().split(/\s+/).length > 80 ||
    !Array.isArray(value.punten) ||
    !value.punten.every(isAnswerPoint) ||
    (value.status === "beantwoord" && value.punten.length === 0) ||
    !isNonblankStringArray(value.voorbehouden) ||
    !Array.isArray(value.vervolgstappen) ||
    !value.vervolgstappen.every(isFollowUpStep) ||
    !isDateString(value.peildatum) ||
    (value.verifier_notes !== undefined &&
      !isNonblankStringArray(value.verifier_notes))
  ) {
    return false;
  }
  return true;
}

function isAnswerPoint(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, ["tekst", "bron_ids"])) {
    return false;
  }
  return (
    typeof value.tekst === "string" &&
    value.tekst.trim().length > 0 &&
    Array.isArray(value.bron_ids) &&
    value.bron_ids.length > 0 &&
    value.bron_ids.every(isUuid) &&
    new Set(value.bron_ids).size === value.bron_ids.length
  );
}

function isFollowUpStep(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, ["tekst", "url"])) {
    return false;
  }
  if (typeof value.tekst !== "string" || value.tekst.trim().length === 0) {
    return false;
  }
  if (typeof value.url !== "string") {
    return false;
  }
  try {
    const protocol = new URL(value.url).protocol;
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function isNonblankStringArray(value: unknown): value is string[] {
  return isStringArray(value) && value.every((item) => item.trim().length > 0);
}

function isUuid(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      value,
    )
  );
}

function isDateString(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const date = new Date(`${value}T00:00:00.000Z`);
  return (
    Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
  );
}

function hasOnlyKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).every((key) => keys.includes(key));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
