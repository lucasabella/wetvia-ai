# 01. Kritische beoordeling van het idee

*Peildatum: 30 oktober 2026. Bronnen staan inline gelinkt.*

## TL;DR

| Vraag | Oordeel |
|---|---|
| Is het idee goed **als portfolioproject**? | **Ja, sterk.** Het raakt alles wat een AI/ML-engineer moet laten zien: RAG over echte, rommelige overheidsdata, lokale inferentie, structured output, evaluatie en optioneel fine-tuning. |
| Is het idee realistisch **zoals het nu beschreven staat** (alle wetten, alle gemeenten, wetsvoorstellen, beleidsstukken, burgers + bedrijven + ambtenaren)? | **Nee.** Dat is werk voor een team van 10+ mensen. Het lijkt op wat Legal Mind, Zeno en Lexboost met funding bouwen. |
| Wat is wél haalbaar in ~1 maand met agents? | **Eén domein (Omgevingswet: dakkapel en uitbouw), voor één doelgroep (burgers), op een kleine set bronnen (5-6 rijksregelingen),** met citaten, een "ik weet het niet"-gedrag en een echte evaluatieset. |
| Grootste risico | **Overtuigend klinkende, foute juridische antwoorden.** Daarom staat **evaluatie** (niet het model) centraal in het plan. |
| Grootste kans om op te vallen | **Lokaal + open source + meetbare betrouwbaarheid.** De bestaande tools zijn closed, cloud-only of alleen voor professionals. Een publieke eval-harness met cijfers is zeldzaam en voor recruiters goed te controleren. |

## 1. Wat is sterk aan het idee

1. **De data is open en goed gestructureerd.** Het Basis Wetten Bestand (BWB, ~45.000 regelingen) is **CC0** en elke dag bijgewerkt, met een SRU-API voor wijzigingen ([data.overheid.nl](https://data.overheid.nl/dataset/basis-wetten-bestand)). Lokale regelgeving (CVDR) en Officiële bekendmakingen zijn ook CC0 ([CVDR](https://data.overheid.nl/dataset/lokale-regelingen), [OB](https://data.overheid.nl/dataset/officiele-bekendmakingen)). De Tweede Kamer-data is CC0 ([disclaimer](https://opendata.tweedekamer.nl/disclaimer)). DSO-data is CC BY 4.0 met een gratis API-key ([Fair Use Policy](https://developer.omgevingswet.overheid.nl/services/fair-use-policy/)). Voor dit domein is dat uitzonderlijk goed.
2. **Elke toestand heeft een geldigheidsperiode.** Elke versie (toestand) van een BWB-regeling heeft `geldigheidsperiode_startdatum` en `_einddatum` (zelf geverifieerd via de SRU-API voor BWBR0041297). Daarmee kun je de eis **"geldend vs. toekomstig vs. vervallen"** deterministisch oplossen, zonder dat het model het hoeft te raden.
3. **Er is een echte nood.** Het gebruikersoordeel over de officiële Vergunningcheck is 3,8 op 7, en veel aanvragers haken af door het aantal vragen ([Sneltoetser](https://sneltoetser.nl/) citeert de Minister van VRO en een IPLO-gebruikersonderzoek uit 2024).
4. **Het sluit aan op wat je al kent.** Bij DeeDeeAI werk je met Qwen 3.5 122B-A10B en je hebt LoRA-fine-tuning van Qwen3.8-27B onderzocht. Wetvia is dezelfde stack, maar op kleiner formaat en in het openbaar. Dat is een sterk verhaal voor sollicitaties.

## 2. Risico's (eerlijk)

### 2.1 Hallucinatie en aansprakelijkheid: risico **hoog**

- Een LLM dat "vergunningvrij" zegt terwijl het lokale omgevingsplan (of een monumentenstatus) een vergunning eist, kan iemand geld kosten: een handhavingsbesluit of verplichte afbraak.
- **Juridisch kader:**
  - Juridisch advies geven is in Nederland **geen beschermd beroep**. Alleen de titel *advocaat* en procesvertegenwoordiging in bepaalde zaken zijn beschermd ([NOvA](https://www.advocatenorde.nl/over-de-advocatuur), [Advocatenwet](https://wetten.overheid.nl/BWBR0002093/2026-01-01/)). Wetvia mag dus juridische informatie geven, maar mag zich niet als advocaat presenteren.
  - **Aan een vergunningcheck kun je geen rechten ontlenen**, ook niet aan de officiële ([ABRvS 22-02-2023, ECLI:NL:RVS:2023:736](https://uitspraken.rechtspraak.nl/details?id=ECLI:NL:RVS:2023:736), aangehaald door Sneltoetser). Wetvia moet dat letterlijk zeggen.
  - **Nieuwe productaansprakelijkheidsrichtlijn (EU) 2024/2853:** software en AI-systemen gelden expliciet als "product". De richtlijn moet uiterlijk **9 december 2026** zijn omgezet (NL: wetsvoorstel 36906). **Gratis open-source software buiten een handelsactiviteit valt erbuiten** ([EUR-Lex](https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng), [Eerste Kamer 36906](https://www.eerstekamer.nl/wetsvoorstel/36906_implementatiewet_richtlijn)). → **Zolang Wetvia een gratis, niet-commercieel open-sourceproject is, blijft het buiten die richtlijn. Ga je er geld voor vragen of een hosted dienst verkopen, dan verandert dat.**
- **Mitigaties (verplicht in het ontwerp):**
  1. *Geen bron, geen claim:* een antwoord zonder opgehaalde bron wordt geweigerd, niet "toch maar" gegenereerd (zie 02, §5).
  2. Elk citaat wordt **automatisch gecontroleerd**: bestaat het artikel, en staat de geciteerde tekst er echt in?
  3. De conclusie over vergunningplicht is altijd **"waarschijnlijk ..."**, met een voorbehoud voor het lokale omgevingsplan en een link naar de Vergunningcheck.
  4. Documenten krijgen een watermerk *CONCEPT, niet gecontroleerd*.

### 2.2 AI-verordening (AI Act): risico **laag tot middel**

- **Art. 50 (transparantie) geldt sinds 2 augustus 2026 en is niet uitgesteld door de Digital Omnibus.** Uitgesteld zijn vooral de high-risk-regels ([EC quick facts](https://digital-strategy.ec.europa.eu/nl/factpages/quick-facts-transparency-rules-ai-systems), [Jones Walker](https://www.joneswalker.com/en/insights/blogs/ai-law-blog/yes-august-2-still-matters-the-eu-approved-a-high-risk-ai-delay-but-most-trans.html)). Gevolg voor Wetvia: gebruikers moeten weten dat ze met AI praten, en gegenereerde documenten krijgen een **machineleesbare markering** (bijv. een metadataveld in de DOCX/PDF plus een zichtbare voettekst).
- **High-risk (Bijlage III):** juridische AI valt daaronder als hij gebruikt wordt **door of namens rechterlijke autoriteiten** of voor toegang tot essentiële publieke diensten (besluiten over uitkeringen e.d.). Een informatietool voor burgers valt daar niet onder. **Laat Wetvia daarom geen besluiten nemen voor een overheidsinstantie.** De doelgroep "ambtenaren" kan later wel high-risk worden als het systeem besluitvorming ondersteunt. Dat is nog een reden om in de MVP alleen burgers te bedienen.

### 2.3 Actualiteit van de data: risico **middel**

- Wetten veranderen vaak: de BWB bevatte voor het Bbl 11 toestanden (SRU-resultaat voor BWBR0041297, opgevraagd op 30-10-2026). Een vector-index van drie maanden oud is dus fout.
- **Oplossing:** een dagelijkse incrementele sync via SRU (`dcterms.modified >= gisteren`). Bij elk chunk sla je `geldig_vanaf` en `geldig_tot` op, en bij elke query filter je op de peildatum. Het antwoord toont **"Geldig op: <datum>"**.
- Gemeentelijke regels zijn het lastigst: sinds de Omgevingswet staan ze in het **omgevingsplan** in het DSO (incl. het "tijdelijk deel" met de oude bestemmingsplannen), en niet in CVDR. Sneltoetser laat zien dat je daarvoor de DSO Presenteren-API en ruimtelijkeplannen.nl nodig hebt ([sneltoetser.nl](https://sneltoetser.nl/)). → **Dat is fase 2, niet de MVP.**

### 2.4 Concurrentie: risico **hoog voor een product, laag voor een portfolio**

| Speler | Wat | Verschil met Wetvia |
|---|---|---|
| **Omgevingsloket Vergunningcheck** ([link](https://omgevingswet.overheid.nl/checken)) | Officieel, beslisbomen per activiteit en locatie | Gratis en officieel, maar stroeve UX. Wetvia vervangt hem niet en **verwijst ernaar** |
| **Sneltoetser** ([link](https://sneltoetser.nl/)) | Proof-of-concept voor burgers: vrije tekst + adres, DSO Presenteren v8, hardcoded Bbl-drempels, Claude als semantische laag, 300+ golden cases, juridische blinde toetsing | **De directe concurrent voor de MVP-use-case, en al verder.** Draait op Claude (cloud) en maakt geen documenten. Leer ervan: hardcoded drempels + LLM, golden cases, wekelijkse drift-check |
| **OmgevingsChat** ([link](https://omgevingschat.nl/)) | Open source, voor ambtenaren (Q&A, omgevingsplan, regelanalist) | B2G, dus andere doelgroep |
| **Legal Mind, Zeno, Lexboost, Saga, LegalMike** ([ICTRecht-onderzoek](https://www.ictrecht.nl/onderzoek-ai-tooling-ictrecht)) | Commerciële legal AI voor juristen; Legal Mind haalde €2 mln op | Betaald, voor professionals, closed |
| **GPT-NL** (TNO/SURF/NFI) | Soeverein Nederlands taalmodel, nog in gecontroleerde release ([gpt-nl.nl](https://gpt-nl.nl/)) | Een mogelijk **model** voor later, geen concurrent |

**Conclusie:** als bedrijf kom je de markt te laat binnen, en zonder juristen en funding win je het niet. Als **open-source portfolioproject** onderscheid je je met:
(a) **volledig lokaal** draaien, (b) **een publiek meetbare evaluatie** (eval-set + dashboard), (c) **conceptdocumenten genereren** (doet Sneltoetser niet) en (d) een strakke engineering-architectuur.

### 2.5 Licenties van data en modellen: risico **laag, als je oplet**

- Overheidsteksten: wetten, besluiten, verordeningen en rechterlijke uitspraken zijn op grond van [art. 11 Auteurswet](https://wetten.overheid.nl/BWBR0001886/) niet auteursrechtelijk beschermd, en de datasets zijn CC0. **Annotaties, commentaren, handboeken en vakbladen (Wolters Kluwer, SDU, Legal Intelligence) zijn wél beschermd.** Scrape ze niet.
- **Les van GEITje:** het Nederlandse model GEITje-7B is in januari 2025 offline gehaald op verzoek van Stichting BREIN, omdat het deels getraind was op Gigacorpus-data uit illegale bronnen ([GoingDutch.ai](https://goingdutch.ai/nl/posts/geitje-takedown/), [BREIN](https://stichtingbrein.nl/brein-takes-llm-offline/)). → **Gebruik voor fine-tuning alleen data met een bewezen licentie (CC0-overheidsdata + eigen synthetische data) en documenteer de herkomst (data card).**
- Modellen: Qwen3.5/3.6/3.8 en Gemma 4 zijn **Apache-2.0** ([Qwen](https://github.com/QwenLM/Qwen3.8/tree/main), [Gemma 4](https://ai.google.dev/gemma/docs/releases)). Daarmee zit je goed.

### 2.6 Privacy (AVG): risico **middel bij uploads**

- Burgers uploaden bezwaarbrieven of tekeningen met naam, adres en BSN. Lokale modus = geen verwerking door derden. **Cloudmodus = Scaleway als verwerker (EU), en dan heb je een verwerkersovereenkomst/DPA nodig**, plus een duidelijke toestemmingsmelding.
- Dataminimalisatie: BSN's automatisch herkennen en maskeren vóór opslag, chats standaard alleen lokaal (IndexedDB) en geen telemetrie.

### 2.7 Scope en tijd: risico **hoog**

5-10 uur per week naast een stage, ook met agents. Agents bouwen snel, maar **jij moet reviewen, evalueren en de juridische inhoud controleren.** Dat laatste kost de meeste tijd. Daarom:

- **Één use-case** in de MVP (dakkapel + uitbouw/aanbouw: Bbl art. 2.29 en verwante artikelen, [IPLO](https://iplo.nl/thema/bouw/bouwen-vergunning-melding/dakkapel/)).
- **Niet** in de MVP: wetsvoorstellen schrijven, beleidsstukken, verschillen tussen gemeenten, ambtenaren-modus en fine-tuning.

## 3. Wat ik zou schrappen of uitstellen (en waarom)

| Feature uit het concept | Besluit | Reden |
|---|---|---|
| Conceptwetsvoorstellen en beleidsstukken opstellen | **Later (fase 4+) of nooit** | Er is geen eval mogelijk zonder wetgevingsjuristen, en het waardeert niet als portfolio-feature |
| Verschillen tussen gemeenten herkennen | **Fase 2-3** | Vereist DSO omgevingsplannen per locatie, en de data is complex (IMOW, tijdelijk deel) |
| Bezwaarschrift genereren | **Fase 2** | Goed tweede documenttype (Awb art. 6:5 vormvereisten zijn eenvoudig en vast) |
| Document upload + analyse | **Fase 2** | Waardevol, maar de MVP moet eerst bronnen goed citeren |
| Wetsvoorstellen (Tweede Kamer) | **Fase 3** | Toon ze alleen als "toekomstig, nog niet geldend", met een link |
| Burgers + bedrijven + ambtenaren | **Alleen burgers** | Ambtenaren-gebruik raakt aan high-risk en heeft andere UX nodig |

## 4. Eindoordeel

**Doen, maar smal beginnen.** Bouw de *betrouwbaarheidsmachine* (bronnen → retrieval met geldigheidsdatum → antwoord met gecontroleerde citaten → eval-harness) voor één use-case. Breid daarna uit. Het verhaal voor een sollicitatie is dan: *"Ik heb een lokaal draaiende juridische RAG-assistent gebouwd die 92% van de citaten correct heeft en in 85% van de vragen zonder antwoord netjes weigert, gemeten op een publieke eval-set van 150 vragen."* Dat is sterker dan een brede demo die soms onzin zegt. *(De percentages zijn voorbeeld-streefwaarden, geen gemeten resultaten.)*
