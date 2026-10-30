# 05. MVP-ontwikkelplan

## Uitgangspunten

- **Tijd:** 5-10 uur per week (Luca). Code wordt grotendeels geschreven door **Cursor cloud agents** op basis van issues met het label `agent-ready`. Luca doet: issues prioriteren, PR's reviewen, de eval-set opstellen en controleren, en de juridische inhoud checken.
- **Ritme:** per week 3-6 agent-issues → max. 1 uur review per PR. Elke PR moet CI groen hebben en, waar relevant, de eval-delta tonen.
- **Demo-doel:** **6 december 2026** (≈ 5 weken). Een werkende lokale demo + een eval-rapport + een video van 2 minuten.
- **Agenda:** wintersport 19-26 december (geen werk); stage loopt af op 29 januari 2027. Rond die periode is er minder tijd, dus fase 2 is ruim gepland.

## MVP-scope (hard)

**Wel:**
1. Chat over **verbouwregels voor woningen** (dakkapel, dakraam, zonnepanelen, uitbouw, met de nadruk op de dakkapel) met bronnen uit 7 regelingen (zie 04).
2. Bronnenpaneel met statusbadges (geldend/toekomstig/vervallen) en peildatum.
3. Abstentie: "weet ik niet zeker" + verwijzing.
4. **Dakkapel-wizard** met regels-als-code (Bbl 2.27/2.29/2.30) → **conceptdossier** DOCX/PDF/MD.
5. Lokaal (Ollama) **én** cloud (Scaleway) via een env-switch.
6. Eval-set v0 (150 vragen) + rapport + CI.

**Niet (expliciet):** accounts, uploads, CVDR/omgevingsplan per adres, bezwaarschriften, wetsvoorstellen schrijven, ambtenaren-modus, fine-tuning, publieke hosting.

## Planning per week

| Week | Data | Milestone | Doel | Luca (uren) | Agents |
|---|---|---|---|---|---|
| **1** | 2-8 nov | **M0 Fundament** | Repo, CI, skelet en de modelkeuze-meting | Repo aanmaken, DSO-key aanvragen, **30 eval-vragen schrijven** (3-4 u); Ollama + modellen installeren op 3070/M3 (1 u) | Monorepo-skelet, Docker Compose + pgvector, FastAPI-skelet + health, SvelteKit-skelet, CI, LLM-provider-abstractie, benchmark-script |
| **2** | 9-15 nov | **M1 Bronnen & RAG** | Wetten in de DB, met hybride zoeken op peildatum | XML-parse-output steekproefsgewijs controleren (2 u), eval naar 80 vragen (3 u) | BWB-SRU-client, BWB-XML-parser → chunks, embeddings-job, hybride retrieval + RRF, `/sources/{id}`-endpoint, retrieval-eval (recall@k) |
| **3** | 16-22 nov | **M2 Chat MVP** | Een vraag stellen en een antwoord met bronnen krijgen, in de UI | Prompts tunen, de eerste end-to-end-eval bekijken (4 u) | Antwoordschema + pipeline, citatie-verifier + abstentie, SSE-endpoint, chat-UI, bronnenpaneel, IndexedDB-geschiedenis, cloud-provider |
| **4** | 23-29 nov | **M3 Dakkapel-dossier** | Wizard → toets → conceptdossier | Regels-als-code juridisch controleren (2 u), eval naar 150 (3 u) | `rules/bbl_dakkapel.py` + tests, wizard-UI, dossier-schema + DOCX/PDF-render, DSO Toepasbare-regels-lookup (indieningsvereisten), drift-check-Action |
| **5** | 30 nov-6 dec | **M4 Evaluatie & demo** | Cijfers, LLM-as-judge, polish, demo | Handmatig 40 antwoorden labelen voor κ (3 u), demovideo opnemen (2 u), README-cijfers | Eval-runner + judge + rapport, eval in CI, a11y-pass (axe), statusbadges/temporele trickcases, landing/"Over" + disclaimer, release v0.1 |

> **Buffer:** week 5 bevat al polish-taken die kunnen vervallen. Loopt week 2 uit (XML-parsing is de grootste onbekende), schrap dan in week 4 de DSO-lookup. De checklist in het dossier wordt dan statisch.

## Latere fases

| Fase | Periode | Milestone | Inhoud | Waarom in deze volgorde |
|---|---|---|---|---|
| **v0.2** | 7 dec 2026 - 17 jan 2027 (excl. 19-26 dec) | **M5 v0.2** | (1) **Omgevingsplan per adres** via DSO Presenteren v8 + PDOK-geocoding; "verschillen tussen gemeenten" voor bouwen. (2) **Document-upload** (Docling, lokaal) + "check mijn aanvraag/brief". (3) **Bezwaarschrift-generator** (Awb 6:5, 6:7; termijn 6 weken). (4) Reranker-experiment. (5) *Optioneel:* publieke demo op een EU-VPS (alleen cloudmodus, rate-limited; nog geen issue, pas aanmaken als er tijd over is). | Maakt het product echt nuttig en vormt het verschil met de bestaande tools |
| **v0.3** | 18 jan - 28 feb 2027 | **M6 v0.3 LoRA** | Synthetische SFT-data + LoRA bf16 op Qwen3.5-4B/9B, A/B op de eval-set, GGUF-release op Hugging Face (Apache-2.0-adapter + data card). Blogpost: "Wat fine-tuning wél en niet oplost bij juridische RAG". | Pas zinvol als er baseline-cijfers zijn; het sterkste leerdeel |
| **v0.4+** | maart 2027 → | Backlog | Wetsvoorstellen-tracker (TK OData + "toekomstig recht"-badges), CVDR-APV's, bedrijfspanden (Bal-meldingen), model-upgrade (GPT-NL als dat beschikbaar komt, Qwen-opvolger), Engelstalige UI. | Alleen als v0.3 goed loopt |

## Moeilijkheden die je gaat tegenkomen (en de aanpak)

| Moeilijkheid | Waarom lastig | Aanpak |
|---|---|---|
| **BWB-XML-structuur** | Diep genest (hoofdstuk/afdeling/paragraaf/artikel/lid/lijst/li), met tabellen, "vervallen"-markeringen en voetnoten | Begin met alleen `artikel` + `lid` + `lijst`, en golden-file tests op Bbl 2.29 en Awb 6:5. Tabellen worden in de MVP Markdown |
| **Toestanden en tijd** | Meerdere versies per regeling; de geldigheid zit in de SRU-metadata, niet in het artikel | Sla de toestand op als eenheid; elk chunk erft de geldigheid. Vergelijk toestanden om "wat verandert er op 01-01-2027?" te kunnen tonen (later) |
| **Kleine modellen en citaten** | 9B-modellen verzinnen soms ID's of citeren de verkeerde chunk | Constrained JSON + verifier + korte chunk-ID's (`[1]`..`[8]`) in de prompt i.p.v. UUID's |
| **Thinking vs. structured output (Qwen3.5)** | Bekende Ollama-bug | `think:false`; een regressietest in CI met een mock |
| **8 GB VRAM** | Embeddings + LLM + context tegelijk | Embeddings op de CPU (ingest eenmalig, queries zijn kort) of e5 in fp16 (~1,1 GB). LLM-context max. 16k |
| **Omgevingsplannen (v0.2)** | IMOW-data is complex; het tijdelijk deel bevat oude bestemmingsplannen | Alleen "relevante regels op locatie" tonen + linken, niet zelf interpreteren. Kijk hoe Sneltoetser het doet |
| **Juridische juistheid** | Je bent geen jurist | Laat de eval-set (minstens 30 items) controleren door een rechtenstudent of iemand van een rechtswinkel; vermeld dat in de README |
| **Agents en domeinkennis** | Agents kennen de BWB-structuur en Bbl-nuances niet | Elk issue linkt naar het juiste docs-bestand, met concrete voorbeelden (ID's, endpoints, verwachte output) |

## Budget

Zie 04 §Kosten: **MVP ≤ €3 per maand, met een demo ≤ €20 per maand, fine-tune eenmalig €5-15.** Ruim binnen €0-25.

## Definition of Done v0.1 (6 december)

- [ ] `docker compose up` + `ollama pull qwen3.5:9b` → werkt op een schone machine (README-instructies getest)
- [ ] 7 regelingen geïngest met de toestand die geldt op de peildatum
- [ ] Chat met bronnenpaneel, statusbadges, abstentie
- [ ] Dakkapel-wizard → conceptdossier (DOCX + PDF) met watermerk
- [ ] Lokaal en cloud werken via `.env`
- [ ] Eval-rapport v0 (150 vragen) gepubliceerd in `eval/reports/v0.1.md`, met κ van de judge
- [ ] Disclaimer + AI-transparantie (art. 50) in de UI en in documenten
- [ ] Demovideo (≤ 2 min) in de README
