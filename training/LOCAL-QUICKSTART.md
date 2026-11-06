# Lokale run op Windows + RTX 3070

Dit is de route om de trainingsomgeving op de eigen pc klaar te zetten, volledig in Windows: PowerShell en Ollama, zonder WSL of Linux. Gebruik voor Qwen3.5 bf16-LoRA, geen QLoRA of CPU-offload. De trainer downloadt het basismodel van Hugging Face; trainingsdata en adapter-output blijven lokaal. De lockfile is al cross-platform: `training/uv.lock` bevat de Windows-wheels (`torch` cu128 `win_amd64`, `triton-windows`).

## Eenmalige pc-setup

1. Werk de NVIDIA-driver in Windows bij (NVIDIA-app of GeForce Experience). Installeer geen aparte CUDA Toolkit; PyTorch cu128 levert de CUDA-runtime zelf mee.
2. Installeer [Ollama voor Windows](https://ollama.com/download) en haal het basismodel voor de A/B-eval binnen:

   ```powershell
   ollama pull qwen3.5:0.8b
   ```

3. Installeer `uv` in PowerShell:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Herstart daarna de terminal en controleer `uv --version`.

4. Clone de repo op een korte padnaam (lange paden geven soms problemen op Windows), bijvoorbeeld `C:\src`:

   ```powershell
   cd C:\src
   git clone https://github.com/lucasabella/wetvia-ai.git
   cd wetvia-ai
   git fetch origin feature/local-qwen35-lora-quickstart
   git switch --track origin/feature/local-qwen35-lora-quickstart
   ```

5. Maak de trainingsomgeving aan. De eerste keer downloadt dit meerdere GB; houd minstens 15 GB schijfruimte vrij voor pakketten, modelcache, dataset en adapter-output:

   ```powershell
   uv sync --project training
   ```

6. Controleer de GPU:

   ```powershell
   nvidia-smi
   ```

   Je moet de RTX 3070 zien met ongeveer 8 GiB geheugen. Sluit `ollama` en andere programma's die VRAM gebruiken terwijl je traint; Ollama laadt modellen in dezelfde VRAM.

## Stap 1: hardware/model preflight

Start met het kleine model. Dit downloadt en laadt het model plus LoRA-lagen, maar traint niets:

```powershell
uv run --project training python training/train_qwen35_lora.py --preflight-only
```

Verwachte uitkomst: CUDA ziet een RTX 3070, bf16 is beschikbaar en Qwen3.5-0.8B met LoRA laadt. Bekijk het piekgebruik in `nvidia-smi` in een tweede PowerShell-terminal.

Daarna kun je ook 2B proberen:

```powershell
uv run --project training python training/train_qwen35_lora.py --model Qwen/Qwen3.5-2B --preflight-only
```

Als de 2B-preflight faalt of het geheugen vrijwel volloopt, blijf dan voor de eerste run bij 0.8B. Unsloth schat bf16-LoRA op circa 3 GB voor 0.8B en 5 GB voor 2B; 4B vraagt circa 10 GB en past niet volledig in deze GPU (die gaat naar Colab of een gehuurde GPU).

## Stap 2: data klaarzetten

Train pas als de gedragstaak vaststaat en er een dataset is die aan de reviewcriteria voldoet. Zet het lokaal gemaakte bestand op:

```text
training/data/sft.jsonl
```

Voor iedere regel:

```json
{
  "id": "unieke-id",
  "messages": [
    { "role": "system", "content": "..." },
    {
      "role": "user",
      "content": "Vraag en bronfragmenten met hun bron-ID's ..."
    },
    {
      "role": "assistant",
      "content": "{\"status\":\"onzeker\",\"samenvatting\":\"...\",\"punten\":[],\"voorbehouden\":[],\"vervolgstappen\":[],\"peildatum\":\"2026-11-06\"}"
    }
  ],
  "metadata": {
    "source_uris": ["https://..."],
    "license": "CC0-1.0",
    "negative": true
  }
}
```

Dit is alleen de vorm van één voorbeeld, geen goedgekeurd trainingsvoorbeeld. De assistentinhoud moet exacte `AnswerV1`-JSON zijn en de `peildatum` moet bij de bron passen. `metadata` is voor audit en wordt niet naar het model gevoerd. Zie [DATA_CARD.template.md](DATA_CARD.template.md).

Voorstel: genereer conceptvoorbeelden in plaats van met de hand te typen. Zet CC0-fragmenten in `training/data/bronnen.jsonl` en draai:

```powershell
uv run --project eval python training/generate_sft.py --mode requests
```

Upload de requestregels naar de Scaleway batch-API (teacher: Qwen3.8-27B) en verwerk het resultaat met `--mode ingest`; de pipeline valideert elke kandidaat, dedupliceert en schrijft een conceptdraft plus data card. Review minimaal 100 voorbeelden (het daarvoor gegenereerde steekproefbestand) en kopieer de goedgekeurde rijen naar `training/data/sft.jsonl`. Zie training/README.md, "Dataflow".

Gebruik voor Tweede Kamerdata een expliciet taakdoel, bijvoorbeeld samenvatten mét bronverwijzingen, of brongebonden vragen over voorstellen. Vermeld in de broncontext datum en documentstatus; train niet alsof een wetsvoorstel geldend recht is. De officiële open-data-portal is [opendata.tweedekamer.nl](https://opendata.tweedekamer.nl/). Projectdocumentatie noemt parlementaire open data CC0; registreer de exacte dataset en licentiebron in de data card.

## Stap 3: train lokaal

De trainer reserveert zelf 5% voor validatie. De aparte menselijke A/B-evalset blijft volledig buiten deze run.

```powershell
uv run --project training python training/train_qwen35_lora.py --train-file training/data/sft.jsonl --model Qwen/Qwen3.5-0.8B --max-seq-length 1024 --output-dir training/output/qwen35-0.8b-lora
```

Na een geslaagde run staan alleen de LoRA-adapter, tokenizer en runmetadata in `training/output/`. Voor de 2B-run verander je model-ID en outputmap. Verhoog context, epochs of modelgrootte niet tegelijk; zo kun je zien welke instelling geheugen gebruikt.

## Stap 4: exporteren naar Ollama en de A/B-eval

1. Bewaar de adapter samen met het exacte basismodel-ID, dataset-hash en chat-template.
2. Exporteer naar een gemergd GGUF-bestand (`q4_k_m`) met Unsloth (`save_pretrained_gguf`) volgens de [Unsloth-exportgids](https://unsloth.ai/docs/models/qwen3.5/fine-tune), en laad het in Ollama onder een eigen tag. Maak een `Modelfile` naast het GGUF-bestand:

   ```text
   FROM C:\src\export\qwen35-0.8b-lora-q4_k_m.gguf
   ```

   ```powershell
   ollama create qwen35-lora-0.8b:latest -f Modelfile
   ollama run qwen35-lora-0.8b:latest "Vat het voorstel in de bron samen."
   ```

   Controleer dat de chat-template en end-of-turn-tokens hetzelfde blijven als tijdens de training (zie ook de [exportgids](https://unsloth.ai/docs/models/qwen3.5/fine-tune)).

3. Vergelijk baseline en LoRA op dezelfde, nooit getrainde eval-items. Installeer daarnaast één keer de workspace-omgeving (extra GB-downloads) en draai:

   ```powershell
   uv sync --all-packages --all-groups
   uv run --project eval python eval/run.py ab --baseline qwen3.5:0.8b --tuned qwen35-lora-0.8b:latest
   ```

   De concept-probe-set `eval/data/ab_kamervragen.jsonl` meet alleen gedrag (abstentie en citatievorm), geen juridische inhoud en is géén Wetvia-kwaliteitsmeting. De drempels doen er pas toe zodra de gereviewde evalset er is (issues #13 en #27); totdat die er is, bewijst een groen rapport alleen dat de trainingspipeline werkt.

   Alternatief: laat de A/B op een ander apparaat draaien (de Mac) tegen Ollama op de pc. Start Ollama dan met `OLLAMA_HOST=0.0.0.0` (plus een firewallregel voor poort 11434) en voeg `--base-url http://<ip-van-pc>:11434` toe. Op de pc zelf blijft Ollama dan gewoon op `127.0.0.1`.

4. Zet de LoRA niet standaard aan als de drempels uit `docs/02-ai-architectuur.md` (abstentie-recall +5pp of citatie-ondersteuning +3pp, zonder daling in kernfeit-correctheid) op de gereviewde set niet gehaald worden.

## Als iets faalt

- **`nvidia-smi` werkt niet:** werk eerst de NVIDIA-driver bij en herstart de terminal (of de pc).
- **CUDA niet gevonden:** controleer dat `uv sync --project training` in deze repo is gedraaid en gebruik `uv run --project training` in dezelfde map.
- **Out of memory:** sluit Ollama en andere GPU-processen, begin met 0.8B, batch 1 en context 1.024. Gebruik geen RAM-offload als eerste oplossing; de Qwen3.5-richtlijn is bf16-LoRA.
- **Kernel- of Transformers-fout:** noteer de fout en versies met `uv run --project training python -m pip freeze`; verander niet willekeurig CUDA-, Torch- of Transformers-versies.
- **Pad- of rechtenproblemen:** houd de repo op een korte locatie (`C:\src\wetvia-ai`) en gebruik een gewone PowerShell (geen administrator).

Dit document kan ik stap voor stap met je doorlopen zodra je op je pc zit. Deel dan eerst `nvidia-smi` en de volledige preflight-uitvoer; daarin horen geen API-sleutels of privédata te staan.
