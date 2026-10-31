"""Piekmeting via nvidia-smi. Zonder die binary is de meting afwezig, niet verzonnen."""

from __future__ import annotations

import subprocess
from collections.abc import Callable


def parse_nvidia_smi_memory_mib(text: str) -> int | None:
    readings: list[int] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            readings.append(int(stripped))
    if not readings:
        return None
    return max(readings)


def query_nvidia_smi_mib(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int | None:
    try:
        completed = runner(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return parse_nvidia_smi_memory_mib(completed.stdout)


def peak_mib(readings: list[int | None]) -> int | None:
    present = [value for value in readings if value is not None]
    if not present:
        return None
    return max(present)
