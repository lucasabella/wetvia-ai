"""Summarize a completed exploratory run without committing data or weights."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    def read(name):
        return json.loads((args.run / name).read_text(encoding="utf-8"))

    results = read("results.json")
    if results["status"] != "complete":
        raise SystemExit("Refusing to present an incomplete run as a completed comparison")
    config = read("config.json")
    before = read("baseline-test.json")
    after = read("final-test.json")
    hardware = results["hardware"]
    assert [x["id"] for x in before["rows"]] == [x["id"] for x in after["rows"]]
    metrics = [
        ("schema", "Geldig JSON-schema"),
        ("status", "Verwachte status onderbouwd/onvoldoende_bron"),
        ("source_ids", "Verwachte broncodes"),
        ("evidence", "Bewijs letterlijk in aangeleverde context"),
        ("contract", "Volledig antwoordcontract"),
    ]
    lines = [
        "# Verkennende lokale LoRA-run — 9 november 2026",
        "",
        "**Concept, niet menselijk gereviewd. Dit is geen juridische kwaliteitsmeting.**",
        "",
        f"De contractscore veranderde van {before['summary']['contract']:.1%} naar "
        f"{after['summary']['contract']:.1%}. De lexicale feitwoorddekking over alle taken "
        f"veranderde van {before['summary']['fact_term_recall_proxy']:.1%} naar "
        f"{after['summary']['fact_term_recall_proxy']:.1%}. Beoordeel structuur en "
        "inhoud dus afzonderlijk; de gemeten uitkomst is geen algemene accuratessewinst.",
        "",
        f"Model: `{config['model']}`, revision `{config['revision']}`. "
        f"Rank-8 q/v-LoRA, bf16, batch 1, {config['steps']} stappen, "
        f"learning rate {config['learning_rate']}. Gekozen checkpoint: "
        f"stap **{results['selected_step']}**, uitsluitend op devresultaten.",
        "",
        "De test bevat zestien afgeleide workflowvragen over vier documenten die niet "
        "in de training of devset voorkomen. Training: 24 voorbeelden uit zes documenten; "
        "dev: acht voorbeelden uit twee andere documenten. Er zijn gedeelde taaksjablonen "
        "en verwante onderwerpen. Ruwe antwoorden en bronmanifest blijven lokaal.",
        "",
        "## Voor en na op dezelfde eindtest",
        "",
        "| Automatische maat | Voor | Na |",
        "| --- | ---: | ---: |",
    ]
    for key, label in metrics:
        lines.append(f"| {label} | {before['summary'][key]:.1%} | {after['summary'][key]:.1%} |")
    summary_proxy = []
    for result in (before, after):
        subset = [row for row in result["rows"] if row["task"] == "samenvatting"]
        summary_proxy.append(
            sum(row["scores"]["fact_term_recall_proxy"] for row in subset) / len(subset)
        )
    lines.extend(
        [
            f"| Feitwoorddekking, alle taken (lexicale proxy) "
            f"| {before['summary']['fact_term_recall_proxy']:.1%} "
            f"| {after['summary']['fact_term_recall_proxy']:.1%} |",
            f"| Feitwoorddekking, alleen samenvattingen (proxy) "
            f"| {summary_proxy[0]:.1%} | {summary_proxy[1]:.1%} |",
        ]
    )
    lines.extend(
        [
            f"| Completion-NLL, lager is beter | {before['summary']['completion_nll']:.3f} "
            f"| {after['summary']['completion_nll']:.3f} |",
            f"| Antwoorden op tokenlimiet | {before['summary']['truncated']} "
            f"| {after['summary']['truncated']} |",
            "",
            "Schema, broncode en status worden ook voor ongeldige JSON als fout geteld. "
            "De contractscore vereist al deze controles plus een bewijszin uit de "
            "**meegeleverde parafrase** (of lege bewijs-/bronnenvelden bij onvoldoende bron). "
            "Deze score controleert niet of de antwoordtekst semantisch klopt. Completion-NLL "
            "meet hoe goed de specifieke agentgeschreven referenties passen. "
            "Feitwoorddekking meet overlap met woorden uit twee referentiefeiten; "
            "synoniemen en kortere antwoorden kunnen de score verlagen. De daling is "
            "een reden om inhoudelijke samenvattingskwaliteit apart te beoordelen; "
            "de hogere contractscore is geen bewijs van betere feitelijke antwoorden.",
            "",
            "| Taak | Voor contract | Na contract | Aantal |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for task in ("samenvatting", "controlepunten", "bewijs", "ontbrekend"):
        original = [x for x in before["rows"] if x["task"] == task]
        trained = [x for x in after["rows"] if x["task"] == task]
        first = sum(x["scores"]["contract"] for x in original)
        last = sum(x["scores"]["contract"] for x in trained)
        lines.append(
            f"| {task} | {first}/{len(original)} | {last}/{len(trained)} | {len(trained)} |"
        )
    pairs = list(zip(before["rows"], after["rows"], strict=True))
    wins = sum(not a["scores"]["contract"] and b["scores"]["contract"] for a, b in pairs)
    losses = sum(a["scores"]["contract"] and not b["scores"]["contract"] for a, b in pairs)
    lines.extend(
        [
            "",
            f"Gepaarde contractuitkomsten: {wins} verbeterd, {losses} verslechterd, "
            f"{len(pairs) - wins - losses} gelijk. Dit kleine aantal onderbouwt geen "
            "statistische significantie of productiegeschiktheid.",
            "",
            "## Benchmarks tijdens training",
            "",
            "| Moment | Devcontract | Dev completion-NLL |",
            "| --- | ---: | ---: |",
            f"| Baseline | {results['baseline_dev']['contract']:.1%} "
            f"| {results['baseline_dev']['completion_nll']:.3f} |",
        ]
    )
    for item in results["dev_history"]:
        lines.append(
            f"| Stap {item['step']} | {item['contract']:.1%} | {item['completion_nll']:.3f} |"
        )
    lines.extend(
        [
            "",
            "Bij gelijke dev-contractscore beslist de lagere dev-NLL. "
            "De eindtest heeft geen checkpoint of hyperparameter gekozen. Na de eindtest is "
            "geen vervolgtraining op deze test uitgevoerd.",
            "",
            "## Gemeten belasting van de hele PC",
            "",
            f"- Hoogste GPU-temperatuur: **{hardware['max_temperature_c']:.0f} °C**.",
            f"- Hoogste totale VRAM: **{hardware['max_total_gpu_mib'] / 1024:.2f} GiB**; "
            f"Torch-piekallocatie: {results['peak_torch_allocated_mib'] / 1024:.2f} GiB.",
            f"- Minimaal beschikbaar systeemgeheugen: "
            f"**{hardware['min_available_ram_mib'] / 1024:.2f} GiB**.",
            f"- Gemiddelde totale GPU-utilisatie: {hardware['mean_gpu_util_percent']:.1f}%; "
            f"hoogste secondewaarneming: {hardware['max_gpu_util_percent']:.0f}%.",
            f"- Gemiddelde totale CPU-utilisatie: {hardware['mean_cpu_percent']:.1f}%.",
            f"- Hoogste gemeten GPU-vermogen: {hardware['max_power_w']:.1f} W.",
            "",
            "Metingen iedere seconde omvatten de al geopende apps. De desktop had vóór "
            "modelbelasting al GPU-activiteit. Het experiment gebruikte twee CPU-threads, "
            "twee logische processors en een lagere procesprioriteit. Iedere trainingsstap "
            "en inferentie-forward kreeg minstens driemaal de rekentijd rust. Dit begrenst "
            "de eigen duty cycle tot 25%, niet de totale GPU-utilisatie of korte pieken. "
            "Snelheidsmetingen bevatten rust en zijn geen ongeknepen modelbenchmark.",
            "",
            "## Artefacten en vervolgstap",
            "",
            f"Runmap: `{args.run.resolve()}`. Adapter: `adapter-best/`. "
            "`config.json` bevat prompts, exacte modelrevision en datahashes. "
            "`baseline-test.json` en `final-test.json` bevatten alle ruwe testantwoorden; "
            "`dev-history.json`, `training.jsonl` en `telemetry.jsonl` leggen het verloop vast.",
            "",
            f"SHA-256 adapter: `{results['adapter_sha256']}`.",
            "",
            "De adapter is lokaal opgeslagen; het productiemodel is niet gewijzigd. "
            "Laat de ruwe antwoorden beoordelen op betekenis, neutrale vraagstelling en "
            "correct brongebruik. Vertaling, lange documenten en echte beleidsvergelijking "
            "zijn niet gemeten. Gebruik een nieuwe ongeziene test voor een volgend "
            "trainingsexperiment. Zie [DATA_CARD](../DATA_CARD.md) en "
            "[het brononderzoek](../../docs/07-tweede-kamer-ai-trainingsonderzoek.md).",
            "",
        ]
    )
    if "baseline_reused_from" in results:
        earlier = results["baseline_run_hardware"]
        lines.extend(
            [
                "",
                f"De baseline is hergebruikt uit `{results['baseline_reused_from']}` na "
                "controle van modelrevision, prompt, decodeerinstellingen, datahashes en scorer. "
                "Die eerdere poging stopte na één trainingsstap op de eigen 3 GiB "
                "Torch-allocatorlimiet. Gradient checkpointing maakte een nieuwe training "
                "vanaf dezelfde basisgewichten "
                "mogelijk binnen dezelfde limiet; model, taken en learning rate bleven gelijk. "
                "De hardwarecijfers hierboven betreffen de hervatte run. De eerdere run "
                f"bereikte maximaal {earlier['max_temperature_c']:.0f} °C en "
                f"{earlier['max_total_gpu_mib'] / 1024:.2f} GiB totaal VRAM; minimaal "
                f"{earlier['min_available_ram_mib'] / 1024:.2f} GiB systeem-RAM bleef vrij.",
                "",
            ]
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
