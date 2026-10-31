import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import type { ChatEvent, components } from "@wetvia/api-client";

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
  await expect(page.getByRole("status")).toContainText(
    "Bronnen worden gezocht…",
  );
  await expectAxeClear(page);

  releaseResponse();
  await expect(page.getByRole("alert")).toHaveText("Synthetic stream error.");
  await expect(
    page.getByText("Synthetic answer for browser testing."),
  ).toHaveCount(0);
  await expectAxeClear(page);
});

async function mockChat(
  page: import("@playwright/test").Page,
  status: components["schemas"]["VerifiedAnswer"]["status"],
): Promise<void> {
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

  await page.route("**/api/chat", (route) =>
    route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache",
      },
      body,
    }),
  );
}

async function openApp(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
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
