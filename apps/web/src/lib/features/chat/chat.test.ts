import { describe, expect, it } from "vitest";

import { ChatStore } from "./chat.svelte";

describe("ChatStore", () => {
  it("starts without messages", () => {
    const chat = new ChatStore();
    expect(chat.messages).toEqual([]);
  });
});
