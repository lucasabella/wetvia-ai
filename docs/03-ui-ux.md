# 03. UI/UX-ontwerp

## Ontwerpprincipes

1. **Vertrouwen boven wow.** Het moet aanvoelen als een rustige, betrouwbare overheidsdienst, niet als een glimmende AI-demo. Bronnen staan altijd in beeld.
2. **Bron eerst.** Elk inhoudelijk punt heeft een klikbaar bronkaartje. Een antwoord zonder bron ziet er visueel anders uit (gestippelde rand + "onzeker").
3. **Tijd zichtbaar.** Elke bron draagt een statusbadge: **Geldend** (groen), **Toekomstig** (blauw, met datum), **Vervallen** (grijs, doorgestreept) of **Wetsvoorstel** (paars). Bovenaan elk antwoord staat "Peildatum: 30-10-2026".
4. **Concept = concept.** Gegenereerde documenten hebben een diagonaal watermerk *CONCEPT* en een gele balk: "Dit is een concept, gemaakt met AI. Laat het controleren voordat u het indient."
5. **Taalniveau B1** in de interface en in de antwoorden. De wettekst zelf blijft letterlijk in het bronpaneel.
6. **Toegankelijk:** WCAG 2.2 AA. Contrast ≥ 4,5:1, alles bedienbaar met het toetsenbord, focus zichtbaar, `prefers-reduced-motion` gerespecteerd en `lang="nl"`.

## Layout (desktop ≥ 1024 px)

```
┌──────────────┬───────────────────────────────────────┬──────────────────────┐
│ § Wetvia     │  Peildatum 30-10-2026  · 🔒 Lokaal ▾   │  Bronnen (4)         │
│              │                                       │ ┌──────────────────┐ │
│ + Nieuw      │  👤 Mag ik een dakkapel aan de        │ │[1] Bbl art. 2.29 │ │
│              │     achterkant zonder vergunning?     │ │ onder b  ●Geldend│ │
│ Vandaag      │                                       │ │ "een dakkapel in │ │
│  Dakkapel... │  § Waarschijnlijk wel, als hij aan    │ │ het achterdakvlak│ │
│  Bezwaar ... │    5 eisen voldoet [1]:               │ │ ..."   ↗ wetten  │ │
│              │    • plat dak [1]                     │ └──────────────────┘ │
│ Dossiers     │    • max. 1,75 m hoog [1]  ...        │ ┌──────────────────┐ │
│  Dakkapel... │  ⚠ Voorbehoud: monument? → art.2.30[2]│ │[2] Bbl art. 2.30 │ │
│              │  ➜ Check in de Vergunningcheck ↗      │ └──────────────────┘ │
│              │  [Maak conceptdossier]                │                      │
│ ⚙ Instellingen│ ┌───────────────────────────────┐   │                      │
│              │ │ Stel een vraag…           ⏎   │   │                      │
│              │ └───────────────────────────────┘   │                      │
│              │  Wetvia geeft informatie, geen advies.│                      │
└──────────────┴───────────────────────────────────────┴──────────────────────┘
```

- **Links:** gespreksgeschiedenis, standaard opgeslagen in IndexedDB in de browser (niets op de server) en dossiers.
- **Midden:** het chatgesprek. Citatienummers `[1]` zijn knoppen die de bijbehorende bron in het rechterpaneel markeren en scrollen.
- **Rechts:** het **bronnenpaneel**. Per bron: regeling, artikel/onderdeel, statusbadge, het geciteerde fragment (gemarkeerd), "Bekijk op wetten.overheid.nl ↗" (JCI-deeplink) en "Geldig van … t/m …".
- **Mobiel (< 768 px):** de bronnen worden een bottom sheet die omhoog schuift bij een tik op `[1]`; de geschiedenis wordt een drawer.

## Belangrijke schermen en flows

### 1. Startscherm (leeg gesprek)
- Een korte uitleg in één zin: "Vraag naar regels voor verbouwen. Wetvia zoekt in officiële bronnen en laat zien waar het staat."
- Drie **startkaarten**: "Dakkapel plaatsen" · "Uitbouw of aanbouw" · "Wat is een omgevingsplan?".
- Modus-schakelaar **🔒 Lokaal / ☁ Cloud (EU)**. Bij de eerste keuze voor Cloud in een gesprek verschijnt een modal: "Uw vraag en de gevonden bronnen worden verwerkt door Scaleway (Parijs). Geen uploads." Annuleren laat de modus ongewijzigd en verstuurt geen vraag. Na akkoord worden modus, toestemmingsversie en tijdstip per gesprek in IndexedDB opgeslagen vóór een cloudverzoek. Cloudverzoeken bevatten alleen de huidige vraag en de gevonden bronnen; eerdere beurten blijven lokaal.

### 2. Antwoord met onzekerheid
- `status: onzeker` → een amberkleurige kaart: "Ik kan dit niet met zekerheid zeggen op basis van de bronnen die ik heb." Daaronder: wat Wetvia wél vond, plus waar het antwoord wél te vinden is (Omgevingsloket, gemeente, Juridisch Loket).
- `status: buiten_scope` → een neutrale kaart met een verwijzing. Geen poging om toch te antwoorden.

### 3. Dossier-wizard (dakkapel)
Stapsgewijs, niet in de chat, want het gaat om gestructureerde data:
1. **Locatie:** het adres is alleen invoer voor de conceptsamenvatting; de MVP doet nog geen automatische lookup en stuurt het adres niet naar de regeltoets. Vraag afzonderlijk naar de monumentrelatie (geen monument, werk in/aan/op, alleen bij, onbekend) en naar een rijksbeschermd stads- of dorpsgezicht.
2. **Plaats op het dak:** een klikbare SVG met voor-, achter- en zijdakvlak plus onbekend. Vraag naar openbaar toegankelijk gebied bij een zijdakvlak en ook bij een achterdakvlak in een rijksbeschermd stads- of dorpsgezicht.
3. **Maten:** vijf invoervelden in meters (hoogte, onderzijde tot dakvoet, bovenzijde tot daknok, en linker- en rechterzijkant tot de dakvlakrand), plus de vraag of het dak plat is. Komma en punt zijn toegestaan; een schematische tekening beweegt mee. De API levert per eis een groene, rode of grijze indicator met het artikel. Invoer blijft alleen in de geopende pagina.
4. **Resultaat:** toon het oordeel van `POST /api/rules/dakkapel`, citaten en officiële bronverwijzingen/provenance, de technische bouwactiviteit apart, het voorbehoud en de Vergunningcheck-link. De client rekent geen wettelijke drempels na.
5. **Conceptdossier:** toon een controleerbare preview met de invoer, toetsing per eis en disclaimer. Bied DOCX-, PDF- en Markdown-downloads aan met het zichtbare CONCEPT-watermerk en de exacte disclosure. Aanvragergegevens blijven placeholders. De officiële DSO-LV-stukkenlijst is nog niet opgehaald of geverifieerd; toon geen ingevulde checklistitems totdat issue #24 brondata levert.

### 4. Instellingen
- Model: lokaal (Ollama-URL, modelnaam) / cloud (API-key, wordt alleen in de backend-env opgeslagen en nooit in de browser getoond).
- "Wis alle gesprekken" (lokaal).
- Over Wetvia: versie, bronnen + licenties, eval-cijfers van de huidige release.

## Visuele identiteit

| Element | Keuze |
|---|---|
| **Naam/merk** | **Wetvia**: "via de wet", de weg door de regels |
| **Logo** | Een **§ (paragraafteken)** waarvan de onderste lus overloopt in een pad of pijl naar rechts: wet → route. Als favicon: § in een afgerond vierkant. Monochroom bruikbaar. |
| **Kleuren** | Achtergrond `#FAFAF7` (warm off-white) · Tekst `#1B1F24` (inkt) · **Accent "wetblauw" `#1F4E79`** · Accent-licht `#E8EFF6` · Geldend `#2E7D4F` · Toekomstig `#2563EB` · Vervallen `#6B7280` · Voorstel `#7C3AED` · Waarschuwing `#B45309` op `#FEF3C7` |
| **Dark mode** | Achtergrond `#111418`, tekst `#E6E8EB`, accent `#7FB0E0` (contrast nog controleren) |
| **Typografie** | **Inter** (UI) + **Source Serif 4** voor geciteerde wettekst (onderscheid "wet" vs. "uitleg"); beide OFL-licentie, self-hosted (geen Google Fonts-CDN, voor privacy) |
| **Iconen** | Lucide (ISC-licentie) |
| **Componenten** | shadcn-svelte (bits-ui) + Tailwind; uitgaan van de standaard, alleen de kleuren aanpassen |
| **Animaties** | Streaming-tekst, een subtiele highlight bij klik op een citaat (200 ms) en niets dat stuitert; uit bij `prefers-reduced-motion` |

## Microcopy (vaste teksten)

- Voettekst onder de invoer: **"Wetvia geeft juridische informatie, geen advies. Controleer altijd de bron. U praat met een AI-systeem."** (AI Act art. 50.)
- Onzeker: **"Dit weet ik niet zeker."** (Nooit "Helaas kan ik…".)
- Conclusie: altijd **"waarschijnlijk"** + de reden; nooit "U mag" of "U hoeft geen vergunning".
- Dossier-watermerk: **"CONCEPT, gemaakt met Wetvia (AI). Niet gecontroleerd door een deskundige."**
