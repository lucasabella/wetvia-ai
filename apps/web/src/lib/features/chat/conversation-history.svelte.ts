import type { ChatTurn } from "./chat.svelte";
import { SvelteDate, SvelteMap } from "svelte/reactivity";
import {
  conversationTitle,
  type ConversationMode,
  type ConversationRepository,
  type ConversationSummary,
  type StoredConversation,
} from "./conversation-repository";

const STORAGE_ERROR = "De lokale gespreksopslag kon niet worden bijgewerkt.";

export type CreateConversationResult = {
  conversation: StoredConversation;
  persisted: boolean;
};

export type ConversationGroup = {
  label: "Vandaag" | "Deze week" | "Ouder";
  conversations: ConversationSummary[];
};

/** Per-shell in-memory index over the injected browser-local repository. */
export class ConversationHistoryStore {
  conversations = $state<ConversationSummary[]>([]);
  activeId = $state<string | null>(null);
  ready = $state(false);
  storageError = $state<string | null>(null);
  skippedRecords = $state(0);

  private readonly repository: ConversationRepository;
  private readonly writes = new SvelteMap<string, Promise<void>>();
  private hydrationId = 0;
  private clearing: Promise<void> | null = null;
  private writeGeneration = 0;

  constructor(repository: ConversationRepository) {
    this.repository = repository;
  }

  async hydrate(): Promise<ConversationSummary[]> {
    const hydrationId = ++this.hydrationId;
    try {
      const result = await this.repository.list();
      if (hydrationId === this.hydrationId) {
        this.conversations = sortConversations(result.conversations);
        this.skippedRecords = result.skippedRecords;
        this.storageError = null;
      }
    } catch {
      if (hydrationId === this.hydrationId) {
        this.conversations = [];
        this.skippedRecords = 0;
        this.storageError = STORAGE_ERROR;
      }
    } finally {
      if (hydrationId === this.hydrationId) {
        this.ready = true;
      }
    }
    return this.conversations;
  }

  setActive(id: string | null): void {
    this.activeId = id;
  }

  async load(id: string): Promise<StoredConversation | undefined> {
    try {
      const conversation = await this.repository.get(id);
      this.storageError = null;
      return conversation;
    } catch {
      this.storageError = STORAGE_ERROR;
      return undefined;
    }
  }

  async create(
    firstQuestion: string,
    mode: ConversationMode = "backend-default",
    messages: ChatTurn[] = [],
  ): Promise<CreateConversationResult> {
    this.hydrationId += 1;
    const now = new SvelteDate().toISOString();
    const conversation: StoredConversation = {
      schemaVersion: 1,
      id: crypto.randomUUID(),
      title: conversationTitle(firstQuestion),
      messages,
      mode,
      createdAt: now,
      updatedAt: now,
    };
    try {
      await this.enqueue(conversation.id, () =>
        this.repository.create(conversation),
      );
      this.upsertSummary(conversation);
      return { conversation, persisted: true };
    } catch {
      return { conversation, persisted: false };
    }
  }

  async saveMessages(id: string, messages: ChatTurn[]): Promise<boolean> {
    try {
      await this.enqueue(id, async () => {
        const current = await this.repository.get(id);
        if (!current) {
          throw new Error("Conversation no longer exists.");
        }
        const updated: StoredConversation = {
          ...current,
          messages,
          updatedAt: new SvelteDate().toISOString(),
        };
        await this.repository.update(updated);
        this.upsertSummary(updated);
      });
      return true;
    } catch {
      return false;
    }
  }

  async rename(id: string, value: string): Promise<boolean> {
    const title = conversationTitle(value);
    if (!title) {
      return false;
    }
    let renamed = false;
    try {
      await this.enqueue(id, async () => {
        const current = await this.repository.get(id);
        if (!current) {
          throw new Error("Conversation no longer exists.");
        }
        const updated = {
          ...current,
          title,
          updatedAt: new SvelteDate().toISOString(),
        };
        await this.repository.update(updated);
        this.upsertSummary(updated);
        renamed = true;
      });
    } catch {
      return false;
    }
    return renamed;
  }

  async delete(id: string): Promise<void> {
    this.hydrationId += 1;
    try {
      await this.enqueue(id, () => this.repository.delete(id));
      this.conversations = this.conversations.filter(
        (conversation) => conversation.id !== id,
      );
      if (this.activeId === id) {
        this.activeId = null;
      }
    } catch {
      // Keep the conversation visible when IndexedDB could not delete it.
    }
  }

  async clear(): Promise<void> {
    this.hydrationId += 1;
    if (this.clearing) {
      await this.clearing;
      return;
    }
    this.writeGeneration += 1;
    const clearOperation = this.clearRepository();
    this.clearing = clearOperation;
    try {
      await clearOperation;
    } catch {
      try {
        const result = await this.repository.list();
        this.conversations = sortConversations(result.conversations);
        this.skippedRecords = result.skippedRecords;
      } catch {
        // Keep the in-memory list if storage also fails to reload.
      }
      this.storageError = STORAGE_ERROR;
    } finally {
      this.ready = true;
      if (this.clearing === clearOperation) {
        this.clearing = null;
      }
    }
  }

  private async enqueue(
    id: string,
    operation: () => Promise<void>,
  ): Promise<void> {
    const clearing = this.clearing;
    if (clearing) {
      await clearing;
      throw new Error("Conversation write invalidated by clear-all.");
    }
    const generation = this.writeGeneration;
    const previous = this.writes.get(id) ?? Promise.resolve();
    const next = previous
      .catch(() => undefined)
      .then(() => {
        if (generation !== this.writeGeneration) {
          throw new Error("Conversation write invalidated by clear-all.");
        }
        return operation();
      });
    this.writes.set(id, next);
    try {
      await next;
      this.storageError = null;
    } catch {
      this.storageError = STORAGE_ERROR;
      throw new Error(STORAGE_ERROR);
    } finally {
      if (this.writes.get(id) === next) {
        this.writes.delete(id);
      }
    }
  }

  private async clearRepository(): Promise<void> {
    await Promise.all(
      [...this.writes.values()].map((write) => write.catch(() => undefined)),
    );
    await this.repository.clear();
    this.conversations = [];
    this.activeId = null;
    this.skippedRecords = 0;
    this.storageError = null;
  }

  private upsertSummary(conversation: StoredConversation): void {
    const { messages, ...summary } = conversation;
    const next = this.conversations.filter(
      (candidate) => candidate.id !== conversation.id,
    );
    next.push({ ...summary, messageCount: messages.length });
    this.conversations = sortConversations(next);
  }
}

export function groupConversations(
  conversations: ConversationSummary[],
  now: Date = new SvelteDate(),
): ConversationGroup[] {
  const todayStart = new SvelteDate(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const mondayOffset = (now.getDay() + 6) % 7;
  const weekStart = new SvelteDate(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - mondayOffset,
  );
  const grouped: Record<ConversationGroup["label"], ConversationSummary[]> = {
    Vandaag: [],
    "Deze week": [],
    Ouder: [],
  };

  for (const conversation of sortConversations(conversations)) {
    const createdAt = Date.parse(conversation.createdAt);
    const label =
      createdAt >= todayStart
        ? "Vandaag"
        : createdAt >= weekStart.getTime()
          ? "Deze week"
          : "Ouder";
    grouped[label].push(conversation);
  }

  return (Object.keys(grouped) as ConversationGroup["label"][]).flatMap(
    (label) => {
      const items = grouped[label];
      return items.length ? [{ label, conversations: items }] : [];
    },
  );
}

function sortConversations(
  conversations: ConversationSummary[],
): ConversationSummary[] {
  return [...conversations].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt),
  );
}
