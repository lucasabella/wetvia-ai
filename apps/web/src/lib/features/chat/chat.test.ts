import { describe, expect, it } from "vitest";

import type { ChatEvent, ChatRequest, components } from "@wetvia/api-client";
import { SourcesStore, type ChatSourceCard } from "../sources/sources.svelte";
import { ConversationHistoryStore } from "./conversation-history.svelte";
import type {
  ConversationListResult,
  ConversationPatch,
  ConversationRepository,
  StoredConversation,
} from "./conversation-repository";
import {
  ChatStore,
  CLOUD_CONSENT_VERSION,
  buildChatRequest,
  currentDateISO,
  formatAnswerDate,
} from "./chat.svelte";

const chunkId = "1d44e29c-b982-4f28-b789-c5cd24fa2de8";

describe("ChatStore", () => {
  it("starts with no messages or persisted conversation", () => {
    const chat = new ChatStore(
      emptyStream,
      new SourcesStore(),
      new ConversationHistoryStore(new MemoryConversationRepository()),
    );
    expect(chat.turns).toEqual([]);
    expect(chat.sending).toBe(false);
  });

  it("streams turn sources and the verified answer into the same shell state", async () => {
    const sources = new SourcesStore();
    const sourceCard = syntheticSource();
    const answer = syntheticAnswer([chunkId]);
    const chat = await createChat(
      async function* (): AsyncGenerator<ChatEvent> {
        yield { type: "sources", sources: [sourceCard] };
        yield { type: "answer", answer };
        yield { type: "done" };
      },
      sources,
    );
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
    const chat = await createChat(
      async function* (): AsyncGenerator<ChatEvent> {
        yield { type: "sources", sources: [sourceCard] };
        yield { type: "answer", answer: syntheticAnswer([chunkId]) };
        yield { type: "done" };
      },
      sources,
    );
    await chat.submit("Synthetic interface question?");

    expect(chat.selectSource(chat.turns[0].id, chunkId)).toBe(true);
    expect(sources.selectedChunkId).toBe(chunkId);
    expect(chat.selectSource(chat.turns[0].id, "unknown")).toBe(false);
  });

  it("restores a conversation and citations without a network replay", async () => {
    const repository = new MemoryConversationRepository();
    const history = new ConversationHistoryStore(repository);
    const sources = new SourcesStore();
    const sourceCard = syntheticSource();
    const answer = {
      ...syntheticAnswer([chunkId]),
      verifier_notes: ["Synthetic private verifier diagnostic"],
    };
    let calls = 0;
    const stream = async function* (): AsyncGenerator<ChatEvent> {
      calls += 1;
      yield { type: "sources", sources: [sourceCard] };
      yield { type: "answer", answer };
      yield { type: "done" };
    };
    const chat = new ChatStore(stream, sources, history);
    await chat.hydrate();
    await chat.submit("Synthetic persistent question?");

    const saved = await repository.get(chat.activeConversationId!);
    expect(saved?.schemaVersion).toBe(2);
    expect(saved?.mode).toBe("local");
    expect(saved?.cloudConsentVersion).toBeNull();
    expect(saved?.messages[0]?.answer?.verifier_notes).toEqual([]);

    const restoredSources = new SourcesStore();
    const restored = new ChatStore(
      stream,
      restoredSources,
      new ConversationHistoryStore(repository),
    );
    await restored.hydrate();

    expect(calls).toBe(1);
    expect(restored.turns[0]).toMatchObject({
      question: "Synthetic persistent question?",
      status: "answered",
      sources: [sourceCard],
    });
    expect(restoredSources.items).toEqual([sourceCard]);
    expect(restored.selectSource(restored.turns[0]!.id, chunkId)).toBe(true);
    expect(restoredSources.selectedChunkId).toBe(chunkId);
  });

  it("keeps local as the default and persists cloud consent before cloud generation", async () => {
    const repository = new MemoryConversationRepository();
    const history = new ConversationHistoryStore(repository);
    const requests: ChatRequest[] = [];
    let persistedBeforeGeneration: StoredConversation | undefined;
    const chat = new ChatStore(
      async function* (request): AsyncGenerator<ChatEvent> {
        requests.push(request);
        persistedBeforeGeneration = await repository.get(
          chat.activeConversationId!,
        );
        yield { type: "sources", sources: [] };
        yield { type: "answer", answer: syntheticAnswer([]) };
        yield { type: "done" };
      },
      new SourcesStore(),
      history,
    );
    chat.setConfiguredChatModes({ local: true, cloud: true });
    await chat.hydrate();

    expect(chat.activeMode).toBe("local");
    expect(await chat.selectMode("cloud")).toBe("consent-required");
    expect(chat.activeMode).toBe("local");
    expect(await chat.confirmCloudConsent()).toBe(true);
    expect(chat.activeMode).toBe("cloud");

    await chat.submit("Synthetic question for cloud processing?");

    expect(requests[0]?.mode).toBe("cloud");
    expect(requests[0]?.messages).toEqual([
      { role: "user", content: "Synthetic question for cloud processing?" },
    ]);
    expect(persistedBeforeGeneration).toMatchObject({
      mode: "cloud",
      cloudConsentVersion: CLOUD_CONSENT_VERSION,
      messages: [
        {
          question: "Synthetic question for cloud processing?",
          status: "pending",
        },
      ],
    });
    expect(
      Date.parse(persistedBeforeGeneration!.cloudConsentAt!),
    ).not.toBeNaN();
  });

  it("blocks cloud generation when the provider is unavailable or consent is stale", async () => {
    let calls = 0;
    const chat = await createChat(
      async function* (): AsyncGenerator<ChatEvent> {
        calls += 1;
        yield { type: "done" };
      },
      new SourcesStore(),
    );
    chat.draft = "Synthetic privacy boundary question?";
    chat.setConfiguredChatModes({ local: true, cloud: false });
    expect(await chat.selectMode("cloud")).toBe("unavailable");
    chat.activeMode = "cloud";
    await chat.submit();
    expect(calls).toBe(0);
    expect(chat.draft).toBe("Synthetic privacy boundary question?");

    chat.setConfiguredChatModes({ local: true, cloud: true });
    await chat.submit();
    expect(calls).toBe(0);
    expect(chat.notice).toBe("Bevestig eerst de verwerking in Cloud (EU).");
  });

  it("requires renewed consent for a restored cloud conversation before sending", async () => {
    const repository = new MemoryConversationRepository();
    const legacyCloudConversation = {
      ...syntheticConversation(
        "legacy-cloud-conversation",
        "Synthetic saved cloud question",
        "2026-10-31T12:00:00.000Z",
      ),
      mode: "cloud" as const,
    };
    await repository.create(legacyCloudConversation);
    let calls = 0;
    const requests: ChatRequest[] = [];
    const history = new ConversationHistoryStore(repository);
    const chat = new ChatStore(
      async function* (request): AsyncGenerator<ChatEvent> {
        calls += 1;
        requests.push(request);
        yield { type: "sources", sources: [] };
        yield { type: "answer", answer: syntheticAnswer([]) };
        yield { type: "done" };
      },
      new SourcesStore(),
      history,
    );
    chat.setConfiguredChatModes({ local: true, cloud: true });
    await chat.hydrate();
    chat.draft = "Synthetic restored cloud follow-up?";

    expect(chat.activeMode).toBe("cloud");
    expect(chat.requiresCloudConsent).toBe(true);
    await chat.submit();
    expect(calls).toBe(0);
    expect(chat.draft).toBe("Synthetic restored cloud follow-up?");

    expect(await chat.selectMode("cloud")).toBe("consent-required");
    expect(await chat.confirmCloudConsent()).toBe(true);
    await chat.submit();
    expect(calls).toBe(1);
    expect(requests[0]?.mode).toBe("cloud");
    expect(requests[0]?.messages).toEqual([
      { role: "user", content: "Synthetic restored cloud follow-up?" },
    ]);
    expect(await repository.get("legacy-cloud-conversation")).toMatchObject({
      mode: "cloud",
      cloudConsentVersion: CLOUD_CONSENT_VERSION,
    });
  });

  it("does not select a locally unavailable mode through the store API", async () => {
    const chat = await createChat(emptyStream, new SourcesStore());
    chat.setConfiguredChatModes({ local: false, cloud: true });

    expect(await chat.selectMode("local")).toBe("unavailable");
    expect(chat.activeMode).toBe("local");
  });

  it("does not apply a delayed mode write after switching conversations", async () => {
    const repository = new DelayedUpdateConversationRepository();
    const cloudConversation = {
      ...syntheticConversation(
        "conversation-cloud",
        "Synthetic cloud conversation",
        "2026-10-01T12:00:00.000Z",
      ),
      mode: "cloud" as const,
      cloudConsentVersion: CLOUD_CONSENT_VERSION,
      cloudConsentAt: "2026-10-01T12:00:00.000Z",
    };
    const localConversation = syntheticConversation(
      "conversation-local",
      "Synthetic local conversation",
      "2026-10-02T12:00:00.000Z",
    );
    await repository.create(cloudConversation);
    await repository.create(localConversation);
    const chat = new ChatStore(
      emptyStream,
      new SourcesStore(),
      new ConversationHistoryStore(repository),
    );
    chat.setConfiguredChatModes({ local: true, cloud: true });
    await chat.hydrate();
    await chat.openConversation(cloudConversation.id);

    const gate = repository.delayNextUpdate(cloudConversation.id);
    const selecting = chat.selectMode("local");
    await gate.started;
    await chat.openConversation(localConversation.id);
    gate.release();

    expect(await selecting).toBe("stale");
    expect(chat.activeConversationId).toBe(localConversation.id);
    expect(chat.activeMode).toBe("local");
    expect(chat.cloudConsentVersion).toBeNull();
    expect(chat.cloudConsentAt).toBeNull();
  });

  it("does not apply delayed consent to a new conversation", async () => {
    const repository = new DelayedUpdateConversationRepository();
    const conversation = syntheticConversation(
      "conversation-awaiting-consent",
      "Synthetic consent conversation",
      "2026-10-01T12:00:00.000Z",
    );
    await repository.create(conversation);
    const chat = new ChatStore(
      emptyStream,
      new SourcesStore(),
      new ConversationHistoryStore(repository),
    );
    chat.setConfiguredChatModes({ local: true, cloud: true });
    await chat.hydrate();
    expect(await chat.selectMode("cloud")).toBe("consent-required");

    const gate = repository.delayNextUpdate(conversation.id);
    const confirming = chat.confirmCloudConsent();
    await gate.started;
    chat.newConversation();
    gate.release();

    expect(await confirming).toBe(false);
    expect(chat.activeConversationId).toBeNull();
    expect(chat.activeMode).toBe("local");
    expect(chat.cloudConsentVersion).toBeNull();
    expect(chat.cloudConsentAt).toBeNull();
  });

  it("stores the first question in the conversation's initial IndexedDB write", async () => {
    const repository = new MemoryConversationRepository();
    const chat = new ChatStore(
      async function* (): AsyncGenerator<ChatEvent> {
        yield { type: "sources", sources: [] };
        yield { type: "answer", answer: syntheticAnswer([]) };
        yield { type: "done" };
      },
      new SourcesStore(),
      new ConversationHistoryStore(repository),
    );
    await chat.hydrate();
    await chat.submit("Synthetic first question is not lost?");

    expect(repository.saves[0]?.messages[0]).toMatchObject({
      question: "Synthetic first question is not lost?",
      status: "pending",
      answer: null,
    });
  });

  it("keeps new conversations isolated and sends history only after explicit follow-up", async () => {
    const repository = new MemoryConversationRepository();
    const history = new ConversationHistoryStore(repository);
    const requests: ChatRequest[] = [];
    const chat = new ChatStore(
      async function* (request): AsyncGenerator<ChatEvent> {
        requests.push(request);
        yield { type: "sources", sources: [] };
        yield { type: "answer", answer: syntheticAnswer([]) };
        yield { type: "done" };
      },
      new SourcesStore(),
      history,
    );
    await chat.hydrate();

    await chat.submit("Synthetic first conversation question?");
    const firstId = chat.activeConversationId;
    chat.newConversation();
    await chat.submit("Synthetic separate conversation question?");
    await chat.openConversation(firstId!);
    await chat.submit("Synthetic explicit follow-up?");

    expect(requests[0]?.messages.map((message) => message.content)).toEqual([
      "Synthetic first conversation question?",
    ]);
    expect(requests[1]?.messages.map((message) => message.content)).toEqual([
      "Synthetic separate conversation question?",
    ]);
    expect(requests[2]?.messages.map((message) => message.content)).toEqual([
      "Synthetic first conversation question?",
      "Synthetic answer for interface testing.",
      "Synthetic explicit follow-up?",
    ]);
    expect(requests.every((request) => request.mode === "local")).toBe(true);
  });

  it("blocks submit while a selected conversation is still loading", async () => {
    const repository = new DelayedLoadConversationRepository();
    await repository.create(
      syntheticConversation(
        "conversation-a",
        "Synthetic conversation A",
        "2026-10-01T12:00:00.000Z",
      ),
    );
    await repository.create(
      syntheticConversation(
        "conversation-b",
        "Synthetic conversation B",
        "2026-10-02T12:00:00.000Z",
      ),
    );
    const history = new ConversationHistoryStore(repository);
    let requests = 0;
    const chat = new ChatStore(
      async function* (): AsyncGenerator<ChatEvent> {
        requests += 1;
        yield { type: "sources", sources: [] };
        yield { type: "answer", answer: syntheticAnswer([]) };
        yield { type: "done" };
      },
      new SourcesStore(),
      history,
    );
    await chat.hydrate();
    expect(chat.activeConversationId).toBe("conversation-b");

    const loadGate = repository.delayNextGet("conversation-a");
    const opening = chat.openConversation("conversation-a");
    await loadGate.started;
    expect(chat.ready).toBe(false);
    const priorConversation = await repository.get("conversation-b");

    await chat.submit("Synthetic question during conversation switch");

    expect(requests).toBe(0);
    expect(chat.activeConversationId).toBe("conversation-b");
    loadGate.release();
    await opening;
    expect(chat.ready).toBe(true);
    expect(chat.activeConversationId).toBe("conversation-a");
    expect(chat.turns[0]?.question).toBe("Synthetic conversation A");
    expect(await repository.get("conversation-b")).toEqual(priorConversation);

    await chat.openConversation("missing-conversation");
    expect(chat.ready).toBe(true);
    expect(chat.activeConversationId).toBe("conversation-a");
    expect(chat.turns[0]?.question).toBe("Synthetic conversation A");
    expect(chat.notice).toBe("Dit gesprek kon niet worden geopend.");
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
    expect(request.mode).toBe("local");
  });

  it("omits prior turns when a conversation is explicitly in cloud mode", () => {
    const request = buildChatRequest(
      [
        {
          id: "old",
          question: "Synthetic earlier question",
          status: "answered",
          sources: [],
          answer: syntheticAnswer([]),
          errorMessage: null,
        },
      ],
      "Current synthetic question",
      "2026-10-31",
      "cloud",
    );
    expect(request.messages).toEqual([
      { role: "user", content: "Current synthetic question" },
    ]);
    expect(request.mode).toBe("cloud");
  });

  it("does not submit an empty or overlapping turn", async () => {
    let calls = 0;
    const chat = await createChat(
      async function* (): AsyncGenerator<ChatEvent> {
        calls += 1;
        yield { type: "sources", sources: [] };
        yield { type: "answer", answer: syntheticAnswer([]) };
        yield { type: "done" };
      },
      new SourcesStore(),
    );
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

async function createChat(
  stream: (
    request: ChatRequest,
    options: { signal?: AbortSignal },
  ) => AsyncIterable<ChatEvent>,
  sources: SourcesStore,
): Promise<ChatStore> {
  const chat = new ChatStore(
    stream,
    sources,
    new ConversationHistoryStore(new MemoryConversationRepository()),
  );
  await chat.hydrate();
  return chat;
}

class MemoryConversationRepository implements ConversationRepository {
  private readonly rows = new Map<string, StoredConversation>();
  readonly saves: StoredConversation[] = [];

  async list(): Promise<ConversationListResult> {
    return {
      conversations: [...this.rows.values()]
        .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
        .map(({ messages, ...conversation }) => ({
          ...conversation,
          messageCount: messages.length,
        })),
      skippedRecords: 0,
    };
  }

  async get(id: string): Promise<StoredConversation | undefined> {
    return this.rows.get(id);
  }

  async create(conversation: StoredConversation): Promise<void> {
    if (this.rows.has(conversation.id)) {
      throw new Error("Conversation already exists.");
    }
    const snapshot = structuredClone(conversation);
    this.saves.push(snapshot);
    this.rows.set(conversation.id, snapshot);
  }

  async update(
    id: string,
    patch: ConversationPatch,
  ): Promise<StoredConversation> {
    const current = this.rows.get(id);
    if (!current) {
      throw new Error("Conversation no longer exists.");
    }
    const snapshot = structuredClone({ ...current, ...patch });
    this.saves.push(snapshot);
    this.rows.set(id, snapshot);
    return snapshot;
  }

  async delete(id: string): Promise<void> {
    this.rows.delete(id);
  }

  async clear(): Promise<void> {
    this.rows.clear();
  }
}

class DelayedLoadConversationRepository extends MemoryConversationRepository {
  private delayedId: string | null = null;
  private startedResolve: () => void = () => undefined;
  private releaseResolve: () => void = () => undefined;
  private startedPromise: Promise<void> = Promise.resolve();
  private releasePromise: Promise<void> = Promise.resolve();

  delayNextGet(id: string): { started: Promise<void>; release: () => void } {
    this.delayedId = id;
    this.startedPromise = new Promise((resolve) => {
      this.startedResolve = resolve;
    });
    this.releasePromise = new Promise((resolve) => {
      this.releaseResolve = resolve;
    });
    return {
      started: this.startedPromise,
      release: () => this.releaseResolve(),
    };
  }

  override async get(id: string): Promise<StoredConversation | undefined> {
    if (id === this.delayedId) {
      this.delayedId = null;
      this.startedResolve();
      await this.releasePromise;
    }
    return super.get(id);
  }
}

class DelayedUpdateConversationRepository extends MemoryConversationRepository {
  private delayedId: string | null = null;
  private startedResolve: () => void = () => undefined;
  private releaseResolve: () => void = () => undefined;
  private releasePromise: Promise<void> = Promise.resolve();

  delayNextUpdate(id: string): { started: Promise<void>; release: () => void } {
    this.delayedId = id;
    const started = new Promise<void>((resolve) => {
      this.startedResolve = resolve;
    });
    this.releasePromise = new Promise((resolve) => {
      this.releaseResolve = resolve;
    });
    return { started, release: () => this.releaseResolve() };
  }

  override async update(
    id: string,
    patch: ConversationPatch,
  ): Promise<StoredConversation> {
    if (id === this.delayedId) {
      this.delayedId = null;
      this.startedResolve();
      await this.releasePromise;
    }
    return super.update(id, patch);
  }
}

function syntheticConversation(
  id: string,
  question: string,
  updatedAt: string,
): StoredConversation {
  return {
    schemaVersion: 2,
    id,
    title: question,
    mode: "local",
    cloudConsentVersion: null,
    cloudConsentAt: null,
    createdAt: updatedAt,
    updatedAt,
    messages: [
      {
        id: `turn-${id}`,
        question,
        status: "answered",
        sources: [],
        answer: syntheticAnswer([]),
        errorMessage: null,
      },
    ],
  };
}
