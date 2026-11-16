# 08. De benchmark op je eigen pc draaien

Dit is de korte handleiding voor een Windows-pc met een NVIDIA RTX 3070 (8 GB geheugen op de kaart). Je hoeft niet te weten hoe een model van binnen werkt.

De meting zet twee rijen naast elkaar:

1. het kleine model zoals je het downloadt (de basis);
2. hetzelfde model nadat het extra heeft geoefend (bijgetraind).

Elke vraag laat een stuk echte overheidstekst meelezen. Een script kijkt of het antwoord overeenkomt met de sleutel. Er is ook een haak voor een tweede model dat open antwoorden nakijkt. Die staat standaard uit.

## Woorden die hier terugkomen

- **4-bit.** Het modelbestand is kleiner gemaakt. Bij Ollama heet die vorm Q4. Een model van ongeveer 4 miljard gewichten past dan in zo'n 3 tot 4 GB. Op een kaart van 8 GB blijft er ruimte over voor Windows. Trainen (het model zelf laten oefenen) past niet op deze kaart. Dat gebeurt later op een gratis GPU in de cloud, zoals in [07](07-benchmark-en-distillatie-plan.md) staat.
- **LoRA.** Een dun extra bestand met aanpassingen, naast het basismodel. Deze meting laadt dat bestand niet zelf. Je zet het eerst in Ollama of LM Studio, en geeft daarna de naam door.
- **Concept.** De vragen zijn nog niet door jou gecontroleerd. Het percentage is daarom geen eindcijfer. Jouw controle is issue #95.

## Wat je installeert

1. Python 3.12, van python.org. Zet bij de installatie "Add python.exe to PATH" aan.
2. Git.
3. Het NVIDIA-stuurprogramma. Daarna werkt in PowerShell het commando `nvidia-smi`.
4. [Ollama voor Windows](https://ollama.com/download). Laat het na de installatie aan staan.
5. uv, de Python-pakkettool van dit project. In PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Sluit PowerShell en open het opnieuw, zodat `uv` gevonden wordt.

## De repo

```powershell
git clone https://github.com/lucasabella/wetvia-ai.git
cd wetvia-ai
uv sync --all-packages --all-groups
ollama pull qwen3.5:4b
```

`qwen3.5:4b` is het basismodel. De download is een paar gigabyte en gebeurt één keer. Alle commando's hieronder typ je in de map `wetvia-ai`.

## Eerste commando

```powershell
uv run wetvia-bench doctor
```

Je krijgt een lijst. Elke regel is `ok` of `niet ok`.

- **Videokaart** moet de 3070 en ongeveer 8192 MiB noemen. Ontbreekt `nvidia-smi`, dan is het stuurprogramma er niet.
- **Endpoint** is het adres waar Ollama luistert, standaard `http://127.0.0.1:11434/v1`.
- **Basismodel** is `ok` als `qwen3.5:4b` gedownload is.
- **Bijgetraind model** is nu `niet ok`. Dat hoort, tot je een geoefend model hebt.
- **Toetsset** noemt hoeveel vragen er zijn, en dat ze nog concept zijn.

De laatste zin zegt of je de basisrij kunt draaien. Het rapport staat ook in `eval/reports/doctor.json`.

## De basisrij

```powershell
uv run wetvia-bench --model base
```

Het script stuurt elke vraag naar Ollama en schrijft `eval/reports/kwaliteit-base.json` en `eval/reports/vergelijking.md`.

De eerste vraag duurt het langst, omdat Ollama het model dan in het geheugen laadt. Daarna is de rest van de set (ongeveer 30 vragen) meestal een paar minuten. In het JSON-bestand staat per vraag hoeveel seconden het antwoord duurde. Dat getal is gemeten op jouw pc. Er staat geen geschatte snelheid in de documentatie.

LM Studio kan hetzelfde, als daar een model geladen is en de lokale server aan staat:

```powershell
uv run wetvia-bench --model base --base-url http://127.0.0.1:1234/v1 --base-tag de-naam-die-lm-studio-toont
```

Er is geen aparte Hugging Face-installatie nodig. Torch zit bewust niet in dit project: dat botst met de rest van de afhankelijkheden, en op Windows is die route breekbaar. Ollama of LM Studio doet de 4-bit-versie.

## De bijgetrainde rij

Die bestaat nog niet op schijf. Dit werkt nog niet:

```powershell
uv run wetvia-bench --model finetuned
```

Je krijgt een duidelijke tekst, exitcode 2, en in de tabel de woorden `niet gemeten`. Een map met een LoRA-adapter (`adapter_config.json`) of een los `.gguf`-bestand wordt niet automatisch geladen.

Als het geoefende model later in Ollama staat, bijvoorbeeld onder de naam `wetvia-qwen3.5-4b`:

```powershell
uv run wetvia-bench --model finetuned --finetuned-tag wetvia-qwen3.5-4b
uv run wetvia-bench compare
```

## Hoe je de tabel leest

Open `eval/reports/vergelijking.md`.

- `8/28` betekent: 8 van de 28 vragen hadden het antwoord dat in de sleutel staat.
- `niet gemeten` betekent: die rij is niet gedraaid. Dat is geen nul.
- **Slechter** zijn vragen die de basis goed had en het bijgetrainde model fout. Die horen in het verslag, ook als het gemiddelde meevalt.
- **Beter** is het omgekeerde.
- De bronkolom in het JSON-bestand zegt of het model het artikel- of documentnummer uit de tekst herhaalde. Ontbreekt die bron, dan telt dat niet als fout.

De vragen komen uit wetten.overheid.nl, de open data van de Tweede Kamer en de Staatscourant. De letterlijke zin staat in de set. Jij moet die links nog nalopen (issue #95). Tot die tijd is het percentage een technische controle, geen oordeel over het model.

De oude snelheidsmeting, zonder kwaliteitsscore, blijft:

```powershell
uv run wetvia-bench
```

Die slaat een model over dat niet in `ollama list` staat en vult dan `niet gemeten` in.
