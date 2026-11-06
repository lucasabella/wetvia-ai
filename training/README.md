# Lokale Qwen3.5 LoRA voor Wetvia

Deze map staat buiten de uv-workspace van Wetvia. De GPU-trainingsomgeving heeft eigen afhankelijkheden en hoort niet in de API-lockfile. Er staan geen trainingsvoorbeelden of modelgewichten in Git.

## Aanbevolen route voor een RTX 3070 met 8 GB VRAM

1. Begin met **Qwen3.5-0.8B** als installatie- en pipelinecontrole. Unsloth noemt ongeveer 3 GB VRAM voor bf16-LoRA.
2. Probeer daarna **Qwen3.5-2B** als lokale kandidaat. Unsloth noemt ongeveer 5 GB. Start met batch 1 en een context van 1.024 tokens; verhoog pas als de run ruim onder de VRAM-grens blijft.
3. Gebruik **bf16-LoRA, rank 16**. Gebruik voor Qwen3.5 geen QLoRA: Unsloth waarschuwt voor de extra quantisatieverschillen. De 4B-variant vraagt volgens dezelfde gids ongeveer 10 GB en hoort dus op Colab of een andere GPU.

De schattingen gelden voor Unsloth en zijn afhankelijk van versie, contextlengte en model. Bekijk de [actuele Qwen3.5-trainingsgids](https://unsloth.ai/docs/models/qwen3.5/fine-tune) voordat je een run start.

## Wat de LoRA moet leren

Train geen actuele juridische feiten in de gewichten. Wetgeving en voorstellen blijven uit retrieval en de regels-engine komen. De LoRA is bedoeld voor gedrag zoals:

- antwoorden in begrijpelijk Nederlands;
- het Wetvia-antwoord consistent structureren;
- `onzeker` kiezen wanneer de meegegeven bronnen het antwoord niet bevatten;
- bij Tweede Kamerstukken duidelijk maken dat een document of motie een voorstel is en de bron-ID's correct overnemen.

De huidige projectplanning richt zich op citatieformaat en abstentie. Voor een Tweede Kamer-taak moeten de trainingsvoorbeelden uit de daarvoor gelicentieerde open data komen, met datum en status als metadata. Meng voorstellen niet met geldend recht.

## Dataformaat

`train_qwen35_lora.py` leest één JSON-object per regel. Elk object heeft `id` en een `messages`-lijst met een gewone `system`-, `user`- en `assistant`-uitwisseling. Het laatste assistentbericht is de doeluitvoer als geldige `AnswerV1`-JSON. Extra velden zoals provenance mogen erbij staan en worden niet aan de trainer gevoerd.

De gebruikerstaak bevat de vraag én de bronfragmenten met dezelfde labels/ID's die in het antwoord worden geciteerd. Houd minstens 5% van de synthetische voorbeelden apart als validatiesplit; gebruik daarnaast een afzonderlijke, menselijk gecontroleerde A/B-evaluatieset die nooit in de training komt.

Gebruik alleen bronnen met vastgelegde herkomst en licentie. Zie [DATA_CARD.template.md](DATA_CARD.template.md). De Tweede Kamer vermeldt CC0 voor parlementaire open data in de projectdocumentatie; leg de specifieke dataset en bron-URL alsnog vast.

## Op de pc starten

Zie [LOCAL-QUICKSTART.md](LOCAL-QUICKSTART.md) voor de Windows-installatie (PowerShell en Ollama, zonder WSL), GPU-controle, preflight en de trainingsopdracht. De eerste stap op de pc is `--preflight-only`; dit controleert CUDA, bf16 en het model laden zonder een dataset of API-sleutel nodig te hebben.

Voor echte training zijn ook nodig:

- een concreet gedragstekort dat de bestaande prompt niet oplost en vastgelegde baseline-cijfers;
- een gevalideerde SFT-dataset (projectdoel: 1.500–3.000 voorbeelden, ongeveer 30% negatieve voorbeelden);
- handmatige review van een steekproef van 100 voorbeelden en een ingevulde data card;
- een afgescheiden eval-set om baseline en LoRA eerlijk te vergelijken.

Deze criteria staan ook in `docs/02-ai-architectuur.md` en issues #34/#35. Zonder die data wacht de trainer met opzet op een expliciet JSONL-bestand in `training/data/`.

## Bestanden

- `train_qwen35_lora.py` — bf16-LoRA voor lokaal 0.8B/2B, met datasetvalidatie, preflight en lokaal opslaan van alleen de adapter.
- `answer_v1.py` — gedeeld AnswerV1-contract; trainer en generator valideren hiermee elke rij.
- `generate_sft.py` — generatiepipeline (issue #34): bronfragmenten → teacher-batch of directe gesprekken → verifier → dedup → n-gram-overlap met de evalset → conceptdraft, data card en reviewsteekproef.
- `DATA_CARD.template.md` — herkomst, licentie, generatie, filtering, menselijke review en beperkingen.
- `LOCAL-QUICKSTART.md` — pc-installatie- en runstappen (Windows, PowerShell + Ollama).

Trainingsdata, runs, caches en modelgewichten blijven lokaal en worden door `.gitignore` uitgesloten.

## Dataflow (issue #34)

1. Zet CC0-fragmenten in `training/data/bronnen.jsonl` (velden: `id`, `tekst`, `bron_uri`, `peildatum`, `status` (`geldig`|`voorstel`), `documentsoort`, `licentie`).
2. `--mode requests` schrijft OpenAI-batch-requestregels voor de Scaleway batch-API (teacher: Qwen3.8-27B); upload die apart.
3. `--mode ingest --batch-results …` of `--mode direct` (tegen Ollama of een OpenAI-compat endpoint) verwerkt antwoorden → verifier, dedup, n-gram-check → `sft-concept-*.jsonl` + `DATA_CARD-concept-*.md` + reviewsteekproef.
4. Review minimaal 100 voorbeelden; kopieer gecontroleerde rijen naar `training/data/sft.jsonl` (minstens 20 rijen voor de trainer, doel 1.500–3.000) en vul `DATA_CARD.md` in.
5. Pas train je reviewed set: zie LOCAL-QUICKSTART.md.

De tests van deze map draaien niet in CI (geen GPU nodig); lokaal via de eval-omgeving:

```bash
uv run --project eval python -m pytest training/tests -q
```
