import createClient from "openapi-fetch";

import type { components, paths } from "./schema.js";

export type { components, operations, paths } from "./schema.js";

export type ChatEvent = components["schemas"]["ChatEvent"];
export type ChatRequest = components["schemas"]["ChatRequest"];

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
          yield event;
        }
      }
    }
    if (buffer.trim()) {
      const event = parseSseFrame(buffer);
      if (event !== undefined) {
        yield event;
      }
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
      if (!Array.isArray(payload.sources)) {
        throw new Error("Invalid sources SSE envelope.");
      }
      return payload as ChatEvent;
    case "answer":
      if (!isRecord(payload.answer)) {
        throw new Error("Invalid answer SSE envelope.");
      }
      return payload as ChatEvent;
    case "error":
      if (typeof payload.message !== "string") {
        throw new Error("Invalid error SSE envelope.");
      }
      return payload as ChatEvent;
    case "done":
      return payload as ChatEvent;
    default:
      throw new Error(`Unsupported SSE event: ${eventName || "(missing)"}.`);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
