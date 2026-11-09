"""Fail-closed, process-local limits for a small supervised experiment."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import psutil
import pynvml

MIB = 1024**2


def violation(sample: dict[str, float]) -> str | None:
    if sample["temperature_c"] >= 75:
        return "GPU temperature reached 75 C"
    if sample["gpu_used_mib"] >= 6656:
        return "total GPU memory reached 6.5 GiB"
    if sample["ram_available_mib"] < 1536:
        return "less than 1.5 GiB system RAM available"
    return None


class ResourceGuard:
    """Monitor the entire PC; never change clocks, power limits or other apps."""

    def __init__(self, directory: Path, max_seconds: int = 7200):
        self.directory = directory
        self.started = time.monotonic()
        self.max_seconds = max_seconds
        self.samples: list[dict[str, float]] = []
        self.error: str | None = None
        self.closed = threading.Event()
        pynvml.nvmlInit()
        self.device = pynvml.nvmlDeviceGetHandleByIndex(0)
        process = psutil.Process()
        if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
            process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        available = process.cpu_affinity()
        process.cpu_affinity(available[:2])
        if psutil.disk_usage(str(directory)).free < 15 * 1024**3:
            raise RuntimeError("Less than 15 GiB disk space available")
        self.sample()
        self.check()
        self.thread = threading.Thread(target=self.monitor, daemon=True)
        self.thread.start()

    def sample(self) -> dict[str, float]:
        memory = pynvml.nvmlDeviceGetMemoryInfo(self.device)
        util = pynvml.nvmlDeviceGetUtilizationRates(self.device)
        item = {
            "elapsed_s": round(time.monotonic() - self.started, 3),
            "temperature_c": float(
                pynvml.nvmlDeviceGetTemperature(self.device, pynvml.NVML_TEMPERATURE_GPU)
            ),
            "gpu_used_mib": memory.used / MIB,
            "gpu_util_percent": float(util.gpu),
            "power_w": pynvml.nvmlDeviceGetPowerUsage(self.device) / 1000,
            "ram_available_mib": psutil.virtual_memory().available / MIB,
            "cpu_percent": psutil.cpu_percent(),
            "rss_mib": psutil.Process().memory_info().rss / MIB,
        }
        self.samples.append(item)
        with (self.directory / "telemetry.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item) + "\n")
        problem = violation(item)
        if problem:
            self.error = problem
        return item

    def monitor(self) -> None:
        while not self.closed.wait(1):
            try:
                self.sample()
            except Exception as exc:
                self.error = f"Monitoring failed: {exc}"
                return

    def check(self) -> None:
        if (self.directory.parent / "STOP").exists():
            raise RuntimeError("STOP file found")
        if time.monotonic() - self.started > self.max_seconds:
            raise RuntimeError("Experiment time limit reached")
        if self.error:
            raise RuntimeError(self.error)
        if time.monotonic() - self.started - self.samples[-1]["elapsed_s"] > 10:
            raise RuntimeError("Hardware monitoring became stale")

    def wait_for_headroom(self) -> None:
        deadline = time.monotonic() + 180
        while True:
            self.check()
            last = self.samples[-1]
            if (
                last["temperature_c"] < 68
                and last["gpu_util_percent"] < 85
                and last["cpu_percent"] < 85
                and last["ram_available_mib"] >= 1792
            ):
                return
            if time.monotonic() > deadline:
                raise RuntimeError("PC stayed busy or warm for 3 minutes; experiment stopped")
            time.sleep(2)

    def cooldown(self, active_seconds: float) -> None:
        # At most 25% application duty cycle over an operation plus its rest.
        time.sleep(max(0.04, 3 * active_seconds))
        self.check()

    def finish(self) -> dict[str, float]:
        self.closed.set()
        self.thread.join(timeout=3)
        pynvml.nvmlShutdown()
        return {
            "samples": len(self.samples),
            "max_temperature_c": max(x["temperature_c"] for x in self.samples),
            "max_total_gpu_mib": max(x["gpu_used_mib"] for x in self.samples),
            "min_available_ram_mib": min(x["ram_available_mib"] for x in self.samples),
            "mean_gpu_util_percent": sum(x["gpu_util_percent"] for x in self.samples)
            / len(self.samples),
            "max_gpu_util_percent": max(x["gpu_util_percent"] for x in self.samples),
            "max_power_w": max(x["power_w"] for x in self.samples),
            "mean_cpu_percent": sum(x["cpu_percent"] for x in self.samples) / len(self.samples),
        }
