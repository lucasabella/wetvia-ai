# Wetvia SFT-data card

Vul dit bestand in voordat trainingsdata een run in gaat. Commit geen ruwe trainingsdata, prompts met API-sleutels, persoonsgegevens of modelgewichten.

## Datasetidentiteit

- Datasetnaam en versie:
- Bestandspad (lokaal):
- SHA-256 van het bevroren bestand:
- Aanmaakdatum:
- Verantwoordelijke reviewer:
- Beoogde basismodelfamilie en chat-template:

## Doel en gebruik

- Gedrag dat moet verbeteren (bijvoorbeeld abstentie, citaties, B1-samenvatting):
- Taak voor Tweede Kamerdata (bijvoorbeeld voorstel samenvatten of brongebonden QA):
- Wat dit model nadrukkelijk niet moet doen:
- Waarom prompt- of verifier-aanpassing alleen niet volstaat:

## Bronnen en rechten

| Collectie/documentsoort | Bron-URL | Licentie | Download-/peildatum | Filters/uitsluitingen |
| ----------------------- | -------- | -------- | ------------------- | --------------------- |
|                         |          |          |                     |                       |

Leg per broncollectie de licentiebron en gebruiksvoorwaarden vast. Voor parlementaire stukken registreer je minimaal het document-ID, de datum en of het een voorstel, stemming, verslag of geldende regeling betreft.

## Samenstelling

- Totaal aantal voorbeelden:
- Positieve/aannemelijke antwoordvoorbeelden:
- Negatieve voorbeelden (`status: onzeker`):
- Buiten-scope voorbeelden:
- Gemiddelde/lengteverdeling van tokens:
- Duplicaten verwijderd en methode:
- N-gram- of overlapcontrole tegen de volledige evalset en resultaat:
- Trein/validatie-split en seed:

## Generatie en filtering

- Synthetisch gegenereerd (ja/nee):
- Generator/modelversie/provider:
- Promptversie of hash:
- Verifier en versie:
- Automatische filters en aantallen verwijderd per filter:
- Handmatige steekproef: aantal bekeken (doel 100), reviewer en bevindingen:
- Herstelacties na review:

## Formaat en chat-template

- Schema: `AnswerV1` JSON in het laatste assistentbericht:
- Template-/tokenizer-revisie:
- `enable_thinking` instelling:
- Hoe bron-ID's in vraag/context aansluiten op bron-ID's in antwoord:

## Beperkingen en risico's

- Verwachte kennishiaten:
- Tijdgevoeligheid/verouderingsrisico:
- Voorstellen die mogelijk met geldend recht worden verward:
- Bekende synthetische fouten of labelruis:
- Beperkingen van de verifier en menselijke controle:

## Run en evaluatie

- Baseline-score en evalset-hash:
- Model, revisie en licentie:
- LoRA-configuratie (rank, modules, learning rate, epochs, context):
- Hardware en softwareversies:
- Dataset-hash:
- A/B-resultaten, inclusief abstentie, citatie-ondersteuning en kernfeit-correctheid:
- Besluit (doorgaan/stoppen) en reden:
- Export-/adapter-hash:
