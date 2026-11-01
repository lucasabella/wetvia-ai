import type { components } from "@wetvia/api-client";

export type ChatSourceCard = components["schemas"]["ChatSourceCard"];
export type SourceMetadata = ChatSourceCard["metadata"];

export type SourceBadge = {
  label: string;
  className: string;
};

export function sourceBadge(metadata: SourceMetadata): SourceBadge {
  const status = metadata.status as string;
  if (status === "voorstel") {
    return {
      label: "Wetsvoorstel",
      className: "bg-purple-100 text-purple-950",
    };
  }
  if (status === "toekomstig") {
    return {
      label: "Toekomstig",
      className: "bg-blue-100 text-blue-950",
    };
  }
  if (
    metadata.status === "vervallen" ||
    metadata.artikel_status === "vervallen"
  ) {
    return {
      label: "Vervallen",
      className: "bg-gray-200 text-gray-950 line-through decoration-gray-600",
    };
  }
  return {
    label: "Geldend",
    className: "bg-green-100 text-green-950",
  };
}

export function formatValidity(metadata: SourceMetadata): string {
  const start = formatDate(metadata.geldig_vanaf);
  const end = metadata.geldig_tot ? formatDate(metadata.geldig_tot) : "heden";
  return `Geldig van ${start} t/m ${end}`;
}

export function formatDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return value;
  }
  const [, year, month, day] = match;
  const yearNumber = Number(year);
  const monthNumber = Number(month);
  const dayNumber = Number(day);
  const leapYear =
    yearNumber % 4 === 0 && (yearNumber % 100 !== 0 || yearNumber % 400 === 0);
  const daysPerMonth = [
    31,
    leapYear ? 29 : 28,
    31,
    30,
    31,
    30,
    31,
    31,
    30,
    31,
    30,
    31,
  ];
  if (
    monthNumber < 1 ||
    monthNumber > 12 ||
    dayNumber < 1 ||
    dayNumber > (daysPerMonth[monthNumber - 1] ?? 0)
  ) {
    return value;
  }
  return `${day}-${month}-${year}`;
}

export function citationLabelFor(
  sources: ChatSourceCard[],
  chunkId: string,
): string | undefined {
  return sources.find((source) => source.chunk_id === chunkId)?.label;
}

/** Per-shell source selection; cards are restored from the active conversation. */
export class SourcesStore {
  items = $state<ChatSourceCard[]>([]);
  activeTurnId = $state<string | null>(null);
  selectedChunkId = $state<string | null>(null);
  selectionRevision = $state(0);

  showTurn(turnId: string, items: ChatSourceCard[]): void {
    this.activeTurnId = turnId;
    this.items = items;
    this.selectedChunkId = null;
    this.selectionRevision += 1;
  }

  clear(): void {
    this.activeTurnId = null;
    this.items = [];
    this.selectedChunkId = null;
    this.selectionRevision += 1;
  }

  selectChunk(chunkId: string): void {
    if (!this.items.some((source) => source.chunk_id === chunkId)) {
      return;
    }
    this.selectedChunkId = chunkId;
    this.selectionRevision += 1;
  }

  clearHighlight(): void {
    this.selectedChunkId = null;
  }
}
