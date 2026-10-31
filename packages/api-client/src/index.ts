import createClient from "openapi-fetch";

import type { components, paths } from "./schema.js";

export type { components, operations, paths } from "./schema.js";

export type ChatEvent = components["schemas"]["ChatEvent"];

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
