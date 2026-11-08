# Agent-runbook: Qwen3.5 LoRA op Luca's Windows-pc

Doel: een reproduceerbare lokale proef op de RTX 3070 (8 GB VRAM, 16 GB systeemgeheugen), gevolgd door een vergelijking met het basismodel. Voer commando's uit vanuit de repo-root in gewone PowerShell. Dit document is een handoff; een geslaagde preflight bewijst niet dat training of export op deze pc past. Gebruik een door Luca aangewezen, actuele checkout van PR #75 en noteer de commit. Het werk hieronder wijzigt geen productieconfiguratie.

**Huidige startstatus:** er staat geen goedgekeurde `training/data/sft.jsonl` of afzonderlijke juridische evalset in Git. De eerste veilige uitvoering is daarom installatie en `--preflight-only`. Als reviewed data niet lokaal klaarstaat, stop vóór training.

## Grenzen en stopmomenten

De agent mag de repo en hardware inspecteren, de geïsoleerde omgeving installeren, modellen downloaden, een preflight uitvoeren en lokale conceptdata en rapporten maken. Wijzig geen Wetvia-code en commit of push niets vanaf de pc-run. Installeer software alleen met de bestaande pc-toestemming; sluit geen gebruikersprogramma's zonder overleg. Geen sleutel in chat, logs, shellgeschiedenis, repository of data card plaatsen; vraag Luca die lokaal in een procesomgeving te zetten. Gebruik geen privégegevens in bronfragmenten of rapporten. Een externe teacher ontvangt de volledige meegestuurde fragmenten: gebruik die alleen met expliciete toestemming voor die dienst en data.

**Stop vóór echte training op juridische inhoud** totdat een mens de bronnen, trainingsdata en afzonderlijke evaluatieset heeft beoordeeld en de go/no-go en taak heeft vastgelegd. Training van modelgedrag moet niet worden gebruikt om actuele wetgeving in gewichten vast te leggen. Een tijdelijke Ollama-testtag mag voor lokale A/B-proeven worden aangemaakt; stel die niet standaard in Wetvia in en distribueer de adapter niet zonder gereviewde evaluatie en expliciet besluit. Een synthetische probe is geen juridische kwaliteitsmeting. Stop bij onduidelijke licentie, ontbrekende bron of datum, privacyprobleem, beschadigde data, afwijkende hashes, onvoldoende geheugen of incompatibele afhankelijkheden. Meld de blokkade en wijzig niet willekeurig de lockfile of drivers.

## 1. Preflight en installatie

Gebruik een aparte checkout zodat werk in Luca's bestaande clone onaangeroerd blijft. Kies een nieuwe lege map; overschrijf geen bestaande map:

```powershell
$repo = 'C:\src\wetvia-ai-training'
if (Test-Path $repo) { throw "Kies een nieuwe lege map; overschrijf geen bestaande checkout: $repo" }
New-Item -ItemType Directory -Force (Split-Path $repo) | Out-Null
git clone --single-branch --branch feature/local-qwen35-lora-quickstart https://github.com/lucasabella/wetvia-ai.git $repo
Set-Location $repo
git status --short --branch
git rev-parse HEAD
```

Stop als de clone niet op de door Luca aangewezen branch/commit staat. Noteer de exacte commit in het rapport.

Installeer zo nodig `uv` volgens de [officiële installatiehandleiding](https://docs.astral.sh/uv/getting-started/installation/) en Ollama volgens [Ollama Windows](https://docs.ollama.com/windows). Start PowerShell opnieuw en controleer beide versies voordat je verdergaat.

Controleer commit, vrije ruimte op zowel de repo- als cache-schijf en vrij GPU-geheugen. Houd minstens 15 GB vrije schijfruimte aan als startmarge, niet als gegarandeerde bovengrens: downloads, buildbestanden, checkpoints en GGUF kunnen extra ruimte vragen. Bekijk ook beschikbaar systeemgeheugen en laat marge voor Windows. Leg output vast zonder persoonsgegevens.

```powershell
git status --short
git rev-parse HEAD
Get-PSDrive -PSProvider FileSystem | Select-Object Name,Free,Used
Get-CimInstance Win32_OperatingSystem | Select-Object @{Name='RAM_GiB';Expression={[math]::Round($_.TotalVisibleMemorySize / 1MB, 1)}}, @{Name='Free_RAM_GiB';Expression={[math]::Round($_.FreePhysicalMemory / 1MB, 1)}}
nvidia-smi
uv --version
ollama --version
```

`nvidia-smi` moet de bedoelde GPU en driver tonen; noteer totale en vrije VRAM en controleer GPU-processen. Maak ruimte vrij in overleg; ontlaad Ollama-modellen vóór training (`ollama ps`, daarna `ollama stop <tag>` per geladen tag). Houd een tweede terminal open met `nvidia-smi -l 2` tijdens laden en trainen. Controleer compatibiliteit van de NVIDIA-driver met de geïnstalleerde CUDA-build volgens [NVIDIA CUDA release notes](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html). Dit pad gebruikt native Windows, geen WSL; voor een eventuele afzonderlijke WSL-route gelden [NVIDIA's WSL-gids](https://docs.nvidia.com/cuda/wsl-user-guide/index.html). `training` heeft een eigen lockfile en staat buiten de workspace. Gebruik de lockfile zonder die te vernieuwen:

```powershell
uv sync --project training --locked
uv run --project training --locked python training/train_qwen35_lora.py --preflight-only
```

Deze preflight downloadt en laadt Qwen/Qwen3.5-0.8B en LoRA, maar leest geen dataset en traint niet. Noteer GPU, bf16, piek-VRAM, versie en eventuele fout. Pas na succes kan de grotere kandidaat apart worden geprobeerd:

```powershell
uv run --project training --locked python training/train_qwen35_lora.py --model Qwen/Qwen3.5-2B --preflight-only
```

[Unsloth's Qwen3.5-gids](https://unsloth.ai/docs/models/qwen3.5/fine-tune) schat bf16-LoRA voor 0.8B op circa 3 GB en 2B op circa 5 GB, afhankelijk van omstandigheden, en raadt QLoRA voor Qwen3.5 af. Dat zijn geen garanties voor deze pc of trainingscontext; 4B wordt daar op circa 10 GB geschat. De [Qwen 0.8B modelkaart](https://huggingface.co/Qwen/Qwen3.5-0.8B) noemt Apache-2.0 en positioneert dit kleine model voor prototyping en taakgericht onderzoek. Bewaar model-ID, revisie, licentie en tokenizer bij elke run. De Windows-combinatie van deze lockfile, Unsloth, Torch en driver moet op de pc zelf worden bewezen; preflight meet het laden, niet de piek van een trainstap.

## 2. Data en teacher

Leg eerst een concreet gedragstekort, baseline en bronbeleid vast. Maak `training/data/bronnen.jsonl` lokaal, met per regel `id`, `tekst`, `bron_uri`, `peildatum` (ISO-datum), `status` (`geldig` of `voorstel`), `documentsoort` en `licentie`. Zie `generate_sft.py` en `DATA_CARD.template.md`. Controleer herkomst, versie, datum, licentie en gebruiksrechten voor elk werkelijk gebruikt bestand; markeer voorstellen als voorstellen. Het [Tweede Kamer open-data-portaal](https://opendata.tweedekamer.nl/) is een officiële ingang. De specifieke CC0-licentie en dekking van de gekozen bestanden zijn hier niet onafhankelijk vastgesteld: verifieer ze bij de officiële dataset en documenteer de URL vóór gebruik; neem CC0 niet automatisch aan voor ieder document.

Voor Tweede Kamerdata is het doel brongebonden gedrag: bijvoorbeeld een voorstel samenvatten met correcte document-ID, datum, bron-ID's en de status `voorstel`, of `onzeker` antwoorden als de meegegeven bron de vraag niet beantwoordt. Train geen model om een voorstel als geldend recht te presenteren of actuele juridische feiten te onthouden; laat die feiten uit bronnen en code komen (`docs/02-ai-architectuur.md`).

Kies één generatiemodus. In alle modi is `--eval-set` het pad naar de afgescheiden evaluatieset voor de n-gramcontrole; die controle is geen bewijs van volledige afwezigheid van datalek of duplicatie. Beoordeel ook overlap op bron, vraag en betekenis. De standaard `eval/data/v0.jsonl` is geen vervanging voor een gereviewde evalset.

`eval_ngramen` behandelt een ontbrekend bestand als een lege set. Controleer daarom vóór `--mode direct` of `--mode ingest` dat het opgegeven evalbestand bestaat en menselijke review heeft gehad; anders faalt de code niet, maar wordt er ook niets op overlap gecontroleerd. `--mode requests` maakt alleen lokale verzoekregels en verstuurt geen data.

**Batch, requests:** maakt lokaal requests; upload gebeurt niet automatisch. Controleer teacher-ID, dienst, kosten en toestemming voordat iemand uploadt. `Qwen/Qwen3.8-27B` is de scriptdefault; controleer dat de gekozen dienst dat ID werkelijk ondersteunt.

```powershell
uv run --project eval python training/generate_sft.py --mode requests --sources training/data/bronnen.jsonl --eval-set training/data/eval-reviewed.jsonl --teacher-model <teacher-model>
```

Upload `training/data/sft-batch-requests.jsonl` via het door de dienst gedocumenteerde proces. Bewaar het resultaat lokaal en gebruik dezelfde sources, teacher-ID, seed en instellingen bij ingest zodat de request-ID's overeenkomen:

```powershell
uv run --project eval python training/generate_sft.py --mode ingest --sources training/data/bronnen.jsonl --eval-set training/data/eval-reviewed.jsonl --teacher-model <teacher-model> --batch-results training/data/batch-results.jsonl
```

**Direct:** tegen een bereikbare OpenAI-compatibele endpoint. Een lokaal Ollama-model moet vooraf geïnstalleerd en geladen kunnen worden; een 27B-teacher is geen aannemelijke lokale keuze op deze hardware. Vervang de placeholder door de daadwerkelijk geïnstalleerde tag:

```powershell
uv run --project eval python training/generate_sft.py --mode direct --sources training/data/bronnen.jsonl --eval-set training/data/eval-reviewed.jsonl --teacher-url http://127.0.0.1:11434/v1 --teacher-model <lokale-ollama-tag>
```

Voor een geautoriseerde externe endpoint laat Luca de sleutel lokaal interactief in de huidige PowerShell-processomgeving zetten; de agent vraagt niet om de waarde en leest of print die niet. Gebruik `--teacher-url <geautoriseerde-https-v1-url> --teacher-model <model-id> --api-key-env WETVIA_TEACHER_KEY` bij het direct-commando. Verwijder na afloop de procesvariabele met `Remove-Item Env:WETVIA_TEACHER_KEY`. Geen commando met letterlijke sleutel gebruiken. Batchupload en externe directe calls blijven afhankelijk van toestemming en dienstvoorwaarden.

De generator schrijft een timestamped `sft-concept-*.jsonl`, `review-steekproef-*.jsonl` en `DATA_CARD-concept-*.md`; de verifier en deduplicatie vervangen geen inhoudelijke controle. Laat een mens ten minste 100 voorbeelden en hun bronondersteuning, status, datum, citaties en negatieve voorbeelden beoordelen, fouten vastleggen en een go/no-go geven. De projectdoelgrootte is 1.500–3.000 voorbeelden, circa 30% negatief; 20 rijen is slechts de technische minimumgrens. Vul de data card in en maak pas na goedkeuring `training/data/sft.jsonl` met de aanvaarde rijen. Houd een onafhankelijk menselijk gereviewde A/B-set buiten alle training en validatie; leg de scheiding op bron- en voorbeeldniveau vast.

## 3. Bevries en train

Leg data card, reviewbesluit, datasetversie, bron- en evaluatiescheiding, modelrevisie, instellingen en hashes vast. Sla datasets lokaal op en commit ze niet. Controleer de evalstructuur (dit is geen juridische review):

```powershell
Get-FileHash training/data/bronnen.jsonl -Algorithm SHA256
Get-FileHash training/data/sft.jsonl -Algorithm SHA256
Get-FileHash training/data/eval-reviewed.jsonl -Algorithm SHA256
# Dit valideert alleen de conceptprobe in de repo, niet eval-reviewed.jsonl.
uv run --project eval python eval/run.py validate --dataset eval/data/ab_kamervragen.jsonl --kind ab
```

De huidige `eval/run.py ab`-runner en `validate --kind ab` accepteren alleen `concept: true`; ze kunnen de gereviewde `concept: false`-set dus niet valideren of scoren. Verander `concept` niet terug naar `true` om de check te omzeilen en gebruik de conceptprobe niet als kwaliteitsbewijs. Behandel een gereviewde A/B-set als geblokkeerd totdat er een ondersteunde validator/runner is; vraag om die uitbreiding apart.

Controleer met `git status --short` dat geen data, sleutels, modelbestanden of output worden toegevoegd. De trainer schudt met seed 3407 en reserveert zelf `max(1, round(n * 0.05))` rijen voor validatie; dit is een rij-split, geen gegarandeerde bronscheiding. Onderzoek en documenteer eventuele bronoverlap vóór de run. De afzonderlijke A/B-set blijft buiten `sft.jsonl`.

Na het menselijke besluit en succesvolle preflight:

```powershell
uv run --project training --locked python training/train_qwen35_lora.py --train-file training/data/sft.jsonl --model Qwen/Qwen3.5-0.8B --max-seq-length 1024 --seed 3407 --output-dir training/output/qwen35-0.8b-lora
```

De trainer gebruikt bf16-LoRA rank 16, batch 1, gradient accumulation 4 en standaard twee epochs. Te lange voorbeelden leiden tot een fout; verkort broncontext alleen na inhoudelijke controle en bevries/hash opnieuw. Gebruik een nieuwe outputmap voor elke run. Bewaar adapter, tokenizer, checkpoints en `run_metadata.json` lokaal met data card en hashes; metadata bevat model, datasethash, splitgroottes, versies en gemeten piek-VRAM. Controleer hash vóór en na de run.

Bij OOM: stop, bewaar de fout en meet VRAM en vrij systeemgeheugen; ontlaad GPU-modellen en sluit alleen met toestemming andere GPU-processen. Start opnieuw met 0.8B en eventueel lagere `--max-seq-length` (minimum 256), mits alle voorbeelden passen en inhoudelijk opnieuw gecontroleerd zijn. Batch is al 1. Als dat niet werkt: stop en gebruik een geschikte grotere machine. Geen QLoRA, offload, modelwissel of geheugenwinst beloven; preflight alleen bewijst niet dat trainen past. Verander niet meerdere parameters tegelijk.

## 4. Export en A/B

De trainer schrijft geen GGUF. [Unsloth's exportvoorbeeld](https://unsloth.ai/docs/models/qwen3.5/fine-tune#saving--export-fine-tuned-model) gebruikt `save_pretrained_gguf`; laden en exporteren kan extra RAM, VRAM, schijfruimte en aanvullende tooling vergen. Test deze stap op de pc; bij ontbrekende Windows-ondersteuning of exportfout stop en rapporteer de fout. Gebruik geen onbevestigde output als resultaat. Het volgende voert een lokale export uit van de opgeslagen adapter met dezelfde trainingomgeving:

```powershell
@'
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="training/output/qwen35-0.8b-lora",
    max_seq_length=1024,
    load_in_4bit=False,
    load_in_16bit=True,
)
model.save_pretrained_gguf("training/output/qwen35-0.8b-gguf", tokenizer, quantization_method="q4_k_m")
'@ | Set-Content -Encoding utf8 training/output/export_qwen35.py
uv run --project training --locked python training/output/export_qwen35.py
Get-ChildItem training/output/qwen35-0.8b-gguf -Filter *.gguf -Recurse
```

Controleer dat precies het bedoelde GGUF-bestand is aangemaakt, hash het, en controleer tokenizer/chat-template en end-of-turn-gedrag tegen de basis. De export en Ollama-baseline kunnen verschillen in quantisatie of template: leg verschillen vast en trek geen causale conclusie zonder passende controle. Volgens [Ollama import](https://docs.ollama.com/import) kan een GGUF via een Modelfile worden geïmporteerd. Vervang hieronder het pad door het werkelijk gevonden absolute pad; controleer het bestand eerst. `ollama create` maakt alleen een lokale proef-tag.

```powershell
ollama pull qwen3.5:0.8b
@'
FROM C:\pad\naar\gecontroleerde-export.gguf
'@ | Set-Content -Encoding ascii training/output/Modelfile
ollama create qwen35-lora-0.8b:latest -f training/output/Modelfile
ollama list
uv sync --all-packages --all-groups --locked
uv run --project eval python eval/run.py ab --baseline qwen3.5:0.8b --tuned qwen35-lora-0.8b:latest --questions eval/data/ab_kamervragen.jsonl --out-dir training/output/ab-report
```

Deze opdracht is uitsluitend een conceptprobe: de huidige A/B-loader vereist `concept: true` en weigert gereviewde items met `concept: false`. De runner kan daarom momenteel geen definitieve A/B op de gereviewde set uitvoeren; stop bij deze blokkade en laat die mogelijkheid eerst apart implementeren en beoordelen. Controleer vooraf dat beide tags werkelijk bestaan en dezelfde eval-items en instellingen krijgen. De runner ontlaadt standaard na elke vraag (`--keep-alive 0`); output bevat ook ruwe antwoorden, dus houd die lokaal en controleer op gevoelige inhoud. Onderzoek foutaantallen en lege noemers naast scores. `eval/data/ab_kamervragen.jsonl` is uitsluitend een conceptprobe voor de pipeline. Acceptatie voor standaardgebruik vraagt op de gereviewde set ten minste +5 procentpunt abstentie-recall **of** +3 procentpunt citatie-ondersteuning, zonder daling in kernfeitcorrectheid (zie `docs/02-ai-architectuur.md`); deze runner meet kernfeitcorrectheid niet volledig, dus organiseer daarvoor onafhankelijke menselijke beoordeling. Afwezig bewijs is geen pass.

## 5. Stop, terugdraaien en rapport

Bij fout, onvoldoende bronreview, uitval van evaluatie-items, regressie of twijfel: behoud baseline als actieve configuratie, gebruik de adapter niet en rapporteer de blokkade. Verwijder alleen met toestemming de specifieke lokale proef-tag (`ollama rm qwen35-lora-0.8b:latest`) of expliciet geïdentificeerde proefbestanden; verwijder geen gedeelde caches of data van anderen. Een nieuwe run krijgt een eigen outputmap en nieuwe hashes.

Gebruik dit verslag zonder geheimen of broninhoud:

```text
Commit / datum / machine en GPU / driver:
Omgeving en versies / model-ID en revisie / licentie:
Preflight en piek VRAM / vrije schijf en RAM / beperkingen:
Data card en reviewbesluit / bron- en dataset-hashes / split en seed:
Trainparameters / status / adapter- en metadata-paden / hashes:
Export en GGUF-hash / Ollama-tags / template- en quantisatieverschillen:
A/B-set en hash / itemaantallen en fouten / scores / menselijke kernfeitbeoordeling:
Besluit en onderbouwing / open blokkades / aanbevolen volgende stap:
```
