"""Train a local Qwen3.5 bf16 LoRA adapter from reviewed Wetvia SFT JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_DEFAULT_MODEL = "Qwen/Qwen3.5-0.8B"
_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]
_ANSWER_FIELDS = {
    "status",
    "samenvatting",
    "punten",
    "voorbehouden",
    "vervolgstappen",
    "peildatum",
}
_STATUSES = {"beantwoord", "onzeker", "buiten_scope"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=_DEFAULT_MODEL)
    parser.add_argument("--train-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("training/output/qwen35-lora"))
    parser.add_argument("--max-seq-length", type=int, default=1024)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Load the base model and LoRA layers without reading a dataset or training.",
    )
    return parser.parse_args()


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Trainingsbestand bestaat niet: {path}")

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ongeldige JSON op regel {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Regel {line_number}: verwacht een JSON-object")

        item_id = row.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(f"Regel {line_number}: `id` moet een niet-lege string zijn")
        if item_id in seen_ids:
            raise ValueError(f"Regel {line_number}: dubbel `id` {item_id!r}")
        seen_ids.add(item_id)

        messages = row.get("messages")
        if not isinstance(messages, list) or len(messages) < 2:
            raise ValueError(
                f"Regel {line_number} ({item_id}): `messages` moet minstens twee berichten bevatten"
            )
        if any(
            not isinstance(message, dict)
            or not isinstance(message.get("role"), str)
            or message["role"] not in {"system", "user", "assistant"}
            or not isinstance(message.get("content"), str)
            or not message["content"].strip()
            for message in messages
        ):
            raise ValueError(
                f"Regel {line_number} ({item_id}): elk bericht vereist role en tekstuele content"
            )
        roles = [message["role"] for message in messages]
        if roles[-1] != "assistant" or roles.count("user") != 1 or roles.count("assistant") != 1:
            raise ValueError(
                f"Regel {line_number} ({item_id}): "
                "verwacht één user- en één laatste assistant-bericht"
            )
        if roles.count("system") > 1 or ("system" in roles and roles[0] != "system"):
            raise ValueError(
                f"Regel {line_number} ({item_id}): optioneel system-bericht moet vooraan staan"
            )

        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError(
                f"Regel {line_number} ({item_id}): `metadata` met bronprovenance ontbreekt"
            )
        source_uris = metadata.get("source_uris")
        if (
            not isinstance(source_uris, list)
            or not source_uris
            or any(
                not isinstance(uri, str) or not uri.startswith(("https://", "http://"))
                for uri in source_uris
            )
        ):
            raise ValueError(
                f"Regel {line_number} ({item_id}): `metadata.source_uris` moet bron-URL's bevatten"
            )
        if not isinstance(metadata.get("license"), str) or not metadata["license"].strip():
            raise ValueError(f"Regel {line_number} ({item_id}): `metadata.license` ontbreekt")
        if not isinstance(metadata.get("negative"), bool):
            raise ValueError(
                f"Regel {line_number} ({item_id}): `metadata.negative` moet true/false zijn"
            )

        _validate_answer(row, line_number, item_id, metadata["negative"])
        rows.append({"id": item_id, "messages": messages})

    if len(rows) < 20:
        raise ValueError(
            "Minstens 20 gecontroleerde voorbeelden zijn nodig voor een train/validatiesplit."
        )
    return rows


def _validate_answer(row: dict[str, Any], line_number: int, item_id: str, negative: bool) -> None:
    content = row["messages"][-1]["content"]
    try:
        answer = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Regel {line_number} ({item_id}): laatste assistant-bericht is geen ruwe JSON"
        ) from exc
    if not isinstance(answer, dict) or set(answer) != _ANSWER_FIELDS:
        raise ValueError(
            f"Regel {line_number} ({item_id}): "
            "assistant-uitvoer moet exact de velden van AnswerV1 bevatten"
        )
    if not isinstance(answer["status"], str) or answer["status"] not in _STATUSES:
        raise ValueError(f"Regel {line_number} ({item_id}): onbekende AnswerV1-status")
    if not isinstance(answer["samenvatting"], str) or not answer["samenvatting"].strip():
        raise ValueError(f"Regel {line_number} ({item_id}): `samenvatting` moet tekst bevatten")
    if len(answer["samenvatting"].split()) > 80:
        raise ValueError(
            f"Regel {line_number} ({item_id}): `samenvatting` is langer dan 80 woorden"
        )
    if not isinstance(answer["punten"], list) or not isinstance(answer["voorbehouden"], list):
        raise ValueError(
            f"Regel {line_number} ({item_id}): `punten` en `voorbehouden` moeten lijsten zijn"
        )
    if any(not isinstance(value, str) or not value.strip() for value in answer["voorbehouden"]):
        raise ValueError(f"Regel {line_number} ({item_id}): elk voorbehoud moet tekst bevatten")
    if not isinstance(answer["vervolgstappen"], list):
        raise ValueError(f"Regel {line_number} ({item_id}): `vervolgstappen` moet een lijst zijn")
    if answer["status"] == "beantwoord" and not answer["punten"]:
        raise ValueError(f"Regel {line_number} ({item_id}): `beantwoord` vereist geciteerde punten")
    for point in answer["punten"]:
        if (
            not isinstance(point, dict)
            or set(point) != {"tekst", "bron_ids"}
            or not isinstance(point["tekst"], str)
            or not point["tekst"].strip()
            or not isinstance(point["bron_ids"], list)
            or not point["bron_ids"]
            or any(
                not isinstance(source_id, str) or not source_id.strip()
                for source_id in point["bron_ids"]
            )
            or len(point["bron_ids"]) != len(set(point["bron_ids"]))
        ):
            raise ValueError(
                f"Regel {line_number} ({item_id}): elk punt vereist tekst en bron-ID's"
            )
    for step in answer["vervolgstappen"]:
        if not isinstance(step, dict) or set(step) != {"tekst", "url"}:
            raise ValueError(
                f"Regel {line_number} ({item_id}): elke vervolgstap vereist tekst en een URL"
            )
        parsed_url = urlparse(step["url"] if isinstance(step["url"], str) else "")
        if (
            not isinstance(step["tekst"], str)
            or not step["tekst"].strip()
            or parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
        ):
            raise ValueError(
                f"Regel {line_number} ({item_id}): "
                "elke vervolgstap vereist tekst en een HTTP(S)-URL"
            )
    try:
        date.fromisoformat(answer["peildatum"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Regel {line_number} ({item_id}): `peildatum` moet YYYY-MM-DD zijn"
        ) from exc
    if negative and (answer["status"] != "onzeker" or answer["punten"]):
        raise ValueError(
            f"Regel {line_number} ({item_id}): "
            "negatieve voorbeelden moeten `onzeker` zijn zonder antwoordpunten"
        )


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def main() -> int:
    args = _parse_args()
    if args.max_seq_length < 256:
        raise ValueError("`--max-seq-length` moet minstens 256 zijn")
    if args.epochs <= 0:
        raise ValueError("`--epochs` moet groter dan nul zijn")
    rows: list[dict[str, Any]] | None = None
    if not args.preflight_only:
        if args.train_file is None:
            raise ValueError("Geef `--train-file` op, of gebruik `--preflight-only`.")
        rows = _load_rows(args.train_file)

    import torch
    from unsloth import FastLanguageModel

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA-GPU niet gevonden. Voer dit uit in de GPU-omgeving op je pc.")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError(
            "Deze GPU/PyTorch-installatie meldt geen bf16-ondersteuning; Qwen3.5-plan vereist bf16."
        )

    properties = torch.cuda.get_device_properties(0)
    print(f"GPU: {properties.name} ({properties.total_memory / 1024**3:.1f} GiB)")
    print(f"bf16: ondersteund; model: {args.model}; context: {args.max_seq_length}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq_length,
        dtype=torch.bfloat16,
        load_in_4bit=False,
        load_in_16bit=True,
        full_finetuning=False,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=_TARGET_MODULES,
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        max_seq_length=args.max_seq_length,
    )
    torch.cuda.synchronize()
    peak_gib = torch.cuda.max_memory_allocated() / 1024**3
    print(f"Piek VRAM bij model + LoRA laden: {peak_gib:.2f} GiB")

    if args.preflight_only:
        print("Preflight geslaagd; er is niets getraind of opgeslagen.")
        return 0

    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    assert rows is not None and args.train_file is not None
    random.Random(args.seed).shuffle(rows)
    validation_size = max(1, round(len(rows) * 0.05))
    validation_rows = rows[:validation_size]
    training_rows = rows[validation_size:]

    def to_text(row: dict[str, Any]) -> dict[str, str]:
        text = tokenizer.apply_chat_template(
            row["messages"],
            tokenize=False,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        token_count = len(tokenizer(text, add_special_tokens=False)["input_ids"])
        if token_count > args.max_seq_length:
            raise ValueError(
                f"Voorbeeld {row['id']} telt {token_count} tokens en "
                f"overschrijdt `--max-seq-length` ({args.max_seq_length}); "
                "verkort de broncontext of verhoog de context voorzichtig."
            )
        return {"text": text}

    train_dataset = Dataset.from_list(training_rows).map(to_text, remove_columns=["id", "messages"])
    validation_dataset = Dataset.from_list(validation_rows).map(
        to_text, remove_columns=["id", "messages"]
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        args=SFTConfig(
            output_dir=str(args.output_dir),
            max_seq_length=args.max_seq_length,
            dataset_text_field="text",
            per_device_train_batch_size=1,
            per_device_eval_batch_size=1,
            gradient_accumulation_steps=4,
            num_train_epochs=args.epochs,
            learning_rate=2e-4,
            warmup_ratio=0.05,
            logging_steps=10,
            eval_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=2,
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            bf16=True,
            fp16=False,
            optim="adamw_8bit",
            seed=args.seed,
            dataset_num_proc=1,
            report_to="none",
        ),
    )
    result = trainer.train()
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    run_metadata = {
        "base_model": args.model,
        "train_file": str(args.train_file),
        "train_file_sha256": hashlib.sha256(args.train_file.read_bytes()).hexdigest(),
        "train_examples": len(training_rows),
        "validation_examples": len(validation_rows),
        "max_seq_length": args.max_seq_length,
        "epochs": args.epochs,
        "seed": args.seed,
        "gpu": properties.name,
        "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 2),
        "loss": result.training_loss,
        "versions": {
            package: _package_version(package)
            for package in ("torch", "unsloth", "transformers", "trl", "datasets")
        },
    }
    (args.output_dir / "run_metadata.json").write_text(
        json.dumps(run_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Adapter opgeslagen in {args.output_dir}")
    print("Dit is nog geen A/B-evaluatie; gebruik de afgescheiden, gereviewde evalset.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
