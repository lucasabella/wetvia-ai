import type {
  DakkapelRuleRequest,
  DakkapelRuleResponse,
} from "@wetvia/api-client";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DakkapelWizardStore,
  parseMeterInput,
  type RuleChecker,
} from "./dakkapel-wizard-state.svelte";

describe("parseMeterInput", () => {
  it.each([
    ["1,75", "1.75"],
    ["1.7500", "1.75"],
    ["000,50", "0.5"],
    [",5", "0.5"],
    [".1250", "0.125"],
    ["000", "0"],
    ["", null],
    [" 1.2 ", "1.2"],
  ])("normalizes %j to %j exactly", (raw, expected) => {
    expect(parseMeterInput(raw)).toEqual({ valid: true, value: expected });
  });

  it.each(["-1", "1,2.3", "1,", "1.", "1e2", "1 000", "1.2.3"])(
    "rejects malformed meter input %j",
    (raw) => {
      expect(parseMeterInput(raw)).toEqual({ valid: false, value: null });
    },
  );
});

describe("DakkapelWizardStore", () => {
  afterEach(() => vi.useRealTimers());

  it("debounces changes and sends canonical values to the injected checker", async () => {
    vi.useFakeTimers();
    const responses: DakkapelRuleResponse[] = [];
    const checker = vi.fn<RuleChecker>(async (request) => {
      responses.push(fakeResult(request.hoogte_m ?? "null"));
      return responses.at(-1)!;
    });
    const wizard = new DakkapelWizardStore(checker, 250);

    wizard.setMeasurement("hoogte_m", "01,7500");
    wizard.setMeasurement("hoogte_m", "1.75");
    expect(checker).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(249);
    expect(checker).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);

    expect(checker).toHaveBeenCalledTimes(1);
    expect(checker.mock.calls[0]![0].hoogte_m).toBe("1.75");
    expect(wizard.result?.eindoordeel).toBe("onbepaald");
    wizard.dispose();
  });

  it("aborts and ignores a stale response after newer input", async () => {
    vi.useFakeTimers();
    const pending: Array<{
      request: DakkapelRuleRequest;
      signal: AbortSignal;
      resolve: (result: DakkapelRuleResponse) => void;
    }> = [];
    const checker: RuleChecker = (request, signal) =>
      new Promise((resolve) => pending.push({ request, signal, resolve }));
    const wizard = new DakkapelWizardStore(checker, 100);

    wizard.refresh();
    await vi.advanceTimersByTimeAsync(100);
    expect(pending).toHaveLength(1);
    wizard.setInput({ monumentrelatie: "bij_monument" });
    expect(pending[0]!.signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(100);
    expect(pending).toHaveLength(2);

    pending[0]!.resolve(fakeResult("stale"));
    await Promise.resolve();
    expect(wizard.result).toBeNull();
    pending[1]!.resolve(fakeResult("fresh"));
    await Promise.resolve();
    expect(wizard.result?.advies).toBe("fresh");
    expect(pending[1]!.request.monumentrelatie).toBe("bij_monument");
    wizard.dispose();
  });

  it("clears results and cancels backend checks while a measurement is invalid", async () => {
    vi.useFakeTimers();
    const checker = vi.fn<RuleChecker>(async () => fakeResult("fresh"));
    const wizard = new DakkapelWizardStore(checker, 100);
    wizard.setMeasurement("hoogte_m", "1,75");
    await vi.advanceTimersByTimeAsync(100);
    expect(wizard.result?.advies).toBe("fresh");

    wizard.setMeasurement("hoogte_m", "1,7.5");
    expect(wizard.hasInvalidMeasurements).toBe(true);
    expect(wizard.result).toBeNull();
    await vi.advanceTimersByTimeAsync(100);
    expect(checker).toHaveBeenCalledTimes(1);
    wizard.dispose();
  });

  it("blocks the result and concept steps for invalid measurements but allows blanks", () => {
    const checker: RuleChecker = async () => fakeResult("fresh");
    const wizard = new DakkapelWizardStore(checker, 100);
    wizard.setMeasurement("hoogte_m", "1,7.5");

    expect(wizard.setStep(3)).toBe(false);
    expect(wizard.step).toBe(2);
    expect(wizard.stepError).toContain("gemarkeerde maatvelden");

    wizard.setMeasurement("hoogte_m", "");
    expect(wizard.stepError).toBeNull();
    expect(wizard.setStep(3)).toBe(true);
    expect(wizard.step).toBe(3);
    wizard.dispose();
  });
});

function fakeResult(advies: string): DakkapelRuleResponse {
  return {
    advies,
    eindoordeel: "onbepaald",
    eisen: [],
    technische_bouwactiviteit: {
      activiteit: "test activity",
      oordeel: "waarschijnlijk_vergunningvrij",
      artikel: "test article",
      citaat: "Synthetic test quote, not a legal source.",
      contextcitaat: "Synthetic test context, not legal text.",
      bron: {
        regeling: "Synthetic test source",
        artikel: "test article",
        url: "https://example.test/source",
        bwb_id: "TEST",
        toestand_geldig_vanaf: "2026-01-01",
        toestand_geldig_tot: "9999-12-31",
        toestand_modified: "2026-01-01",
        opgehaald_op: "2026-01-02",
        bronbestand: "test.xml",
        bron_url: "https://example.test/source.xml",
        sha256: "test",
      },
      voorbehoud: "Synthetic test caveat.",
      vergunningcheck_url: "https://example.test/check",
    },
    voorbehoud: "Synthetic test caveat.",
    vergunningcheck_url: "https://example.test/check",
  };
}
