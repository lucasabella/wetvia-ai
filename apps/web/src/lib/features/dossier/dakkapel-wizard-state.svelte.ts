import type {
  DakkapelRuleRequest,
  DakkapelRuleResponse,
} from "@wetvia/api-client";

export const MEASUREMENT_FIELDS = [
  "hoogte_m",
  "onderzijde_boven_dakvoet_m",
  "bovenzijde_onder_daknok_m",
  "linker_zijkant_tot_dakvlakrand_m",
  "rechter_zijkant_tot_dakvlakrand_m",
] as const satisfies readonly (keyof DakkapelRuleRequest)[];

export type MeasurementField = (typeof MEASUREMENT_FIELDS)[number];
export type RuleChecker = (
  request: DakkapelRuleRequest,
  signal: AbortSignal,
) => Promise<DakkapelRuleResponse>;

export type ParsedMeasurement = {
  valid: boolean;
  value: string | null;
};

const EMPTY_REQUEST: DakkapelRuleRequest = {
  dakvlak: "onbekend",
  dakvlak_naar_openbaar_toegankelijk_gebied: null,
  plat_dak: null,
  hoogte_m: null,
  onderzijde_boven_dakvoet_m: null,
  bovenzijde_onder_daknok_m: null,
  linker_zijkant_tot_dakvlakrand_m: null,
  rechter_zijkant_tot_dakvlakrand_m: null,
  monumentrelatie: "onbekend",
  gebiedsbescherming: "onbekend",
};

const EMPTY_MEASUREMENTS: Record<MeasurementField, string> = {
  hoogte_m: "",
  onderzijde_boven_dakvoet_m: "",
  bovenzijde_onder_daknok_m: "",
  linker_zijkant_tot_dakvlakrand_m: "",
  rechter_zijkant_tot_dakvlakrand_m: "",
};

const EMPTY_VALIDITY: Record<MeasurementField, boolean> = {
  hoogte_m: true,
  onderzijde_boven_dakvoet_m: true,
  bovenzijde_onder_daknok_m: true,
  linker_zijkant_tot_dakvlakrand_m: true,
  rechter_zijkant_tot_dakvlakrand_m: true,
};

/** Parse a user meter value exactly, without converting through JS Number. */
export function parseMeterInput(raw: string): ParsedMeasurement {
  const value = raw.trim();
  if (value === "") {
    return { valid: true, value: null };
  }
  if (value.length > 64 || !/^(?:\d+(?:[,.]\d+)?|[,.]\d+)$/.test(value)) {
    return { valid: false, value: null };
  }

  const normalized = value.replace(",", ".");
  const withWholePart = normalized.startsWith(".")
    ? `0${normalized}`
    : normalized;
  const [whole = "0", fraction] = withWholePart.split(".");
  const canonicalWhole = whole.replace(/^0+(?=\d)/, "") || "0";
  const canonicalFraction = fraction?.replace(/0+$/, "");

  return {
    valid: true,
    value: canonicalFraction
      ? `${canonicalWhole}.${canonicalFraction}`
      : canonicalWhole,
  };
}

/** Per-page, in-memory state and debounced calls to the public rules endpoint. */
export class DakkapelWizardStore {
  step = $state(0);
  input = $state<DakkapelRuleRequest>({ ...EMPTY_REQUEST });
  rawMeasurements = $state<Record<MeasurementField, string>>({
    ...EMPTY_MEASUREMENTS,
  });
  validMeasurements = $state<Record<MeasurementField, boolean>>({
    ...EMPTY_VALIDITY,
  });
  result = $state<DakkapelRuleResponse | null>(null);
  checking = $state(false);
  error = $state<string | null>(null);
  stepError = $state<string | null>(null);

  private timer: ReturnType<typeof setTimeout> | undefined;
  private controller: AbortController | undefined;
  private revision = 0;

  constructor(
    private readonly check: RuleChecker,
    private readonly debounceMs = 300,
  ) {}

  get hasInvalidMeasurements(): boolean {
    return MEASUREMENT_FIELDS.some((field) => !this.validMeasurements[field]);
  }

  setStep(step: number): boolean {
    const target = Math.min(4, Math.max(0, step));
    if (target >= 3 && this.hasInvalidMeasurements) {
      this.step = 2;
      this.stepError =
        "Controleer de gemarkeerde maatvelden voordat u naar het resultaat gaat.";
      return false;
    }
    this.stepError = null;
    this.step = target;
    return true;
  }

  refresh(): void {
    this.scheduleCheck();
  }

  setInput(patch: Partial<DakkapelRuleRequest>): void {
    this.input = { ...this.input, ...patch };
    this.scheduleCheck();
  }

  setMeasurement(field: MeasurementField, raw: string): void {
    const parsed = parseMeterInput(raw);
    this.rawMeasurements = { ...this.rawMeasurements, [field]: raw };
    this.validMeasurements = {
      ...this.validMeasurements,
      [field]: parsed.valid,
    };
    this.input = { ...this.input, [field]: parsed.value };
    if (parsed.valid && !this.hasInvalidMeasurements) {
      this.stepError = null;
    }
    this.scheduleCheck();
  }

  dispose(): void {
    this.revision += 1;
    this.clearPendingCheck();
    this.checking = false;
  }

  private scheduleCheck(): void {
    this.revision += 1;
    const revision = this.revision;
    this.clearPendingCheck();
    this.result = null;
    this.error = null;
    this.checking = false;

    if (this.hasInvalidMeasurements) {
      return;
    }

    const request = { ...this.input };
    this.checking = true;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      const controller = new AbortController();
      this.controller = controller;
      void this.runCheck(request, controller, revision);
    }, this.debounceMs);
  }

  private async runCheck(
    request: DakkapelRuleRequest,
    controller: AbortController,
    revision: number,
  ): Promise<void> {
    try {
      const result = await this.check(request, controller.signal);
      if (this.isCurrent(revision, controller)) {
        this.result = result;
      }
    } catch {
      if (this.isCurrent(revision, controller)) {
        this.error =
          "De toets kon niet worden bijgewerkt. Probeer het opnieuw.";
      }
    } finally {
      if (this.isCurrent(revision, controller)) {
        this.checking = false;
        this.controller = undefined;
      }
    }
  }

  private isCurrent(revision: number, controller: AbortController): boolean {
    return revision === this.revision && !controller.signal.aborted;
  }

  private clearPendingCheck(): void {
    if (this.timer !== undefined) {
      clearTimeout(this.timer);
      this.timer = undefined;
    }
    this.controller?.abort();
    this.controller = undefined;
  }
}
