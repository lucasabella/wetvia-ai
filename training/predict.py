"""Use a saved local adapter on one short UTF-8 source, with the same safeguards."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from prepare_experiment import SYSTEM
from resource_guard import ResourceGuard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.source.stat().st_size > 20000:
        raise SystemExit("Use a short source fragment, not a complete document")
    context = args.source.read_text(encoding="utf-8")
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["HF_HOME"] = "D:/Wetvia/huggingface"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    guard = ResourceGuard(args.output, max_seconds=600)
    try:
        import torch
        from peft import PeftConfig, PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; refusing CPU fallback")
        torch.cuda.set_per_process_memory_fraction(0.375)
        config = PeftConfig.from_pretrained(args.adapter)
        if not config.revision:
            raise RuntimeError("Adapter must pin its base model revision")
        tokenizer = AutoTokenizer.from_pretrained(args.adapter, local_files_only=True)
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"BRON [{args.source_id}]:\n{context}\n\n{args.question}"},
        ]
        encoded = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            enable_thinking=False,
            tokenize=True,
            return_tensors="pt",
            return_dict=True,
        )
        if encoded["input_ids"].shape[-1] + 192 > 768:
            raise RuntimeError("Source and question exceed the conservative context limit")
        guard.wait_for_headroom()
        base = AutoModelForCausalLM.from_pretrained(
            config.base_model_name_or_path,
            revision=config.revision,
            torch_dtype=torch.bfloat16,
            device_map={"": "cuda:0"},
            low_cpu_mem_usage=True,
            attn_implementation="sdpa",
            local_files_only=True,
        )
        model = PeftModel.from_pretrained(base, args.adapter).eval()
        timing = [0.0]

        def before_forward(module, inputs):
            guard.check()
            torch.cuda.synchronize()
            timing[0] = time.monotonic()

        def after_forward(module, inputs, output):
            torch.cuda.synchronize()
            guard.cooldown(time.monotonic() - timing[0])

        model.register_forward_pre_hook(before_forward)
        model.register_forward_hook(after_forward)
        guard.wait_for_headroom()
        with torch.inference_mode():
            result = model.generate(
                **encoded.to("cuda"),
                max_new_tokens=192,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        response = tokenizer.decode(
            result[0, encoded["input_ids"].shape[-1] :], skip_special_tokens=True
        ).strip()
        (args.output / "response.txt").write_text(response, encoding="utf-8")
        print(response, flush=True)
    finally:
        (args.output / "hardware.json").write_text(
            json.dumps(guard.finish(), indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
