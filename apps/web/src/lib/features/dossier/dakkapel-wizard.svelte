<script lang="ts">
  import { resolve } from "$app/paths";
  import { onMount, tick } from "svelte";
  import type {
    DakkapelRuleRequest,
    DakkapelRuleResponse,
    WetviaClient,
  } from "@wetvia/api-client";

  import {
    DakkapelWizardStore,
    MEASUREMENT_FIELDS,
    parseMeterInput,
    type MeasurementField,
  } from "./dakkapel-wizard-state.svelte";

  let { client }: { client: WetviaClient } = $props();

  const wizard = new DakkapelWizardStore(async (body, signal) => {
    const { data, error } = await client.POST("/api/rules/dakkapel", {
      body,
      signal,
    });
    if (error || !data) {
      throw new Error("The dakkapel check request failed.");
    }
    return data;
  });

  const steps = ["Locatie", "Dakvlak", "Maten", "Resultaat", "Conceptdossier"];

  type RoofValue = DakkapelRuleRequest["dakvlak"];
  const roofChoices: { value: RoofValue; label: string; points: string }[] = [
    {
      value: "ander_dakvlak",
      label: "Voorzijde",
      points: "9,8 36,2 63,8 63,33 9,33",
    },
    {
      value: "achterdakvlak",
      label: "Achterzijde",
      points: "9,8 36,2 63,8 63,33 9,33",
    },
    {
      value: "zijdakvlak",
      label: "Zijkant",
      points: "12,8 42,3 60,9 60,33 12,33",
    },
    {
      value: "onbekend",
      label: "Weet ik niet",
      points: "8,8 36,2 64,8 64,33 8,33",
    },
  ];

  const measurementDetails: {
    field: MeasurementField;
    label: string;
    help: string;
    eis: DakkapelRuleResponse["eisen"][number]["eis"];
  }[] = [
    {
      field: "hoogte_m",
      label: "Hoogte vanaf de voet",
      help: "Meet recht omhoog vanaf de voet van de dakkapel.",
      eis: "hoogte",
    },
    {
      field: "onderzijde_boven_dakvoet_m",
      label: "Onderzijde boven de dakvoet",
      help: "Meet de afstand tussen de onderzijde en de dakvoet.",
      eis: "onderzijde",
    },
    {
      field: "bovenzijde_onder_daknok_m",
      label: "Bovenzijde onder de daknok",
      help: "Meet de afstand tussen de bovenzijde en de daknok.",
      eis: "bovenzijde",
    },
    {
      field: "linker_zijkant_tot_dakvlakrand_m",
      label: "Linkerzijkant tot de dakvlakrand",
      help: "Meet de afstand tot de linkerzijkant van het dakvlak.",
      eis: "linker_zijkant",
    },
    {
      field: "rechter_zijkant_tot_dakvlakrand_m",
      label: "Rechterzijkant tot de dakvlakrand",
      help: "Meet de afstand tot de rechterzijkant van het dakvlak.",
      eis: "rechter_zijkant",
    },
  ];
  const contextRequirements = [
    "locatie",
    "monument",
    "gebiedsbescherming",
  ] as const satisfies readonly DakkapelRuleResponse["eisen"][number]["eis"][];

  let address = $state("");

  onMount(() => {
    wizard.refresh();
    return () => wizard.dispose();
  });

  function requirement(
    code: DakkapelRuleResponse["eisen"][number]["eis"],
  ): DakkapelRuleResponse["eisen"][number] | undefined {
    return wizard.result?.eisen.find((item) => item.eis === code);
  }

  function indicatorLabel(value: boolean | null | undefined): string {
    if (value === true) return "Voldaan";
    if (value === false) return "Niet voldaan";
    return "Nog onbekend";
  }

  function indicatorClass(value: boolean | null | undefined): string {
    if (value === true) return "border-green-700 bg-green-50 text-green-900";
    if (value === false) return "border-red-700 bg-red-50 text-red-900";
    return "border-border bg-muted text-foreground";
  }

  function verdictLabel(result: DakkapelRuleResponse): string {
    switch (result.eindoordeel) {
      case "waarschijnlijk_vergunningvrij":
        return "Waarschijnlijk vergunningvrij";
      case "waarschijnlijk_vergunningplichtig":
        return "Waarschijnlijk vergunning nodig";
      case "onbepaald":
        return "Dat kunnen we niet bepalen";
    }
  }

  function verdictExplanation(result: DakkapelRuleResponse): string {
    if (result.eindoordeel === "waarschijnlijk_vergunningvrij") {
      return "De ingevoerde gegevens voldoen aan de getoetste voorwaarden.";
    }
    if (result.eindoordeel === "onbepaald") {
      return (
        result.advies ?? "Er ontbreken gegevens om deze toets af te maken."
      );
    }
    const failed = result.eisen.find((item) => item.voldaan === false);
    return (
      failed?.toelichting ??
      failed?.omschrijving ??
      "Een van de getoetste voorwaarden is niet voldaan."
    );
  }

  function sketchDimension(
    field: MeasurementField,
    fallback: number,
    minimum: number,
    maximum: number,
  ): number {
    const parsed = parseMeterInput(wizard.rawMeasurements[field]);
    if (!parsed.valid || parsed.value === null) return fallback;
    const numeric = Number(parsed.value);
    if (!Number.isFinite(numeric)) return fallback;
    return Math.max(minimum, Math.min(maximum, numeric * 22));
  }

  function next(): void {
    navigateToStep(wizard.step + 1);
  }

  function back(): void {
    navigateToStep(wizard.step - 1);
  }

  function navigateToStep(step: number): void {
    if (wizard.setStep(step)) return;
    const firstInvalid = MEASUREMENT_FIELDS.find(
      (field) => !wizard.validMeasurements[field],
    );
    void tick().then(() => {
      if (firstInvalid) document.getElementById(firstInvalid)?.focus();
    });
  }

  const diagramHeight = $derived(sketchDimension("hoogte_m", 58, 18, 64));
  const diagramUnderside = $derived(
    sketchDimension("onderzijde_boven_dakvoet_m", 30, 10, 36),
  );
  const diagramTopGap = $derived(
    sketchDimension("bovenzijde_onder_daknok_m", 38, 10, 36),
  );
  const diagramLeft = $derived(
    sketchDimension("linker_zijkant_tot_dakvlakrand_m", 34, 16, 44),
  );
  const diagramRight = $derived(
    sketchDimension("rechter_zijkant_tot_dakvlakrand_m", 34, 16, 44),
  );
  const diagramBottom = $derived(158 - diagramUnderside);
  const diagramTop = $derived(diagramBottom - diagramHeight);
  const diagramRoofPeak = $derived(diagramTop - diagramTopGap);
  const flatRoof = $derived(requirement("plat_dak"));
</script>

<section
  class="mx-auto flex h-full min-h-0 max-w-4xl flex-col"
  aria-labelledby="dakkapel-kop"
>
  <header class="mb-4 space-y-1">
    <p class="text-sm text-muted-foreground">
      Dossier · stap {wizard.step + 1} van 5
    </p>
    <h1 id="dakkapel-kop" class="text-xl font-semibold">Dakkapeltoets</h1>
    <p class="text-sm text-muted-foreground">
      Vul de gegevens stap voor stap in. De toets controleert de Bbl-voorwaarden
      en laat de bron zien.
    </p>
  </header>

  <nav aria-label="Stappen in de dakkapeltoets" class="mb-5">
    <ol class="grid grid-cols-5 gap-1 sm:gap-2">
      {#each steps as stepName, index (stepName)}
        <li>
          <button
            type="button"
            class={`min-h-11 w-full rounded-md border px-1 text-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring sm:px-2 sm:text-sm ${wizard.step === index ? "border-primary bg-accent font-semibold" : "border-border bg-background"}`}
            aria-current={wizard.step === index ? "step" : undefined}
            onclick={() => navigateToStep(index)}
          >
            <span class="block text-muted-foreground">{index + 1}</span>
            <span>{stepName}</span>
          </button>
        </li>
      {/each}
    </ol>
  </nav>

  <div
    class="min-h-0 flex-1 overflow-y-auto rounded-xl border border-border bg-card p-4 sm:p-6"
  >
    {#if wizard.step === 0}
      <section aria-labelledby="locatie-kop" class="space-y-5">
        <div>
          <h2 id="locatie-kop" class="text-lg font-semibold">
            Locatie en bescherming
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Deze stap vraagt naar monumenten en beschermd gebied. Er is nog geen
            adreslookup; uw adres wordt niet naar de toets gestuurd.
          </p>
        </div>

        <div class="space-y-2">
          <label for="dakkapel-adres" class="block text-sm font-medium"
            >Adres (alleen voor dit concept)</label
          >
          <input
            id="dakkapel-adres"
            bind:value={address}
            autocomplete="street-address"
            class="min-h-11 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            placeholder="Straat en plaats"
          />
          <p class="text-xs text-muted-foreground">
            Het adres blijft alleen in deze geopende pagina.
          </p>
        </div>

        <fieldset class="space-y-2">
          <legend class="text-sm font-medium"
            >Wat is de relatie van de dakkapel tot een beschermd monument?</legend
          >
          <p class="text-xs text-muted-foreground">
            Kies waar het werk wordt uitgevoerd: in, aan of op een monument,
            alleen bij een monument, of weet ik niet.
          </p>
          {#each [["geen_monument", "Geen beschermd monument"], ["in_aan_of_op_monument", "In, aan of op een beschermd monument"], ["bij_monument", "Alleen bij een beschermd monument"], ["onbekend", "Weet ik niet"]] as [value, label] (value)}
            <label
              class="flex min-h-10 items-center gap-3 rounded-md border border-border px-3 text-sm"
            >
              <input
                type="radio"
                name="monumentrelatie"
                {value}
                checked={wizard.input.monumentrelatie === value}
                onchange={() =>
                  wizard.setInput({
                    monumentrelatie:
                      value as DakkapelRuleRequest["monumentrelatie"],
                  })}
              />
              {label}
            </label>
          {/each}
        </fieldset>

        <fieldset class="space-y-2">
          <legend class="text-sm font-medium"
            >Ligt de woning in een rijksbeschermd stads- of dorpsgezicht?</legend
          >
          {#each [["rijksbeschermd_stads_of_dorpsgezicht", "Ja"], ["geen_rijksbeschermd_stads_of_dorpsgezicht", "Nee"], ["onbekend", "Weet ik niet"]] as [value, label] (value)}
            <label
              class="flex min-h-10 items-center gap-3 rounded-md border border-border px-3 text-sm"
            >
              <input
                type="radio"
                name="gebiedsbescherming"
                {value}
                checked={wizard.input.gebiedsbescherming === value}
                onchange={() =>
                  wizard.setInput({
                    gebiedsbescherming:
                      value as DakkapelRuleRequest["gebiedsbescherming"],
                  })}
              />
              {label}
            </label>
          {/each}
        </fieldset>
      </section>
    {:else if wizard.step === 1}
      <section aria-labelledby="dakvlak-kop" class="space-y-5">
        <div>
          <h2 id="dakvlak-kop" class="text-lg font-semibold">
            Plaats op het dak
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Kies het dakvlak. De tekening is schematisch.
          </p>
        </div>

        <svg
          viewBox="0 0 260 150"
          role="img"
          aria-labelledby="dakillustratie-title"
          class="mx-auto h-40 w-full max-w-sm"
        >
          <title id="dakillustratie-title"
            >Schematische woning met voor-, achter- en zijdakvlak</title
          >
          <path
            d="M40 72 130 22 220 72v62H40z"
            fill="none"
            stroke="currentColor"
            stroke-width="3"
          />
          <path d="M40 72 130 22v112H40z" fill="currentColor" opacity=".12" />
          <path d="M130 22 220 72v62h-90z" fill="currentColor" opacity=".24" />
          <path
            d="M220 72 242 60v61l-22 13z"
            fill="currentColor"
            opacity=".08"
            stroke="currentColor"
            stroke-width="2"
          />
          <text x="67" y="94" font-size="12" fill="currentColor">VOOR</text>
          <text x="154" y="94" font-size="12" fill="currentColor">ACHTER</text>
          <text x="222" y="99" font-size="10" fill="currentColor">ZIJ</text>
        </svg>

        <div
          role="group"
          aria-label="Kies een dakvlak"
          class="grid grid-cols-2 gap-3 sm:grid-cols-4"
        >
          {#each roofChoices as choice (choice.value)}
            <button
              type="button"
              aria-pressed={wizard.input.dakvlak === choice.value}
              aria-label={`${choice.label} kiezen`}
              class={`flex min-h-24 flex-col items-center justify-center gap-2 rounded-lg border p-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring ${wizard.input.dakvlak === choice.value ? "border-primary bg-accent font-semibold" : "border-border hover:bg-muted"}`}
              onclick={() => wizard.setInput({ dakvlak: choice.value })}
            >
              <svg viewBox="0 0 72 40" aria-hidden="true" class="h-10 w-16">
                <polygon
                  points={choice.points}
                  fill="currentColor"
                  fill-opacity=".2"
                  stroke="currentColor"
                  stroke-width="2"
                />
                {#if choice.value === "onbekend"}
                  <text x="30" y="27" font-size="22" fill="currentColor">?</text
                  >
                {/if}
              </svg>
              {choice.label}
            </button>
          {/each}
        </div>

        {#if wizard.input.dakvlak === "zijdakvlak" || (wizard.input.dakvlak === "achterdakvlak" && wizard.input.gebiedsbescherming === "rijksbeschermd_stads_of_dorpsgezicht")}
          <fieldset class="space-y-2 rounded-lg border border-border p-4">
            <legend class="px-1 text-sm font-medium">
              {wizard.input.dakvlak === "zijdakvlak"
                ? "Ligt dit zijdakvlak naar openbaar toegankelijk gebied, zoals een straat of openbaar pad?"
                : "Keert dit achterdakvlak naar openbaar toegankelijk gebied?"}
            </legend>
            {#each [[true, "Ja"], [false, "Nee"], [null, "Weet ik niet"]] as [value, label] (String(value))}
              <label class="flex min-h-10 items-center gap-3 text-sm">
                <input
                  type="radio"
                  name="zijdak-openbaar"
                  checked={wizard.input
                    .dakvlak_naar_openbaar_toegankelijk_gebied === value}
                  onchange={() =>
                    wizard.setInput({
                      dakvlak_naar_openbaar_toegankelijk_gebied: value as
                        boolean | null,
                    })}
                />
                {label}
              </label>
            {/each}
          </fieldset>
        {/if}
      </section>
    {:else if wizard.step === 2}
      <section aria-labelledby="maten-kop" class="space-y-5">
        <div>
          <h2 id="maten-kop" class="text-lg font-semibold">
            Maten van de dakkapel
          </h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Vul de maten in meters in. Een komma of punt werkt. De tekening
            beweegt mee en is niet op schaal.
          </p>
        </div>

        <fieldset class="space-y-2">
          <legend class="text-sm font-medium"
            >Heeft de dakkapel een plat dak?</legend
          >
          {#each [[true, "Ja"], [false, "Nee"], [null, "Weet ik niet"]] as [value, label] (String(value))}
            <label class="inline-flex min-h-10 items-center gap-2 pr-5 text-sm">
              <input
                type="radio"
                name="plat-dak"
                checked={wizard.input.plat_dak === value}
                onchange={() =>
                  wizard.setInput({ plat_dak: value as boolean | null })}
              />
              {label}
            </label>
          {/each}
        </fieldset>

        <svg
          viewBox="0 0 320 200"
          role="img"
          aria-labelledby="maten-illustratie-title"
          class="mx-auto h-48 w-full max-w-lg rounded-lg border border-border bg-background p-2"
        >
          <title id="maten-illustratie-title"
            >Schematische dakkapel met maatlijnen</title
          >
          <path
            data-testid="dak-schets"
            d={`M30 158 160 ${diagramRoofPeak} 290 158`}
            fill="none"
            stroke="currentColor"
            stroke-width="5"
          />
          <line
            x1="30"
            y1="158"
            x2="290"
            y2="158"
            stroke="currentColor"
            stroke-width="2"
          />
          <rect
            data-testid="dakkapel-schets"
            x={160 - diagramLeft - 54}
            y={diagramTop}
            width={Math.max(35, 108 - diagramLeft - diagramRight)}
            height={diagramHeight}
            rx="3"
            fill="currentColor"
            fill-opacity=".16"
            stroke="currentColor"
            stroke-width="3"
          />
          <line
            x1="160"
            y1={diagramTop}
            x2="160"
            y2={diagramBottom}
            stroke="currentColor"
            stroke-dasharray="4 3"
          />
          <line
            data-testid="nokafstand-schets"
            x1="207"
            y1={diagramRoofPeak}
            x2="207"
            y2={diagramTop}
            stroke="currentColor"
            stroke-dasharray="4 3"
          />
          <line
            data-testid="dakvoetafstand-schets"
            x1="118"
            y1={diagramBottom}
            x2="118"
            y2="158"
            stroke="currentColor"
            stroke-dasharray="4 3"
          />
          <text
            x="171"
            y={(diagramTop + diagramBottom) / 2}
            font-size="12"
            fill="currentColor">hoogte</text
          >
          <text x="12" y="176" font-size="10" fill="currentColor">dakvoet</text>
          <text x="142" y="31" font-size="10" fill="currentColor">nok</text>
        </svg>

        <div class="grid gap-4 sm:grid-cols-2">
          {#each measurementDetails as detail (detail.field)}
            {@const item = requirement(detail.eis)}
            <div class="space-y-2 rounded-lg border border-border p-3">
              <label for={detail.field} class="block text-sm font-medium"
                >{detail.label} (m)</label
              >
              <input
                id={detail.field}
                type="text"
                inputmode="decimal"
                autocomplete="off"
                maxlength="64"
                placeholder="bijv. 1,75"
                value={wizard.rawMeasurements[detail.field]}
                aria-invalid={!wizard.validMeasurements[detail.field]}
                aria-describedby={wizard.stepError
                  ? `${detail.field}-help ${detail.field}-error measure-navigation-error`
                  : `${detail.field}-help ${detail.field}-error`}
                class="min-h-11 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                oninput={(event) =>
                  wizard.setMeasurement(
                    detail.field,
                    event.currentTarget.value,
                  )}
              />
              <p
                id={`${detail.field}-help`}
                class="text-xs text-muted-foreground"
              >
                {detail.help}
              </p>
              {#if !wizard.validMeasurements[detail.field]}
                <p id={`${detail.field}-error`} class="text-sm text-red-900">
                  Gebruik een niet-negatief getal met komma of punt,
                  bijvoorbeeld 1,75.
                </p>
              {:else}
                <span id={`${detail.field}-error`} class="sr-only"
                  >Geen invoerfout.</span
                >
              {/if}
              <div
                class={`flex items-center justify-between gap-2 rounded-md border px-2 py-1 text-xs ${indicatorClass(item?.voldaan)}`}
                aria-label={`${detail.label}: ${indicatorLabel(item?.voldaan)}`}
              >
                <span>{indicatorLabel(item?.voldaan)}</span>
                <span>{item?.artikel ?? "Artikel 2.29, onder b"}</span>
              </div>
              {#if item?.toelichting}
                <p class="text-xs text-muted-foreground">{item.toelichting}</p>
              {/if}
            </div>
          {/each}
        </div>

        <div
          class={`flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm ${indicatorClass(flatRoof?.voldaan)}`}
          aria-label={`Plat dak: ${indicatorLabel(flatRoof?.voldaan)}`}
        >
          <span>Plat dak · {indicatorLabel(flatRoof?.voldaan)}</span>
          <span>{flatRoof?.artikel ?? "Artikel 2.29, onder b, onder 1°"}</span>
        </div>
        <section
          aria-label="Locatie- en beschermingsvoorwaarden"
          class="space-y-2"
        >
          {#each contextRequirements as code (code)}
            {@const item = requirement(code)}
            <div
              class={`flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm ${indicatorClass(item?.voldaan)}`}
            >
              <span
                >{item?.omschrijving ?? code.replaceAll("_", " ")} · {indicatorLabel(
                  item?.voldaan,
                )}</span
              >
              <span>{item?.artikel ?? "Artikel 2.30"}</span>
            </div>
          {/each}
        </section>
        {#if wizard.checking}
          <p
            class="text-sm text-muted-foreground"
            role="status"
            aria-live="polite"
          >
            De toets wordt bijgewerkt…
          </p>
        {/if}
        {#if wizard.error}
          <p class="text-sm text-red-900" role="alert">{wizard.error}</p>
        {/if}
        {#if wizard.stepError}
          <p
            id="measure-navigation-error"
            class="text-sm text-red-900"
            role="alert"
            aria-live="assertive"
          >
            {wizard.stepError}
          </p>
        {/if}
      </section>
    {:else if wizard.step === 3}
      <section aria-labelledby="resultaat-kop" class="space-y-5">
        <div>
          <h2 id="resultaat-kop" class="text-lg font-semibold">Resultaat</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Dit is een voorlopige toets van de ingevoerde feiten.
          </p>
        </div>
        {#if wizard.checking || (!wizard.result && !wizard.error)}
          <p
            role="status"
            aria-live="polite"
            class="rounded-lg border border-border p-4 text-sm"
          >
            De toets wordt bijgewerkt…
          </p>
        {:else if wizard.error}
          <p
            role="alert"
            class="rounded-lg border border-red-700 bg-red-50 p-4 text-sm text-red-900"
          >
            {wizard.error}
          </p>
        {:else if wizard.result}
          <section
            class="space-y-3 rounded-lg border border-primary bg-accent p-4"
            aria-labelledby="eindoordeel-kop"
          >
            <h3 id="eindoordeel-kop" class="text-base font-semibold">
              {verdictLabel(wizard.result)}
            </h3>
            <p class="text-sm leading-relaxed">
              {verdictExplanation(wizard.result)}
            </p>
          </section>

          <ul class="space-y-3" aria-label="Toets per eis">
            {#each wizard.result.eisen as item (`${item.eis}-${item.artikel}`)}
              <li class="rounded-lg border border-border p-4">
                <div
                  class="mb-2 flex flex-wrap items-center justify-between gap-2"
                >
                  <h3 class="font-medium">{item.omschrijving}</h3>
                  <span
                    class={`rounded-full border px-2 py-1 text-xs ${indicatorClass(item.voldaan)}`}
                    >{indicatorLabel(item.voldaan)}</span
                  >
                </div>
                <p class="text-sm">{item.artikel}</p>
                {#if item.toelichting}<p
                    class="mt-1 text-sm text-muted-foreground"
                  >
                    {item.toelichting}
                  </p>{/if}
                <blockquote
                  class="mt-3 border-l-2 border-primary pl-3 font-serif text-sm leading-relaxed"
                >
                  “{item.citaat}”
                </blockquote>
                {#if item.contextcitaat}
                  <p class="mt-2 text-xs text-muted-foreground">
                    Context: “{item.contextcitaat}”
                  </p>
                {/if}
                <p class="mt-3 text-xs text-muted-foreground">
                  {item.bron.bwb_id} · geldig vanaf {item.bron
                    .toestand_geldig_vanaf} · bron opgehaald {item.bron
                    .opgehaald_op}
                </p>
                <!-- eslint-disable svelte/no-navigation-without-resolve -->
                <a
                  class="mt-2 inline-block text-sm text-primary underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  href={item.bron.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Bekijk {item.bron.artikel} op wetten.overheid.nl ↗
                </a>
                <!-- eslint-enable svelte/no-navigation-without-resolve -->
              </li>
            {/each}
          </ul>

          <section
            class="rounded-lg border border-border p-4"
            aria-labelledby="technische-activiteit-kop"
          >
            <h3 id="technische-activiteit-kop" class="font-semibold">
              Technische bouwactiviteit apart
            </h3>
            <p class="mt-1 text-sm">
              {wizard.result.technische_bouwactiviteit.artikel} · {wizard.result.technische_bouwactiviteit.oordeel.replaceAll(
                "_",
                " ",
              )}
            </p>
            <blockquote
              class="mt-3 border-l-2 border-primary pl-3 font-serif text-sm"
            >
              “{wizard.result.technische_bouwactiviteit.citaat}”
            </blockquote>
            <p class="mt-2 text-xs text-muted-foreground">
              Context: “{wizard.result.technische_bouwactiviteit.contextcitaat}”
            </p>
            <p class="mt-2 text-xs text-muted-foreground">
              {wizard.result.technische_bouwactiviteit.bron.bwb_id} · bron opgehaald
              {wizard.result.technische_bouwactiviteit.bron.opgehaald_op}
            </p>
            <!-- eslint-disable svelte/no-navigation-without-resolve -->
            <a
              class="mt-2 inline-block text-sm text-primary underline underline-offset-2"
              href={wizard.result.technische_bouwactiviteit.bron.url}
              target="_blank"
              rel="noopener noreferrer"
              >Bekijk {wizard.result.technische_bouwactiviteit.artikel} op wetten.overheid.nl
              ↗</a
            >
            <!-- eslint-enable svelte/no-navigation-without-resolve -->
          </section>

          <aside
            class="rounded-lg border border-amber-700 bg-amber-50 p-4 text-sm text-amber-950"
          >
            <p>{wizard.result.voorbehoud}</p>
            <!-- eslint-disable svelte/no-navigation-without-resolve -->
            <a
              class="mt-2 inline-block font-medium underline underline-offset-2"
              href={wizard.result.vergunningcheck_url}
              target="_blank"
              rel="noopener noreferrer"
              >Controleer dit bij de officiële Vergunningcheck ↗</a
            >
            <!-- eslint-enable svelte/no-navigation-without-resolve -->
          </aside>
        {/if}
      </section>
    {:else}
      <section aria-labelledby="concept-kop" class="space-y-5">
        <div>
          <h2 id="concept-kop" class="text-lg font-semibold">Conceptdossier</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Controleer de ingevulde gegevens en de toets voordat u verdergaat.
          </p>
        </div>
        <div
          class="relative overflow-hidden rounded-xl border-2 border-amber-600 bg-amber-50 p-5 text-amber-950"
        >
          <p
            class="absolute top-8 right-2 rotate-12 border-2 border-amber-800 px-2 py-1 text-center text-xs font-bold tracking-widest sm:right-8"
          >
            CONCEPT
          </p>
          <p class="max-w-[75%] text-sm font-semibold">
            CONCEPT, gemaakt met Wetvia (AI). Niet gecontroleerd door een
            deskundige.
          </p>
          <p class="mt-3 text-sm">
            Dit is een concept, gemaakt met AI. Laat het controleren voordat u
            het indient.
          </p>
        </div>
        <section
          class="space-y-2 rounded-lg border border-border p-4"
          aria-labelledby="concept-invoer-kop"
        >
          <h3 id="concept-invoer-kop" class="font-semibold">
            Ingevoerde gegevens
          </h3>
          <p class="text-sm">Adres: {address.trim() || "Niet ingevuld"}</p>
          <p class="text-sm">
            Dakvlak: {roofChoices.find(
              (choice) => choice.value === wizard.input.dakvlak,
            )?.label ?? "Weet ik niet"}
          </p>
          <p class="text-sm">
            Monumentrelatie: {wizard.input.monumentrelatie.replaceAll("_", " ")}
          </p>
          <p class="text-sm">
            Beschermd stads- of dorpsgezicht: {wizard.input.gebiedsbescherming.replaceAll(
              "_",
              " ",
            )}
          </p>
          <ul class="list-disc space-y-1 pl-5 text-sm">
            {#each MEASUREMENT_FIELDS as field (field)}
              <li>
                {measurementDetails.find((detail) => detail.field === field)
                  ?.label}: {wizard.rawMeasurements[field] || "Niet ingevuld"} m
              </li>
            {/each}
          </ul>
        </section>
        {#if wizard.result}
          <section
            class="space-y-2 rounded-lg border border-border p-4"
            aria-labelledby="concept-resultaat-kop"
          >
            <h3 id="concept-resultaat-kop" class="font-semibold">Toets</h3>
            <p class="text-sm">
              {verdictLabel(wizard.result)}: {verdictExplanation(wizard.result)}
            </p>
            <p class="text-xs text-muted-foreground">
              Gebaseerd op de officiële Bbl-toestand die bij de bronverwijzingen
              staat.
            </p>
            {#each wizard.result.eisen as item (`concept-${item.eis}-${item.artikel}`)}
              <p class="border-t border-border pt-2 text-sm">
                <strong>{item.artikel}</strong> · {indicatorLabel(item.voldaan)} —
                “{item.citaat}”
              </p>
            {/each}
            <p class="text-sm">Voorbehoud: {wizard.result.voorbehoud}</p>
            <!-- eslint-disable svelte/no-navigation-without-resolve -->
            <a
              class="inline-block text-sm underline"
              href={wizard.result.vergunningcheck_url}
              target="_blank"
              rel="noopener noreferrer">Officiële Vergunningcheck ↗</a
            >
            <!-- eslint-enable svelte/no-navigation-without-resolve -->
          </section>
        {:else if wizard.checking}
          <p role="status" aria-live="polite" class="text-sm">
            De toets wordt bijgewerkt…
          </p>
        {:else if wizard.error}
          <p role="alert" class="text-sm text-red-900">{wizard.error}</p>
        {/if}
        <p class="text-sm text-muted-foreground">
          Deze stap toont alleen een conceptvoorbeeld. Documenten downloaden of
          indienen kan hier nog niet.
        </p>
      </section>
    {/if}
  </div>

  <footer class="mt-4 flex flex-wrap justify-between gap-3">
    <button
      type="button"
      class="min-h-11 rounded-md border border-border px-4 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
      onclick={back}
      disabled={wizard.step === 0}
    >
      Vorige
    </button>
    <p class="sr-only" role="status" aria-live="polite">
      Stap {wizard.step + 1} van 5: {steps[wizard.step]}
    </p>
    {#if wizard.step < 4}
      <button
        type="button"
        class="min-h-11 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        onclick={next}
      >
        Volgende: {steps[wizard.step + 1]}
      </button>
    {:else}
      <a
        href={resolve("/")}
        class="inline-flex min-h-11 items-center rounded-md border border-border px-4 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >Terug naar Wetvia</a
      >
    {/if}
  </footer>
</section>
