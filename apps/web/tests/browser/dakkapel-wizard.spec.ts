import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import type {
  DakkapelRuleRequest,
  DakkapelRuleResponse,
} from "@wetvia/api-client";

const ruleResult = makeRuleResult();

test("dakkapel wizard keeps input through steps and shows sourced rule results", async ({
  page,
}) => {
  const requests = await openDakkapelWizard(page);

  await expect(
    page.getByRole("heading", { name: "Dakkapeltoets" }),
  ).toBeVisible();
  await expectAxeClear(page);

  await page
    .getByLabel("Adres (alleen voor dit concept)")
    .fill("Teststraat 1, Utrecht");
  await page.getByRole("radio", { name: "Geen beschermd monument" }).check();
  await page.getByRole("radio", { name: "Nee", exact: true }).last().check();
  await page.getByRole("button", { name: "Volgende: Dakvlak" }).click();
  await expect(
    page.getByRole("heading", { name: "Plaats op het dak" }),
  ).toBeVisible();
  await expectAxeClear(page);

  const rearChoice = page.getByRole("button", { name: "Achterzijde kiezen" });
  await rearChoice.focus();
  await page.keyboard.press("Enter");
  await expect(rearChoice).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Volgende: Maten" }).click();
  await expect(
    page.getByRole("heading", { name: "Maten van de dakkapel" }),
  ).toBeVisible();
  await page.getByRole("radio", { name: "Ja", exact: true }).check();
  await page.getByLabel("Hoogte vanaf de voet (m)").fill("1,75");
  await page.getByLabel("Onderzijde boven de dakvoet (m)").fill("0,75");
  await page.getByLabel("Bovenzijde onder de daknok (m)").fill("0.75");
  await page.getByLabel("Linkerzijkant tot de dakvlakrand (m)").fill("0,75");
  await page.getByLabel("Rechterzijkant tot de dakvlakrand (m)").fill("0,75");

  await expect
    .poll(() => requests.at(-1)?.hoogte_m, { timeout: 5000 })
    .toBe("1.75");
  await expect(
    page.getByText("Voldaan", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Bbl 2.29, onder b, onder 2°").first(),
  ).toBeVisible();
  await expectAxeClear(page);

  await page.getByRole("button", { name: "Volgende: Resultaat" }).click();
  await expect(
    page.getByRole("heading", { name: "Waarschijnlijk vergunningvrij" }),
  ).toBeVisible();
  await expect(
    page.getByText("Context: “In afwijking van de artikelen 2.25 en 2.26", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("link", {
        name: /Bekijk Bbl 2\.29 op wetten\.overheid\.nl/,
      })
      .first(),
  ).toHaveAttribute(
    "href",
    "https://wetten.overheid.nl/jci1.3:c:BWBR0041297&artikel=2.29&z=2026-09-24&g=2026-09-24",
  );
  await expect(
    page.getByRole("link", {
      name: "Controleer dit bij de officiële Vergunningcheck ↗",
    }),
  ).toHaveAttribute("href", "https://omgevingswet.overheid.nl/checken");
  await expectAxeClear(page);

  await page.getByRole("button", { name: "Volgende: Conceptdossier" }).click();
  await expect(
    page.getByText(
      "CONCEPT, gemaakt met Wetvia (AI). Niet gecontroleerd door een deskundige.",
    ),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Dit is een concept, gemaakt met AI. Laat het controleren voordat u het indient.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /download|pdf|docx/i }),
  ).toHaveCount(0);
  await expect(page.getByText("Adres: Teststraat 1, Utrecht")).toBeVisible();
  await expectAxeClear(page);

  await page.getByRole("button", { name: "Vorige" }).click();
  await page.getByRole("button", { name: "Vorige" }).click();
  await expect(page.getByLabel("Hoogte vanaf de voet (m)")).toHaveValue("1,75");
  const previousRequestCount = requests.length;
  await page.getByLabel("Hoogte vanaf de voet (m)").fill("1.70");
  await expect
    .poll(() => requests.length, { timeout: 5000 })
    .toBeGreaterThan(previousRequestCount);
  await expect.poll(() => requests.at(-1)?.hoogte_m).toBe("1.7");
});

test("protected rear roof asks and sends its public-area orientation", async ({
  page,
}) => {
  const requests = await openDakkapelWizard(page);
  await page.getByRole("radio", { name: "Geen beschermd monument" }).check();
  await page.getByRole("radio", { name: "Ja", exact: true }).last().check();
  await page.getByRole("button", { name: "Volgende: Dakvlak" }).click();
  await page.getByRole("button", { name: "Achterzijde kiezen" }).click();

  const orientation = page.getByRole("group", {
    name: "Keert dit achterdakvlak naar openbaar toegankelijk gebied?",
  });
  await expect(orientation).toBeVisible();
  await orientation.getByRole("radio", { name: "Nee" }).check();
  await expectAxeClear(page);

  await page.getByRole("button", { name: "Volgende: Maten" }).click();
  await expect
    .poll(() => requests.at(-1)?.dakvlak_naar_openbaar_toegankelijk_gebied, {
      timeout: 5000,
    })
    .toBe(false);
  expect(requests.at(-1)).toMatchObject({
    dakvlak: "achterdakvlak",
    gebiedsbescherming: "rijksbeschermd_stads_of_dorpsgezicht",
  });
});

test("the measurement sketch reflects the height, underside and top distances", async ({
  page,
}) => {
  await openDakkapelWizard(page);
  await page.getByRole("button", { name: "Volgende: Dakvlak" }).click();
  await page.getByRole("button", { name: "Volgende: Maten" }).click();

  const diagram = page.getByTestId("dakkapel-schets");
  const roof = page.getByTestId("dak-schets");
  const initialY = await diagram.getAttribute("y");
  const initialHeight = await diagram.getAttribute("height");
  const initialRoof = await roof.getAttribute("d");

  await page.getByLabel("Onderzijde boven de dakvoet (m)").fill("0,5");
  await expect(diagram).not.toHaveAttribute("y", initialY!);
  await page.getByLabel("Hoogte vanaf de voet (m)").fill("1,2");
  await expect(diagram).not.toHaveAttribute("height", initialHeight!);
  const roofAfterHeight = await roof.getAttribute("d");
  await page.getByLabel("Bovenzijde onder de daknok (m)").fill("0,5");
  await expect(roof).not.toHaveAttribute("d", roofAfterHeight!);
  expect(await roof.getAttribute("d")).not.toBe(initialRoof);
  await expectAxeClear(page);
});

test("unknown monument answer stays onbepaald and prompts the user to check", async ({
  page,
}) => {
  const requests = await openDakkapelWizard(page);
  await page
    .getByRole("navigation", { name: "Stappen in de dakkapeltoets" })
    .getByRole("button", { name: /Resultaat/ })
    .click();

  await expect(
    page.getByRole("heading", { name: "Dat kunnen we niet bepalen" }),
  ).toBeVisible();
  await expect(page.getByText(/Vraag na of de activiteit/)).toBeVisible();
  await expect
    .poll(() => requests.at(-1)?.monumentrelatie, { timeout: 5000 })
    .toBe("onbekend");
  await expectAxeClear(page);
});

test("invalid measurement navigation focuses and announces the field; blank stays unknown", async ({
  page,
}) => {
  await openDakkapelWizard(page);
  await page.getByRole("button", { name: "Volgende: Dakvlak" }).click();
  await page.getByRole("button", { name: "Achterzijde kiezen" }).click();
  await page.getByRole("button", { name: "Volgende: Maten" }).click();

  const height = page.getByLabel("Hoogte vanaf de voet (m)");
  await height.fill("1,7.5");
  await page
    .getByRole("navigation", { name: "Stappen in de dakkapeltoets" })
    .getByRole("button", { name: /Resultaat/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Maten van de dakkapel" }),
  ).toBeVisible();
  await expect(height).toBeFocused();
  await expect(page.locator("#measure-navigation-error")).toContainText(
    "gemarkeerde maatvelden",
  );
  await expect(page.locator("#hoogte_m-error")).toContainText(
    "niet-negatief getal",
  );
  await expect(height).toHaveAttribute(
    "aria-describedby",
    /measure-navigation-error/,
  );
  await expect(height).toHaveAttribute("aria-invalid", "true");
  await expectAxeClear(page);

  await height.fill("");
  await page.getByRole("button", { name: "Volgende: Resultaat" }).click();
  await expect(page.getByRole("heading", { name: "Resultaat" })).toBeVisible();
});

test("dossier navigation is in the sidebar and wizard state is not persisted", async ({
  page,
}) => {
  await installWizardApi(page);
  const healthResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/health"),
  );
  await page.goto("/");
  await healthResponse;
  if (page.viewportSize()!.width < 768) {
    await page.getByRole("button", { name: "Geschiedenis" }).click();
  }
  const initialRuleCheck = page.waitForResponse((response) =>
    response.url().endsWith("/api/rules/dakkapel"),
  );
  await page
    .getByRole("navigation", { name: "Dossiers" })
    .getByRole("link", { name: "Dakkapeltoets" })
    .click();
  await expect(page).toHaveURL(/\/dossier\/dakkapel$/);
  await initialRuleCheck;
  await page
    .getByLabel("Adres (alleen voor dit concept)")
    .fill("Tijdelijk adres");
  const reloadedRuleCheck = page.waitForResponse((response) =>
    response.url().endsWith("/api/rules/dakkapel"),
  );
  await page.reload();
  await reloadedRuleCheck;
  await expect(
    page.getByRole("heading", { name: "Locatie en bescherming" }),
  ).toBeVisible();
  await expect(page.getByLabel("Adres (alleen voor dit concept)")).toHaveValue(
    "",
  );
  await expectAxeClear(page);
});

async function installWizardApi(
  page: import("@playwright/test").Page,
): Promise<DakkapelRuleRequest[]> {
  const requests: DakkapelRuleRequest[] = [];
  await page.route("**/api/health", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        db: "ok",
        configured_chat_modes: { local: true, cloud: false },
        default_chat_mode: "local",
        version: "browser-test",
      }),
    }),
  );
  await page.route("**/api/rules/dakkapel", async (route) => {
    const request = route.request().postDataJSON() as DakkapelRuleRequest;
    requests.push(request);
    const response =
      request.monumentrelatie === "onbekend"
        ? {
            ...ruleResult,
            eindoordeel: "onbepaald" as const,
            advies:
              "Vraag na of de activiteit in, aan of op een beschermd monument wordt verricht.",
            eisen: ruleResult.eisen.map((item) =>
              item.eis === "monument" || item.eis === "gebiedsbescherming"
                ? { ...item, voldaan: null }
                : item,
            ),
          }
        : ruleResult;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(response),
    });
  });
  return requests;
}

async function openDakkapelWizard(
  page: import("@playwright/test").Page,
): Promise<DakkapelRuleRequest[]> {
  const requests = await installWizardApi(page);
  const healthResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/health"),
  );
  const initialRuleCheck = page.waitForResponse((response) =>
    response.url().endsWith("/api/rules/dakkapel"),
  );
  await page.goto("/dossier/dakkapel");
  await Promise.all([healthResponse, initialRuleCheck]);
  await expect(
    page.getByRole("heading", { name: "Dakkapeltoets" }),
  ).toBeVisible();
  return requests;
}

function makeRuleResult(): DakkapelRuleResponse {
  const citation = {
    location:
      "een dakkapel in het achterdakvlak of een niet naar openbaar toegankelijk gebied gekeerd zijdakvlak, als wordt voldaan aan de volgende eisen:",
    flat: "voorzien van een plat dak;",
    height: "gemeten vanaf de voet van de dakkapel niet hoger dan 1,75 m;",
    underside: "onderzijde meer dan 0,5 m en minder dan 1 m boven de dakvoet;",
    top: "bovenzijde meer dan 0,5 m onder de daknok; en",
    side: "zijkanten meer dan 0,5 m van de zijkanten van het dakvlak;",
    area: "een wijziging van een achtergevel of achterdakvlak, als die gevel of dat dakvlak niet naar openbaar toegankelijk gebied is gekeerd;",
    technical: "een dakkapel;",
    technicalContext:
      "In afwijking van de artikelen 2.25 en 2.26 en ongeacht of een uitzondering als bedoeld in het eerste lid van toepassing is, geldt het verbod, bedoeld in artikel 5.1, tweede lid, van de wet, om zonder omgevingsvergunning een bouwactiviteit te verrichten ook niet voor een bouwactiviteit die betrekking heeft op een van de volgende bouwwerken:",
  };
  const source = (article: "2.27" | "2.29" | "2.30") => ({
    regeling: "Besluit bouwwerken leefomgeving (Bbl)",
    artikel: `Bbl ${article}`,
    url: `https://wetten.overheid.nl/jci1.3:c:BWBR0041297&artikel=${article}&z=2026-09-24&g=2026-09-24`,
    bwb_id: "BWBR0041297",
    toestand_geldig_vanaf: "2026-09-24",
    toestand_geldig_tot: "9999-12-31",
    toestand_modified: "2026-09-30",
    opgehaald_op: "2026-10-31",
    bronbestand:
      "packages/nl-wetten-ingest/tests/fixtures/bwb_xml/bbl-2026-09-24.xml",
    bron_url:
      "https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0041297/2026-09-24_0/xml/BWBR0041297_2026-09-24_0.xml",
    sha256: "52ef1dbbf8d109ba9c1e452193735ef32790d604dec0c8e03ede02245c6b7690",
  });
  const requirement = (
    eis: DakkapelRuleResponse["eisen"][number]["eis"],
    artikel: string,
    citaat: string,
    article: "2.29" | "2.30",
  ): DakkapelRuleResponse["eisen"][number] => ({
    eis,
    omschrijving: {
      locatie:
        "De dakkapel ligt in het achterdakvlak of in een niet-openbaar zijdakvlak.",
      plat_dak: "De dakkapel heeft een plat dak.",
      hoogte: "De hoogte vanaf de voet is niet groter dan 1,75 m.",
      onderzijde:
        "De onderzijde ligt meer dan 0,5 m en minder dan 1 m boven de dakvoet.",
      bovenzijde: "De bovenzijde ligt meer dan 0,5 m onder de daknok.",
      linker_zijkant:
        "De linkerzijkant ligt meer dan 0,5 m van de rand van het dakvlak.",
      rechter_zijkant:
        "De rechterzijkant ligt meer dan 0,5 m van de rand van het dakvlak.",
      monument:
        "De monumentregels beperken de toepassing van artikel 2.29, onder b, niet.",
      gebiedsbescherming:
        "In een rijksbeschermd stads- of dorpsgezicht moet het achterdakvlak niet naar openbaar gebied zijn gekeerd.",
    }[eis],
    voldaan: true,
    artikel,
    citaat,
    contextcitaat: null,
    toelichting: null,
    bron: source(article),
    voorbehoud:
      "Onverminderd regels in het omgevingsplan over het in stand houden van een bouwwerk die betrekking hebben op de ernstige ontsiering van het uiterlijk van dat bouwwerk,",
    vergunningcheck_url: "https://omgevingswet.overheid.nl/checken",
  });
  const caveat =
    "Onverminderd regels in het omgevingsplan over het in stand houden van een bouwwerk die betrekking hebben op de ernstige ontsiering van het uiterlijk van dat bouwwerk,";

  return {
    eindoordeel: "waarschijnlijk_vergunningvrij",
    eisen: [
      requirement("locatie", "Bbl 2.29, onder b", citation.location, "2.29"),
      requirement(
        "plat_dak",
        "Bbl 2.29, onder b, onder 1°",
        citation.flat,
        "2.29",
      ),
      requirement(
        "hoogte",
        "Bbl 2.29, onder b, onder 2°",
        citation.height,
        "2.29",
      ),
      requirement(
        "onderzijde",
        "Bbl 2.29, onder b, onder 3°",
        citation.underside,
        "2.29",
      ),
      requirement(
        "bovenzijde",
        "Bbl 2.29, onder b, onder 4°",
        citation.top,
        "2.29",
      ),
      requirement(
        "linker_zijkant",
        "Bbl 2.29, onder b, onder 5°",
        citation.side,
        "2.29",
      ),
      requirement(
        "rechter_zijkant",
        "Bbl 2.29, onder b, onder 5°",
        citation.side,
        "2.29",
      ),
      requirement("monument", "Bbl 2.29, onder b", citation.location, "2.29"),
      requirement(
        "gebiedsbescherming",
        "Bbl 2.30, derde lid, onder b, onder 2°",
        citation.area,
        "2.30",
      ),
    ],
    technische_bouwactiviteit: {
      activiteit: "bouwactiviteit (technisch)",
      oordeel: "waarschijnlijk_vergunningvrij",
      artikel: "Bbl 2.27, tweede lid, onder a",
      citaat: citation.technical,
      contextcitaat: citation.technicalContext,
      bron: source("2.27"),
      voorbehoud: caveat,
      vergunningcheck_url: "https://omgevingswet.overheid.nl/checken",
    },
    advies: null,
    voorbehoud: caveat,
    vergunningcheck_url: "https://omgevingswet.overheid.nl/checken",
  };
}

async function expectAxeClear(
  page: import("@playwright/test").Page,
): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
}
