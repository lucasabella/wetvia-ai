import type { ChatTurn } from "./chat.svelte";

export type ConversationMode = "local" | "cloud" | "backend-default";

export type StoredConversation = {
  schemaVersion: 1;
  id: string;
  title: string;
  messages: ChatTurn[];
  mode: ConversationMode;
  createdAt: string;
  updatedAt: string;
};

export type ConversationSummary = Omit<StoredConversation, "messages"> & {
  messageCount: number;
};

export type ConversationListResult = {
  conversations: ConversationSummary[];
  skippedRecords: number;
};

/** Browser-local storage boundary for conversations. No server adapter exists. */
export interface ConversationRepository {
  list(): Promise<ConversationListResult>;
  get(id: string): Promise<StoredConversation | undefined>;
  /** Insert a new conversation without replacing an existing ID. */
  create(conversation: StoredConversation): Promise<void>;
  /** Update a valid existing conversation atomically; never upsert. */
  update(conversation: StoredConversation): Promise<void>;
  delete(id: string): Promise<void>;
  clear(): Promise<void>;
}

export function conversationTitle(firstQuestion: string): string {
  return Array.from(firstQuestion.trim()).slice(0, 60).join("");
}
