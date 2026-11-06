# Lokale run op Windows + RTX 3070

Dit is de route om de trainingsomgeving op de eigen pc klaar te zetten. Gebruik voor Qwen3.5 bf16-LoRA, geen QLoRA of CPU-offload. De trainer downloadt het basismodel van Hugging Face; trainingsdata en adapter-output blijven lokaal.

## Eenmalige pc-setup

1. Werk de NVIDIA-driver in Windows bij. Installeer niet handmatig een aparte CUDA Toolkit.
2. Installeer WSL2 met Ubuntu 24.04 vanuit PowerShell als administrator:

   ```powershell
   wsl --install -d Ubuntu-24.04
   ```

   Herstart als Windows daarom vraagt, open Ubuntu en maak de Linux-gebruiker aan.

3. In Ubuntu controleer je de GPU:

   ```bash
   nvidia-smi
   ```

   Je moet de RTX 3070 zien met ongeveer 8 GiB geheugen. De CUDA-driver wordt door de Windows-driver geleverd; installeer geen Linux-displaydriver in WSL.

4. Installeer `uv` in Ubuntu:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source "$HOME/.local/bin/env"
   ```

5. Clone de repo in de Linux-home-directory, niet onder `/mnt/c` (model- en dataset-I/O is daar trager):

   ```bash
   mkdir -p ~/src
   cd ~/src
   git clone https://github.com/lucasabella/wetvia-ai.git
   cd wetvia-ai
   ```

   Haal daarna de trainingsbranch op:

   ```bash
   git fetch origin feature/local-qwen35-lora-quickstart
   git switch --track origin/feature/local-qwen35-lora-quickstart
   ```

6. Maak de eigen trainingsomgeving aan:

   ```bash
   uv sync --project training
   ```

   Eerste keer installeren kan meerdere GB downloaden. Houd minstens 15 GB vrije schijfruimte aan voor Python-pakketten, modelcache, dataset en adapter-output.

## Stap 1: hardware/model preflight

Start met het kleine model. Dit downloadt en laadt het model plus LoRA-lagen, maar traint niets:

```bash
uv run --project training python training/train_qwen35_lora.py --preflight-only
```

Verwachte uitkomst: CUDA ziet een RTX 3070, bf16 is beschikbaar en Qwen3.5-0.8B met LoRA laadt. Bekijk het piekgebruik in `nvidia-smi` in een tweede Ubuntu-terminal.

Daarna kun je ook 2B proberen:

```bash
uv run --project training python training/train_qwen35_lora.py \
  --model Qwen/Qwen3.5-2B --preflight-only
```

Als de 2B-preflight faalt of het geheugen vrijwel volloopt, blijf dan voor de eerste run bij 0.8B. Unsloth schat bf16-LoRA op circa 3 GB voor 0.8B en 5 GB voor 2B; 4B vraagt circa 10 GB en past niet volledig in deze GPU.

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

Gebruik voor Tweede Kamerdata een expliciet taakdoel, bijvoorbeeld samenvatten mét bronverwijzingen, of brongebonden vragen over voorstellen. Vermeld in de broncontext datum en documentstatus; train niet alsof een wetsvoorstel geldend recht is. De officiële open-data-portal is [opendata.tweedekamer.nl](https://opendata.tweedekamer.nl/). Projectdocumentatie noemt parlementaire open data CC0; registreer de exacte dataset en licentiebron in de data card.

## Stap 3: train lokaal

De trainer reserveert zelf 5% voor validatie. De aparte menselijke A/B-evalset blijft volledig buiten deze run.

```bash
uv run --project training python training/train_qwen35_lora.py \
  --train-file training/data/sft.jsonl \
  --model Qwen/Qwen3.5-0.8B \
  --max-seq-length 1024 \
  --output-dir training/output/qwen35-0.8b-lora
```

Na een geslaagde run staan alleen de LoRA-adapter, tokenizer en runmetadata in `training/output/`. Voor de 2B-run verander je model-ID en outputmap. Verhoog context, epochs of modelgrootte niet tegelijk; zo kun je zien welke instelling geheugen gebruikt.

## Stap 4: lokale gebruiksproef en A/B-eval

1. Bewaar de adapter samen met het exacte basismodel-ID, dataset-hash en chat-template.
2. Exporteer naar GGUF met Unsloth (`save_pretrained_gguf`, `q4_k_m`) en laad hem in Ollama volgens de [Unsloth-exportgids](https://unsloth.ai/docs/models/qwen3.5/fine-tune). Controleer dat de chat-template en end-of-turn-tokens hetzelfde blijven (doe dat in Ollama met een aparte tag, bijvoorbeeld `qwen35-lora-0.8b:latest`).
3. Vergelijk baseline en LoRA op dezelfde, nooit getrainde eval-items:

   ```bash
   uv run --project eval python eval/run.py ab \
     --baseline qwen3.5:0.8b \
     --tuned qwen35-lora-0.8b:latest
   ```

   De concept-probe-set `eval/data/ab_kamervragen.jsonl` meet alleen gedrag (abstentie en citatievorm), geen juridische inhoud en is géén Wetvia-kwaliteitsmeting. De drempels doen er pas toe zodra de gereviewde evalset er is (issues #13 en #27); totdat die er is, bewijst een groen rapport alleen dat de trainingspipeline werken is.

4. Zet de LoRA niet standaard aan als de drempels uit `docs/02-ai-architectuur.md` (abstentie-recall +5pp of citatie-ondersteuning +3pp, zonder daling in kernfeit-correctheid) op de gereviewde set niet gehaald worden.

## Als iets faalt

- **`nvidia-smi` werkt niet in WSL:** update de Windows NVIDIA-driver en voer `wsl --update` in PowerShell uit.
- **CUDA niet gevonden:** controleer dat `uv sync --project training` in Ubuntu is uitgevoerd en dat je de `uv`-omgeving gebruikt.
- **Out of memory:** sluit andere GPU-processen, begin met 0.8B, batch 1 en context 1.024. Gebruik geen RAM-offload als eerste oplossing; de Qwen3.5-richtlijn is bf16-LoRA.
- **Kernel- of Transformers-fout:** noteer de fout en versies met `uv run --project training python -m pip freeze`; verander niet willekeurig CUDA-, Torch- of Transformers-versies.

Dit document kan ik stap voor stap met je doorlopen zodra je op je pc zit. Deel dan eerst `nvidia-smi` en de volledige preflight-uitvoer; daarin horen geen API-sleutels of privédata te staan.
