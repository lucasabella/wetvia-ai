import Dexie, { type Table } from "dexie";

import type {
  ConversationRepository,
  ConversationListResult,
  ConversationSummary,
  StoredConversation,
} from "./conversation-repository";

const DATABASE_NAME = "wetvia-chat-history";

class WetviaChatDatabase extends Dexie {
  conversations!: Table<StoredConversation, string>;

  constructor(name: string) {
    super(name);
    this.version(1).stores({
      conversations: "id, mode, createdAt, updatedAt",
    });
  }
}

/** Dexie-backed IndexedDB adapter; the database opens lazily on first access. */
export class DexieConversationRepository implements ConversationRepository {
  private readonly database: WetviaChatDatabase;

  constructor(databaseName = DATABASE_NAME) {
    this.database = new WetviaChatDatabase(databaseName);
  }

  async list(): Promise<ConversationListResult> {
    const table = this.database.conversations;
    return this.database.transaction("r", table, async () => {
      const rows = (await table.toArray()) as unknown[];
      const conversations: ConversationSummary[] = [];
      let skippedRecords = 0;

      rows.forEach((row) => {
        const parsed = parseConversation(row);
        if (parsed.kind === "valid") {
          conversations.push(toSummary(parsed.conversation));
        } else {
          skippedRecords += 1;
        }
      });

      return {
        conversations,
        skippedRecords,
      };
    });
  }

  get(id: string): Promise<StoredConversation | undefined> {
    return this.database.conversations.get(id);
  }

  async save(conversation: StoredConversation): Promise<void> {
    await this.database.conversations.put(conversation);
  }

  async delete(id: string): Promise<void> {
    await this.database.conversations.delete(id);
  }

  async clear(): Promise<void> {
    await this.database.conversations.clear();
  }

  close(): void {
    this.database.close();
  }
}

function toSummary(conversation: StoredConversation): ConversationSummary {
  const { messages, ...summary } = conversation;
  return { ...summary, messageCount: messages.length };
}

type ParsedConversation =
  | { kind: "valid"; conversation: StoredConversation }
  | { kind: "corrupt" }
  | { kind: "unsupported" };

function parseConversation(value: unknown): ParsedConversation {
  if (!isRecord(value)) {
    return { kind: "corrupt" };
  }
  if (typeof value.schemaVersion === "number" && value.schemaVersion > 1) {
    return { kind: "unsupported" };
  }
  if (
    value.schemaVersion !== 1 ||
    typeof value.id !== "string" ||
    !value.id ||
    typeof value.title !== "string" ||
    !isConversationMode(value.mode) ||
    !isIsoTimestamp(value.createdAt) ||
    !isIsoTimestamp(value.updatedAt) ||
    !Array.isArray(value.messages) ||
    !value.messages.every(isStoredTurn)
  ) {
    return { kind: "corrupt" };
  }
  return {
    kind: "valid",
    conversation: value as unknown as StoredConversation,
  };
}

function isStoredTurn(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    typeof value.question === "string" &&
    (value.status === "pending" ||
      value.status === "answered" ||
      value.status === "error") &&
    Array.isArray(value.sources) &&
    value.sources.every(isSourceCard) &&
    (value.answer === null || isVerifiedAnswer(value.answer)) &&
    (value.errorMessage === null || typeof value.errorMessage === "string")
  );
}

function isSourceCard(value: unknown): boolean {
  if (!isRecord(value) || !isRecord(value.metadata)) {
    return false;
  }
  return (
    typeof value.label === "string" &&
    isUuid(value.chunk_id) &&
    typeof value.tekst === "string" &&
    typeof value.score === "number" &&
    Number.isFinite(value.score) &&
    typeof value.metadata.bwb_id === "string" &&
    typeof value.metadata.regeling_titel === "string" &&
    typeof value.metadata.artikel === "string" &&
    typeof value.metadata.kop_pad === "string" &&
    isHttpUrl(value.metadata.bron_url) &&
    isHttpUrl(value.metadata.toestand_url) &&
    isNullableString(value.metadata.lid) &&
    isNullableString(value.metadata.onderdeel) &&
    isNullableString(value.metadata.opschrift) &&
    isIsoDate(value.metadata.geldig_vanaf) &&
    isNullableIsoDate(value.metadata.geldig_tot) &&
    isLegalStatus(value.metadata.status) &&
    (value.metadata.artikel_status === "geldend" ||
      value.metadata.artikel_status === "vervallen")
  );
}

function isVerifiedAnswer(value: unknown): boolean {
  if (!isRecord(value)) {
    return false;
  }
  return (
    (value.status === "beantwoord" ||
      value.status === "onzeker" ||
      value.status === "buiten_scope") &&
    typeof value.samenvatting === "string" &&
    Array.isArray(value.punten) &&
    value.punten.every(
      (point) =>
        isRecord(point) &&
        typeof point.tekst === "string" &&
        Array.isArray(point.bron_ids) &&
        point.bron_ids.every((id) => typeof id === "string"),
    ) &&
    Array.isArray(value.voorbehouden) &&
    value.voorbehouden.every((item) => typeof item === "string") &&
    Array.isArray(value.vervolgstappen) &&
    value.vervolgstappen.every(
      (step) =>
        isRecord(step) && typeof step.tekst === "string" && isHttpUrl(step.url),
    ) &&
    typeof value.peildatum === "string" &&
    Array.isArray(value.verifier_notes) &&
    value.verifier_notes.every((item) => typeof item === "string")
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isConversationMode(
  value: unknown,
): value is StoredConversation["mode"] {
  return value === "local" || value === "cloud" || value === "backend-default";
}

function isLegalStatus(value: unknown): boolean {
  return value === "geldend" || value === "toekomstig" || value === "vervallen";
}

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function isNullableIsoDate(value: unknown): boolean {
  return value === null || isIsoDate(value);
}

function isUuid(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      value,
    )
  );
}

function isHttpUrl(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function isIsoTimestamp(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}
