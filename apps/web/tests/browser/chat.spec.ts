import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import type { ChatEvent, ChatRequest, components } from "@wetvia/api-client";

const chunkId = "1d44e29c-b982-4f28-b789-c5cd24fa2de8";
const source = {
  label: "[1]",
  chunk_id: chunkId,
  tekst: "Synthetic source excerpt for interface testing.",
  score: 0.5,
  metadata: {
    bwb_id: "synthetic-interface-fixture",
    regeling_titel: "Synthetic test source",
    artikel: "Test item",
    kop_pad: "Interface fixture",
    bron_url: "https://example.test/synthetic-source",
    toestand_url: "https://example.test/synthetic-state",
    lid: null,
    onderdeel: null,
    opschrift: null,
    geldig_vanaf: "2026-01-01",
    geldig_tot: null,
    status: "geldend",
    artikel_status: "geldend",
  },
} satisfies components["schemas"]["ChatSourceCard"];

test("chat, source citation, keyboard input and axe", async ({ page }) => {
  await mockChat(page, "beantwoord");
  await openApp(page);

  await expect(
    page.getByText(
      "Vraag naar regels voor verbouwen. Wetvia zoekt in officiële bronnen en laat zien waar het staat.",
    ),
  ).toBeVisible();
  await expectAxeClear(page);
  await page.getByRole("button", { name: "Dakkapel plaatsen" }).click();
  const input = page.getByRole("textbox", { name: "Stel een vraag" });
  await expect(input).toHaveValue("Dakkapel plaatsen");
  await input.fill("Synthetic interface question");
  await input.press("Shift+Enter");
  await expect(input).toHaveValue("Synthetic interface question\n");
  await input.fill("Synthetic interface question?");
  await input.press("Enter");

  await expect(
    page.getByText("Synthetic answer for browser testing."),
  ).toBeVisible();
  await expect(page.getByText("Synthetic supported point.")).toBeVisible();
  await expect(
    page.getByText("Synthetic caveat for browser testing.", { exact: true }),
  ).toHaveCount(2);
  const followUpLinks = page.getByRole("link", {
    name: /Synthetic follow-up link/,
  });
  await expect(followUpLinks).toHaveCount(2);
  await expect(followUpLinks.first()).toHaveAttribute(
    "href",
    "https://example.test/synthetic-follow-up",
  );
  await expect(
    page.getByText("Synthetic verifier diagnostic must stay server-side.", {
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page
      .getByRole("region", { name: "Antwoord" })
      .getByText("Peildatum: 31-10-2026"),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Wetvia geeft juridische informatie, geen advies. Controleer altijd de bron. U praat met een AI-systeem.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Toon bron [1]" }).click();
  const prefix = page.viewportSize()!.width < 768 ? "mobile" : "desktop";
  const sourceCard = page.locator(`#${prefix}-bron-${chunkId}`);
  await expect(
    page.getByRole("heading", { name: "Synthetic test source" }),
  ).toBeVisible();
  await expect(sourceCard.getByText("Geldend", { exact: true })).toBeVisible();
  await expect(
    sourceCard.getByRole("link", { name: /Bekijk op wetten\.overheid\.nl/ }),
  ).toHaveAttribute("href", "https://example.test/synthetic-source");
  await expect(sourceCard).toHaveAttribute("aria-current", "true");
  await expect(sourceCard).toBeInViewport();

  await expectAxeClear(page);
  await page.evaluate(() => document.documentElement.classList.add("dark"));
  await expectAxeClear(page);
});

test("mobile uncertainty card opens and highlights its cited source with reduced motion", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "mobile-chromium",
    "Mobile sheet behavior",
  );
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const behaviors: string[] = [];
    Object.defineProperty(window, "__wetviaScrollBehaviors", {
      value: behaviors,
    });
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (
      options?: boolean | ScrollIntoViewOptions,
    ) {
      const behavior =
        typeof options === "object" && options !== null
          ? (options.behavior ?? "auto")
          : "auto";
      behaviors.push(behavior);
      return original.call(this, options);
    };
  });
  await mockChat(page, "onzeker");
  await openApp(page);
  await page
    .getByRole("textbox", { name: "Stel een vraag" })
    .fill("Synthetic mobile question?");
  await page.getByRole("textbox", { name: "Stel een vraag" }).press("Enter");

  await expect(page.getByText("Dit weet ik niet zeker.")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Onzeker antwoord" }),
  ).toHaveClass(/border-dotted/);
  await expect(
    page.getByText(
      "Ik kan dit niet met zekerheid zeggen op basis van de bronnen die ik heb.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Toon bron [1]" }).click();
  const sourceCard = page.locator(`#mobile-bron-${chunkId}`);
  await expect(page.getByRole("dialog", { name: "Bronnen" })).toBeVisible();
  await expect(sourceCard).toHaveAttribute("aria-current", "true");
  await expect(sourceCard).toBeInViewport();
  const scrollBehaviors = await page.evaluate(
    () =>
      (window as Window & { __wetviaScrollBehaviors?: string[] })
        .__wetviaScrollBehaviors ?? [],
  );
  expect(scrollBehaviors).toContain("auto");

  await expectAxeClear(page);
});

test("buiten_scope is neutral and does not turn into an answer", async ({
  page,
}) => {
  await mockChat(page, "buiten_scope");
  await openApp(page);
  await page
    .getByRole("textbox", { name: "Stel een vraag" })
    .fill("Synthetic unrelated question?");
  await page.getByRole("textbox", { name: "Stel een vraag" }).press("Enter");

  await expect(
    page.getByText("Buiten onderwerp", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Synthetic out-of-scope response."),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Voor meer informatie kunt u het Omgevingsloket, uw gemeente of het Juridisch Loket raadplegen.",
    ),
  ).toBeVisible();
  await expectAxeClear(page);
});

test("cloud choice is disclosed, cancel-safe, per-conversation, and omits history", async ({
  page,
}) => {
  const requests: ChatRequest[] = [];
  const answer: components["schemas"]["VerifiedAnswer"] = {
    status: "beantwoord",
    samenvatting: "Synthetic answer for browser testing.",
    punten: [
      { tekst: "Synthetic cloud supported point.", bron_ids: [chunkId] },
    ],
    voorbehouden: [],
    vervolgstappen: [],
    peildatum: "2026-10-31",
    verifier_notes: [],
  };
  const events: ChatEvent[] = [
    { type: "sources", sources: [source] },
    { type: "answer", answer },
    { type: "done" },
  ];
  await page.route("**/api/chat", async (route) => {
    requests.push(route.request().postDataJSON() as ChatRequest);
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream; charset=utf-8" },
      body: events
        .map(
          (event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`,
        )
        .join(""),
    });
  });
  await openApp(page, { local: true, cloud: true });

  const modeGroup = page.getByRole("group", { name: "Verwerkingsmodus" });
  const localButton = modeGroup.getByRole("button", { name: /Lokaal/ });
  const cloudButton = modeGroup.getByRole("button", { name: /Cloud \(EU\)/ });
  await expect(localButton).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("textbox", { name: "Stel een vraag" })
    .fill("Synthetic local prior question?");
  await page.getByRole("textbox", { name: "Stel een vraag" }).press("Enter");
  await expect(
    page.getByText("Synthetic answer for browser testing."),
  ).toBeVisible();
  expect(requests[0]).toMatchObject({
    mode: "local",
    messages: [{ role: "user", content: "Synthetic local prior question?" }],
  });

  await cloudButton.click();
  const disclosure = page.getByRole("dialog", {
    name: "Cloud (EU) gebruiken?",
  });
  await expect(disclosure).toBeVisible();
  await expect(disclosure).toContainText(
    "Uw vraag en de gevonden bronnen worden verwerkt door Scaleway (Parijs). Geen uploads.",
  );
  await expect(
    disclosure.getByRole("button", { name: "Annuleren" }),
  ).toBeFocused();
  await expectAxeClear(page);
  await disclosure.getByRole("button", { name: "Annuleren" }).click();
  await expect(disclosure).toBeHidden();
  await expect(localButton).toHaveAttribute("aria-pressed", "true");
  await expect(cloudButton).toBeFocused();
  expect(requests).toHaveLength(1);

  await cloudButton.click();
  await expect(
    page.getByRole("dialog", { name: "Cloud (EU) gebruiken?" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("dialog", { name: "Cloud (EU) gebruiken?" }),
  ).toBeHidden();
  await expect(localButton).toHaveAttribute("aria-pressed", "true");
  await expect(cloudButton).toBeFocused();
  expect(requests).toHaveLength(1);

  await cloudButton.click();
  await page
    .getByRole("dialog", { name: "Cloud (EU) gebruiken?" })
    .getByRole("button", { name: "Akkoord en doorgaan" })
    .click();
  await expect(cloudButton).toHaveAttribute("aria-pressed", "true");

  const persistedConsent = await readSavedConversation(page);
  expect(persistedConsent).toMatchObject({
    mode: "cloud",
    cloudConsentVersion: 1,
  });
  expect(typeof persistedConsent?.cloudConsentAt).toBe("string");
  expect(Date.parse(String(persistedConsent?.cloudConsentAt))).not.toBeNaN();

  await page
    .getByRole("textbox", { name: "Stel een vraag" })
    .fill("Synthetic cloud follow-up question?");
  await page.getByRole("textbox", { name: "Stel een vraag" }).press("Enter");
  await expect(
    page.getByText("Synthetic answer for browser testing."),
  ).toHaveCount(2);
  expect(requests).toHaveLength(2);
  expect(requests[1]).toMatchObject({
    mode: "cloud",
    messages: [
      { role: "user", content: "Synthetic cloud follow-up question?" },
    ],
  });
  await expectAxeClear(page);
});

test("a known unavailable local mode cannot submit while configured cloud remains selectable", async ({
  page,
}) => {
  await openApp(page, { local: false, cloud: true });
  const modeGroup = page.getByRole("group", { name: "Verwerkingsmodus" });
  const localButton = modeGroup.getByRole("button", { name: /Lokaal/ });
  const cloudButton = modeGroup.getByRole("button", { name: /Cloud \(EU\)/ });
  await expect(localButton).toBeDisabled();
  await expect(cloudButton).toBeEnabled();
  await page
    .getByRole("textbox", { name: "Stel een vraag" })
    .fill("Synthetic mode availability check?");
  await expect(page.getByRole("button", { name: "Verstuur" })).toBeDisabled();
  await expectAxeClear(page);
});

test("loading and stream error states keep visible keyboard focus and pass axe", async ({
  page,
}) => {
  const events: ChatEvent[] = [
    { type: "sources", sources: [] },
    { type: "error", message: "Synthetic stream error." },
    { type: "done" },
  ];
  const body = events
    .map((event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`)
    .join("");
  let releaseResponse!: () => void;
  const responseGate = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  await page.route("**/api/chat", async (route) => {
    await responseGate;
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream; charset=utf-8" },
      body,
    });
  });
  await openApp(page);

  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Ga naar de inhoud" });
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();
  await expect
    .poll(() =>
      skipLink.evaluate((element) => getComputedStyle(element).outlineWidth),
    )
    .toBe("2px");

  await page
    .getByRole("textbox", { name: "Stel een vraag" })
    .fill("Synthetic question that will error?");
  await page.getByRole("textbox", { name: "Stel een vraag" }).press("Enter");
  await expect(
    page.getByText("Bronnen worden gezocht…", { exact: true }),
  ).toBeVisible();
  await expectAxeClear(page);

  releaseResponse();
  await expect(page.getByRole("alert")).toHaveText("Synthetic stream error.");
  await expect(
    page.getByText("Synthetic answer for browser testing."),
  ).toHaveCount(0);
  await expectAxeClear(page);
});

test("history restores citations and supports rename, delete and confirmed clear", async ({
  page,
}) => {
  const requestCount = await mockChat(page, "beantwoord");
  await openApp(page);
  const question = "Synthetic saved conversation question?";
  await page.getByRole("textbox", { name: "Stel een vraag" }).fill(question);
  await page.getByRole("textbox", { name: "Stel een vraag" }).press("Enter");
  await expect(
    page.getByText("Synthetic answer for browser testing."),
  ).toBeVisible();

  await openHistory(page);
  const history = page.getByRole("navigation", {
    name: "Gespreksgeschiedenis",
  });
  await expect(history.getByRole("heading", { name: "Vandaag" })).toBeVisible();
  const initialConversation = history
    .getByRole("button")
    .filter({ hasText: question });
  await expect(initialConversation).toBeVisible();
  await page.getByRole("button", { name: `Hernoem ${question}` }).click();
  const renameInput = page.getByRole("textbox", { name: "Gesprek hernoemen" });
  await expect(renameInput).toBeFocused();
  await renameInput.fill("Renamed synthetic conversation");
  await page.getByRole("button", { name: "Opslaan" }).click();
  await expect(
    history
      .getByRole("button")
      .filter({ hasText: "Renamed synthetic conversation" }),
  ).toBeVisible();
  await expectAxeClear(page);

  await page
    .getByRole("region", { name: "Gesprekken" })
    .getByRole("button", { name: /Nieuw gesprek/ })
    .click();
  await expect(
    page.getByText(
      "Vraag naar regels voor verbouwen. Wetvia zoekt in officiële bronnen en laat zien waar het staat.",
    ),
  ).toBeVisible();
  await openHistory(page);
  await history
    .getByRole("button")
    .filter({ hasText: "Renamed synthetic conversation" })
    .click();
  await expect(
    page.getByText("Synthetic answer for browser testing."),
  ).toBeVisible();

  await page.keyboard.press("Escape");
  await page.reload();
  await openApp(page);
  expect(requestCount()).toBe(1);
  await expect(
    page.getByText("Synthetic answer for browser testing."),
  ).toBeVisible();
  await openHistory(page);
  await expect(
    page
      .getByRole("navigation", { name: "Gespreksgeschiedenis" })
      .getByRole("button")
      .filter({ hasText: "Renamed synthetic conversation" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Toon bron [1]" }).click();
  await expect(
    page.getByRole("heading", { name: "Synthetic test source" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  await openHistory(page);
  await page
    .getByRole("button", { name: "Verwijder Renamed synthetic conversation" })
    .click();
  await expect(
    page
      .getByRole("navigation", { name: "Gespreksgeschiedenis" })
      .getByText("Nog geen gesprekken."),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  await page
    .getByRole("textbox", { name: "Stel een vraag" })
    .fill("Synthetic conversation to clear?");
  await page.getByRole("textbox", { name: "Stel een vraag" }).press("Enter");
  await expect(
    page.getByText("Synthetic answer for browser testing."),
  ).toBeVisible();
  await openHistory(page);
  const clearButton = page.getByRole("button", { name: "Wis alle gesprekken" });
  await clearButton.scrollIntoViewIfNeeded();
  await clearButton.click();
  const confirmation = page.getByRole("dialog", {
    name: "Alle gesprekken wissen?",
  });
  await expect(confirmation).toBeVisible();
  await expect(
    confirmation.getByRole("button", { name: "Annuleren" }),
  ).toBeFocused();
  await expectAxeClear(page);
  await page.getByRole("button", { name: "Annuleren" }).click();
  await expect(confirmation).toBeHidden();
  await expect(
    page
      .getByRole("navigation", { name: "Gespreksgeschiedenis" })
      .getByRole("button")
      .filter({ hasText: "Synthetic conversation to clear" }),
  ).toBeVisible();

  await clearButton.click();
  await page
    .getByRole("dialog", { name: "Alle gesprekken wissen?" })
    .getByRole("button", { name: "Wis alles" })
    .click();
  await expect(
    page
      .getByRole("navigation", { name: "Gespreksgeschiedenis" })
      .getByText("Nog geen gesprekken."),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByText(
      "Vraag naar regels voor verbouwen. Wetvia zoekt in officiële bronnen en laat zien waar het staat.",
    ),
  ).toBeVisible();

  await page.reload();
  await openApp(page);
  await expect(
    page.getByText(
      "Vraag naar regels voor verbouwen. Wetvia zoekt in officiële bronnen en laat zien waar het staat.",
    ),
  ).toBeVisible();
  await openHistory(page);
  await expect(
    page
      .getByRole("navigation", { name: "Gespreksgeschiedenis" })
      .getByText("Nog geen gesprekken."),
  ).toBeVisible();
});

async function mockChat(
  page: import("@playwright/test").Page,
  status: components["schemas"]["VerifiedAnswer"]["status"],
): Promise<() => number> {
  const answer: components["schemas"]["VerifiedAnswer"] = {
    status,
    samenvatting:
      status === "buiten_scope"
        ? "Synthetic out-of-scope response."
        : "Synthetic answer for browser testing.",
    punten:
      status === "buiten_scope"
        ? []
        : [{ tekst: "Synthetic supported point.", bron_ids: [chunkId] }],
    voorbehouden:
      status === "beantwoord"
        ? [
            "Synthetic caveat for browser testing.",
            "Synthetic caveat for browser testing.",
          ]
        : [],
    vervolgstappen:
      status === "beantwoord"
        ? [
            {
              tekst: "Synthetic follow-up link 1",
              url: "https://example.test/synthetic-follow-up",
            },
            {
              tekst: "Synthetic follow-up link 2",
              url: "https://example.test/synthetic-follow-up",
            },
          ]
        : [],
    peildatum: "2026-10-31",
    verifier_notes: ["Synthetic verifier diagnostic must stay server-side."],
  };
  const events: ChatEvent[] = [
    { type: "sources", sources: status === "buiten_scope" ? [] : [source] },
    { type: "answer", answer },
    { type: "done" },
  ];
  const body = events
    .map((event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`)
    .join("");

  let requestCount = 0;
  await page.route("**/api/chat", (route) => {
    requestCount += 1;
    return route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache",
      },
      body,
    });
  });
  return () => requestCount;
}

async function openApp(
  page: import("@playwright/test").Page,
  configuredModes = { local: true, cloud: false },
): Promise<void> {
  await page.route("**/api/health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        db: "ok",
        configured_chat_modes: configuredModes,
        default_chat_mode: "local",
        version: "browser-test",
      }),
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("form", { name: "Stel een vraag" }),
  ).toHaveAttribute("aria-busy", "false");
}

async function readSavedConversation(
  page: import("@playwright/test").Page,
): Promise<Record<string, unknown> | undefined> {
  return page.evaluate(
    () =>
      new Promise<Record<string, unknown> | undefined>((resolve, reject) => {
        const request = indexedDB.open("wetvia-chat-history");
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          const database = request.result;
          const transaction = database.transaction("conversations", "readonly");
          const records = transaction.objectStore("conversations").getAll();
          records.onerror = () => reject(records.error);
          records.onsuccess = () => {
            resolve(records.result[0] as Record<string, unknown> | undefined);
            database.close();
          };
        };
      }),
  );
}

async function openHistory(
  page: import("@playwright/test").Page,
): Promise<void> {
  if (page.viewportSize()!.width < 768) {
    await page.getByRole("button", { name: "Geschiedenis" }).click();
  }
  await expect(
    page.getByRole("navigation", { name: "Gespreksgeschiedenis" }),
  ).toBeVisible();
}

async function expectAxeClear(
  page: import("@playwright/test").Page,
): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const seriousOrCritical = results.violations.filter(
    (violation) =>
      violation.impact === "serious" || violation.impact === "critical",
  );
  expect(
    seriousOrCritical.map(({ id, help, nodes }) => ({
      id,
      help,
      nodes: nodes.map((node) => node.target),
    })),
  ).toEqual([]);
}
