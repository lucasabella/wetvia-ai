import "fake-indexeddb/auto";

import Dexie from "dexie";
import { afterEach, describe, expect, it } from "vitest";
import { SourcesStore } from "../sources/sources.svelte";
import { ChatStore, type ChatStreamer } from "./chat.svelte";

import {
  ConversationHistoryStore,
  groupConversations,
} from "./conversation-history.svelte";
import { DexieConversationRepository } from "./dexie-conversation-repository";
import type {
  ConversationListResult,
  ConversationPatch,
  ConversationRepository,
  ConversationSummary,
  StoredConversation,
} from "./conversation-repository";

describe("ConversationHistoryStore", () => {
  const databaseNames: string[] = [];
  const repositories: DexieConversationRepository[] = [];
  const rawDatabases: Dexie[] = [];

  afterEach(async () => {
    rawDatabases.splice(0).forEach((database) => database.close());
    repositories.splice(0).forEach((repository) => repository.close());
    await Promise.all(
      databaseNames.splice(0).map((name) => new Dexie(name).delete()),
    );
  });

  it("saves and restores a versioned backend-default conversation in IndexedDB", async () => {
    const name = databaseName(databaseNames);
    const repository = createRepository(name, repositories);
    const history = new ConversationHistoryStore(repository);
    await history.hydrate();

    const result = await history.create(
      "A synthetic question " + "x".repeat(70),
    );

    expect(result.persisted).toBe(true);
    expect(result.conversation.schemaVersion).toBe(1);
    expect(result.conversation.mode).toBe("backend-default");
    expect(Array.from(result.conversation.title)).toHaveLength(60);
    expect(history.conversations[0]?.title).toBe(result.conversation.title);

    const restored = new ConversationHistoryStore(
      createRepository(name, repositories),
    );
    const summaries = await restored.hydrate();
    expect(summaries).toHaveLength(1);
    const record = await restored.load(result.conversation.id);
    expect(record).toMatchObject({
      schemaVersion: 1,
      id: result.conversation.id,
      title: result.conversation.title,
      mode: "backend-default",
      messages: [],
    });
  });

  it("does not report failed IndexedDB writes as saved conversations", async () => {
    const history = new ConversationHistoryStore(new FailingRepository());
    await history.hydrate();

    const result = await history.create("Synthetic question");

    expect(result.persisted).toBe(false);
    expect(history.conversations).toEqual([]);
    expect(history.storageError).toBe(
      "De lokale gespreksopslag kon niet worden bijgewerkt.",
    );
  });

  it("renames and deletes one conversation and clears the remaining records", async () => {
    const repository = createRepository(
      databaseName(databaseNames),
      repositories,
    );
    const history = new ConversationHistoryStore(repository);
    await history.hydrate();
    const first = await history.create("Synthetic conversation one");
    const second = await history.create("Synthetic conversation two");

    expect(
      await history.rename(first.conversation.id, "Renamed synthetic thread"),
    ).toBe(true);
    expect((await history.load(first.conversation.id))?.title).toBe(
      "Renamed synthetic thread",
    );
    await history.delete(first.conversation.id);
    expect(await history.load(first.conversation.id)).toBeUndefined();
    expect(
      history.conversations.map((conversation) => conversation.id),
    ).toEqual([second.conversation.id]);

    await history.clear();
    expect(await repository.list()).toMatchObject({
      conversations: [],
      skippedRecords: 0,
    });
    expect(history.conversations).toEqual([]);
  });

  it("skips corrupt rows without deleting them or hiding valid conversations", async () => {
    const name = databaseName(databaseNames);
    const repository = createRepository(name, repositories);
    const original = new ConversationHistoryStore(repository);
    await original.hydrate();
    await original.create("Synthetic valid conversation one");
    await original.create("Synthetic valid conversation two");

    const corruptWriter = new Dexie(name);
    rawDatabases.push(corruptWriter);
    corruptWriter.version(1).stores({
      conversations: "id, mode, createdAt, updatedAt",
    });
    await corruptWriter.open();
    await corruptWriter.table("conversations").put({
      schemaVersion: 1,
      id: "corrupt-record",
      title: 42,
      messages: [],
      mode: "backend-default",
      createdAt: "2026-10-31T12:00:00.000Z",
      updatedAt: "2026-10-31T12:00:00.000Z",
    });

    const restored = new ConversationHistoryStore(
      createRepository(name, repositories),
    );
    await restored.hydrate();

    expect(
      restored.conversations.map((conversation) => conversation.title).sort(),
    ).toEqual(
      [
        "Synthetic valid conversation one",
        "Synthetic valid conversation two",
      ].sort(),
    );
    expect(restored.skippedRecords).toBe(1);
    expect((await repository.list()).skippedRecords).toBe(1);
    expect(
      await corruptWriter.table("conversations").get("corrupt-record"),
    ).toMatchObject({
      id: "corrupt-record",
      title: 42,
    });
    await expect(repository.get("corrupt-record")).rejects.toThrow(
      "Stored conversation is corrupt or unsupported.",
    );
  });

  it.each(["corrupt", "future-version"] as const)(
    "does not open, rename, or overwrite a summarized %s row",
    async (kind) => {
      const name = databaseName(databaseNames);
      const repository = createRepository(name, repositories);
      const history = new ConversationHistoryStore(repository);
      await history.hydrate();
      const created = await history.create("Synthetic row before corruption");
      const id = created.conversation.id;

      const chat = new ChatStore(emptyChatStream, new SourcesStore(), history);
      await chat.hydrate();
      expect(history.conversations.map((item) => item.id)).toContain(id);

      const rawDatabase = new Dexie(name);
      rawDatabases.push(rawDatabase);
      rawDatabase.version(1).stores({
        conversations: "id, mode, createdAt, updatedAt",
      });
      await rawDatabase.open();
      const corruptRow = {
        schemaVersion: kind === "future-version" ? 2 : 1,
        id,
        title: kind === "future-version" ? "Newer schema" : 42,
        messages: [],
        mode: "backend-default",
        createdAt: "2026-10-31T12:00:00.000Z",
        updatedAt: "2026-10-31T12:00:00.000Z",
      };
      await rawDatabase.table("conversations").put(corruptRow);

      await expect(repository.get(id)).rejects.toThrow(
        "Stored conversation is corrupt or unsupported.",
      );
      await chat.openConversation(id);
      expect(chat.activeConversationId).toBe(id);
      expect(chat.notice).toBe("Dit gesprek kon niet worden geopend.");
      expect(history.storageError).toBe(
        "De lokale gespreksopslag kon niet worden bijgewerkt.",
      );
      expect(
        await chat.renameConversation(id, "Synthetic attempted rename"),
      ).toBe(false);
      expect(await history.saveMessages(id, [])).toBe(false);
      await expect(
        repository.update(id, {
          title: "Synthetic attempted overwrite",
          updatedAt: created.conversation.updatedAt,
        }),
      ).rejects.toThrow("Stored conversation is corrupt or unsupported.");
      expect(await rawDatabase.table("conversations").get(id)).toEqual(
        corruptRow,
      );
    },
  );

  it("reports a missing conversation instead of claiming its messages were saved", async () => {
    const history = new ConversationHistoryStore(new FailingRepository());
    await history.hydrate();

    expect(await history.saveMessages("missing-conversation", [])).toBe(false);
    expect(history.storageError).toBe(
      "De lokale gespreksopslag kon niet worden bijgewerkt.",
    );
  });

  it("inserts on create and never resurrects a row deleted through another repository", async () => {
    const name = databaseName(databaseNames);
    const repository = createRepository(name, repositories);
    const otherRepository = createRepository(name, repositories);
    const history = new ConversationHistoryStore(repository);
    await history.hydrate();

    const first = await history.create("Synthetic cross-tab delete question");
    await expect(
      otherRepository.create({
        ...first.conversation,
        title: "Synthetic duplicate create must not replace",
      }),
    ).rejects.toThrow();
    expect((await otherRepository.get(first.conversation.id))?.title).toBe(
      first.conversation.title,
    );

    await otherRepository.delete(first.conversation.id);
    expect(
      await history.rename(
        first.conversation.id,
        "Synthetic rename after external delete",
      ),
    ).toBe(false);
    expect(await history.saveMessages(first.conversation.id, [])).toBe(false);
    expect(await repository.get(first.conversation.id)).toBeUndefined();

    const second = await history.create("Synthetic cross-tab update race");
    const otherHistory = new ConversationHistoryStore(otherRepository);
    await otherHistory.hydrate();
    const updatedTurn = {
      id: "turn-cross-tab-update",
      question: "Synthetic concurrent message update",
      status: "error" as const,
      sources: [],
      answer: null,
      errorMessage: "Synthetic interrupted response",
    };
    await Promise.allSettled([
      history.rename(second.conversation.id, "Synthetic concurrent rename"),
      otherHistory.saveMessages(second.conversation.id, [updatedTurn]),
    ]);
    const merged = await repository.get(second.conversation.id);
    expect(merged?.title).toBe("Synthetic concurrent rename");
    expect(merged?.messages).toEqual([updatedTurn]);

    const third = await history.create("Synthetic cross-tab delete race");
    await Promise.allSettled([
      otherRepository.update(third.conversation.id, {
        title: "Synthetic update before concurrent delete",
        updatedAt: new Date().toISOString(),
      }),
      repository.delete(third.conversation.id),
    ]);
    expect(await otherRepository.get(third.conversation.id)).toBeUndefined();
  });

  it("clears after delayed writes and rejects writes started during clear-all", async () => {
    const repository = new DelayedSaveRepository();
    const history = new ConversationHistoryStore(repository);
    await history.hydrate();

    const firstCreate = history.create("Synthetic first conversation");
    await repository.started;
    const clear = history.clear();
    const concurrentCreate = history.create("Synthetic stale conversation");
    repository.release();
    const firstResult = await firstCreate;
    const secondResult = await concurrentCreate;
    await clear;

    expect(firstResult.persisted).toBe(true);
    expect(secondResult.persisted).toBe(false);
    expect(await repository.list()).toMatchObject({
      conversations: [],
      skippedRecords: 0,
    });
    expect(history.conversations).toEqual([]);
  });

  it("finishes hydration when clear invalidates a delayed history read", async () => {
    for (const failClear of [false, true]) {
      const preservedConversation: ConversationSummary = {
        schemaVersion: 1,
        id: "preserved-conversation",
        title: "Synthetic conversation kept after failed clear",
        mode: "backend-default",
        createdAt: "2026-10-31T12:00:00.000Z",
        updatedAt: "2026-10-31T12:00:00.000Z",
        messageCount: 1,
      };
      const repository = new DelayedListRepository(
        failClear,
        failClear
          ? { conversations: [preservedConversation], skippedRecords: 0 }
          : { conversations: [], skippedRecords: 0 },
      );
      const history = new ConversationHistoryStore(repository);
      const hydration = history.hydrate();
      await repository.listStarted;

      expect(history.ready).toBe(false);
      await history.clear();
      expect(history.ready).toBe(true);
      expect(history.storageError).toBe(
        failClear
          ? "De lokale gespreksopslag kon niet worden bijgewerkt."
          : null,
      );
      expect(history.conversations).toEqual(
        failClear ? [preservedConversation] : [],
      );

      repository.releaseList();
      await hydration;
      expect(history.ready).toBe(true);
    }
  });
});

describe("conversation date groups", () => {
  it("groups local calendar dates by today, Monday-based week, and older", () => {
    const summary = (id: string, createdAt: string): ConversationSummary => ({
      schemaVersion: 1,
      id,
      title: id,
      mode: "backend-default",
      createdAt,
      updatedAt: createdAt,
      messageCount: 1,
    });
    const now = new Date(2026, 2, 31, 12);
    const groups = groupConversations(
      [
        summary("today", new Date(2026, 2, 31, 9).toISOString()),
        summary("week", new Date(2026, 2, 30, 9).toISOString()),
        summary("older", new Date(2026, 2, 29, 9).toISOString()),
      ],
      now,
    );

    expect(
      groups.map((group) => [
        group.label,
        group.conversations.map((c) => c.id),
      ]),
    ).toEqual([
      ["Vandaag", ["today"]],
      ["Deze week", ["week"]],
      ["Ouder", ["older"]],
    ]);
  });
});

function databaseName(names: string[]): string {
  const name = `wetvia-chat-test-${crypto.randomUUID()}`;
  names.push(name);
  return name;
}

const emptyChatStream: ChatStreamer = async function* () {
  // This test exercises local restoration only.
};

function createRepository(
  name: string,
  repositories: DexieConversationRepository[],
): DexieConversationRepository {
  const repository = new DexieConversationRepository(name);
  repositories.push(repository);
  return repository;
}

class FailingRepository implements ConversationRepository {
  async list(): Promise<ConversationListResult> {
    return { conversations: [], skippedRecords: 0 };
  }

  async get(): Promise<undefined> {
    return undefined;
  }

  async create(): Promise<void> {
    throw new Error("Synthetic storage failure");
  }

  async update(): Promise<StoredConversation> {
    throw new Error("Synthetic storage failure");
  }

  async delete(): Promise<void> {}

  async clear(): Promise<void> {}
}

class DelayedListRepository extends FailingRepository {
  private listResolve!: (result: ConversationListResult) => void;
  private listStartedResolve!: () => void;
  private listCalls = 0;
  readonly listStarted = new Promise<void>((resolve) => {
    this.listStartedResolve = resolve;
  });
  private readonly listResult = new Promise<ConversationListResult>(
    (resolve) => {
      this.listResolve = resolve;
    },
  );

  constructor(
    private readonly failClear: boolean,
    private readonly result: ConversationListResult,
  ) {
    super();
  }

  override list(): Promise<ConversationListResult> {
    this.listCalls += 1;
    if (this.listCalls === 1) {
      this.listStartedResolve();
      return this.listResult;
    }
    return Promise.resolve(this.result);
  }

  override async clear(): Promise<void> {
    if (this.failClear) {
      throw new Error("Synthetic clear failure");
    }
  }

  releaseList(): void {
    this.listResolve({ conversations: [], skippedRecords: 0 });
  }
}

class DelayedSaveRepository implements ConversationRepository {
  private readonly rows = new Map<string, StoredConversation>();
  private startedResolve!: () => void;
  private releaseResolve!: () => void;
  readonly started = new Promise<void>((resolve) => {
    this.startedResolve = resolve;
  });
  private readonly releasePromise = new Promise<void>((resolve) => {
    this.releaseResolve = resolve;
  });
  private delay = true;

  async list(): Promise<ConversationListResult> {
    return {
      conversations: [...this.rows.values()].map(({ messages, ...row }) => ({
        ...row,
        messageCount: messages.length,
      })),
      skippedRecords: 0,
    };
  }

  async get(id: string): Promise<StoredConversation | undefined> {
    return this.rows.get(id);
  }

  async create(conversation: StoredConversation): Promise<void> {
    if (this.delay) {
      this.delay = false;
      this.startedResolve();
      await this.releasePromise;
    }
    this.rows.set(conversation.id, structuredClone(conversation));
  }

  async update(
    id: string,
    patch: ConversationPatch,
  ): Promise<StoredConversation> {
    const current = this.rows.get(id);
    if (!current) {
      throw new Error("Conversation no longer exists.");
    }
    const updated = { ...current, ...patch };
    this.rows.set(id, structuredClone(updated));
    return updated;
  }

  async delete(id: string): Promise<void> {
    this.rows.delete(id);
  }

  async clear(): Promise<void> {
    this.rows.clear();
  }

  release(): void {
    this.releaseResolve();
  }
}
