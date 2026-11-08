"""Train a local Qwen3.5 bf16 LoRA adapter from reviewed Wetvia SFT JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from answer_v1 import validate_row

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
            row: object = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Ongeldige JSON op regel {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Regel {line_number}: verwacht een JSON-object")

        item_id = row.get("id")
        label = (
            f"Regel {line_number} ({item_id})"
            if isinstance(item_id, str)
            else (f"Regel {line_number}")
        )
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError(f"{label}: `id` moet een niet-lege string zijn")
        if item_id in seen_ids:
            raise ValueError(f"{label}: dubbel `id` {item_id!r}")
        seen_ids.add(item_id)

        structural_errors = validate_row(row)
        if structural_errors:
            raise ValueError(f"{label}: " + "; ".join(structural_errors))
        rows.append({"id": item_id, "messages": row["messages"]})

    if len(rows) < 20:
        raise ValueError(
            "Minstens 20 gecontroleerde voorbeelden zijn nodig voor een train/validatiesplit."
        )
    return rows


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
