import type { ChatEvent, ChatRequest, components } from "@wetvia/api-client";
import type { SourcesStore, ChatSourceCard } from "../sources/sources.svelte";

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
const GENERIC_ERROR = "Er is iets misgegaan. Probeer het opnieuw.";

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
): ChatRequest {
  const history = turns.slice(-MAX_HISTORY_TURNS).flatMap((turn) => {
    const messages: ChatRequest["messages"] = [
      { role: "user", content: turn.question },
    ];
    if (turn.answer) {
      messages.push({ role: "assistant", content: turn.answer.samenvatting });
    }
    return messages;
  });
  return {
    messages: [...history, { role: "user", content: question }],
    peildatum,
  };
}

/** In-memory conversation and currently selected turn; no browser persistence. */
export class ChatStore {
  turns = $state<ChatTurn[]>([]);
  draft = $state("");
  sending = $state(false);
  peildatum = $state(currentDateISO());

  private readonly stream: ChatStreamer;
  private readonly sources: SourcesStore;
  private requestId = 0;
  private controller: AbortController | null = null;

  constructor(stream: ChatStreamer, sources: SourcesStore) {
    this.stream = stream;
    this.sources = sources;
  }

  async submit(value = this.draft): Promise<void> {
    const question = value.trim();
    if (!question || this.sending) {
      return;
    }

    this.draft = "";
    this.sending = true;
    const turn: ChatTurn = {
      id: `turn-${++this.requestId}`,
      question,
      status: "pending",
      sources: [],
      answer: null,
      errorMessage: null,
    };
    const request = buildChatRequest(this.turns, question, this.peildatum);
    this.turns.push(turn);
    this.sources.showTurn(turn.id, []);
    const activeTurn = () => this.turns.find((item) => item.id === turn.id);
    this.controller = new AbortController();

    try {
      for await (const event of this.stream(request, {
        signal: this.controller.signal,
      })) {
        if (event.type === "sources") {
          const currentTurn = activeTurn();
          if (currentTurn) {
            currentTurn.sources = event.sources;
          }
          if (this.sources.activeTurnId === turn.id) {
            this.sources.showTurn(turn.id, event.sources);
          }
        } else if (event.type === "answer") {
          const currentTurn = activeTurn();
          if (currentTurn) {
            currentTurn.answer = event.answer;
            currentTurn.status = "answered";
          }
        } else if (event.type === "error") {
          const currentTurn = activeTurn();
          if (currentTurn) {
            currentTurn.errorMessage = event.message;
            currentTurn.status = "error";
          }
        }
      }
      const currentTurn = activeTurn();
      if (currentTurn?.status === "pending") {
        currentTurn.status = "error";
        currentTurn.errorMessage = GENERIC_ERROR;
      }
    } catch {
      const currentTurn = activeTurn();
      if (currentTurn) {
        currentTurn.status = "error";
        currentTurn.errorMessage = GENERIC_ERROR;
      }
    } finally {
      this.controller = null;
      this.sending = false;
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
