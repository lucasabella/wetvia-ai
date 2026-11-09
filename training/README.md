# training

Klein lokaal LoRA-experiment op expliciet verzoek, buiten de uv-workspace.
Het wijzigt het productiemodel en de API niet. Geen trainingsdata of gewichten in git.
Onderbouwing: [Tweede Kamer-onderzoek](../docs/07-tweede-kamer-ai-trainingsonderzoek.md).
Herkomst en beperkingen: [DATA_CARD.md](DATA_CARD.md).
De [uitgevoerde run](reports/qwen3-06b-20261109.md) gaf gemengde resultaten:
betere structuur en bronvelden, maar lagere feitwoorddekking in samenvattingen.
De [notitie voor de volgende sessie](NEXT_STEPS.md) bewaart de bevindingen,
lokale artefactpaden en prioriteiten voor vervolgonderzoek.

## Lokale bestanden

De Windows-omgeving staat op `D:/Wetvia/training-env`; de Hugging Face-cache op
`D:/Wetvia/huggingface`. Bronmanifest, datasets, adapters en ruwe resultaten staan
op `D:/Wetvia/training-runs`, buiten OneDrive en de repository.
`requirements.lock.txt` legt de daadwerkelijk gebruikte omgeving vast.

```powershell
uv venv --python 3.12 D:/Wetvia/training-env
uv pip install --python D:/Wetvia/training-env/Scripts/python.exe `
  --extra-index-url https://download.pytorch.org/whl/cu128 `
  -r training/requirements.lock.txt
D:/Wetvia/training-env/Scripts/python.exe training/prepare_experiment.py `
  D:/Wetvia/training-runs/research_sources.json D:/Wetvia/training-runs/data-v1
D:/Wetvia/training-env/Scripts/python.exe training/run_experiment.py `
  --data D:/Wetvia/training-runs/data-v1 `
  --output D:/Wetvia/training-runs/new-run --steps 96 --checkpoint-every 32
```

De uitvoermap moet nieuw zijn. Het bronmanifest is bewust lokaal; reconstructie
vereist de daarin vastgelegde bronnen en parafrases. De exacte modelrevision,
datasethashes, instellingen en prompt staan per run in `config.json`.
Gebruik `--revision <commit-uit-config.json>` om dezelfde basisgewichten te laden.

## Belasting en stoppen

- Twee CPU-threads, affiniteit tot twee logische processors, lagere procesprioriteit.
- Qwen3-0.6B, bf16, batch 1, maximaal 768 tokens, rank-8 LoRA op q/v,
  gradient checkpointing om activaties kleiner te houden.
- Torch-allocator maximaal 37,5% van 8 GiB; dit omvat geen geheugen van andere apps.
- Na iedere trainingsstap en iedere inferentie-forward minstens driemaal de
  rekentijd rust. Dit begrenst de duty cycle van dit experiment tot 25%; het is
  geen harde limiet voor de totale GPU-utilisatie. Korte rekenpieken blijven mogelijk.
- NVML/psutil meten iedere seconde. Pauze vanaf 68 C of bij hoge gemeten
  CPU/GPU-belasting; stop vanaf 75 C, 6,5 GiB totaal GPU-gebruik of minder dan
  1,5 GiB beschikbaar RAM. Na drie minuten onvoldoende ruimte stopt de run.
- Maximaal twee uur per run. Monitoringfouten en verouderde meetgegevens stoppen
  het experiment. Kloksnelheden, vermogenslimieten en andere apps worden niet aangepast.

Handmatig stoppen kan met dit bestand; de run controleert het tussen bewerkingen:

```powershell
New-Item -ItemType File -Force D:/Wetvia/training-runs/STOP
```

Verwijder dat bestand bewust voordat een volgende run start. Een CUDA-kernel of
modeldownload die al loopt kan niet op dit bestand worden onderbroken; de controle
volgt bij de volgende bewerkingsgrens. De limieten zijn bewaking, geen OS-quota.

## Vergelijking

Eerst baseline op dev en test met uitgeschakelde adapter. Daarna alleen dev op
stap 32, 64 en 96. Selectie op hoogste dev-contractscore, bij gelijke stand laagste
completion-NLL. Alleen het gekozen checkpoint wordt daarna op de test gemeten.
Alle generaties gebruiken greedy decoding, dezelfde prompts en maximaal 192 nieuwe
tokens. Ruwe antwoorden blijven bewaard; afgekapt antwoord telt gewoon mee.
Snelheden bevatten de opgelegde rust en zijn geen throughputbenchmark.

Met `--baseline-run D:/Wetvia/training-runs/eerdere-run` kan een al afgeronde
baseline worden hergebruikt na een technisch gestopte trainingspoging. De runner
controleert modelrevision, prompt, datahashes, decodeerinstellingen en de scorer
voordat hij de baseline overneemt. Dit bespaart herhaalde GPU-belasting.

De contractscore meet JSON, verwachte broncode/status en een bewijszin die letterlijk
in de meegeleverde parafrase staat. Zij controleert de semantische juistheid van het
antwoord niet. Woorddekking is slechts een lexicale proxy. Zie DATA_CARD.md.

## Adapter lokaal gebruiken

`predict.py` laadt alleen reeds lokaal aanwezige basisgewichten en een adapter met
vastgelegde modelrevision. Het verwerkt één kort UTF-8-bronfragment met dezelfde
CPU-, geheugen- en temperatuurgrenzen. De uitvoermap moet nieuw zijn. Controleer
antwoorden steeds tegen de originele bron; de adapter kan broncodes verkeerd kopiëren.

```powershell
D:/Wetvia/training-env/Scripts/python.exe training/predict.py `
  --adapter D:/Wetvia/training-runs/qwen3-06b-lora-20261109-run4/adapter-best `
  --source D:/Wetvia/bronfragment.txt --source-id bron-1 `
  --question 'Vat de bron neutraal samen in maximaal twee zinnen.' `
  --output D:/Wetvia/training-runs/nieuwe-voorspelling
```

Het antwoord staat in `response.txt`, de belasting in `hardware.json` en
`telemetry.jsonl`. De broninhoud wordt lokaal verwerkt.

```powershell
D:/Wetvia/training-env/Scripts/ruff.exe check training
D:/Wetvia/training-env/Scripts/ruff.exe format --check training
D:/Wetvia/training-env/Scripts/python.exe -m pytest training -q
```
