"""Small, throttled LoRA run; baseline, dev checkpoints, then held-out comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import time
import traceback
from pathlib import Path

from resource_guard import ResourceGuard


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def score(row: dict, text: str) -> dict:
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        value = None
    schema = (
        isinstance(value, dict)
        and set(value) == {"status", "antwoord", "bron_ids", "bewijs"}
        and value["status"] in ("onderbouwd", "onvoldoende_bron")
        and isinstance(value["antwoord"], str)
        and bool(value["antwoord"].strip())
        and isinstance(value["bron_ids"], list)
        and all(isinstance(x, str) for x in value["bron_ids"])
        and isinstance(value["bewijs"], str)
    )
    result = dict.fromkeys(("schema", "status", "source_ids", "evidence", "contract"), False)
    result["schema"] = bool(schema)
    if schema:
        result["status"] = value["status"] == row["target"]["status"]
        result["source_ids"] = value["bron_ids"] == row["target"]["bron_ids"]
        result["evidence"] = (
            value["bewijs"] == ""
            if row["task"] == "ontbrekend"
            else len(value["bewijs"].strip()) >= 15 and value["bewijs"] in row["context"]
        )
        result["contract"] = all(
            result[key] for key in ("schema", "status", "source_ids", "evidence")
        )
    # Lexical overlap is only a proxy; it does not prove factual or legal correctness.
    terms = set(re.findall(r"\b\w{5,}\b", " ".join(row["fact_terms"]).lower()))
    answer = value["antwoord"] if schema else text
    result["fact_term_recall_proxy"] = (
        len(terms & set(re.findall(r"\b\w{5,}\b", answer.lower()))) / len(terms) if terms else 0
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=96)
    parser.add_argument("--checkpoint-every", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=0.0002)
    parser.add_argument("--baseline-run", type=Path)
    parser.add_argument("--revision", help="Pin a recorded Hugging Face model commit")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HOME"] = "D:/Wetvia/huggingface"
    guard = ResourceGuard(args.output)
    report = {"status": "running", "concept": True, "human_reviewed": False}
    try:
        import torch
        from huggingface_hub import model_info
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        torch.manual_seed(42)
        random.seed(42)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; refusing an unbounded CPU fallback")
        torch.cuda.set_per_process_memory_fraction(0.375)
        model_id = "Qwen/Qwen3-0.6B"
        revision = args.revision or model_info(model_id).sha
        tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
        guard.wait_for_headroom()
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            revision=revision,
            torch_dtype=torch.bfloat16,
            device_map={"": "cuda:0"},
            low_cpu_mem_usage=True,
            attn_implementation="sdpa",
        )
        model.generation_config.pad_token_id = tokenizer.eos_token_id
        model.generation_config.do_sample = False
        model = get_peft_model(
            model,
            LoraConfig(
                r=8,
                lora_alpha=16,
                lora_dropout=0.05,
                target_modules=["q_proj", "v_proj"],
                task_type="CAUSAL_LM",
                revision=revision,
            ),
        )
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
        model.print_trainable_parameters()
        splits = {
            split: [
                json.loads(line)
                for line in (args.data / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
                if line
            ]
            for split in ("train", "dev", "test")
        }
        groups = {split: {row["source_id"] for row in rows} for split, rows in splits.items()}
        assert not groups["train"] & (groups["dev"] | groups["test"])
        assert not groups["dev"] & groups["test"]

        def encode(row):
            prompt = tokenizer.apply_chat_template(
                row["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
            target_ids = tokenizer.encode(
                json.dumps(row["target"], ensure_ascii=False) + tokenizer.eos_token,
                add_special_tokens=False,
            )
            if len(prompt_ids) + len(target_ids) > 768:
                raise ValueError(f"Example too long: {row['id']}")
            return prompt_ids, target_ids

        encoded = {row["id"]: encode(row) for rows in splits.values() for row in rows}
        config = {
            "model": model_id,
            "revision": revision,
            "seed": 42,
            "lora_rank": 8,
            "target_modules": ["q_proj", "v_proj"],
            "steps": args.steps,
            "learning_rate": args.learning_rate,
            "batch_size": 1,
            "max_sequence_tokens": 768,
            "max_new_tokens": 192,
            "dtype": "bfloat16",
            "gradient_checkpointing": True,
            "gpu_allocator_fraction": 0.375,
            "cpu_threads": 2,
            "application_duty_cycle_ceiling": 0.25,
            "temperature_stop_c": 75,
            "temperature_pause_c": 68,
            "selection": "highest dev contract pass, then lowest dev completion NLL",
            "data_manifest": json.loads((args.data / "data_manifest.json").read_text()),
            "base_prompt": splits["train"][0]["messages"][0]["content"],
        }
        write_json(args.output / "config.json", config)

        def tensors(row):
            prompt_ids, target_ids = encoded[row["id"]]
            ids = torch.tensor([prompt_ids + target_ids], device="cuda")
            labels = ids.clone()
            labels[:, : len(prompt_ids)] = -100
            return {"input_ids": ids, "attention_mask": torch.ones_like(ids), "labels": labels}

        inference_hooks = []

        def enable_inference_throttle():
            timing = [0.0]

            def before_forward(module, inputs):
                guard.check()
                torch.cuda.synchronize()
                timing[0] = time.monotonic()

            def after_forward(module, inputs, output):
                torch.cuda.synchronize()
                guard.cooldown(time.monotonic() - timing[0])

            inference_hooks.extend(
                [
                    model.register_forward_pre_hook(before_forward),
                    model.register_forward_hook(after_forward),
                ]
            )

        def disable_inference_throttle():
            for hook in inference_hooks:
                hook.remove()
            inference_hooks.clear()

        def evaluate(split, name):
            model.eval()
            model.config.use_cache = True
            enable_inference_throttle()
            rows = []
            try:
                for row in splits[split]:
                    guard.wait_for_headroom()
                    prompt_ids, _ = encoded[row["id"]]
                    ids = torch.tensor([prompt_ids], device="cuda")
                    started = time.monotonic()
                    with torch.inference_mode():
                        result = model.generate(
                            input_ids=ids,
                            attention_mask=torch.ones_like(ids),
                            max_new_tokens=192,
                            do_sample=False,
                            pad_token_id=tokenizer.eos_token_id,
                        )
                        generated = result[0, len(prompt_ids) :]
                        text = tokenizer.decode(generated, skip_special_tokens=True).strip()
                        loss = model(**tensors(row)).loss.item()
                    measured = {
                        "id": row["id"],
                        "task": row["task"],
                        "response": text,
                        "scores": score(row, text),
                        "completion_nll": loss,
                        "generated_tokens": len(generated),
                        "throttled_elapsed_s": time.monotonic() - started,
                        "hit_token_limit": len(generated) == 192,
                    }
                    rows.append(measured)
                    print(
                        json.dumps(
                            {
                                "event": name,
                                "id": row["id"],
                                "contract": measured["scores"]["contract"],
                            }
                        ),
                        flush=True,
                    )
                    write_json(args.output / f"{name}.json", {"rows": rows, "partial": True})
            finally:
                disable_inference_throttle()
            summary = {
                key: sum(float(x["scores"][key]) for x in rows) / len(rows)
                for key in rows[0]["scores"]
            }
            summary["completion_nll"] = sum(x["completion_nll"] for x in rows) / len(rows)
            summary["items"] = len(rows)
            summary["truncated"] = sum(x["hit_token_limit"] for x in rows)
            write_json(
                args.output / f"{name}.json",
                {
                    "summary": summary,
                    "rows": rows,
                    "partial": False,
                    "split": split,
                    "concept": True,
                },
            )
            return summary

        # Adapter is disabled for an uncontaminated baseline of the same base weights.
        if args.baseline_run:
            previous = json.loads((args.baseline_run / "config.json").read_text(encoding="utf-8"))
            for key in ("model", "revision", "seed", "dtype", "max_new_tokens", "base_prompt"):
                if previous[key] != config[key]:
                    raise ValueError(f"Baseline configuration differs: {key}")
            if previous["data_manifest"]["sha256"] != config["data_manifest"]["sha256"]:
                raise ValueError("Baseline data hashes differ")
            for split in ("dev", "test"):
                filename = f"baseline-{split}.json"
                saved = json.loads((args.baseline_run / filename).read_text(encoding="utf-8"))
                assert saved["partial"] is False
                assert [row["id"] for row in saved["rows"]] == [row["id"] for row in splits[split]]
                for example, result in zip(splits[split], saved["rows"], strict=True):
                    assert score(example, result["response"]) == result["scores"]
                shutil.copyfile(args.baseline_run / filename, args.output / filename)
                report[f"baseline_{split}"] = saved["summary"]
            report["baseline_reused_from"] = str(args.baseline_run.resolve())
            report["baseline_run_hardware"] = json.loads(
                (args.baseline_run / "results.json").read_text(encoding="utf-8")
            )["hardware"]
            print(
                "Reused baseline after checking model, prompts, data hashes and scorer", flush=True
            )
        else:
            with model.disable_adapter():
                report["baseline_dev"] = evaluate("dev", "baseline-dev")
                report["baseline_test"] = evaluate("test", "baseline-test")
        torch.cuda.empty_cache()
        best_score = (-1, -math.inf)
        history = []
        optimizer = torch.optim.AdamW(
            (p for p in model.parameters() if p.requires_grad),
            lr=args.learning_rate,
            weight_decay=0.01,
        )
        order = list(splits["train"])
        for step in range(1, args.steps + 1):
            if (step - 1) % len(order) == 0:
                random.shuffle(order)
            guard.wait_for_headroom()
            model.train()
            model.config.use_cache = False
            optimizer.zero_grad(set_to_none=True)
            started = time.monotonic()
            loss = model(**tensors(order[(step - 1) % len(order)])).loss
            if not torch.isfinite(loss):
                raise RuntimeError("Non-finite training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            torch.cuda.synchronize()
            active = time.monotonic() - started
            guard.cooldown(active)
            entry = {"step": step, "loss": loss.item(), "active_s": active}
            with (args.output / "training.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
            if step % 8 == 0:
                print(json.dumps({"event": "train", **entry}), flush=True)
            if step % args.checkpoint_every == 0 or step == args.steps:
                summary = evaluate("dev", f"dev-step-{step}")
                history.append({"step": step, **summary})
                candidate = (summary["contract"], -summary["completion_nll"])
                if candidate > best_score:
                    best_score = candidate
                    model.save_pretrained(args.output / "adapter-best")
                    tokenizer.save_pretrained(args.output / "adapter-best")
                    report["selected_step"] = step
                write_json(args.output / "dev-history.json", history)
        # Reload the dev-selected checkpoint before touching held-out test results.
        from peft import set_peft_model_state_dict
        from safetensors.torch import load_file

        state = load_file(str(args.output / "adapter-best" / "adapter_model.safetensors"))
        set_peft_model_state_dict(model, state)
        report["final_dev"] = evaluate("dev", "final-dev")
        report["final_test"] = evaluate("test", "final-test")
        report["status"] = "complete"
        report["dev_history"] = history
        report["adapter_sha256"] = hashlib.sha256(
            (args.output / "adapter-best" / "adapter_model.safetensors").read_bytes()
        ).hexdigest()
        report["peak_torch_allocated_mib"] = torch.cuda.max_memory_allocated() / 1024**2
    except Exception as exc:
        report["status"] = "stopped"
        report["error"] = str(exc)
        traceback.print_exc()
    finally:
        report["hardware"] = guard.finish()
        write_json(args.output / "results.json", report)
        print(json.dumps(report), flush=True)
    if report["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
