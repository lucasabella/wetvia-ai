import type { ChatTurn } from "./chat.svelte";

export type ConversationMode = "local" | "cloud";

export type CloudConsent = {
  cloudConsentVersion: number | null;
  cloudConsentAt: string | null;
};

export type StoredConversation = {
  schemaVersion: 2;
  id: string;
  title: string;
  messages: ChatTurn[];
  mode: ConversationMode;
  cloudConsentVersion: number | null;
  cloudConsentAt: string | null;
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

export type ConversationPatch =
  | Pick<StoredConversation, "title" | "updatedAt">
  | Pick<StoredConversation, "messages" | "updatedAt">
  | Pick<StoredConversation, "mode" | "updatedAt">
  | Pick<
      StoredConversation,
      "mode" | "cloudConsentVersion" | "cloudConsentAt" | "updatedAt"
    >;

/** Browser-local storage boundary for conversations. No server adapter exists. */
export interface ConversationRepository {
  list(): Promise<ConversationListResult>;
  get(id: string): Promise<StoredConversation | undefined>;
  /** Insert a new conversation without replacing an existing ID. */
  create(conversation: StoredConversation): Promise<void>;
  /** Apply a field patch to a valid existing conversation atomically. */
  update(id: string, patch: ConversationPatch): Promise<StoredConversation>;
  delete(id: string): Promise<void>;
  clear(): Promise<void>;
}

export function conversationTitle(firstQuestion: string): string {
  return Array.from(firstQuestion.trim()).slice(0, 60).join("");
}
