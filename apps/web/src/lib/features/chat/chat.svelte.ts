import type { ChatEvent, ChatRequest, components } from "@wetvia/api-client";
import { SvelteDate } from "svelte/reactivity";
import type { SourcesStore, ChatSourceCard } from "../sources/sources.svelte";
import { ConversationHistoryStore } from "./conversation-history.svelte";
import type {
  ConversationMode,
  StoredConversation,
} from "./conversation-repository";

export type VerifiedAnswer = components["schemas"]["VerifiedAnswer"];
export type ChatRole = "user" | "assistant";
export type ChatTurnStatus = "pending" | "answered" | "error";

export type ChatTurn = {
  id: string;
  question: string;
  status: ChatTurnStatus;
  sources: ChatSourceCard[];
  answer: VerifiedAnswer | null;
  errorMessage: string | null;
};

export type ChatStreamer = (
  request: ChatRequest,
  options: { signal?: AbortSignal },
) => AsyncIterable<ChatEvent>;

const MAX_HISTORY_TURNS = 19;
export const CLOUD_CONSENT_VERSION = 1;
const GENERIC_ERROR = "Er is iets misgegaan. Probeer het opnieuw.";
const INTERRUPTED_ERROR =
  "Dit antwoord is onderbroken. Stel uw vraag opnieuw om verder te gaan.";
const CLOUD_UNAVAILABLE = "Cloud (EU) is op dit moment niet geconfigureerd.";
const CLOUD_CONSENT_REQUIRED = "Bevestig eerst de verwerking in Cloud (EU).";

type ConversationContext = {
  conversationId: string | null;
  generation: number;
};

type PendingCloudConsent = ConversationContext & { operationId: number };

export function currentDateISO(now = Date.now()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const part = (type: string) =>
    parts.find((candidate) => candidate.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function buildChatRequest(
  turns: ChatTurn[],
  question: string,
  peildatum: string,
  mode: ConversationMode = "local",
): ChatRequest {
  const history = (
    mode === "cloud" ? [] : turns.slice(-MAX_HISTORY_TURNS)
  ).flatMap((turn) => {
    const messages: ChatRequest["messages"] = [
      { role: "user", content: turn.question },
    ];
    if (turn.answer) {
      messages.push({ role: "assistant", content: turn.answer.samenvatting });
    }
    return messages;
  });
  const request: ChatRequest = {
    messages: [...history, { role: "user", content: question }],
    peildatum,
  };
  request.mode = mode;
  return request;
}

/** Per-shell active conversation; IndexedDB persistence is injected separately. */
export class ChatStore {
  turns = $state<ChatTurn[]>([]);
  draft = $state("");
  sending = $state(false);
  peildatum = $state(currentDateISO());
  ready = $state(false);
  notice = $state<string | null>(null);
  activeMode = $state<ConversationMode>("local");
  localAvailable = $state<boolean | null>(null);
  cloudAvailable = $state<boolean | null>(null);
  modeAvailabilityStatus = $state<"loading" | "loaded" | "error">("loading");
  cloudConsentVersion = $state<number | null>(null);
  cloudConsentAt = $state<string | null>(null);
  conversationGeneration = $state(0);

  private readonly stream: ChatStreamer;
  private readonly sources: SourcesStore;
  private readonly history: ConversationHistoryStore;
  private requestId = 0;
  private loadId = 0;
  private conversationGenerationValue = 0;
  private modeOperationId = 0;
  private pendingCloudConsent: PendingCloudConsent | null = null;
  private controller: AbortController | null = null;

  constructor(
    stream: ChatStreamer,
    sources: SourcesStore,
    history: ConversationHistoryStore,
  ) {
    this.stream = stream;
    this.sources = sources;
    this.history = history;
  }

  get activeConversationId(): string | null {
    return this.history.activeId;
  }

  get activeModeAvailable(): boolean | null {
    return this.activeMode === "local"
      ? this.localAvailable
      : this.cloudAvailable;
  }

  get hasCurrentCloudConsent(): boolean {
    return (
      this.cloudConsentVersion === CLOUD_CONSENT_VERSION &&
      this.cloudConsentAt !== null
    );
  }

  get requiresCloudConsent(): boolean {
    return !this.hasCurrentCloudConsent;
  }

  setConfiguredChatModes(modes: { local: boolean; cloud: boolean }): void {
    this.localAvailable = modes.local;
    this.cloudAvailable = modes.cloud;
    this.modeAvailabilityStatus = "loaded";
  }

  setModeAvailabilityError(): void {
    this.localAvailable = null;
    this.cloudAvailable = null;
    this.modeAvailabilityStatus = "error";
  }

  async selectMode(
    mode: ConversationMode,
  ): Promise<
    "selected" | "consent-required" | "unavailable" | "save-failed" | "stale"
  > {
    const operationId = ++this.modeOperationId;
    this.pendingCloudConsent = null;
    const context = this.captureConversationContext();
    if (mode === "local" && this.localAvailable === false) {
      return "unavailable";
    }
    if (mode === "cloud") {
      if (this.cloudAvailable !== true) {
        return "unavailable";
      }
      if (!this.hasCurrentCloudConsent) {
        this.pendingCloudConsent = { ...context, operationId };
        return "consent-required";
      }
    }
    if (context.conversationId) {
      const saved = await this.history.updateMode(context.conversationId, mode);
      if (!this.isCurrentModeOperation(context, operationId)) {
        return "stale";
      }
      if (!saved) {
        this.notice = this.history.storageError;
        return "save-failed";
      }
    }
    if (!this.isCurrentModeOperation(context, operationId)) {
      return "stale";
    }
    this.activeMode = mode;
    this.notice = null;
    return "selected";
  }

  requestCloudConsent(): boolean {
    if (this.cloudAvailable !== true) {
      this.notice = CLOUD_UNAVAILABLE;
      return false;
    }
    const operationId = ++this.modeOperationId;
    this.pendingCloudConsent = {
      ...this.captureConversationContext(),
      operationId,
    };
    return true;
  }

  cancelCloudConsent(): void {
    this.modeOperationId += 1;
    this.pendingCloudConsent = null;
  }

  async confirmCloudConsent(): Promise<boolean> {
    const pending = this.pendingCloudConsent;
    if (
      !pending ||
      !this.isCurrentModeOperation(pending, pending.operationId)
    ) {
      this.pendingCloudConsent = null;
      return false;
    }
    if (this.cloudAvailable !== true) {
      this.notice = CLOUD_UNAVAILABLE;
      return false;
    }
    const consent = {
      cloudConsentVersion: CLOUD_CONSENT_VERSION,
      cloudConsentAt: new SvelteDate().toISOString(),
    };
    if (
      pending.conversationId &&
      !(await this.history.updateMode(pending.conversationId, "cloud", consent))
    ) {
      if (this.isCurrentModeOperation(pending, pending.operationId)) {
        this.notice = this.history.storageError;
      }
      return false;
    }
    if (
      !this.isCurrentModeOperation(pending, pending.operationId) ||
      this.pendingCloudConsent !== pending
    ) {
      return false;
    }
    this.pendingCloudConsent = null;
    this.activeMode = "cloud";
    this.cloudConsentVersion = consent.cloudConsentVersion;
    this.cloudConsentAt = consent.cloudConsentAt;
    this.notice = null;
    return true;
  }

  async hydrate(): Promise<void> {
    const loadId = ++this.loadId;
    this.advanceConversationGeneration();
    const conversations = await this.history.hydrate();
    if (loadId !== this.loadId) {
      return;
    }
    const latest = conversations[0];
    if (latest) {
      const conversation = await this.history.load(latest.id);
      if (loadId !== this.loadId) {
        return;
      }
      if (conversation) {
        this.restore(conversation);
      }
    }
    if (loadId === this.loadId) {
      this.ready = true;
    }
  }

  async openConversation(id: string): Promise<void> {
    this.invalidateActiveRequest();
    const loadId = ++this.loadId;
    this.advanceConversationGeneration();
    const wasReady = this.ready;
    this.ready = false;
    this.notice = null;
    const conversation = await this.history.load(id);
    if (loadId !== this.loadId) {
      return;
    }
    if (!conversation) {
      this.notice = "Dit gesprek kon niet worden geopend.";
      this.ready = wasReady || this.history.ready;
      return;
    }
    this.restore(conversation);
    this.ready = true;
  }

  newConversation(): void {
    this.invalidateActiveRequest();
    this.loadId += 1;
    this.advanceConversationGeneration();
    this.history.setActive(null);
    this.activeMode = "local";
    this.cloudConsentVersion = null;
    this.cloudConsentAt = null;
    this.turns = [];
    this.notice = null;
    this.sources.clear();
    this.ready = true;
  }

  async renameConversation(id: string, title: string): Promise<boolean> {
    return this.history.rename(id, title);
  }

  async deleteConversation(id: string): Promise<void> {
    if (this.history.activeId === id) {
      this.newConversation();
    }
    await this.history.delete(id);
  }

  async clearAllConversations(): Promise<void> {
    this.newConversation();
    await this.history.clear();
  }

  async submit(value = this.draft): Promise<void> {
    const question = value.trim();
    if (!question || this.sending || !this.ready) {
      return;
    }
    if (this.activeMode === "local" && this.localAvailable === false) {
      this.notice = "Lokaal is op dit moment niet geconfigureerd.";
      return;
    }
    if (this.activeMode === "cloud" && this.cloudAvailable !== true) {
      this.notice =
        this.cloudAvailable === false
          ? CLOUD_UNAVAILABLE
          : this.modeAvailabilityStatus === "error"
            ? "Beschikbaarheid van Cloud (EU) kon niet worden opgehaald."
            : "Beschikbaarheid van Cloud (EU) wordt nog gecontroleerd.";
      return;
    }
    if (this.activeMode === "cloud" && !this.hasCurrentCloudConsent) {
      this.notice = CLOUD_CONSENT_REQUIRED;
      return;
    }

    this.sending = true;
    this.notice = null;
    const requestId = ++this.requestId;
    const priorTurns = [...this.turns];
    const turn: ChatTurn = {
      id: `turn-${crypto.randomUUID()}`,
      question,
      status: "pending",
      sources: [],
      answer: null,
      errorMessage: null,
    };
    let conversationId = this.history.activeId;
    let createdConversation = false;
    if (!conversationId) {
      const result = await this.history.create(
        question,
        this.activeMode,
        [turn],
        {
          cloudConsentVersion: this.cloudConsentVersion,
          cloudConsentAt: this.cloudConsentAt,
        },
      );
      const conversation = result.conversation;
      if (requestId !== this.requestId) {
        await this.history.delete(conversation.id);
        return;
      }
      if (!result.persisted) {
        this.notice = this.history.storageError;
        if (this.activeMode === "cloud") {
          this.draft = question;
          this.sending = false;
          return;
        }
      }
      conversationId = conversation.id;
      this.history.setActive(conversationId);
      this.activeMode = conversation.mode;
      this.cloudConsentVersion = conversation.cloudConsentVersion;
      this.cloudConsentAt = conversation.cloudConsentAt;
      createdConversation = true;
      this.turns.push(turn);
    } else {
      this.turns.push(turn);
    }

    this.draft = "";
    const request = buildChatRequest(
      priorTurns,
      question,
      this.peildatum,
      this.activeMode,
    );
    this.sources.showTurn(turn.id, []);
    if (!createdConversation) {
      await this.persistConversation(conversationId);
    }
    if (requestId !== this.requestId) {
      return;
    }
    const activeTurn = () => this.turns.find((item) => item.id === turn.id);
    const controller = new AbortController();
    this.controller = controller;

    try {
      for await (const event of this.stream(request, {
        signal: controller.signal,
      })) {
        if (requestId !== this.requestId) {
          return;
        }
        if (event.type === "sources") {
          const currentTurn = activeTurn();
          if (currentTurn) {
            currentTurn.sources = event.sources;
          }
          if (this.sources.activeTurnId === turn.id) {
            this.sources.showTurn(turn.id, event.sources);
          }
          await this.persistConversation(conversationId);
        } else if (event.type === "answer") {
          const currentTurn = activeTurn();
          if (currentTurn) {
            currentTurn.answer = event.answer;
            currentTurn.status = "answered";
          }
          await this.persistConversation(conversationId);
        } else if (event.type === "error") {
          const currentTurn = activeTurn();
          if (currentTurn) {
            currentTurn.errorMessage = event.message;
            currentTurn.status = "error";
          }
          await this.persistConversation(conversationId);
        }
      }
      if (requestId !== this.requestId) {
        return;
      }
      const currentTurn = activeTurn();
      if (currentTurn?.status === "pending") {
        currentTurn.status = "error";
        currentTurn.errorMessage = GENERIC_ERROR;
        await this.persistConversation(conversationId);
      }
    } catch {
      if (requestId !== this.requestId) {
        return;
      }
      const currentTurn = activeTurn();
      if (currentTurn) {
        currentTurn.status = "error";
        currentTurn.errorMessage = GENERIC_ERROR;
        await this.persistConversation(conversationId);
      }
    } finally {
      if (requestId === this.requestId) {
        this.controller = null;
        this.sending = false;
      }
    }
  }

  selectSource(turnId: string, chunkId: string): boolean {
    const turn = this.turns.find((candidate) => candidate.id === turnId);
    if (!turn || !turn.sources.some((source) => source.chunk_id === chunkId)) {
      return false;
    }
    this.sources.showTurn(turnId, turn.sources);
    this.sources.selectChunk(chunkId);
    return true;
  }

  cancel(): void {
    this.controller?.abort();
  }

  private restore(conversation: StoredConversation): void {
    this.history.setActive(conversation.id);
    this.activeMode = conversation.mode;
    this.cloudConsentVersion = conversation.cloudConsentVersion;
    this.cloudConsentAt = conversation.cloudConsentAt;
    this.turns = conversation.messages.map((turn) =>
      turn.status === "pending"
        ? { ...turn, status: "error", errorMessage: INTERRUPTED_ERROR }
        : turn,
    );
    const latestWithSources = [...this.turns]
      .reverse()
      .find((turn) => turn.sources.length > 0);
    if (latestWithSources) {
      this.sources.showTurn(latestWithSources.id, latestWithSources.sources);
    } else {
      this.sources.clear();
    }
  }

  private invalidateActiveRequest(): void {
    this.requestId += 1;
    this.controller?.abort();
    this.controller = null;
    this.sending = false;
  }

  private captureConversationContext(): ConversationContext {
    return {
      conversationId: this.history.activeId,
      generation: this.conversationGeneration,
    };
  }

  private isCurrentModeOperation(
    context: ConversationContext,
    operationId: number,
  ): boolean {
    return (
      context.generation === this.conversationGeneration &&
      context.conversationId === this.history.activeId &&
      operationId === this.modeOperationId
    );
  }

  private advanceConversationGeneration(): void {
    this.conversationGenerationValue += 1;
    this.conversationGeneration = this.conversationGenerationValue;
    this.modeOperationId += 1;
    this.pendingCloudConsent = null;
  }

  private async persistConversation(id: string): Promise<void> {
    const snapshot = $state.snapshot(this.turns) as ChatTurn[];
    const messages = snapshot.map((turn) => ({
      ...turn,
      answer: turn.answer ? { ...turn.answer, verifier_notes: [] } : null,
    }));
    const persisted = await this.history.saveMessages(id, messages);
    if (!persisted) {
      this.notice = this.history.storageError;
    }
  }
}

export function citedSources(
  sourceCards: ChatSourceCard[],
  sourceIds: string[],
): ChatSourceCard[] {
  return sourceIds.flatMap((id) => {
    const source = sourceCards.find((candidate) => candidate.chunk_id === id);
    return source ? [source] : [];
  });
}

export function formatAnswerDate(value: string): string {
  const [year, month, day] = value.split("-");
  if (!year || !month || !day) {
    return value;
  }
  return `${day}-${month}-${year}`;
}

export const STARTER_QUESTIONS = [
  "Dakkapel plaatsen",
  "Uitbouw of aanbouw",
  "Wat is een omgevingsplan?",
] as const;
