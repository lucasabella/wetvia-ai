# Vervolg na het experiment van 9 november 2026

Afspraak: het huidige werk vastleggen en committen/pushen. Nieuw onderzoek en
verdere training bewaren voor een volgende sessie. Er draait geen trainings- of
inferentieproces meer.

## Wat vaststaat

Qwen3-0.6B kreeg een rank-8 q/v-LoRA met 96 stappen. De conceptdata bevatten
24 trainingsvoorbeelden uit zes documenten, acht devvoorbeelden uit twee andere
documenten en zestien testvoorbeelden uit vier andere documenten. Alle voorbeelden
zijn afgeleid van openbare bronnen en niet menselijk gereviewd. Het checkpoint van
stap 96 is uitsluitend op dev gekozen.

De eindtest gaf gemengde resultaten:

- Volledig JSON-/bron-/bewijscontract: 4/16 naar 10/16.
- Ontbrekende informatie correct volgens het contract: 0/4 naar 3/4.
- Bewijstaak volgens het contract: 1/4 naar 3/4.
- Samenvattingen volgens het contract: 1/4 naar 1/4.
- Lexicale feitwoorddekking bij samenvattingen: 55,1% naar 29,2%.

Een juiste broncode en een aanwezig citaat bewijzen niet dat de antwoordtekst uit
die bron volgt. Bij de herziene convocatie `2026D01188` miste het model de
afgelasting/omzetting en verwarde het raadsdata met een commissiedebat, terwijl de
contractcheck slaagde. Er blijven ook fouten in het Nederlands en inconsistenties
tussen antwoordtekst en statusveld. Houd deze adapter experimenteel; er is geen
onderbouwing voor betere feitelijke samenvattingen of juridische nauwkeurigheid.

Het [volledige verslag](reports/qwen3-06b-20261109.md) bevat de metingen,
tussentijdse benchmarks, beperkingen en inhoudelijke observaties. Het
[onderzoek](../docs/07-tweede-kamer-ai-trainingsonderzoek.md) onderscheidt bevestigd
AI-gebruik van overwogen toepassingen. Het onderbouwt vooral samenvatten, redactie,
documentvergelijking, vertaling en informatieontsluiting; deze run dekt slechts
enkele korte bronanalysetaken.

## Waar alles staat

- Omgeving: `D:/Wetvia/training-env`.
- Basisgewichten/cache: `D:/Wetvia/huggingface`.
- Bronmanifest: `D:/Wetvia/training-runs/research_sources.json`.
- Dataset en hashes: `D:/Wetvia/training-runs/data-v1`.
- Definitieve run: `D:/Wetvia/training-runs/qwen3-06b-lora-20261109-run4`.
- Adapter: `adapter-best/` binnen die run; basisrevision staat ook in
  `adapter_config.json`.
- Opgeslagen baseline: dezelfde runmap, overgenomen uit `run3` na controle van
  modelrevision, prompt, datahashes, decodeerinstellingen en scorer.
- Laadcontrole: `D:/Wetvia/training-runs/reload-check-20261109`.

De ruwe antwoorden, checkpointscores, trainingslog en telemetrie staan lokaal.
Gewichten en datasets blijven buiten git. De adapter is in een nieuw proces
geladen; het developmentantwoord werd exact gereproduceerd en de SHA-256 opnieuw
gecontroleerd. Zie [README](README.md) voor commando's.

## Onderzoek voor de volgende sessie

1. Onderzoek hoe brononderbouwing op **antwoordclaims** kan worden beoordeeld,
   naast broncode en letterlijk bewijs. Begin met de gemiste afgelasting,
   datums, documentstatus en tegenstrijdige statusvelden. Gebruik inhoudelijke
   beoordeling naast automatische controles; woordoverlap alleen is onvoldoende.
2. Onderzoek waarom de kleine fine-tune Nederlandse formuleringen en feitdekking
   verslechtert. Vergelijk hypotheses zoals te weinig gevarieerde voorbeelden,
   te sterke stijl-/sjabloonovername en een te hoge learning rate. Een lagere
   learning rate is een te testen hypothese, geen bewezen verbetering.
3. Verzamel meer gevarieerde, inhoudelijk gereviewde voorbeelden van korte
   briefings, neutrale vervolgvragen en expliciete onzekerheid. Leg per voorbeeld
   noodzakelijke feiten en de status van het document vast. Actuele feiten blijven
   aangeleverde broninformatie; de gewichten zijn geen juridische kennisbank.
4. Ontwerp vóór verdere optimalisatie een nieuwe, ongeziene test met gescheiden
   documenten en relevante taken. De huidige test is al ingezien en mag niet als
   onafhankelijke eindtest van een volgend experiment worden gebruikt. Kies
   instellingen op dev, met inhoudelijke criteria naast structuur; rapporteer
   ook verslechteringen en beoordeel ruwe antwoorden.
5. Beoordeel de waarde van promptverbetering, bronvalidatie en retrieval naast
   verdere training. Vertaling en lange documentvergelijking vragen een eigen
   evaluatie; deze run zegt daar niets over.

## Grenzen voor een volgende lokale run

Behoud de conservatieve instellingen totdat nieuwe metingen een wijziging
rechtvaardigen: twee CPU-threads, twee logische processors, lagere prioriteit,
batch 1, korte context, 37,5% Torch-allocatorlimiet en minstens driemaal de
rekentijd rust. Deze duty-cyclegrens is geen harde quota voor de hele GPU.

De eerste trainingspoging raakte de eigen 3 GiB allocatorlimiet. Gradient
checkpointing maakte een nieuwe run binnen dezelfde limiet mogelijk. Verhoog de
limiet niet alleen om een fout te omzeilen. De geslaagde run bereikte 68 °C,
4,47 GiB totaal VRAM en gemiddeld 39,9% GPU-/29,3% CPU-gebruik; minstens
3,44 GiB systeem-RAM bleef beschikbaar. Metingen omvatten andere geopende apps.

De bewaking pauzeert vanaf 68 °C en stopt vanaf 75 °C, 6,5 GiB totaal VRAM,
te weinig vrij RAM, monitoringfouten of de tijdslimiet. Het STOP-bestand staat
beschreven in de README. Controleer vóór iedere volgende run eerst de actuele
belasting en beschikbare ruimte. Wijzig geen kloksnelheden of andere apps.
